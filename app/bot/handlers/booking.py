# app/bot/handlers/booking.py
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from aiogram import F, Router, types

from app.bot.constants.dates import WEEKDAYS
from app.bot.handlers.booking_flow import (
    get_free_hours_for_day,
    get_slot_length_value,
    get_weekly_limit_value,
)
from app.bot.handlers.booking_guards import (
    ACCESS_PENDING_EDIT_TEXT,
    ACCESS_PENDING_TEXT,
    require_allowed_user,
    require_registered_user,
)
from app.bot.handlers.booking_messages import (
    build_booking_success_two_slots_text,
    build_weekly_limit_text,
)
from app.bot.handlers.booking_renderers import (
    render_booking_success as _render_booking_success,
)
from app.bot.handlers.booking_renderers import (
    render_day_picker as _render_day_picker,
)
from app.bot.handlers.booking_renderers import (
    render_hours as _render_hours,
)
from app.bot.handlers.flash_book import notify_slot_taken
from app.bot.keyboards.inline_kb import booking_success_kb
from app.bot.ui import (
    edit_or_answer,
    format_slot_text,
    safe_answer_callback,
)
from app.core.config import TIMEZONE
from app.core.database import AsyncSessionLocal
from app.core.limits import BusyError, acquire_booking_slot, release_booking_slot
from app.core.rate_limit import allow_booking_start
from app.core.reset_gate import is_reset_in_progress
from app.services.booking_queries import get_user_bookings
from app.services.booking_queries import (
    is_weekly_reserved_on_date as is_weekly_reserved,
)
from app.services.booking_service import safe_create_booking
from app.services.calendar_service import get_google_calendar_link
from app.services.date_service import get_current_week_date
from app.services.time_service import now_tz

router = Router()

BUSY_TEXT = "⏳ *High load* — try again in a few seconds."


@router.message(F.text == "🎵 Book a slot")
async def start_booking(message: types.Message):
    user_tg_id = message.from_user.id

    if is_reset_in_progress():
        return await message.answer(
            "🔄 Weekly reset in progress.\nTry again in a few seconds."
        )

    if not await allow_booking_start(user_tg_id):
        return await message.answer("⏳ Too many requests.\nPlease wait and try again.")

    try:
        await acquire_booking_slot()
    except BusyError:
        return await message.answer(BUSY_TEXT)

    try:
        async with AsyncSessionLocal() as db:
            user = await require_allowed_user(
                message,
                db,
                user_tg_id,
                use_edit=False,
                pending_text=ACCESS_PENDING_TEXT,
            )
            if not user:
                return None
            return await _render_day_picker(message, db=db, user_id=user.id)
    finally:
        release_booking_slot()


@router.callback_query(F.data == "book_back_days")
async def handle_booking_back_days(callback: types.CallbackQuery):
    await safe_answer_callback(callback)
    async with AsyncSessionLocal() as db:
        user = await require_registered_user(
            callback,
            db,
            callback.from_user.id,
            use_edit=True,
        )
        if not user:
            return None
        return await _render_day_picker(callback, db=db, user_id=user.id)


@router.callback_query(F.data == "book_recover_days")
async def handle_booking_recover_days(callback: types.CallbackQuery):
    return await handle_booking_back_days(callback)


@router.callback_query(F.data.startswith("book_day_"))
async def handle_pick_day(callback: types.CallbackQuery):
    await safe_answer_callback(callback)
    weekday_idx = int(callback.data.split("_")[2])
    target_date = get_current_week_date(weekday_idx)

    async with AsyncSessionLocal() as db:
        user = await require_allowed_user(
            callback,
            db,
            callback.from_user.id,
            use_edit=True,
            pending_text=ACCESS_PENDING_EDIT_TEXT,
        )
        if not user:
            return None
        return await _render_hours(
            callback.message,
            db=db,
            weekday_idx=weekday_idx,
            target_date=target_date,
            user_id=user.id,
        )


@router.callback_query(F.data.startswith("book_hour_"))
async def handle_pick_hour(callback: types.CallbackQuery):
    await safe_answer_callback(callback)

    _, _, weekday_idx_s, date_str, hour_str = callback.data.split("_")
    weekday_idx = int(weekday_idx_s)
    hour = int(hour_str)
    target_date = date.fromisoformat(date_str)

    now = now_tz()
    slot_dt = datetime.combine(target_date, time(hour)).replace(
        tzinfo=ZoneInfo(TIMEZONE)
    )
    if slot_dt <= now:
        return await edit_or_answer(
            callback,
            "⏰ This slot is in the past.",
            parse_mode="Markdown",
        )

    try:
        await acquire_booking_slot()
    except BusyError:
        return await edit_or_answer(callback, BUSY_TEXT, parse_mode="Markdown")

    try:
        async with AsyncSessionLocal() as db:
            user = await require_allowed_user(
                callback,
                db,
                callback.from_user.id,
                use_edit=True,
                pending_text=ACCESS_PENDING_EDIT_TEXT,
            )
            if not user:
                return None

            if await is_weekly_reserved(db, target_date, hour):
                return await edit_or_answer(
                    callback,
                    f"🔒 *Reserved slot*\n\n⏰ {format_slot_text(target_date, hour)}",
                    parse_mode="Markdown",
                )

            status, booking = await safe_create_booking(db, user.id, target_date, hour)
            if status == "limit":
                weekly_limit = await get_weekly_limit_value()
                bookings = await get_user_bookings(db, user.id)
                return await edit_or_answer(
                    callback,
                    build_weekly_limit_text(bookings, weekly_limit),
                    parse_mode="Markdown",
                )

            if status == "taken":
                free_hours = await get_free_hours_for_day(db, weekday_idx, target_date)
                if free_hours:
                    return await _render_hours(
                        callback,
                        db=db,
                        weekday_idx=weekday_idx,
                        target_date=target_date,
                        taken_message="⚠️ That slot was just taken.",
                        user_id=user.id,
                    )
                return await edit_or_answer(
                    callback,
                    (
                        "❌ *Slot unavailable*\n\n"
                        f"⏰ {WEEKDAYS[weekday_idx]} · {hour:02d}:00\n\n"
                        "Pick another available time."
                    ),
                    parse_mode="Markdown",
                )

            if booking is None:
                return await edit_or_answer(
                    callback,
                    "⚠️ Booking failed.\nTry again, or contact an admin if it persists.",
                )

            name = user.full_name or user.tg_username or "Unknown user"
            await notify_slot_taken(callback.bot, target_date, hour, name)
            return await _render_booking_success(
                callback,
                db=db,
                booking_date=target_date,
                booking_hour=hour,
                user_id=user.id,
            )
    finally:
        release_booking_slot()


@router.callback_query(F.data.startswith("book_next_"))
async def handle_book_consecutive(callback: types.CallbackQuery):
    await safe_answer_callback(callback)

    parts = callback.data.split("_")
    date_str = parts[2]
    hour_str = parts[3]
    target_date = date.fromisoformat(date_str)
    hour = int(hour_str)
    prev_date = date.fromisoformat(parts[4]) if len(parts) > 4 else None
    prev_hour = int(parts[5]) if len(parts) > 5 else None
    slot_dt = datetime.combine(target_date, time(hour)).replace(
        tzinfo=ZoneInfo(TIMEZONE)
    )
    if slot_dt <= now_tz():
        return await callback.message.answer(
            "⏰ This slot is in the past.",
        )

    try:
        await acquire_booking_slot()
    except BusyError:
        return await callback.message.answer(BUSY_TEXT)

    try:
        async with AsyncSessionLocal() as db:
            user = await require_allowed_user(
                callback.message,
                db,
                callback.from_user.id,
                use_edit=False,
                pending_text=ACCESS_PENDING_TEXT,
            )
            if not user:
                return None

            if await is_weekly_reserved(db, target_date, hour):
                return await callback.message.answer(
                    f"🔒 *Reserved slot*\n\n⏰ {format_slot_text(target_date, hour)}",
                    parse_mode="Markdown",
                )

            status, booking = await safe_create_booking(db, user.id, target_date, hour)
            if status == "taken":
                return await callback.message.answer(
                    (
                        f"❌ *Slot unavailable*\n\n⏰ {format_slot_text(target_date, hour)}\n\n"
                        "That slot was just taken. Pick another day."
                    ),
                    parse_mode="Markdown",
                )
            if status == "limit":
                return await callback.message.answer(
                    "⚠️ *Weekly limit reached*\n\nCancel a booking if your plans change.",
                    parse_mode="Markdown",
                )
            if booking is None:
                return await callback.message.answer(
                    "⚠️ Booking failed.\nTry again, or contact an admin if it persists.",
                    parse_mode="Markdown",
                )

            name = user.full_name or user.tg_username or "Unknown user"
            await notify_slot_taken(callback.bot, target_date, hour, name)

            if prev_date is not None and prev_hour is not None:
                slot_length = await get_slot_length_value()
                link = get_google_calendar_link(
                    prev_date,
                    prev_hour,
                    slot_length_minutes=slot_length * 2,
                )
                return await callback.message.edit_text(
                    build_booking_success_two_slots_text(
                        format_slot_text(prev_date, prev_hour),
                        format_slot_text(target_date, hour),
                    ),
                    reply_markup=booking_success_kb(
                        calendar_link=link,
                        consecutive_callback=None,
                    ),
                    parse_mode="Markdown",
                )

            return await _render_booking_success(
                callback,
                db=db,
                booking_date=target_date,
                booking_hour=hour,
                user_id=user.id,
            )
    finally:
        release_booking_slot()
