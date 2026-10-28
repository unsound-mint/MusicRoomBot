# app/services/time_service.py
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.core.config import TIMEZONE

TZ = ZoneInfo(TIMEZONE)


def now_tz() -> datetime:
    """Return timezone-aware datetime in bot's configured timezone."""
    return datetime.now(TZ)


def today_tz() -> date:
    """Return today's date in configured TZ."""
    return now_tz().date()


def slot_start(slot_date: date, hour: int) -> datetime:
    """Return the timezone-aware start of the slot at `hour` on `slot_date`."""
    return datetime.combine(slot_date, time(hour)).replace(tzinfo=TZ)
