from datetime import date, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from app.core import metrics
from app.core.config import TIMEZONE
from app.services.booking_service import (
    accept_gift_offer,
    build_status_summary,
    get_consecutive_slot_option,
    gift_booking_to_username,
    safe_create_booking,
    weekly_reset,
)


class _Result:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar(self):
        return self.value

    def all(self):
        return self.value


class _FakeDb:
    def __init__(self, *results) -> None:
        self.results = list(results)
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.added = []
        self.executed = []
        self.objects = {}

    async def execute(self, stmt):
        self.executed.append(stmt)
        return _Result(self.results.pop(0))

    def add(self, value) -> None:
        self.added.append(value)

    async def get(self, _model, item_id):
        return self.objects.get(item_id)


class BookingServiceAsyncTests(IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        metrics.reset()

    async def test_build_status_summary(self) -> None:
        user = SimpleNamespace(id=7, allowed=True, full_name="Test User")
        bookings = [
            SimpleNamespace(date=date(2026, 3, 24), hour=18),
            SimpleNamespace(date=date(2026, 3, 25), hour=20),
        ]

        with (
            patch("app.services.booking_service.get_user_bookings", new=AsyncMock(return_value=bookings)),
            patch("app.services.booking_service._weekly_limit_value", new=AsyncMock(return_value=3)),
        ):
            summary = await build_status_summary(object(), user)

        self.assertIn("Test User", summary)
        self.assertIn("• Tuesday · 18:00", summary)
        self.assertIn("• Wednesday · 20:00", summary)

    async def test_build_status_summary_escapes_markdown_name(self) -> None:
        user = SimpleNamespace(id=7, allowed=True, full_name="Test_User *Lead*")

        with (
            patch("app.services.booking_service.get_user_bookings", new=AsyncMock(return_value=[])),
            patch("app.services.booking_service._weekly_limit_value", new=AsyncMock(return_value=3)),
        ):
            summary = await build_status_summary(object(), user)

        self.assertIn("👤 *Test\\_User \\*Lead\\**", summary)

    async def test_get_consecutive_slot_option_returns_adjacent_hour_when_eligible(self) -> None:
        db = AsyncMock()
        with (
            patch(
                "app.services.booking_service.now_tz",
                return_value=datetime(2026, 3, 24, 10, 0, tzinfo=ZoneInfo(TIMEZONE)),
            ),
            patch("app.services.booking_service.get_working_hours", new=AsyncMock(return_value=(8, 22))),
            patch("app.services.booking_service.is_weekly_reserved", new=AsyncMock(return_value=False)),
            patch("app.services.booking_service.is_slot_free", new=AsyncMock(return_value=True)),
            patch("app.services.booking_service._weekly_limit_value", new=AsyncMock(return_value=2)),
            patch("app.services.booking_service.count_user_bookings_this_week", new=AsyncMock(return_value=1)),
        ):
            result = await get_consecutive_slot_option(
                db,
                user_id=5,
                b_date=date(2026, 3, 24),
                b_hour=18,
            )

        self.assertEqual(result, (date(2026, 3, 24), 19))

    async def test_get_consecutive_slot_option_returns_none_at_limit(self) -> None:
        db = AsyncMock()
        with (
            patch(
                "app.services.booking_service.now_tz",
                return_value=datetime(2026, 3, 24, 10, 0, tzinfo=ZoneInfo(TIMEZONE)),
            ),
            patch("app.services.booking_service.get_working_hours", new=AsyncMock(return_value=(8, 22))),
            patch("app.services.booking_service.is_weekly_reserved", new=AsyncMock(return_value=False)),
            patch("app.services.booking_service.is_slot_free", new=AsyncMock(return_value=True)),
            patch("app.services.booking_service._weekly_limit_value", new=AsyncMock(return_value=2)),
            patch("app.services.booking_service.count_user_bookings_this_week", new=AsyncMock(return_value=2)),
        ):
            result = await get_consecutive_slot_option(
                db,
                user_id=5,
                b_date=date(2026, 3, 24),
                b_hour=18,
            )

        self.assertIsNone(result)

    async def test_gift_booking_to_username_creates_pending_offer(self) -> None:
        booking = SimpleNamespace(
            id=11,
            user_id=7,
            date=date(2026, 3, 24),
            hour=18,
            booking_source="manual",
            assigned_at=None,
            location_prompted=True,
            absence_reported=True,
        )
        recipient = SimpleNamespace(
            id=9,
            tg_username="receiver",
            full_name="Receiver User",
            allowed=True,
            banned=False,
        )
        db = _FakeDb(booking, recipient, 1, None)

        with (
            patch(
                "app.services.booking_service.now_tz",
                return_value=datetime(2026, 3, 24, 10, 0, tzinfo=ZoneInfo(TIMEZONE)),
            ),
            patch("app.services.booking_service._weekly_limit_value", new=AsyncMock(return_value=2)),
        ):
            result = await gift_booking_to_username(
                db,
                booking_id=11,
                giver_user_id=7,
                recipient_username="@receiver",
            )

        self.assertEqual(result.status, "pending")
        self.assertEqual(booking.user_id, 7)
        self.assertEqual(len(db.added), 1)
        self.assertEqual(db.added[0].booking_id, 11)
        self.assertEqual(db.added[0].giver_user_id, 7)
        self.assertEqual(db.added[0].recipient_user_id, 9)
        db.commit.assert_awaited_once()

    async def test_accept_gift_offer_transfers_future_booking(self) -> None:
        offer = SimpleNamespace(
            id=21,
            booking_id=11,
            giver_user_id=7,
            recipient_user_id=9,
            status="pending",
            responded_at=None,
        )
        booking = SimpleNamespace(
            id=11,
            user_id=7,
            date=date(2026, 3, 24),
            hour=18,
            booking_source="manual",
            assigned_at=None,
            location_prompted=True,
            absence_reported=True,
            attendance_verified=True,
            attendance_lat=1.0,
            attendance_lon=2.0,
            attendance_recorded_at=datetime(
                2026, 3, 24, 17, 30, tzinfo=ZoneInfo(TIMEZONE)
            ),
        )
        recipient = SimpleNamespace(
            id=9,
            tg_username="receiver",
            full_name="Receiver User",
            allowed=True,
            banned=False,
        )
        giver = SimpleNamespace(id=7, tg_username="giver", tg_user_id=1007)
        db = _FakeDb(offer, booking, recipient, giver, None, 1)

        with (
            patch(
                "app.services.booking_service.now_tz",
                return_value=datetime(2026, 3, 24, 10, 0, tzinfo=ZoneInfo(TIMEZONE)),
            ),
            patch("app.services.booking_service._weekly_limit_value", new=AsyncMock(return_value=2)),
        ):
            result = await accept_gift_offer(
                db,
                offer_id=21,
                recipient_user_id=9,
            )

        self.assertEqual(result.status, "success")
        self.assertEqual(booking.user_id, 9)
        self.assertEqual(booking.booking_source, "gifted")
        self.assertFalse(booking.location_prompted)
        self.assertFalse(booking.absence_reported)
        self.assertFalse(booking.attendance_verified)
        self.assertIsNone(booking.attendance_lat)
        self.assertIsNone(booking.attendance_lon)
        self.assertIsNone(booking.attendance_recorded_at)
        self.assertEqual(offer.status, "accepted")
        self.assertIsNotNone(offer.responded_at)
        db.commit.assert_awaited_once()

    async def test_accept_gift_offer_reports_banned_before_not_allowed(self) -> None:
        offer = SimpleNamespace(
            id=21,
            booking_id=11,
            giver_user_id=7,
            recipient_user_id=9,
            status="pending",
            responded_at=None,
        )
        booking = SimpleNamespace(
            id=11,
            user_id=7,
            date=date(2026, 3, 24),
            hour=18,
        )
        recipient = SimpleNamespace(
            id=9,
            allowed=False,
            banned=True,
        )
        giver = SimpleNamespace(id=7)
        db = _FakeDb(offer, booking, recipient, giver)

        with patch(
            "app.services.booking_service.now_tz",
            return_value=datetime(2026, 3, 24, 10, 0, tzinfo=ZoneInfo(TIMEZONE)),
        ):
            result = await accept_gift_offer(
                db,
                offer_id=21,
                recipient_user_id=9,
            )

        self.assertEqual(result.status, "recipient_banned")
        db.commit.assert_not_awaited()

    async def test_gift_booking_to_username_rejects_recipient_at_limit(self) -> None:
        booking = SimpleNamespace(
            id=11,
            user_id=7,
            date=date(2026, 3, 24),
            hour=18,
        )
        recipient = SimpleNamespace(
            id=9,
            tg_username="receiver",
            allowed=True,
            banned=False,
        )
        db = _FakeDb(booking, recipient, 2)

        with (
            patch(
                "app.services.booking_service.now_tz",
                return_value=datetime(2026, 3, 24, 10, 0, tzinfo=ZoneInfo(TIMEZONE)),
            ),
            patch("app.services.booking_service._weekly_limit_value", new=AsyncMock(return_value=2)),
        ):
            result = await gift_booking_to_username(
                db,
                booking_id=11,
                giver_user_id=7,
                recipient_username="receiver",
            )

        self.assertEqual(result.status, "recipient_limit_reached")
        self.assertEqual(booking.user_id, 7)
        db.commit.assert_not_awaited()

    async def test_safe_create_booking_locks_user_week_before_limit_count(self) -> None:
        booking = SimpleNamespace(id=44)
        db = _FakeDb(None, 1, 44)
        db.objects[44] = booking

        with patch(
            "app.services.booking_service._weekly_limit_value",
            new=AsyncMock(return_value=2),
        ), patch(
            "app.services.booking_service.is_weekly_reserved_on_date",
            new=AsyncMock(return_value=False),
        ):
            status, created = await safe_create_booking(
                db,
                user_id=7,
                b_date=date(2026, 3, 24),
                b_hour=18,
            )

        self.assertEqual(status, "success")
        self.assertIs(created, booking)
        self.assertIn("pg_advisory_xact_lock", str(db.executed[0]))
        counters = metrics.snapshot()["counters"]
        self.assertTrue(
            any(
                sample.name == "booking_create_total"
                and sample.labels == {"source": "manual", "status": "success"}
                and sample.value == 1
                for sample in counters
            ),
            counters,
        )
        db.commit.assert_awaited_once()

    async def test_safe_create_booking_keeps_limit_check_inside_user_week_lock(self) -> None:
        db = _FakeDb(None, 2)

        with patch(
            "app.services.booking_service._weekly_limit_value",
            new=AsyncMock(return_value=2),
        ), patch(
            "app.services.booking_service.is_weekly_reserved_on_date",
            new=AsyncMock(return_value=False),
        ):
            status, created = await safe_create_booking(
                db,
                user_id=7,
                b_date=date(2026, 3, 24),
                b_hour=18,
            )

        self.assertEqual(status, "limit")
        self.assertIsNone(created)
        self.assertEqual(len(db.executed), 2)
        self.assertIn("pg_advisory_xact_lock", str(db.executed[0]))
        db.commit.assert_not_awaited()

    async def test_safe_create_booking_rejects_weekly_reserved_slot_before_insert(self) -> None:
        db = _FakeDb()

        with (
            patch(
                "app.services.booking_service._weekly_limit_value",
                new=AsyncMock(return_value=2),
            ),
            patch(
                "app.services.booking_service.is_weekly_reserved_on_date",
                new=AsyncMock(return_value=True),
            ),
        ):
            status, created = await safe_create_booking(
                db,
                user_id=7,
                b_date=date(2026, 3, 24),
                b_hour=18,
            )

        self.assertEqual(status, "taken")
        self.assertIsNone(created)
        self.assertEqual(db.executed, [])
        db.commit.assert_not_awaited()

    async def test_weekly_reset_only_deletes_bookings_before_bookable_week(self) -> None:
        db = _FakeDb([(1,), (2,)], None)

        with patch(
            "app.services.booking_service.get_current_week_dates",
            return_value=[date(2026, 3, 30)],
        ):
            await weekly_reset(db)

        self.assertIn("bookings.date < :date_1", str(db.executed[0]))
        db.commit.assert_awaited_once()
