# app/services/calendar_service.py
import urllib.parse
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import TIMEZONE


def get_google_calendar_link(
    booking_date: date,
    booking_hour: int,
    slot_length_minutes: int = 60,
) -> str:
    """Build a Google Calendar template URL for a booking."""
    local_tz = ZoneInfo(TIMEZONE)
    start_dt = datetime.combine(booking_date, time(booking_hour, 0)).replace(
        tzinfo=local_tz
    )
    end_dt = start_dt + timedelta(minutes=slot_length_minutes)

    start_utc = start_dt.astimezone(ZoneInfo("UTC"))
    end_utc = end_dt.astimezone(ZoneInfo("UTC"))

    fmt = "%Y%m%dT%H%M%SZ"
    dates = f"{start_utc.strftime(fmt)}/{end_utc.strftime(fmt)}"

    params = {
        "action": "TEMPLATE",
        "text": "Music Room Practice 🎸",
        "dates": dates,
        "details": (
            "Don't forget your instruments 🎸\n\nBooking managed by Music Room Bot."
        ),
        "location": "Music Room",
    }

    base_url = "https://www.google.com/calendar/render"
    return f"{base_url}?{urllib.parse.urlencode(params)}"
