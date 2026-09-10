from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import TIMEZONE
from app.models.booking import Booking
from app.models.club import Club, ClubLeader, ClubSlotCancellation
from app.models.user import User
from app.models.weekly_slot import WeeklySlot
from app.services.time_service import now_tz


@dataclass(frozen=True)
class ClubSlotOccurrence:
    slot: WeeklySlot
    target_date: date
    club_name: str
    is_cancelled: bool
    has_booking: bool


def normalize_club_name(name: str) -> str:
    return " ".join(name.strip().split())


def normalize_username(username: str) -> str:
    return username.strip().removeprefix("@").lower()


async def list_clubs(db: AsyncSession) -> list[Club]:
    return list(
        (
            await db.execute(select(Club).order_by(func.lower(Club.name), Club.id))
        ).scalars()
    )


async def create_club(db: AsyncSession, name: str) -> tuple[str, Club | None]:
    club_name = normalize_club_name(name)
    if not club_name:
        return ("invalid", None)

    club = Club(name=club_name)
    db.add(club)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = (
            await db.execute(
                select(Club).where(func.lower(Club.name) == club_name.lower())
            )
        ).scalar_one_or_none()
        return ("exists", existing)
    await db.refresh(club)
    return ("created", club)


async def get_club(db: AsyncSession, club_id: int) -> Club | None:
    return await db.get(Club, club_id)


async def get_user_clubs(db: AsyncSession, user_id: int) -> list[Club]:
    return list(
        (
            await db.execute(
                select(Club)
                .join(ClubLeader, ClubLeader.club_id == Club.id)
                .where(ClubLeader.user_id == user_id)
                .order_by(func.lower(Club.name), Club.id)
            )
        ).scalars()
    )


async def user_has_clubs(db: AsyncSession, tg_user_id: int) -> bool:
    row = (
        await db.execute(
            select(ClubLeader.id)
            .join(User, User.id == ClubLeader.user_id)
            .where(User.tg_user_id == tg_user_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    return row is not None


async def is_club_leader(db: AsyncSession, club_id: int, user_id: int) -> bool:
    row = (
        await db.execute(
            select(ClubLeader.id).where(
                ClubLeader.club_id == club_id,
                ClubLeader.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    return row is not None


async def add_leader_by_username(
    db: AsyncSession,
    club_id: int,
    username: str,
) -> tuple[str, User | None]:
    normalized = normalize_username(username)
    if not normalized:
        return ("invalid_username", None)

    user = (
        await db.execute(
            select(User).where(func.lower(User.tg_username) == normalized)
        )
    ).scalar_one_or_none()
    if user is None:
        return ("user_not_found", None)

    leader = ClubLeader(club_id=club_id, user_id=user.id)
    db.add(leader)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return ("already_leader", user)
    return ("added", user)


async def get_club_leaders(db: AsyncSession, club_id: int) -> list[User]:
    return list(
        (
            await db.execute(
                select(User)
                .join(ClubLeader, ClubLeader.user_id == User.id)
                .where(ClubLeader.club_id == club_id)
                .order_by(
                    func.lower(func.coalesce(User.full_name, "")),
                    func.lower(func.coalesce(User.tg_username, "")),
                    User.id,
                )
            )
        ).scalars()
    )


async def assign_weekly_slot_to_club(
    db: AsyncSession,
    *,
    club_id: int,
    weekday: int,
    hour: int,
) -> tuple[str, WeeklySlot | None]:
    club = await db.get(Club, club_id)
    if club is None:
        return ("club_not_found", None)

    slot = (
        await db.execute(
            select(WeeklySlot).where(
                WeeklySlot.weekday == weekday,
                WeeklySlot.hour == hour,
            )
        )
    ).scalar_one_or_none()
    if slot is None:
        slot = WeeklySlot(weekday=weekday, hour=hour, group_name=club.name, club_id=club.id)
        db.add(slot)
    else:
        slot.club_id = club.id
        slot.group_name = club.name

    await db.commit()
    await db.refresh(slot)
    return ("assigned", slot)


async def set_admin_weekly_slot(
    db: AsyncSession,
    *,
    weekday: int,
    hour: int,
    group_name: str,
) -> WeeklySlot:
    slot = (
        await db.execute(
            select(WeeklySlot).where(
                WeeklySlot.weekday == weekday,
                WeeklySlot.hour == hour,
            )
        )
    ).scalar_one_or_none()
    if slot is None:
        slot = WeeklySlot(weekday=weekday, hour=hour, group_name=group_name)
        db.add(slot)
    else:
        slot.group_name = group_name

    await db.commit()
    return slot


async def delete_admin_weekly_slot(
    db: AsyncSession,
    *,
    weekly_slot_id: int,
) -> tuple[str, WeeklySlot | None]:
    slot = await db.get(WeeklySlot, weekly_slot_id)
    if slot is None:
        return ("not_found", None)
    if slot.weekday is None:
        return ("invalid", slot)

    await db.delete(slot)
    await db.commit()
    return ("deleted", slot)


async def get_club_slots(db: AsyncSession, club_id: int) -> list[WeeklySlot]:
    return list(
        (
            await db.execute(
                select(WeeklySlot)
                .where(WeeklySlot.club_id == club_id)
                .order_by(WeeklySlot.weekday, WeeklySlot.hour)
            )
        ).scalars()
    )


async def is_weekly_slot_cancelled(
    db: AsyncSession,
    weekly_slot_id: int,
    target_date: date,
) -> bool:
    row = (
        await db.execute(
            select(ClubSlotCancellation.id).where(
                ClubSlotCancellation.weekly_slot_id == weekly_slot_id,
                ClubSlotCancellation.date == target_date,
            )
        )
    ).scalar_one_or_none()
    return row is not None


async def is_weekly_reserved_for_date(
    db: AsyncSession,
    target_date: date,
    hour: int,
) -> bool:
    slot = (
        await db.execute(
            select(WeeklySlot).where(
                WeeklySlot.weekday == target_date.weekday(),
                WeeklySlot.hour == hour,
            )
        )
    ).scalar_one_or_none()
    if slot is None:
        return False
    return not await is_weekly_slot_cancelled(db, slot.id, target_date)


async def get_club_slot_occurrences(
    db: AsyncSession,
    club_id: int,
    week_dates: Sequence[date],
) -> list[ClubSlotOccurrence]:
    club = await db.get(Club, club_id)
    if club is None:
        return []

    slots = await get_club_slots(db, club_id)
    booking_rows = (
        await db.execute(
            select(Booking.date, Booking.hour).where(Booking.date.in_(week_dates))
        )
    ).all()
    booking_set = set(booking_rows)

    cancellation_rows = (
        await db.execute(
            select(ClubSlotCancellation.weekly_slot_id, ClubSlotCancellation.date)
            .where(ClubSlotCancellation.club_id == club_id)
            .where(ClubSlotCancellation.date.in_(week_dates))
        )
    ).all()
    cancellation_set = set(cancellation_rows)

    dates_by_weekday = {week_date.weekday(): week_date for week_date in week_dates}
    occurrences: list[ClubSlotOccurrence] = []
    for slot in slots:
        target_date = dates_by_weekday.get(slot.weekday)
        if target_date is None:
            continue
        occurrences.append(
            ClubSlotOccurrence(
                slot=slot,
                target_date=target_date,
                club_name=club.name,
                is_cancelled=(slot.id, target_date) in cancellation_set,
                has_booking=(target_date, slot.hour) in booking_set,
            )
        )
    return occurrences


async def cancel_club_slot_occurrence(
    db: AsyncSession,
    *,
    club_id: int,
    weekly_slot_id: int,
    target_date: date,
    cancelled_by_user_id: int,
    require_leader: bool = True,
) -> str:
    slot = await db.get(WeeklySlot, weekly_slot_id)
    if slot is None:
        return "slot_not_found"
    if require_leader and slot.club_id != club_id:
        return "slot_not_found"

    if slot.weekday != target_date.weekday():
        return "invalid_date"

    if require_leader and not await is_club_leader(db, club_id, cancelled_by_user_id):
        return "not_allowed"

    booking_dt = datetime.combine(target_date, time(slot.hour)).replace(
        tzinfo=ZoneInfo(TIMEZONE)
    )
    if booking_dt <= now_tz():
        return "past_slot"

    existing_booking = (
        await db.execute(
            select(Booking.id).where(
                Booking.date == target_date,
                Booking.hour == slot.hour,
            )
        )
    ).scalar_one_or_none()
    if existing_booking is not None:
        return "booking_exists"

    db.add(
        ClubSlotCancellation(
            club_id=slot.club_id,
            weekly_slot_id=weekly_slot_id,
            date=target_date,
            cancelled_by_user_id=cancelled_by_user_id,
        )
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return "already_cancelled"
    return "cancelled"
