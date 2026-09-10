from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import TIMEZONE
from app.models.booking import Booking
from app.models.swap_offer import SwapOffer
from app.models.user import User
from app.services.time_service import now_tz


@dataclass(frozen=True)
class CreatedSwapOffer:
    status: Literal["created"]
    offer_id: int
    receiver_tg_user_id: int | None
    giver_display_name: str | None
    give_date: date
    give_hour: int
    want_date: date
    want_hour: int


@dataclass(frozen=True)
class MissingSwapBooking:
    status: Literal["missing_booking"]


CreateSwapOfferResult = CreatedSwapOffer | MissingSwapBooking


@dataclass(frozen=True)
class AcceptedSwapOffer:
    status: Literal["accepted"]
    giver_user_id: int
    receiver_user_id: int
    giver_tg_user_id: int | None
    giver_new_date: date
    giver_new_hour: int
    receiver_new_date: date
    receiver_new_hour: int


@dataclass(frozen=True)
class UnavailableSwapOffer:
    status: Literal["unavailable"]


AcceptSwapOfferResult = AcceptedSwapOffer | MissingSwapBooking | UnavailableSwapOffer


@dataclass(frozen=True)
class DeclinedSwapOffer:
    status: Literal["declined"]
    giver_user_id: int
    giver_tg_user_id: int | None
    give_date: date
    give_hour: int
    want_date: date
    want_hour: int


DeclineSwapOfferResult = DeclinedSwapOffer | UnavailableSwapOffer


async def create_swap_offer(
    db: AsyncSession,
    target_booking_id: int,
    my_booking_id: int,
    *,
    giver_user_id: int,
) -> CreateSwapOfferResult:
    target_b = await db.get(Booking, target_booking_id)
    my_b = await db.get(Booking, my_booking_id)

    if not target_b or not my_b:
        return MissingSwapBooking(status="missing_booking")
    if my_b.user_id != giver_user_id or target_b.user_id == giver_user_id:
        return MissingSwapBooking(status="missing_booking")
    if not _is_future_slot(my_b.date, my_b.hour) or not _is_future_slot(
        target_b.date,
        target_b.hour,
    ):
        return MissingSwapBooking(status="missing_booking")

    give_date = my_b.date
    give_hour = my_b.hour
    want_date = target_b.date
    want_hour = target_b.hour

    offer = SwapOffer(
        giver_user_id=my_b.user_id,
        receiver_user_id=target_b.user_id,
        give_date=give_date,
        give_hour=give_hour,
        want_date=want_date,
        want_hour=want_hour,
        status="pending",
    )
    db.add(offer)
    await db.commit()
    await db.refresh(offer)

    receiver_user = await db.get(User, target_b.user_id)
    giver_user = await db.get(User, my_b.user_id)
    giver_display_name = (
        (giver_user.full_name or giver_user.tg_username) if giver_user else None
    )

    return CreatedSwapOffer(
        status="created",
        offer_id=offer.id,
        receiver_tg_user_id=receiver_user.tg_user_id if receiver_user else None,
        giver_display_name=giver_display_name,
        give_date=give_date,
        give_hour=give_hour,
        want_date=want_date,
        want_hour=want_hour,
    )


async def accept_swap_offer(
    db: AsyncSession,
    offer_id: int,
    *,
    receiver_user_id: int,
) -> AcceptSwapOfferResult:
    offer = (
        await db.execute(
            select(SwapOffer).where(SwapOffer.id == offer_id).with_for_update()
        )
    ).scalar_one_or_none()
    if not offer or offer.status != "pending":
        return UnavailableSwapOffer(status="unavailable")
    if offer.receiver_user_id != receiver_user_id:
        return UnavailableSwapOffer(status="unavailable")

    giver_b = (
        await db.execute(
            select(Booking).where(
                Booking.user_id == offer.giver_user_id,
                Booking.date == offer.give_date,
                Booking.hour == offer.give_hour,
            ).with_for_update()
        )
    ).scalar_one_or_none()

    receiver_b = (
        await db.execute(
            select(Booking).where(
                Booking.user_id == offer.receiver_user_id,
                Booking.date == offer.want_date,
                Booking.hour == offer.want_hour,
            ).with_for_update()
        )
    ).scalar_one_or_none()

    if not giver_b or not receiver_b:
        offer.status = "cancelled"
        await db.commit()
        return MissingSwapBooking(status="missing_booking")
    if not _is_future_slot(giver_b.date, giver_b.hour) or not _is_future_slot(
        receiver_b.date,
        receiver_b.hour,
    ):
        offer.status = "cancelled"
        await db.commit()
        return MissingSwapBooking(status="missing_booking")

    giver_new_date = receiver_b.date
    giver_new_hour = receiver_b.hour
    receiver_new_date = giver_b.date
    receiver_new_hour = giver_b.hour
    giver_uid = giver_b.user_id
    receiver_uid = receiver_b.user_id

    giver_b.user_id = receiver_uid
    receiver_b.user_id = giver_uid
    offer.status = "accepted"
    await db.execute(
        update(SwapOffer)
        .where(SwapOffer.id != offer_id)
        .where(SwapOffer.status == "pending")
        .where(
            or_(
                and_(
                    SwapOffer.give_date == offer.give_date,
                    SwapOffer.give_hour == offer.give_hour,
                ),
                and_(
                    SwapOffer.want_date == offer.give_date,
                    SwapOffer.want_hour == offer.give_hour,
                ),
                and_(
                    SwapOffer.give_date == offer.want_date,
                    SwapOffer.give_hour == offer.want_hour,
                ),
                and_(
                    SwapOffer.want_date == offer.want_date,
                    SwapOffer.want_hour == offer.want_hour,
                ),
            )
        )
        .values(status="cancelled")
    )
    await db.commit()

    giver_user = await db.get(User, giver_uid)

    return AcceptedSwapOffer(
        status="accepted",
        giver_user_id=giver_uid,
        receiver_user_id=receiver_uid,
        giver_tg_user_id=giver_user.tg_user_id if giver_user else None,
        giver_new_date=giver_new_date,
        giver_new_hour=giver_new_hour,
        receiver_new_date=receiver_new_date,
        receiver_new_hour=receiver_new_hour,
    )


def _is_future_slot(slot_date: date, slot_hour: int) -> bool:
    slot_dt = datetime.combine(slot_date, time(slot_hour)).replace(
        tzinfo=ZoneInfo(TIMEZONE)
    )
    return slot_dt > now_tz()


async def decline_swap_offer(
    db: AsyncSession,
    offer_id: int,
    *,
    receiver_user_id: int,
    after_commit: Callable[[DeclinedSwapOffer], Awaitable[None]] | None = None,
) -> DeclineSwapOfferResult:
    offer = (
        await db.execute(
            select(SwapOffer).where(SwapOffer.id == offer_id).with_for_update()
        )
    ).scalar_one_or_none()
    if not offer or offer.status != "pending":
        return UnavailableSwapOffer(status="unavailable")
    if offer.receiver_user_id != receiver_user_id:
        return UnavailableSwapOffer(status="unavailable")

    offer.status = "declined"
    give_date = offer.give_date
    give_hour = offer.give_hour
    want_date = offer.want_date
    want_hour = offer.want_hour
    giver_user_id = offer.giver_user_id

    giver_user = await db.get(User, giver_user_id)

    result = DeclinedSwapOffer(
        status="declined",
        giver_user_id=giver_user_id,
        giver_tg_user_id=giver_user.tg_user_id if giver_user else None,
        give_date=give_date,
        give_hour=give_hour,
        want_date=want_date,
        want_hour=want_hour,
    )

    await db.commit()

    if after_commit is not None:
        await after_commit(result)

    return result
