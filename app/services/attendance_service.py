# app/services/attendance_service.py
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import TIMEZONE
from app.models.booking import Booking
from app.services.config_runtime import get_runtime_config
from app.services.time_service import now_tz


async def record_attendance(
    db: AsyncSession,
    booking_id: int,
    user_id: int,
    lat: float,
    lon: float,
    distance: float,
    *,
    commit: bool = True,
    verified: bool | None = None,
) -> Booking:
    """
    Store attendance state on the booking and set verified based on geo_radius.

    commit=True keeps backward compatibility with your current code.
    In chain operations, you can call commit=False and commit once outside.
    """
    booking = (
        await db.execute(
            select(Booking).where(Booking.id == booking_id, Booking.user_id == user_id)
        )
    ).scalar_one()

    if verified is None:
        geo_radius = await get_runtime_config("geo_radius")
        try:
            verified = float(distance) <= float(geo_radius)
        except Exception:
            verified = float(distance) <= 50.0

    booking.attendance_verified = verified
    booking.attendance_lat = lat
    booking.attendance_lon = lon
    booking.attendance_recorded_at = now_tz()
    booking.absence_reported = True
    booking.location_prompted = True

    if commit:
        await db.commit()
        await db.refresh(booking)
    else:
        await db.flush()

    return booking


async def get_current_booking(db: AsyncSession, user_id: int) -> Booking | None:
    """
    Returns today's booking that contains current time:
    booking.start <= now < booking.start + slot_length minutes.
    """
    now = now_tz()

    # slot_length minutes
    slot_length = await get_runtime_config("slot_length")
    try:
        slot_length = int(slot_length)
    except Exception:
        slot_length = 60

    # fetch today's bookings for user
    q = await db.execute(
        select(Booking)
        .where(Booking.user_id == user_id)
        .where(Booking.date == now.date())
    )
    rows = q.scalars().all()

    active_bookings: list[Booking] = []
    for b in rows:
        booking_dt = datetime.combine(b.date, time(b.hour, 0)).replace(
            tzinfo=ZoneInfo(TIMEZONE)
        )
        if booking_dt <= now < booking_dt + timedelta(minutes=slot_length):
            active_bookings.append(b)

    if active_bookings:
        return max(active_bookings, key=lambda booking: booking.hour)

    return None


async def record_absence(
    db: AsyncSession,
    booking_id: int,
    user_id: int,
    *,
    commit: bool = True,
) -> Booking:
    """
    Record an absence on the booking.
    """
    booking = (
        await db.execute(
            select(Booking).where(Booking.id == booking_id, Booking.user_id == user_id)
        )
    ).scalar_one()
    booking.attendance_verified = False
    booking.attendance_lat = None
    booking.attendance_lon = None
    booking.attendance_recorded_at = now_tz()
    booking.absence_reported = True
    booking.location_prompted = True

    if commit:
        await db.commit()
        await db.refresh(booking)
    else:
        await db.flush()

    return booking
