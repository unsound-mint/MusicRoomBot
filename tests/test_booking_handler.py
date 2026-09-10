from datetime import date
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, skipIf
from unittest.mock import AsyncMock, Mock, patch

from app.bot.handlers.booking import (
    _render_booking_success,
    handle_pick_hour,
)

try:
    from app.bot.handlers.swap import handle_swap_decline
except ModuleNotFoundError as exc:
    if exc.name != "aiogram":
        raise
    handle_swap_decline = None

try:
    from app.bot.handlers.my_bookings import _notify_gift_recipient, my_booking_detail
except ModuleNotFoundError as exc:
    if exc.name != "aiogram":
        raise
    _notify_gift_recipient = None
    my_booking_detail = None


class BookingHandlerTests(IsolatedAsyncioTestCase):
    async def test_render_booking_success_sends_new_message(self) -> None:
        callback = SimpleNamespace(message=SimpleNamespace(answer=AsyncMock()))
        db = object()

        with (
            patch("app.bot.handlers.booking_renderers.get_slot_length_value", new=AsyncMock(return_value=60)),
            patch("app.bot.handlers.booking_renderers.get_google_calendar_link", return_value="https://calendar.test"),
            patch(
                "app.bot.handlers.booking_renderers.get_consecutive_slot_option",
                new=AsyncMock(return_value=(date(2026, 3, 27), 19)),
            ),
        ):
            await _render_booking_success(
                callback,
                db=db,
                booking_date=date(2026, 3, 27),
                booking_hour=18,
                user_id=5,
            )

        callback.message.answer.assert_awaited_once()
        self.assertIn("✅ *Booking confirmed*", callback.message.answer.await_args.args[0])
        reply_markup = callback.message.answer.await_args.kwargs["reply_markup"]
        texts = [button.text for row in reply_markup.inline_keyboard for button in row]
        self.assertIn("Book next hour", texts)
        self.assertIn("Add to calendar", texts)

    async def test_render_booking_success_hides_consecutive_when_none(self) -> None:
        callback = SimpleNamespace(message=SimpleNamespace(answer=AsyncMock()))
        db = object()

        with (
            patch("app.bot.handlers.booking_renderers.get_slot_length_value", new=AsyncMock(return_value=60)),
            patch("app.bot.handlers.booking_renderers.get_google_calendar_link", return_value="https://calendar.test"),
            patch(
                "app.bot.handlers.booking_renderers.get_consecutive_slot_option",
                new=AsyncMock(return_value=None),
            ),
        ):
            await _render_booking_success(
                callback,
                db=db,
                booking_date=date(2026, 3, 27),
                booking_hour=18,
                user_id=5,
            )

        reply_markup = callback.message.answer.await_args.kwargs["reply_markup"]
        texts = [button.text for row in reply_markup.inline_keyboard for button in row]
        self.assertNotIn("Book next hour", texts)
        self.assertIn("Add to calendar", texts)

    async def test_taken_slot_shows_unavailable_message(self) -> None:
        callback = SimpleNamespace(
            data="book_hour_4_2026-03-27_18",
            from_user=SimpleNamespace(id=10),
            message=SimpleNamespace(answer=AsyncMock(), edit_text=AsyncMock()),
        )
        user = SimpleNamespace(id=7)
        session = AsyncMock()
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = session
        session_cm.__aexit__.return_value = False

        with (
            patch("app.bot.handlers.booking.safe_answer_callback", new=AsyncMock()),
            patch("app.bot.handlers.booking.acquire_booking_slot", new=AsyncMock()),
            patch("app.bot.handlers.booking.release_booking_slot"),
            patch("app.bot.handlers.booking.AsyncSessionLocal", return_value=session_cm),
            patch("app.bot.handlers.booking.require_allowed_user", new=AsyncMock(return_value=user)),
            patch("app.bot.handlers.booking.is_weekly_reserved", new=AsyncMock(return_value=False)),
            patch("app.bot.handlers.booking.safe_create_booking", new=AsyncMock(return_value=("taken", None))),
            patch("app.bot.handlers.booking.get_free_hours_for_day", new=AsyncMock(return_value=[])),
            patch("app.bot.handlers.booking.now_tz") as now_tz,
            patch("app.bot.handlers.booking.edit_or_answer", new=AsyncMock()) as edit_or_answer,
        ):
            now_tz.return_value = __import__("datetime").datetime(
                2026,
                3,
                27,
                12,
                0,
                tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Almaty"),
            )
            await handle_pick_hour(callback)

        edit_or_answer.assert_awaited_once()
        rendered = edit_or_answer.await_args.args[1]
        self.assertIn("Slot unavailable", rendered)

    @skipIf(my_booking_detail is None, "aiogram is not installed")
    async def test_missing_booking_returns_to_bookings_with_note(self) -> None:
        callback = SimpleNamespace(
            data="myb_booking_999",
            from_user=SimpleNamespace(id=10),
            message=SimpleNamespace(answer=AsyncMock(), edit_text=AsyncMock()),
        )
        state = AsyncMock()
        user = SimpleNamespace(id=7)
        session = AsyncMock()
        session.get.return_value = None
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = session
        session_cm.__aexit__.return_value = False

        with (
            patch("app.bot.handlers.my_bookings.safe_answer_callback", new=AsyncMock()),
            patch("app.bot.handlers.my_bookings.AsyncSessionLocal", return_value=session_cm),
            patch("app.bot.handlers.my_bookings._current_user", new=AsyncMock(return_value=user)),
            patch("app.bot.handlers.my_bookings.get_user_bookings", new=AsyncMock(return_value=[])),
            patch("app.bot.handlers.my_bookings.edit_or_answer", new=AsyncMock()) as edit_or_answer,
        ):
            await my_booking_detail(callback, state)

        rendered = edit_or_answer.await_args.args[1]
        self.assertIn("That booking is no longer available.", rendered)
        self.assertIn("My bookings", rendered)

    @skipIf(_notify_gift_recipient is None, "aiogram is not installed")
    async def test_gift_notification_from_field_uses_username(self) -> None:
        bot = SimpleNamespace(send_message=AsyncMock())
        recipient = SimpleNamespace(id=9, tg_user_id=1009)
        giver = SimpleNamespace(id=7, tg_username="giver_name", full_name="True Name")
        booking = SimpleNamespace(id=11, date=date(2026, 3, 24), hour=18)

        await _notify_gift_recipient(
            bot=bot,
            recipient=recipient,
            giver=giver,
            booking=booking,
            offer_id=21,
        )

        text = bot.send_message.await_args.args[1]
        self.assertIn("👤 From: @giver\\_name", text)
        self.assertNotIn("True Name", text)

    @skipIf(handle_swap_decline is None, "aiogram is not installed")
    async def test_swap_decline_handles_missing_offer_without_slot_fields(self) -> None:
        callback = SimpleNamespace(
            data="swap_decline_42",
            from_user=SimpleNamespace(id=80),
            message=SimpleNamespace(),
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

        self.assertEqual(session.execute.await_count, 2)
        edit_or_answer.assert_awaited_once()
        rendered = edit_or_answer.await_args.args[1]
        self.assertIn("*Swap offer unavailable*", rendered)
        self.assertIn("Your bookings are unchanged.", rendered)
        self.assertEqual(edit_or_answer.await_args.kwargs["parse_mode"], "Markdown")
