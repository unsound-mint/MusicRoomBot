from datetime import date, datetime
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from app.models.weekly_slot import WeeklySlot
from app.services.club_service import (
    cancel_club_slot_occurrence,
    delete_admin_weekly_slot,
    set_admin_weekly_slot,
)


class _Result:
    def __init__(self, value: WeeklySlot | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> WeeklySlot | None:
        return self.value


class _FakeDb:
    def __init__(self, result: WeeklySlot | None = None) -> None:
        self.result = result
        self.objects: dict[int, WeeklySlot] = {}
        self.added: list[WeeklySlot] = []
        self.deleted: list[WeeklySlot] = []
        self.commit = AsyncMock()

    async def execute(self, stmt):
        return _Result(self.result)

    async def get(self, _model, item_id: int) -> WeeklySlot | None:
        return self.objects.get(item_id)

    def add(self, slot: WeeklySlot) -> None:
        self.added.append(slot)

    async def delete(self, slot: WeeklySlot) -> None:
        self.deleted.append(slot)


class AdminWeeklySlotCommandTests(IsolatedAsyncioTestCase):
    async def test_set_admin_weekly_slot_creates_and_commits(self) -> None:
        db = _FakeDb()

        slot = await set_admin_weekly_slot(
            db,
            weekday=1,
            hour=19,
            group_name="Band A",
        )

        self.assertEqual(slot.weekday, 1)
        self.assertEqual(slot.hour, 19)
        self.assertEqual(slot.group_name, "Band A")
        self.assertEqual(db.added, [slot])
        db.commit.assert_awaited_once()

    async def test_set_admin_weekly_slot_updates_existing_and_commits(self) -> None:
        existing = WeeklySlot(weekday=2, hour=20, group_name="Old Band")
        db = _FakeDb(existing)

        slot = await set_admin_weekly_slot(
            db,
            weekday=2,
            hour=20,
            group_name="New Band",
        )

        self.assertIs(slot, existing)
        self.assertEqual(existing.group_name, "New Band")
        self.assertEqual(db.added, [])
        db.commit.assert_awaited_once()

    async def test_delete_admin_weekly_slot_deletes_and_commits(self) -> None:
        slot = WeeklySlot(id=5, weekday=3, hour=18, group_name="Band B")
        db = _FakeDb()
        db.objects[5] = slot

        result, deleted_slot = await delete_admin_weekly_slot(db, weekly_slot_id=5)

        self.assertEqual(result, "deleted")
        self.assertIs(deleted_slot, slot)
        self.assertEqual(db.deleted, [slot])
        db.commit.assert_awaited_once()

    async def test_delete_admin_weekly_slot_missing_does_not_commit(self) -> None:
        db = _FakeDb()

        result, slot = await delete_admin_weekly_slot(db, weekly_slot_id=404)

        self.assertEqual(result, "not_found")
        self.assertIsNone(slot)
        self.assertEqual(db.deleted, [])
        db.commit.assert_not_awaited()

    async def test_cancel_admin_weekly_slot_occurrence_allows_null_club(self) -> None:
        slot = WeeklySlot(id=9, weekday=1, hour=18, group_name="Admin Band")
        slot.club_id = None
        db = _FakeDb()
        db.objects[9] = slot
        db.result = None

        with patch(
            "app.services.club_service.now_tz",
            return_value=datetime(2026, 3, 24, 10, 0, tzinfo=ZoneInfo("Asia/Almaty")),
        ):
            result = await cancel_club_slot_occurrence(
                db,
                club_id=0,
                weekly_slot_id=9,
                target_date=date(2026, 3, 24),
                cancelled_by_user_id=7,
                require_leader=False,
            )

        self.assertEqual(result, "cancelled")
        self.assertEqual(len(db.added), 1)
        self.assertIsNone(db.added[0].club_id)
        db.commit.assert_awaited_once()

    async def test_delete_admin_weekly_slot_invalid_does_not_commit(self) -> None:
        slot = WeeklySlot(id=6, weekday=1, hour=18, group_name="Band C")
        slot.weekday = None
        db = _FakeDb()
        db.objects[6] = slot

        result, returned_slot = await delete_admin_weekly_slot(db, weekly_slot_id=6)

        self.assertEqual(result, "invalid")
        self.assertIs(returned_slot, slot)
        self.assertEqual(db.deleted, [])
        db.commit.assert_not_awaited()
