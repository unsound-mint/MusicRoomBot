from datetime import date
from types import SimpleNamespace
from unittest import TestCase

from app.bot.keyboards.inline_kb import (
    booking_detail_kb,
    booking_success_kb,
    bookings_hub_kb,
    gift_offer_response_kb,
)


class InlineKeyboardTests(TestCase):
    def test_booking_success_keyboard_hides_consecutive_button_when_missing(self) -> None:
        keyboard = booking_success_kb(
            calendar_link="https://example.com",
            consecutive_callback=None,
        )

        texts = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertEqual(
            texts,
            [
                "Add to calendar",
            ],
        )

    def test_booking_success_keyboard_shows_consecutive_button_when_provided(self) -> None:
        keyboard = booking_success_kb(
            calendar_link="https://example.com",
            consecutive_callback="book_next_2026-03-27_19",
        )

        texts = [button.text for row in keyboard.inline_keyboard for button in row]
        self.assertEqual(
            texts,
            [
                "Book next hour",
                "Add to calendar",
            ],
        )

    def test_bookings_hub_keyboard_lists_confirmed_bookings(self) -> None:
        confirmed = [SimpleNamespace(id=1, date=date(2026, 3, 24), hour=18)]

        keyboard = bookings_hub_kb(confirmed=confirmed)
        texts = [button.text for row in keyboard.inline_keyboard for button in row]

        self.assertEqual(texts, ["Tue 18:00"])

    def test_booking_detail_keyboard_includes_gift_for_future_booking(self) -> None:
        keyboard = booking_detail_kb(
            5,
            calendar_link="https://example.com",
            can_swap=True,
            can_cancel=True,
            can_gift=True,
        )

        buttons = [button for row in keyboard.inline_keyboard for button in row]
        texts = [button.text for button in buttons]
        callbacks = [button.callback_data for button in buttons]

        self.assertEqual(
            texts,
            [
                "Cancel booking",
                "Swap booking",
                "Gift booking",
                "Add to calendar",
                "⬅️ Back",
            ],
        )
        self.assertIn("myb_gift_5", callbacks)

    def test_gift_offer_response_keyboard_includes_accept_and_decline(self) -> None:
        keyboard = gift_offer_response_kb(21)

        buttons = [button for row in keyboard.inline_keyboard for button in row]
        self.assertEqual(
            [button.text for button in buttons],
            ["Accept booking", "Decline"],
        )
        self.assertEqual(
            [button.callback_data for button in buttons],
            ["gift_accept_21", "gift_decline_21"],
        )
