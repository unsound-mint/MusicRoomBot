# app/bot/keyboards/main_menu.py
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def build_main_menu(
    is_admin: bool = False,
    include_location_button: bool = False,
    has_club_slots: bool = False,
):
    if has_club_slots:
        keyboard = [
            [KeyboardButton(text="🎵 Book a slot"), KeyboardButton(text="🎸 My bookings")],
            [KeyboardButton(text="🎼 Club slots"), KeyboardButton(text="📅 Schedule")],
            [KeyboardButton(text="🎤 Equipment"), KeyboardButton(text="📜 Rules")],
        ]
    else:
        keyboard = [
            [KeyboardButton(text="🎵 Book a slot")],
            [KeyboardButton(text="🎸 My bookings"), KeyboardButton(text="📅 Schedule")],
            [KeyboardButton(text="🎤 Equipment"), KeyboardButton(text="📜 Rules")],
        ]

    if include_location_button:
        keyboard.insert(
            0,
            [KeyboardButton(text="📍 Send Location", request_location=True)],
        )

    if is_admin:
        keyboard.append([KeyboardButton(text="🛠 Admin")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        selective=True,
    )
