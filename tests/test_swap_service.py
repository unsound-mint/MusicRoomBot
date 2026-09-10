from datetime import date, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

from app.core.config import TIMEZONE
from app.services.swap_service import (
    accept_swap_offer,
    create_swap_offer,
    decline_swap_offer,
)


class _ScalarResult:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class SwapServiceTests(IsolatedAsyncioTestCase):
    async def test_create_swap_offer_persists_pending_offer(self) -> None:
        target_booking = SimpleNamespace(
            id=99,
            user_id=8,
            date=date(2026, 3, 27),
            hour=18,
        )
        my_booking = SimpleNamespace(
            id=77,
            user_id=7,
            date=date(2026, 3, 28),
            hour=12,
        )
        receiver_user = SimpleNamespace(tg_user_id=800)
        giver_user = SimpleNamespace(full_name="Giver", tg_username="giver")
        db = AsyncMock()
        db.get.side_effect = [
            target_booking,
            my_booking,
            receiver_user,
            giver_user,
        ]
        db.add = Mock()

        async def refresh(offer) -> None:
            offer.id = 42

        db.refresh.side_effect = refresh

        with patch(
            "app.services.swap_service.now_tz",
            return_value=datetime.fromisoformat("2026-03-24T10:00:00+05:00"),
        ):
            result = await create_swap_offer(db, 99, 77, giver_user_id=7)

        self.assertEqual(result.status, "created")
        self.assertEqual(result.offer_id, 42)
        self.assertEqual(result.receiver_tg_user_id, 800)
        self.assertEqual(result.giver_display_name, "Giver")
        added_offer = db.add.call_args.args[0]
        self.assertEqual(added_offer.giver_user_id, 7)
        self.assertEqual(added_offer.receiver_user_id, 8)
        self.assertEqual(added_offer.give_date, date(2026, 3, 28))
        self.assertEqual(added_offer.give_hour, 12)
        self.assertEqual(added_offer.want_date, date(2026, 3, 27))
        self.assertEqual(added_offer.want_hour, 18)
        self.assertEqual(added_offer.status, "pending")
        db.commit.assert_awaited_once()

    async def test_accept_swap_offer_swaps_booking_owners(self) -> None:
        offer = SimpleNamespace(
            status="pending",
            giver_user_id=7,
            receiver_user_id=8,
            give_date=date(2026, 3, 28),
            give_hour=12,
            want_date=date(2026, 3, 27),
            want_hour=18,
        )
        giver_booking = SimpleNamespace(
            user_id=7,
            date=date(2026, 3, 28),
            hour=12,
        )
        receiver_booking = SimpleNamespace(
            user_id=8,
            date=date(2026, 3, 27),
            hour=18,
        )
        giver_user = SimpleNamespace(tg_user_id=700)
        db = AsyncMock()
        db.get.return_value = giver_user
        db.execute.side_effect = [
            _ScalarResult(offer),
            _ScalarResult(giver_booking),
            _ScalarResult(receiver_booking),
            SimpleNamespace(),
        ]

        with patch(
            "app.services.swap_service.now_tz",
            return_value=datetime(2026, 3, 24, 10, 0, tzinfo=ZoneInfo(TIMEZONE)),
        ):
            result = await accept_swap_offer(db, 42, receiver_user_id=8)

        self.assertEqual(result.status, "accepted")
        self.assertEqual(giver_booking.user_id, 8)
        self.assertEqual(receiver_booking.user_id, 7)
        self.assertEqual(offer.status, "accepted")
        self.assertEqual(result.giver_tg_user_id, 700)
        self.assertEqual(result.giver_new_date, date(2026, 3, 27))
        self.assertEqual(result.receiver_new_date, date(2026, 3, 28))
        db.commit.assert_awaited_once()

    async def test_accept_swap_offer_cancels_when_booking_missing(self) -> None:
        offer = SimpleNamespace(
            status="pending",
            giver_user_id=7,
            receiver_user_id=8,
            give_date=date(2026, 3, 28),
            give_hour=12,
            want_date=date(2026, 3, 27),
            want_hour=18,
        )
        db = AsyncMock()
        db.execute.side_effect = [
            _ScalarResult(offer),
            _ScalarResult(None),
            _ScalarResult(None),
        ]

        result = await accept_swap_offer(db, 42, receiver_user_id=8)

        self.assertEqual(result.status, "missing_booking")
        self.assertEqual(offer.status, "cancelled")
        db.commit.assert_awaited_once()

    async def test_create_swap_offer_rejects_non_owner(self) -> None:
        target_booking = SimpleNamespace(
            id=99,
            user_id=8,
            date=date(2026, 3, 27),
            hour=18,
        )
        my_booking = SimpleNamespace(
            id=77,
            user_id=7,
            date=date(2026, 3, 28),
            hour=12,
        )
        db = AsyncMock()
        db.get.side_effect = [target_booking, my_booking]

        result = await create_swap_offer(db, 99, 77, giver_user_id=999)

        self.assertEqual(result.status, "missing_booking")
        db.add.assert_not_called()
        db.commit.assert_not_awaited()

    async def test_accept_swap_offer_rejects_non_receiver(self) -> None:
        offer = SimpleNamespace(
            status="pending",
            giver_user_id=7,
            receiver_user_id=8,
            give_date=date(2026, 3, 28),
            give_hour=12,
            want_date=date(2026, 3, 27),
            want_hour=18,
        )
        db = AsyncMock()
        db.execute.return_value = _ScalarResult(offer)

        result = await accept_swap_offer(db, 42, receiver_user_id=999)

        self.assertEqual(result.status, "unavailable")
        db.execute.assert_awaited_once()
        db.commit.assert_not_awaited()

    async def test_decline_swap_offer_marks_offer_declined(self) -> None:
        offer = SimpleNamespace(
            status="pending",
            giver_user_id=7,
            receiver_user_id=8,
            give_date=date(2026, 3, 28),
            give_hour=12,
            want_date=date(2026, 3, 27),
            want_hour=18,
        )
        giver_user = SimpleNamespace(tg_user_id=700)
        db = AsyncMock()
        db.execute.return_value = _ScalarResult(offer)
        db.get.return_value = giver_user

        result = await decline_swap_offer(db, 42, receiver_user_id=8)

        self.assertEqual(result.status, "declined")
        self.assertEqual(offer.status, "declined")
        self.assertEqual(result.giver_tg_user_id, 700)
        self.assertEqual(result.give_date, date(2026, 3, 28))
        self.assertEqual(result.want_date, date(2026, 3, 27))
        db.commit.assert_awaited_once()

    async def test_decline_swap_offer_rejects_non_receiver(self) -> None:
        offer = SimpleNamespace(
            status="pending",
            giver_user_id=7,
            receiver_user_id=8,
            give_date=date(2026, 3, 28),
            give_hour=12,
            want_date=date(2026, 3, 27),
            want_hour=18,
        )
        db = AsyncMock()
        db.execute.return_value = _ScalarResult(offer)

        result = await decline_swap_offer(db, 42, receiver_user_id=999)

        self.assertEqual(result.status, "unavailable")
        self.assertEqual(offer.status, "pending")
        db.commit.assert_not_awaited()

    async def test_decline_swap_offer_notifies_after_commit(self) -> None:
        offer = SimpleNamespace(
            status="pending",
            giver_user_id=7,
            receiver_user_id=8,
            give_date=date(2026, 3, 28),
            give_hour=12,
            want_date=date(2026, 3, 27),
            want_hour=18,
        )
        giver_user = SimpleNamespace(tg_user_id=700)
        events: list[str] = []
        db = AsyncMock()
        db.execute.return_value = _ScalarResult(offer)
        db.get.return_value = giver_user

        async def commit() -> None:
            events.append("commit")

        async def after_commit(_result) -> None:
            events.append("notify")

        db.commit.side_effect = commit

        result = await decline_swap_offer(
            db,
            42,
            receiver_user_id=8,
            after_commit=after_commit,
        )

        self.assertEqual(result.status, "declined")
        self.assertEqual(events, ["commit", "notify"])
