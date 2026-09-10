# app/bot/ui.py
from collections.abc import Awaitable
from datetime import date

from aiogram import types
from sqlalchemy import select

from app.bot.constants.dates import WEEKDAYS


def format_slot_date(target_date: date) -> str:
    return f"*{WEEKDAYS[target_date.weekday()]}*"


def format_slot_text(target_date: date, hour: int) -> str:
    return f"{format_slot_date(target_date)} at {hour:02d}:00"


def format_slot_button(target_date: date, hour: int) -> str:
    return f"{WEEKDAYS[target_date.weekday()][:3]} {hour:02d}:00"


async def edit_or_answer(
    target: types.Message | types.CallbackQuery,
    text: str,
    *,
    reply_markup=None,
    parse_mode: str | None = None,
) -> types.Message:
    message = target.message if isinstance(target, types.CallbackQuery) else target
    if message is None:
        raise RuntimeError("Message target is unavailable")

    try:
        return await message.edit_text(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    except Exception:
        return await message.answer(
            text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )


async def safe_answer_callback(callback: types.CallbackQuery, text: str | None = None) -> None:
    try:
        await callback.answer(text)
    except Exception:
        return


async def get_main_menu_kb(db, tg_user_id: int):
    from app.bot.keyboards.main_menu import build_main_menu
    from app.models.user import User
    from app.services.admin_service import is_admin
    from app.services.attendance_service import get_current_booking
    from app.services.club_service import user_has_clubs

    is_admin_user = await is_admin(db, tg_user_id)
    has_club_slots = await user_has_clubs(db, tg_user_id)
    user = (await db.execute(select(User).where(User.tg_user_id == tg_user_id))).scalar_one_or_none()

    include_location = False
    if user:
        current_booking = await get_current_booking(db, user.id)
        include_location = bool(current_booking and not current_booking.absence_reported)

    return build_main_menu(
        is_admin=is_admin_user,
        include_location_button=include_location,
        has_club_slots=has_club_slots,
    )


async def run_with_fallback(
    primary: Awaitable[types.Message],
    fallback: Awaitable[types.Message],
) -> types.Message:
    try:
        return await primary
    except Exception:
        return await fallback
