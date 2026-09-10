# app/services/time_service.py
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import TIMEZONE

TZ = ZoneInfo(TIMEZONE)


def now_tz() -> datetime:
    """Return timezone-aware datetime in bot's configured timezone."""
    return datetime.now(TZ)


def today_tz() -> date:
    """Return today's date in configured TZ."""
    return now_tz().date()
