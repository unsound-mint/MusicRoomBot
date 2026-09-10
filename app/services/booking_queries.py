from datetime import date

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.weekly_slot import WeeklySlot
from app.services.booking_limits import start_and_end_of_week
from app.services.club_service import is_weekly_reserved_for_date
from app.services.date_service import get_current_week_dates


async def count_user_bookings_this_week(db: AsyncSession, user_id: int) -> int:
    week_dates = get_current_week_dates()
    monday = week_dates[0]
    _, next_monday = start_and_end_of_week(monday)

    q = await db.execute(
        select(func.count(Booking.id))
        .where(Booking.user_id == user_id)
        .where(Booking.date >= monday)
        .where(Booking.date < next_monday)
    )
    return int(q.scalar() or 0)


async def get_bookings_for_day(
    db: AsyncSession,
    target_date: date,
) -> list[Booking]:
    q = await db.execute(select(Booking).where(Booking.date == target_date))
    return list(q.scalars().all())


async def get_user_bookings(db: AsyncSession, user_id: int) -> list[Booking]:
    week_dates = get_current_week_dates()
    monday = week_dates[0]
    sunday = week_dates[-1]

    rows = await db.execute(
        select(Booking)
        .where(Booking.user_id == user_id)
        .where(Booking.date >= monday)
        .where(Booking.date <= sunday)
        .order_by(Booking.date, Booking.hour)
    )
    return list(rows.scalars().all())


async def is_slot_free(db: AsyncSession, target_date: date, hour: int) -> bool:
    q = await db.execute(
        select(Booking.id).where(
            and_(Booking.date == target_date, Booking.hour == hour)
        )
    )
    return q.scalar_one_or_none() is None


async def is_weekly_reserved(db: AsyncSession, weekday: int, hour: int) -> bool:
    q = await db.execute(
        select(WeeklySlot.id).where(
            and_(WeeklySlot.weekday == weekday, WeeklySlot.hour == hour)
        )
    )
    return q.scalar_one_or_none() is not None


async def is_weekly_reserved_on_date(
    db: AsyncSession,
    target_date: date,
    hour: int,
) -> bool:
    if not await is_weekly_reserved(db, target_date.weekday(), hour):
        return False

    return await is_weekly_reserved_for_date(db, target_date, hour)
