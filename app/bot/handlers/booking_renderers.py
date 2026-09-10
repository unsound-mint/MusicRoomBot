from datetime import date
from typing import Any

from aiogram import types

from app.bot.constants.dates import WEEKDAYS
from app.bot.handlers.booking_flow import (
    get_available_days_and_usage,
    get_free_hours_for_day,
    get_slot_length_value,
)
from app.bot.handlers.booking_messages import (
    build_booking_success_text,
    build_no_free_slots_text,
    build_pick_day_text,
    build_weekly_limit_text,
)
from app.bot.keyboards.inline_kb import (
    booking_success_kb,
    day_selection_kb,
    hour_selection_kb,
)
from app.bot.ui import edit_or_answer, format_slot_text
from app.services.booking_queries import get_user_bookings
from app.services.booking_service import (
    get_consecutive_slot_option,
)
from app.services.calendar_service import get_google_calendar_link


async def render_day_picker(
    target: types.Message | types.CallbackQuery,
    *,
    db: Any,
    user_id: int,
) -> types.Message:
    available_days, booked_count, weekly_limit = await get_available_days_and_usage(
        db, user_id
    )
    if booked_count >= weekly_limit:
        bookings = await get_user_bookings(db, user_id)
        return await edit_or_answer(
            target,
            build_weekly_limit_text(bookings, weekly_limit),
            parse_mode="Markdown",
        )

    if not available_days:
        return await edit_or_answer(
            target,
            build_no_free_slots_text(),
            parse_mode="Markdown",
        )

    return await edit_or_answer(
        target,
        build_pick_day_text(
            booked_count=booked_count,
            weekly_limit=weekly_limit,
            title="📅 Pick a day.",
        ),
        reply_markup=day_selection_kb(available_days),
        parse_mode="Markdown",
    )


async def render_hours(
    target: types.Message | types.CallbackQuery,
    *,
    db: Any,
    weekday_idx: int,
    target_date: date,
    taken_message: str | None = None,
    user_id: int | None = None,
) -> types.Message:
    free_hours = await get_free_hours_for_day(db, weekday_idx, target_date)
    if not free_hours:
        if user_id is not None:
            return await render_day_picker(target, db=db, user_id=user_id)
        return await edit_or_answer(
            target,
            build_no_free_slots_text(),
            parse_mode="Markdown",
        )

    prefix = f"{taken_message}\n\n" if taken_message else ""
    return await edit_or_answer(
        target,
        f"{prefix}📅 {WEEKDAYS[weekday_idx]}\n\n⏰ Pick a time.",
        reply_markup=hour_selection_kb(free_hours, weekday_idx, target_date),
        parse_mode="Markdown",
    )


async def render_booking_success(
    callback: types.CallbackQuery,
    *,
    db: Any,
    booking_date: date,
    booking_hour: int,
    user_id: int,
) -> types.Message:
    slot_length = await get_slot_length_value()
    link = get_google_calendar_link(
        booking_date,
        booking_hour,
        slot_length_minutes=slot_length,
    )
    consecutive = await get_consecutive_slot_option(db, user_id, booking_date, booking_hour)
    consecutive_callback = None
    if consecutive is not None:
        next_date, next_hour = consecutive
        consecutive_callback = (
            f"book_next_{next_date.isoformat()}_{next_hour}"
            f"_{booking_date.isoformat()}_{booking_hour}"
        )

    return await callback.message.answer(
        build_booking_success_text(format_slot_text(booking_date, booking_hour)),
        reply_markup=booking_success_kb(
            calendar_link=link,
            consecutive_callback=consecutive_callback,
        ),
        parse_mode="Markdown",
    )
