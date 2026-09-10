from datetime import date
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

try:
    from app.bot.handlers.admin_bookings import (
        _admin_bookable_dates,
        admin_add_booking_username,
    )
except ModuleNotFoundError as exc:
    if exc.name != "aiogram":
        raise
    _admin_bookable_dates = None
    admin_add_booking_username = None

from app.bot.keyboards.admin_inline_kb import admin_bookings_kb


class _Result:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


@__import__("unittest").skipIf(_admin_bookable_dates is None, "aiogram is not installed")
class AdminBookingsKeyboardTests(TestCase):
    def test_admin_bookings_menu_exposes_add_booking(self) -> None:
        keyboard = admin_bookings_kb()

        buttons = [button for row in keyboard.inline_keyboard for button in row]

        self.assertIn(
            ("Add booking", "admin_bookings_add"),
            [(button.text, button.callback_data) for button in buttons],
        )

    def test_admin_bookable_dates_include_next_week(self) -> None:
        current_week = [date(2026, 3, 23 + offset) for offset in range(7)]

        with (
            patch(
                "app.bot.handlers.admin_bookings.get_current_week_dates",
                return_value=current_week,
            ),
            patch(
                "app.bot.handlers.admin_bookings.today_tz",
                return_value=date(2026, 3, 24),
            ),
        ):
            dates = _admin_bookable_dates()

        self.assertNotIn(date(2026, 3, 23), dates)
        self.assertIn(date(2026, 3, 30), dates)
        self.assertIn(date(2026, 4, 5), dates)


@__import__("unittest").skipIf(admin_add_booking_username is None, "aiogram is not installed")
class AdminAddBookingHandlerTests(IsolatedAsyncioTestCase):
    async def test_admin_add_booking_username_creates_next_week_booking(self) -> None:
        target_date = date(2026, 3, 31)
        state = AsyncMock()
        state.get_data.return_value = {
            "admin_booking_date": target_date.isoformat(),
            "admin_booking_hour": 18,
        }
        user = SimpleNamespace(
            id=7,
            tg_user_id=700,
            tg_username="member",
            allowed=True,
            banned=False,
        )
        booking = SimpleNamespace(id=99)
        db = SimpleNamespace(
            execute=AsyncMock(return_value=_Result(user)),
        )
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = db
        session_cm.__aexit__.return_value = False
        bot = SimpleNamespace(send_message=AsyncMock())
        message = SimpleNamespace(
            text="@member",
            bot=bot,
            from_user=SimpleNamespace(id=1),
            answer=AsyncMock(),
        )

        with (
            patch(
                "app.bot.handlers.admin_bookings.check_admin_and_reply",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "app.bot.handlers.admin_bookings.AsyncSessionLocal",
                return_value=session_cm,
            ),
            patch(
                "app.bot.handlers.admin_bookings.safe_create_booking",
                new=AsyncMock(return_value=("success", booking)),
            ) as safe_create_booking,
        ):
            await admin_add_booking_username(message, state)

        safe_create_booking.assert_awaited_once_with(
            db,
            7,
            target_date,
            18,
            booking_source="admin",
        )
        bot.send_message.assert_awaited_once()
        state.clear.assert_awaited_once()
        rendered = message.answer.await_args.args[0]
        self.assertIn("Booking added", rendered)
        self.assertIn("2026-03-31", rendered)
