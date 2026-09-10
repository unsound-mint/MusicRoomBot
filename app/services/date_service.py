# app/services/date_service.py
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.constants.dates import WEEKDAYS
from app.services.config_service import get_working_hours
from app.services.time_service import now_tz, today_tz


def get_current_week_date(weekday_idx: int) -> date:
    """
    Returns the date for the given weekday of the *bookable* week.
    Switch to next week on Sunday at 22:00.
    """
    today = today_tz()
    now = now_tz()

    # Determine base Monday
    monday = today - timedelta(days=today.weekday())

    # If it's Sunday AND time >= 22:00 → shift booking week to next week
    if today.weekday() == 6 and now.hour >= 22:
        monday = monday + timedelta(days=7)

    return monday + timedelta(days=weekday_idx)


def is_future_slot(target_date: date, hour: int) -> bool:
    """
    Checks whether a given day/hour slot is in the future.
    """
    now = now_tz()
    if target_date > now.date():
        return True
    return target_date == now.date() and hour > now.hour


def get_current_week_dates() -> list[date]:
    """
    Returns Monday–Sunday for the *bookable* week.
    Switch to next week on Sunday 22:00.
    """
    today = today_tz()
    now = now_tz()

    monday = today - timedelta(days=today.weekday())

    if today.weekday() == 6 and now.hour >= 22:
        monday = monday + timedelta(days=7)

    return [monday + timedelta(days=i) for i in range(7)]


async def get_hours_list(db: AsyncSession, weekday_idx: int) -> list[int]:
    weekday = WEEKDAYS[weekday_idx]
    start, end = await get_working_hours(db, weekday)
    return list(range(start, end))
