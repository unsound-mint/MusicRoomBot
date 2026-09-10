from datetime import date

from sqlalchemy import select

from app.bot.constants.dates import WEEKDAYS
from app.models.booking import Booking
from app.services.booking_queries import count_user_bookings_this_week
from app.services.club_service import is_weekly_reserved_for_date
from app.services.config_runtime import get_runtime_config
from app.services.config_service import get_working_hours, get_working_hours_bulk
from app.services.date_service import (
    get_current_week_date,
    get_current_week_dates,
    is_future_slot,
)


async def get_weekly_limit_value() -> int:
    value = await get_runtime_config("weekly_limit")
    try:
        return int(value)
    except Exception:
        return 2


async def get_slot_length_value() -> int:
    value = await get_runtime_config("slot_length")
    try:
        return int(value)
    except Exception:
        return 60


async def get_available_days_and_usage(db, user_id: int) -> tuple[list[int], int, int]:
    weekly_limit = await get_weekly_limit_value()
    booked_count = await count_user_bookings_this_week(db, user_id)

    week_dates = get_current_week_dates()
    monday = week_dates[0]
    sunday = week_dates[-1]

    booked_rows = await db.execute(
        select(Booking.date, Booking.hour)
        .where(Booking.date >= monday)
        .where(Booking.date <= sunday)
    )
    booked_set = set(booked_rows.all())

    working_hours = await get_working_hours_bulk(db, WEEKDAYS)
    available_days: list[int] = []

    for weekday_idx in range(7):
        target_date = get_current_week_date(weekday_idx)
        start_hour, end_hour = working_hours.get(WEEKDAYS[weekday_idx], (9, 22))

        has_free = False
        for hour in range(start_hour, end_hour):
            if not is_future_slot(target_date, hour):
                continue
            if await is_weekly_reserved_for_date(db, target_date, hour):
                continue
            if (target_date, hour) in booked_set:
                continue
            has_free = True
            break

        if has_free:
            available_days.append(weekday_idx)

    return available_days, booked_count, weekly_limit


async def get_free_hours_for_day(db, weekday_idx: int, target_date: date) -> list[int]:
    start_hour, end_hour = await get_working_hours(db, WEEKDAYS[weekday_idx])
    booked_rows = await db.execute(select(Booking.hour).where(Booking.date == target_date))
    booked_hours = set(booked_rows.scalars().all())
    free_hours: list[int] = []
    for hour in range(start_hour, end_hour):
        if not is_future_slot(target_date, hour):
            continue
        if await is_weekly_reserved_for_date(db, target_date, hour):
            continue
        if hour in booked_hours:
            continue
        free_hours.append(hour)

    return free_hours
