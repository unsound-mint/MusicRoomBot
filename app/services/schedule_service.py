from collections.abc import Mapping, Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.constants.dates import WEEKDAYS
from app.bot.markdown import markdown_display
from app.models.booking import Booking
from app.models.club import Club, ClubSlotCancellation
from app.models.user import User
from app.models.weekly_slot import WeeklySlot
from app.services.date_service import get_current_week_dates, get_hours_list

WeeklySlotMap = Mapping[tuple[int, int], str]
BookingOwnerMap = Mapping[tuple[date, int], str]
HoursByWeekday = Mapping[int, Sequence[int]]


async def build_schedule_text(
    db: AsyncSession,
    *,
    week_dates: Sequence[date] | None = None,
) -> str:
    dates = list(get_current_week_dates() if week_dates is None else week_dates)
    weekly_map = await get_weekly_slot_map(db, dates)
    booking_map = await get_booking_owner_map(db, dates)
    hours_by_weekday = await get_hours_by_weekday(db, dates)

    return render_schedule_text(
        dates,
        weekly_map=weekly_map,
        booking_map=booking_map,
        hours_by_weekday=hours_by_weekday,
    )


async def get_weekly_slot_map(
    db: AsyncSession,
    week_dates: Sequence[date] | None = None,
) -> dict[tuple[int, int], str]:
    rows = (
        await db.execute(
            select(WeeklySlot, Club.name)
            .outerjoin(Club, Club.id == WeeklySlot.club_id)
            .order_by(WeeklySlot.weekday, WeeklySlot.hour)
        )
    ).all()

    cancelled: set[tuple[int, date]] = set()
    if week_dates:
        cancellation_rows = (
            await db.execute(
                select(ClubSlotCancellation.weekly_slot_id, ClubSlotCancellation.date)
                .where(ClubSlotCancellation.date.in_(week_dates))
            )
        ).all()
        cancelled = {
            (weekly_slot_id, cancellation_date)
            for weekly_slot_id, cancellation_date in cancellation_rows
        }
        date_by_weekday = {week_date.weekday(): week_date for week_date in week_dates}
    else:
        date_by_weekday = {}

    weekly_map: dict[tuple[int, int], str] = {}
    for slot, club_name in rows:
        target_date = date_by_weekday.get(slot.weekday)
        if target_date is not None and (slot.id, target_date) in cancelled:
            continue
        weekly_map[(slot.weekday, slot.hour)] = club_name or slot.group_name
    return weekly_map


async def get_booking_owner_map(
    db: AsyncSession,
    week_dates: Sequence[date],
) -> dict[tuple[date, int], str]:
    if not week_dates:
        return {}

    rows = (
        await db.execute(
            select(Booking.date, Booking.hour, User.full_name, User.tg_username)
            .join(User, Booking.user_id == User.id)
            .where(Booking.date >= week_dates[0])
            .where(Booking.date <= week_dates[-1])
        )
    ).all()

    booking_map: dict[tuple[date, int], str] = {}
    for booking_date, booking_hour, full_name, tg_username in rows:
        booking_map[(booking_date, booking_hour)] = full_name or tg_username or "-"
    return booking_map


async def get_hours_by_weekday(
    db: AsyncSession,
    week_dates: Sequence[date],
) -> dict[int, list[int]]:
    hours_by_weekday: dict[int, list[int]] = {}
    for day_date in week_dates:
        weekday = day_date.weekday()
        if weekday not in hours_by_weekday:
            hours_by_weekday[weekday] = await get_hours_list(db, weekday)
    return hours_by_weekday


def render_schedule_text(
    week_dates: Sequence[date],
    *,
    weekly_map: WeeklySlotMap,
    booking_map: BookingOwnerMap,
    hours_by_weekday: HoursByWeekday,
) -> str:
    lines = ["", ""]

    for day_date in week_dates:
        weekday_idx = day_date.weekday()
        weekday = WEEKDAYS[weekday_idx]

        lines.append(f"📅 *{weekday}*")
        lines.append("════════════════════")

        any_slots = False

        for hour in hours_by_weekday.get(weekday_idx, ()):
            hour_str = f"`{hour:02d}:00`"
            weekly_owner = weekly_map.get((weekday_idx, hour))
            booking_owner = booking_map.get((day_date, hour))

            if weekly_owner is not None:
                lines.append(f"{hour_str}  {markdown_display(weekly_owner)}")
                any_slots = True
            elif booking_owner is not None:
                lines.append(f"{hour_str}  {markdown_display(booking_owner)}")
                any_slots = True

        if not any_slots:
            lines.append("_No sessions today._")

        lines.append("")

    return "\n".join(lines)
