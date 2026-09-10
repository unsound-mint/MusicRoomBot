from datetime import date, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, skipIf
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

try:
    from app.bot.handlers.swap import (
        _do_create_swap_offer,
        handle_swap_accept,
        handle_swap_day_pick,
        handle_swap_decline,
        handle_swap_hour_pick,
    )
except ModuleNotFoundError as exc:
    if exc.name != "aiogram":
        raise
    _do_create_swap_offer = None
    handle_swap_accept = None
    handle_swap_day_pick = None
    handle_swap_decline = None
    handle_swap_hour_pick = None


def _callback_data(reply_markup) -> list[str]:
    if reply_markup is None:
        return []
    return [
        button.callback_data
        for row in reply_markup.inline_keyboard
        for button in row
    ]


@skipIf(handle_swap_day_pick is None, "aiogram is not installed")
class SwapHandlerRecoveryTests(IsolatedAsyncioTestCase):
    async def test_no_target_slots_shows_recovery_actions(self) -> None:
        callback = SimpleNamespace(
            data="swap_day_4",
            from_user=SimpleNamespace(id=10),
            message=SimpleNamespace(answer=AsyncMock(), edit_text=AsyncMock()),
        )
        state = AsyncMock()
        state.get_data.return_value = {"offer_booking_id": 123}
        session = AsyncMock()
        session.execute.return_value = Mock(
            scalars=Mock(return_value=Mock(all=Mock(return_value=[])))
        )
        session.get.return_value = SimpleNamespace(date=date(2026, 3, 27), hour=18)
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = session
        session_cm.__aexit__.return_value = False

        with (
            patch("app.bot.handlers.swap.safe_answer_callback", new=AsyncMock()),
            patch("app.bot.handlers.swap.AsyncSessionLocal", return_value=session_cm),
            patch("app.bot.handlers.swap.get_current_week_date", return_value=date(2026, 3, 27)),
            patch("app.bot.handlers.swap.edit_or_answer", new=AsyncMock()) as edit_or_answer,
        ):
            await handle_swap_day_pick(callback, state)

        rendered = edit_or_answer.await_args.args[1]
        self.assertIn("No upcoming bookings", rendered)

    async def test_no_own_bookings_to_offer_shows_recovery_actions(self) -> None:
        callback = SimpleNamespace(
            data="swap_hour_18",
            from_user=SimpleNamespace(id=10),
            message=SimpleNamespace(answer=AsyncMock(), edit_text=AsyncMock()),
        )
        state = AsyncMock()
        state.get_data.return_value = {"swap_target_date": "2026-03-27"}
        target_booking = SimpleNamespace(id=99, date=date(2026, 3, 27), hour=18)
        target_user = SimpleNamespace(id=8)
        me = SimpleNamespace(id=7)
        first_session = AsyncMock()
        first_session.execute.return_value = Mock(first=Mock(return_value=(target_booking, target_user)))
        second_session = AsyncMock()
        second_session.execute.return_value = Mock(scalar_one=Mock(return_value=me))
        session_cm_1 = AsyncMock()
        session_cm_1.__aenter__.return_value = first_session
        session_cm_1.__aexit__.return_value = False
        session_cm_2 = AsyncMock()
        session_cm_2.__aenter__.return_value = second_session
        session_cm_2.__aexit__.return_value = False

        with (
            patch("app.bot.handlers.swap.safe_answer_callback", new=AsyncMock()),
            patch("app.bot.handlers.swap.AsyncSessionLocal", side_effect=[session_cm_1, session_cm_2]),
            patch("app.bot.handlers.swap._load_upcoming_bookings", new=AsyncMock(return_value=[])),
            patch("app.bot.handlers.swap.edit_or_answer", new=AsyncMock()) as edit_or_answer,
        ):
            await handle_swap_hour_pick(callback, state)

        rendered = edit_or_answer.await_args.args[1]
        self.assertIn("No upcoming bookings", rendered)

    async def test_target_slot_gone_shows_recovery_actions(self) -> None:
        callback = SimpleNamespace(
            data="swap_hour_18",
            from_user=SimpleNamespace(id=10),
            message=SimpleNamespace(answer=AsyncMock(), edit_text=AsyncMock()),
        )
        state = AsyncMock()
        state.get_data.return_value = {"swap_target_date": "2026-03-27"}
        session = AsyncMock()
        session.execute.return_value = Mock(first=Mock(return_value=None))
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = session
        session_cm.__aexit__.return_value = False

        with (
            patch("app.bot.handlers.swap.safe_answer_callback", new=AsyncMock()),
            patch("app.bot.handlers.swap.AsyncSessionLocal", return_value=session_cm),
            patch("app.bot.handlers.swap.edit_or_answer", new=AsyncMock()) as edit_or_answer,
        ):
            await handle_swap_hour_pick(callback, state)

        rendered = edit_or_answer.await_args.args[1]
        self.assertIn("That slot is no longer available", rendered)

    async def test_swap_request_sent_shows_confirmation(self) -> None:
        callback = SimpleNamespace(
            bot=SimpleNamespace(send_message=AsyncMock()),
            message=SimpleNamespace(answer=AsyncMock(), edit_text=AsyncMock()),
        )
        state = AsyncMock()
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
        receiver_user = SimpleNamespace(tg_user_id=800, full_name="Receiver")
        giver_user = SimpleNamespace(tg_user_id=700, full_name="Giver", tg_username="giver")
        session = AsyncMock()
        session.get.side_effect = [
            target_booking,
            my_booking,
            receiver_user,
            giver_user,
        ]
        session_cm = AsyncMock()
        session.add = Mock()
        session_cm.__aenter__.return_value = session
        session_cm.__aexit__.return_value = False

        with (
            patch("app.bot.handlers.swap.AsyncSessionLocal", return_value=session_cm),
            patch(
                "app.services.swap_service.now_tz",
                return_value=datetime(
                    2026, 3, 24, 10, 0, tzinfo=ZoneInfo("Asia/Almaty")
                ),
            ),
            patch("app.bot.handlers.swap.edit_or_answer", new=AsyncMock()) as edit_or_answer,
        ):
            await _do_create_swap_offer(
                callback,
                state,
                target_booking.id,
                my_booking.id,
                giver_user_id=7,
            )

        rendered = edit_or_answer.await_args.args[1]
        self.assertIn("Swap request sent", rendered)

    async def test_invalid_accept_shows_message(self) -> None:
        callback = SimpleNamespace(
            data="swap_accept_42",
            from_user=SimpleNamespace(id=80),
            answer=AsyncMock(),
            message=SimpleNamespace(delete=AsyncMock()),
        )
        user = SimpleNamespace(id=8)
        session = AsyncMock()
        session.execute.side_effect = [
            Mock(scalar_one_or_none=Mock(return_value=user)),
            Mock(scalar_one_or_none=Mock(return_value=None)),
        ]
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = session
        session_cm.__aexit__.return_value = False

        with (
            patch("app.bot.handlers.swap.AsyncSessionLocal", return_value=session_cm),
            patch("app.bot.handlers.swap.edit_or_answer", new=AsyncMock()) as edit_or_answer,
        ):
            await handle_swap_accept(callback)

        callback.message.delete.assert_not_awaited()
        rendered = edit_or_answer.await_args.args[1]
        self.assertIn("Swap offer unavailable", rendered)

    async def test_accept_success_shows_confirmation(self) -> None:
        callback = SimpleNamespace(
            data="swap_accept_42",
            from_user=SimpleNamespace(id=80),
            bot=SimpleNamespace(send_message=AsyncMock()),
            message=SimpleNamespace(answer=AsyncMock(), edit_text=AsyncMock()),
        )
        user = SimpleNamespace(id=8)
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
        session = AsyncMock()
        session.get.return_value = giver_user
        session.execute.side_effect = [
            Mock(scalar_one_or_none=Mock(return_value=user)),
            Mock(scalar_one_or_none=Mock(return_value=offer)),
            Mock(scalar_one_or_none=Mock(return_value=giver_booking)),
            Mock(scalar_one_or_none=Mock(return_value=receiver_booking)),
            Mock(),
        ]
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = session
        session_cm.__aexit__.return_value = False

        with (
            patch("app.bot.handlers.swap.AsyncSessionLocal", return_value=session_cm),
            patch(
                "app.services.swap_service.now_tz",
                return_value=datetime(
                    2026, 3, 24, 10, 0, tzinfo=ZoneInfo("Asia/Almaty")
                ),
            ),
            patch("app.bot.handlers.swap.edit_or_answer", new=AsyncMock()) as edit_or_answer,
        ):
            await handle_swap_accept(callback)

        rendered = edit_or_answer.await_args.args[1]
        self.assertIn("Swap completed", rendered)

    async def test_decline_success_shows_confirmation(self) -> None:
        callback = SimpleNamespace(
            data="swap_decline_42",
            from_user=SimpleNamespace(id=80),
            bot=SimpleNamespace(send_message=AsyncMock()),
            message=SimpleNamespace(answer=AsyncMock(), edit_text=AsyncMock()),
        )
        user = SimpleNamespace(id=8)
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
        session = AsyncMock()
        session.execute.side_effect = [
            Mock(scalar_one_or_none=Mock(return_value=user)),
            Mock(scalar_one_or_none=Mock(return_value=offer)),
        ]
        session.get.return_value = giver_user
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = session
        session_cm.__aexit__.return_value = False

        with (
            patch("app.bot.handlers.swap.AsyncSessionLocal", return_value=session_cm),
            patch("app.bot.handlers.swap.edit_or_answer", new=AsyncMock()) as edit_or_answer,
        ):
            await handle_swap_decline(callback)

        rendered = edit_or_answer.await_args.args[1]
        self.assertIn("Swap declined", rendered)

    async def test_invalid_decline_shows_message(self) -> None:
        callback = SimpleNamespace(
            data="swap_decline_42",
            from_user=SimpleNamespace(id=80),
            message=SimpleNamespace(answer=AsyncMock(), edit_text=AsyncMock()),
        )
        user = SimpleNamespace(id=8)
        session = AsyncMock()
        session.execute.side_effect = [
            Mock(scalar_one_or_none=Mock(return_value=user)),
            Mock(scalar_one_or_none=Mock(return_value=None)),
        ]
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = session
        session_cm.__aexit__.return_value = False

        with (
            patch("app.bot.handlers.swap.AsyncSessionLocal", return_value=session_cm),
            patch("app.bot.handlers.swap.edit_or_answer", new=AsyncMock()) as edit_or_answer,
        ):
            await handle_swap_decline(callback)

        rendered = edit_or_answer.await_args.args[1]
        self.assertIn("Swap offer unavailable", rendered)
