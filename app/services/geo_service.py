# app/services/geo_service.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, SupportsFloat, SupportsIndex
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.constants.dates import WEEKDAYS
from app.bot.keyboards.location_kb import request_location_kb
from app.core.config import TIMEZONE
from app.core.database import AsyncSessionLocal
from app.models.booking import Booking
from app.models.user import User
from app.services.attendance_service import record_attendance
from app.services.config_runtime import get_runtime_config
from app.services.time_service import now_tz
from app.services.warning_service import add_warning

if TYPE_CHECKING:
    from aiogram import Bot

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeoConfig:
    center_lat: float
    center_lon: float
    radius: float


def normalize_geo_config(
    center_lat: str | bytes | SupportsFloat | SupportsIndex | None,
    center_lon: str | bytes | SupportsFloat | SupportsIndex | None,
    radius: str | bytes | SupportsFloat | SupportsIndex | None,
) -> GeoConfig:
    try:
        parsed_lat = _to_float(center_lat)
        parsed_lon = _to_float(center_lon)
    except (TypeError, ValueError):
        parsed_lat = 0.0
        parsed_lon = 0.0

    try:
        parsed_radius = _to_float(radius)
    except (TypeError, ValueError):
        parsed_radius = 50.0

    return GeoConfig(
        center_lat=parsed_lat,
        center_lon=parsed_lon,
        radius=parsed_radius,
    )


def _to_float(value: str | bytes | SupportsFloat | SupportsIndex | None) -> float:
    if value is None:
        raise TypeError("missing numeric value")
    return float(value)


async def get_geo_config() -> GeoConfig:
    return normalize_geo_config(
        await get_runtime_config("geo_center_lat"),
        await get_runtime_config("geo_center_lon"),
        await get_runtime_config("geo_radius"),
    )


async def mark_attendance_chain_verified(
    db: AsyncSession,
    user: User,
    booking: Booking,
    lat: float,
    lon: float,
    distance: float,
    *,
    commit: bool = True,
) -> None:
    """
    Record attendance for this booking and all consecutive unprocessed bookings.
    """
    if not booking.absence_reported:
        await record_attendance(
            db,
            booking.id,
            user.id,
            lat,
            lon,
            distance,
            commit=False,
            verified=True,
        )

    next_hour = booking.hour + 1
    while True:
        result = await db.execute(
            select(Booking).where(
                Booking.user_id == user.id,
                Booking.date == booking.date,
                Booking.hour == next_hour,
                Booking.absence_reported == False,  # noqa: E712
            )
        )
        next_booking = result.scalar_one_or_none()
        if not next_booking:
            break

        await record_attendance(
            db,
            next_booking.id,
            user.id,
            lat,
            lon,
            distance,
            commit=False,
            verified=True,
        )
        next_hour += 1

    if commit:
        await db.commit()


async def is_first_in_chain(
    db: AsyncSession, user_id: int, b_date: date, hour: int
) -> bool:
    prev_hour = hour - 1
    if prev_hour < 0:
        return True

    q = await db.execute(
        select(Booking.id).where(
            Booking.user_id == user_id,
            Booking.date == b_date,
            Booking.hour == prev_hour,
        )
    )
    return q.scalar_one_or_none() is None


async def get_chain_booking_ids(
    db: AsyncSession, user_id: int, b_date: date, start_hour: int
) -> list[int]:
    ids: list[int] = []
    h = start_hour

    while True:
        q = await db.execute(
            select(Booking.id).where(
                Booking.user_id == user_id,
                Booking.date == b_date,
                Booking.hour == h,
            )
        )
        booking_id = q.scalar_one_or_none()
        if not booking_id:
            break
        ids.append(booking_id)
        h += 1

    return ids


def _display_name(full_name: str | None, tg_username: str | None, user_id: int) -> str:
    if full_name:
        return full_name
    if tg_username:
        return f"@{tg_username}"
    return f"id={user_id}"


async def process_geo_checks(bot: Bot) -> None:
    """
    Scheduler job every minute.

    Guarantees:
      1) At exact HH:00 we prompt ONLY the FIRST slot in each consecutive chain.
         Prompt uses a reply keyboard location request button.
      2) After late_minutes, if still not verified, we mark ABSENT for the whole chain,
         add ONE warning, and notify the user.
      3) The location prompt is resolved even if the hour already changed
         (we process expirations for both current and previous hour slot).
    """
    now = now_tz().replace(second=0, microsecond=0)

    late_minutes_raw = await get_runtime_config("late_minutes")
    try:
        late_minutes = int(late_minutes_raw)
    except Exception:
        late_minutes = 10

    # ------------------------------------------------------------
    # Which slot-hours do we need to process for expiration cleanup?
    # - current hour (today)
    # - previous hour (might be previous day if now.hour == 0)
    #
    # This ensures: once a window expires, we still clean it up even
    # after hour has rolled over.
    # ------------------------------------------------------------
    today = now.date()
    cur_hour = now.hour

    prev_dt = now - timedelta(hours=1)
    prev_date = prev_dt.date()
    prev_hour = prev_dt.hour

    hours_for_expiry: list[tuple[date, int]] = [(today, cur_hour)]
    if (prev_date, prev_hour) != (today, cur_hour):
        hours_for_expiry.append((prev_date, prev_hour))

    # ------------------------------------------------------------
    # PHASE A: PROMPT (only at minute == 0)
    # ------------------------------------------------------------
    if now.minute == 0:
        rows_to_prompt: list[tuple[int, int, int, str]] = []
        # (booking_id, user_id, tg_user_id, display)

        async with AsyncSessionLocal() as db:
            q = (
                select(
                    Booking.id,
                    Booking.user_id,
                    User.tg_user_id,
                    User.full_name,
                    User.tg_username,
                )
                .join(User, User.id == Booking.user_id)
                .where(
                    Booking.date == today,
                    Booking.hour == cur_hour,
                    Booking.location_prompted == False,  # noqa: E712
                    Booking.absence_reported == False,  # noqa: E712
                )
            )
            rows = (await db.execute(q)).all()

            # Only prompt the FIRST slot of a consecutive chain
            for booking_id, user_id, tg_user_id, full_name, tg_username in rows:
                if not tg_user_id:
                    continue
                if await is_first_in_chain(db, user_id, today, cur_hour):
                    rows_to_prompt.append(
                        (
                            booking_id,
                            user_id,
                            tg_user_id,
                            _display_name(full_name, tg_username, user_id),
                        )
                    )

        if rows_to_prompt:
            prompted_booking_ids: list[int] = []

            for booking_id, _user_id, tg_user_id, _display in rows_to_prompt:
                try:
                    await bot.send_message(
                        tg_user_id,
                        "Check-in window is open now.\n"
                        f"Deadline: {(booking_start := datetime.combine(today, time(cur_hour)).replace(tzinfo=ZoneInfo(TIMEZONE)) + timedelta(minutes=late_minutes)).strftime('%H:%M')}",
                        reply_markup=request_location_kb(),
                    )
                    prompted_booking_ids.append(booking_id)
                except Exception:
                    log.exception(
                        "Failed to send location request",
                        extra={"booking_id": booking_id, "tg_user_id": tg_user_id},
                    )

            # Flip location_prompted=True in one DB transaction
            if prompted_booking_ids:
                async with AsyncSessionLocal() as db:
                    await db.execute(
                        update(Booking)
                        .where(Booking.id.in_(prompted_booking_ids))
                        .values(location_prompted=True)
                    )
                    await db.commit()

    # ------------------------------------------------------------
    # PHASE B: EXPIRATION / ABSENCE (process current + previous hour)
    # ------------------------------------------------------------
    for b_date, b_hour in hours_for_expiry:
        booking_start = datetime.combine(b_date, time(b_hour)).replace(
            tzinfo=ZoneInfo(TIMEZONE)
        )
        deadline = booking_start + timedelta(minutes=late_minutes)

        # If window not expired yet, skip
        if now < deadline:
            continue

        # Collect candidates: prompted but not yet marked absent
        async with AsyncSessionLocal() as db:
            q = (
                select(
                    Booking.id,
                    Booking.user_id,
                    User.tg_user_id,
                    User.full_name,
                    User.tg_username,
                )
                .join(User, User.id == Booking.user_id)
                .where(
                    Booking.date == b_date,
                    Booking.hour == b_hour,
                    Booking.location_prompted == True,  # noqa: E712
                    Booking.absence_reported == False,  # noqa: E712
                    Booking.attendance_verified == False,  # noqa: E712
                )
            )
            candidates = (await db.execute(q)).all()

            # Only mark absence starting from FIRST slot of chain
            # Also, we must do chain operations and warning inside this session.
            from app.services.attendance_service import record_absence

            notify_rows: list[tuple[int, int]] = []
            # (user_id, tg_user_id)

            for (
                _booking_id,
                user_id,
                tg_user_id,
                _full_name,
                _tg_username,
            ) in candidates:
                if not tg_user_id:
                    continue

                if not await is_first_in_chain(db, user_id, b_date, b_hour):
                    # not first slot -> it will be handled via chain of the first slot
                    continue

                chain_ids = await get_chain_booking_ids(db, user_id, b_date, b_hour)
                if not chain_ids:
                    continue

                # Record absences for whole chain (flush only), then update flags once
                for bid in chain_ids:
                    try:
                        await record_absence(db, bid, user_id, commit=False)
                    except Exception:
                        log.exception(
                            "Failed to record absence",
                            extra={"booking_id": bid, "user_id": user_id},
                        )

                await db.execute(
                    update(Booking)
                    .where(Booking.id.in_(chain_ids))
                    .values(absence_reported=True, location_prompted=True)
                )

                await db.commit()

                # One warning per chain (best-effort)
                try:
                    await add_warning(
                        db=db,
                        bot=bot,
                        user_id=user_id,
                        reason=f"Absent for {WEEKDAYS[b_date.weekday()]} at {b_hour:02d}:00",
                    )
                except Exception:
                    log.exception(
                        "Failed to add absence warning",
                        extra={"user_id": user_id, "date": b_date.isoformat()},
                    )

                notify_rows.append((user_id, tg_user_id))

        # Notify users + REMOVE location button (outside DB)
        if notify_rows:
            weekday = WEEKDAYS[b_date.weekday()]

            for _user_id, tg_user_id in notify_rows:
                try:
                    await bot.send_message(
                        tg_user_id,
                        "⏱ *Check-in Expired*\n\n"
                        f"⏰ *Slot:* {weekday}, {b_hour:02d}:00\n"
                        "⚠️ *Status:* Absent\n\n"
                        "Admins can help if you believe this is a mistake.",
                        parse_mode="Markdown",
                    )
                except Exception:
                    log.exception(
                        "Failed to send check-in expired notification",
                        extra={
                            "tg_user_id": tg_user_id,
                            "date": b_date.isoformat(),
                            "hour": b_hour,
                        },
                    )
