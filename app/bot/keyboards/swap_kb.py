# app/bot/keyboards/swap_kb.py
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.constants.dates import WEEKDAYS


def swap_pick_day_kb(week_dates):
    rows = []
    for d in week_dates:
        weekday_idx = d.weekday()
        text = WEEKDAYS[weekday_idx]
        cb = f"swap_day_{weekday_idx}"
        rows.append([InlineKeyboardButton(text=text, callback_data=cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def swap_hour_kb(taken_hours):
    rows = []
    for h in sorted(taken_hours):
        text = f"{h:02d}:00"
        cb = f"swap_hour_{h}"
        rows.append([InlineKeyboardButton(text=text, callback_data=cb)])
    
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="swap_start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def swap_offer_kb(offer_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Accept Swap", callback_data=f"swap_accept_{offer_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Decline", callback_data=f"swap_decline_{offer_id}"
                )
            ],
        ]
    )
