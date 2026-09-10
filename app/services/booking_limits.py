from __future__ import annotations

import hashlib
from datetime import date, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.services.config_runtime import get_runtime_config

_BOOKING_LIMIT_LOCK_NAMESPACE = "musicroom:booking-limit"


async def weekly_limit_value() -> int:
    weekly_limit = await get_runtime_config("weekly_limit")
    if weekly_limit is None:
        return 2
    try:
        return int(str(weekly_limit).strip())
    except Exception:
        return 2


def start_and_end_of_week(target_date: date) -> tuple[date, date]:
    start_week = target_date - timedelta(days=target_date.weekday())
    end_week = start_week + timedelta(days=7)
    return start_week, end_week


def user_week_lock_key(user_id: int, week_start: date) -> int:
    raw = f"{_BOOKING_LIMIT_LOCK_NAMESPACE}:{user_id}:{week_start.isoformat()}"
    digest = hashlib.blake2b(raw.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=False) & ((1 << 63) - 1)


async def lock_user_week_booking_limit(
    db: AsyncSession,
    *,
    user_id: int,
    week_start: date,
) -> None:
    """
    Serialize per-user weekly booking limit checks across bot processes.

    PostgreSQL releases transaction-scoped advisory locks automatically on commit
    or rollback, which matches the count-then-insert/update operations here.
    """
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)").bindparams(
            lock_key=user_week_lock_key(user_id, week_start)
        )
    )


async def count_user_bookings_in_week(
    db: AsyncSession,
    *,
    user_id: int,
    start_week: date,
    end_week: date,
) -> int:
    q = await db.execute(
        select(func.count(Booking.id))
        .where(Booking.user_id == user_id)
        .where(Booking.date >= start_week)
        .where(Booking.date < end_week)
    )
    return int(q.scalar() or 0)
