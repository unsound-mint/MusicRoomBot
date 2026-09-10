# app/bot/keyboards/location_kb.py
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def request_location_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📍 Send Location", request_location=True)],
        ],
        resize_keyboard=True,
    )
