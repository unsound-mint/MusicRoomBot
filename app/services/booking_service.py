# app/services/booking_service.py
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, delete, func, insert, select
from sqlalchemy.exc import IntegrityError

from app.bot.constants.dates import WEEKDAYS
from app.bot.markdown import markdown_display
from app.core.config import TIMEZONE
from app.core.metrics import increment, timed
from app.models.booking import Booking
from app.models.gift_offer import GiftOffer
from app.models.user import User
from app.models.weekly_slot import WeeklySlot
from app.services.booking_limits import (
    count_user_bookings_in_week,
    lock_user_week_booking_limit,
    start_and_end_of_week,
    weekly_limit_value,
)
from app.services.club_service import is_weekly_reserved_for_date
from app.services.config_runtime import get_runtime_config
from app.services.config_service import get_working_hours
from app.services.date_service import get_current_week_dates
from app.services.time_service import now_tz
from app.services.warning_service import add_warning

log = logging.getLogger(__name__)

GiftBookingStatus = Literal[
    "pending",
    "invalid_username",
    "booking_not_found",
    "past_booking",
    "recipient_not_found",
    "recipient_not_allowed",
    "recipient_banned",
    "same_user",
    "recipient_limit_reached",
    "pending_offer_exists",
]

GiftOfferDecisionStatus = Literal[
    "success",
    "offer_not_found",
    "not_recipient",
    "booking_not_found",
    "past_booking",
    "recipient_not_allowed",
    "recipient_banned",
    "recipient_limit_reached",
]


@dataclass(frozen=True)
class GiftBookingResult:
    status: GiftBookingStatus
    booking: Booking | None = None
    recipient: User | None = None
    offer: GiftOffer | None = None


@dataclass(frozen=True)
class GiftOfferDecisionResult:
    status: GiftOfferDecisionStatus
    booking: Booking | None = None
    recipient: User | None = None
    giver: User | None = None
    offer: GiftOffer | None = None


# -------------------------
# Queries / helpers
# -------------------------


async def get_bookings_for_day(db, target_date: date) -> list[Booking]:
    q = await db.execute(select(Booking).where(Booking.date == target_date))
    return q.scalars().all()


async def is_slot_free(db, target_date: date, hour: int) -> bool:
    q = await db.execute(
        select(Booking.id).where(
            and_(Booking.date == target_date, Booking.hour == hour)
        )
    )
    return q.scalar_one_or_none() is None


async def is_weekly_reserved(db, weekday: int, hour: int) -> bool:
    q = await db.execute(
        select(WeeklySlot.id).where(
            and_(WeeklySlot.weekday == weekday, WeeklySlot.hour == hour)
        )
    )
    return q.scalar_one_or_none() is not None


async def is_weekly_reserved_on_date(db, target_date: date, hour: int) -> bool:
    if not await is_weekly_reserved(db, target_date.weekday(), hour):
        return False
    return await is_weekly_reserved_for_date(db, target_date, hour)


async def get_user_bookings(db, user_id: int) -> list[Booking]:
    week_dates = get_current_week_dates()
    monday = week_dates[0]
    sunday = week_dates[-1]

    q = (
        select(Booking)
        .where(Booking.user_id == user_id)
        .where(Booking.date >= monday)
        .where(Booking.date <= sunday)
        .order_by(Booking.date, Booking.hour)
    )
    rows = await db.execute(q)
    return rows.scalars().all()


async def count_user_bookings_this_week(db, user_id: int) -> int:
    week_dates = get_current_week_dates()
    monday = week_dates[0]
    sunday = week_dates[-1]

    q = await db.execute(
        select(func.count(Booking.id))
        .where(Booking.user_id == user_id)
        .where(Booking.date >= monday)
        .where(Booking.date <= sunday)
    )
    val = q.scalar()
    return int(val or 0)


async def build_status_summary(db, user: User) -> str:
    bookings = await get_user_bookings(db, user.id)
    weekly_limit = await _weekly_limit_value()
    booked_count = len(bookings)

    booking_lines = [
        f"• {WEEKDAYS[booking.date.weekday()]} · {booking.hour:02d}:00"
        for booking in bookings
    ]
    bookings_text = "\n".join(booking_lines) if booking_lines else "No bookings yet."

    return (
        "🎵 *Music Room*\n\n"
        f"👤 *{markdown_display(user.full_name, fallback='Member')}*\n"
        f"📅 *Bookings:* {booked_count} / {weekly_limit}\n\n"
        f"{bookings_text}"
    )


# -------------------------
# Cancellation / reset
# -------------------------


async def delete_booking(db, booking_id: int, user_id: int, bot=None) -> bool:
    """
    Deletes a booking and optionally notifies member chat/topic.
    Also:
      - prevents cancelling past bookings
      - gives warning only if cancelled < 1 hour before a future booking
    """

    booking = (
        await db.execute(
            select(Booking).where(Booking.id == booking_id, Booking.user_id == user_id)
        )
    ).scalar_one_or_none()

    if not booking:
        return False

    return await _do_delete_booking(db, booking, bot)


def _normalize_username(username: str) -> str | None:
    value = username.strip().removeprefix("@").strip()
    return value or None


async def gift_booking_to_username(
    db,
    booking_id: int,
    giver_user_id: int,
    recipient_username: str,
) -> GiftBookingResult:
    username = _normalize_username(recipient_username)
    if username is None:
        return GiftBookingResult(status="invalid_username")

    booking = (
        await db.execute(
            select(Booking).where(
                Booking.id == booking_id,
                Booking.user_id == giver_user_id,
            )
        )
    ).scalar_one_or_none()
    if booking is None:
        return GiftBookingResult(status="booking_not_found")

    booking_dt = datetime.combine(booking.date, time(booking.hour)).replace(
        tzinfo=ZoneInfo(TIMEZONE)
    )
    if booking_dt <= now_tz():
        return GiftBookingResult(status="past_booking", booking=booking)

    recipient = (
        await db.execute(
            select(User).where(func.lower(User.tg_username) == username.lower())
        )
    ).scalar_one_or_none()
    if recipient is None:
        return GiftBookingResult(status="recipient_not_found", booking=booking)
    if recipient.id == giver_user_id:
        return GiftBookingResult(
            status="same_user",
            booking=booking,
            recipient=recipient,
        )
    if recipient.banned:
        return GiftBookingResult(
            status="recipient_banned",
            booking=booking,
            recipient=recipient,
        )
    if not recipient.allowed:
        return GiftBookingResult(
            status="recipient_not_allowed",
            booking=booking,
            recipient=recipient,
        )

    weekly_limit = await _weekly_limit_value()
    start_week, end_week = _start_and_end_of_week(booking.date)
    recipient_count = await count_user_bookings_in_week(
        db,
        user_id=recipient.id,
        start_week=start_week,
        end_week=end_week,
    )
    if recipient_count >= weekly_limit:
        return GiftBookingResult(
            status="recipient_limit_reached",
            booking=booking,
            recipient=recipient,
        )

    pending_offer = (
        await db.execute(
            select(GiftOffer).where(
                GiftOffer.booking_id == booking.id,
                GiftOffer.status == "pending",
            )
        )
    ).scalar_one_or_none()
    if pending_offer is not None:
        return GiftBookingResult(
            status="pending_offer_exists",
            booking=booking,
            recipient=recipient,
            offer=pending_offer,
        )

    offer = GiftOffer(
        booking_id=booking.id,
        giver_user_id=giver_user_id,
        recipient_user_id=recipient.id,
        status="pending",
    )
    db.add(offer)
    await db.commit()
    log.info(
        "Booking gift offer created",
        extra={
            "booking_id": booking.id,
            "giver_user_id": giver_user_id,
            "recipient_user_id": recipient.id,
            "date": booking.date.isoformat(),
            "hour": booking.hour,
        },
    )

    return GiftBookingResult(
        status="pending",
        booking=booking,
        recipient=recipient,
        offer=offer,
    )


def _reset_booking_attendance_for_gift(booking: Booking) -> None:
    booking.booking_source = "gifted"
    booking.assigned_at = now_tz()
    booking.location_prompted = False
    booking.absence_reported = False
    booking.attendance_verified = False
    booking.attendance_lat = None
    booking.attendance_lon = None
    booking.attendance_recorded_at = None


async def accept_gift_offer(
    db,
    *,
    offer_id: int,
    recipient_user_id: int,
) -> GiftOfferDecisionResult:
    offer = (
        await db.execute(
            select(GiftOffer).where(
                GiftOffer.id == offer_id,
                GiftOffer.status == "pending",
            )
        )
    ).scalar_one_or_none()
    if offer is None:
        return GiftOfferDecisionResult(status="offer_not_found")
    if offer.recipient_user_id != recipient_user_id:
        return GiftOfferDecisionResult(status="not_recipient", offer=offer)

    booking = (
        await db.execute(
            select(Booking).where(
                Booking.id == offer.booking_id,
                Booking.user_id == offer.giver_user_id,
            )
        )
    ).scalar_one_or_none()
    if booking is None:
        offer.status = "cancelled"
        offer.responded_at = now_tz()
        await db.commit()
        return GiftOfferDecisionResult(status="booking_not_found", offer=offer)

    booking_dt = datetime.combine(booking.date, time(booking.hour)).replace(
        tzinfo=ZoneInfo(TIMEZONE)
    )
    if booking_dt <= now_tz():
        offer.status = "expired"
        offer.responded_at = now_tz()
        await db.commit()
        return GiftOfferDecisionResult(
            status="past_booking",
            booking=booking,
            offer=offer,
        )

    recipient = (
        await db.execute(select(User).where(User.id == offer.recipient_user_id))
    ).scalar_one_or_none()
    giver = (
        await db.execute(select(User).where(User.id == offer.giver_user_id))
    ).scalar_one_or_none()
    if recipient is None:
        return GiftOfferDecisionResult(
            status="recipient_not_allowed",
            booking=booking,
            recipient=recipient,
            giver=giver,
            offer=offer,
        )
    if recipient.banned:
        return GiftOfferDecisionResult(
            status="recipient_banned",
            booking=booking,
            recipient=recipient,
            giver=giver,
            offer=offer,
        )
    if not recipient.allowed:
        return GiftOfferDecisionResult(
            status="recipient_not_allowed",
            booking=booking,
            recipient=recipient,
            giver=giver,
            offer=offer,
        )

    weekly_limit = await _weekly_limit_value()
    start_week, end_week = _start_and_end_of_week(booking.date)
    await lock_user_week_booking_limit(
        db,
        user_id=recipient.id,
        week_start=start_week,
    )
    recipient_count = await count_user_bookings_in_week(
        db,
        user_id=recipient.id,
        start_week=start_week,
        end_week=end_week,
    )
    if recipient_count >= weekly_limit:
        return GiftOfferDecisionResult(
            status="recipient_limit_reached",
            booking=booking,
            recipient=recipient,
            giver=giver,
            offer=offer,
        )

    booking.user_id = recipient.id
    _reset_booking_attendance_for_gift(booking)
    offer.status = "accepted"
    offer.responded_at = now_tz()
    await db.commit()
    log.info(
        "Booking gift offer accepted",
        extra={
            "offer_id": offer.id,
            "booking_id": booking.id,
            "giver_user_id": offer.giver_user_id,
            "recipient_user_id": recipient.id,
            "date": booking.date.isoformat(),
            "hour": booking.hour,
        },
    )

    return GiftOfferDecisionResult(
        status="success",
        booking=booking,
        recipient=recipient,
        giver=giver,
        offer=offer,
    )


async def decline_gift_offer(
    db,
    *,
    offer_id: int,
    recipient_user_id: int,
) -> GiftOfferDecisionResult:
    offer = (
        await db.execute(
            select(GiftOffer).where(
                GiftOffer.id == offer_id,
                GiftOffer.status == "pending",
            )
        )
    ).scalar_one_or_none()
    if offer is None:
        return GiftOfferDecisionResult(status="offer_not_found")
    if offer.recipient_user_id != recipient_user_id:
        return GiftOfferDecisionResult(status="not_recipient", offer=offer)

    booking = (
        await db.execute(select(Booking).where(Booking.id == offer.booking_id))
    ).scalar_one_or_none()
    giver = (
        await db.execute(select(User).where(User.id == offer.giver_user_id))
    ).scalar_one_or_none()
    recipient = (
        await db.execute(select(User).where(User.id == offer.recipient_user_id))
    ).scalar_one_or_none()

    offer.status = "declined"
    offer.responded_at = now_tz()
    await db.commit()
    log.info(
        "Booking gift offer declined",
        extra={
            "offer_id": offer.id,
            "booking_id": offer.booking_id,
            "giver_user_id": offer.giver_user_id,
            "recipient_user_id": offer.recipient_user_id,
        },
    )

    return GiftOfferDecisionResult(
        status="success",
        booking=booking,
        recipient=recipient,
        giver=giver,
        offer=offer,
    )


async def cancel_booking_by_admin(
    db,
    booking_id: int,
    bot=None,
    *,
    notify_reason: str = "cancelled by admin.",
) -> bool:
    """
    Cancels a booking by admin request. Notifies the user.
    """
    booking = (
        await db.execute(select(Booking).where(Booking.id == booking_id))
    ).scalar_one_or_none()

    if not booking:
        return False

    user_id = booking.user_id
    b_date = booking.date
    b_hour = booking.hour

    # Get user to notify them later
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()

    # Reuse deletion logic
    success = await _do_delete_booking(db, booking, bot, is_admin_cancel=True)

    if success and bot and user.tg_user_id:
        weekday = WEEKDAYS[b_date.weekday()]
        try:
            await bot.send_message(
                user.tg_user_id,
                (f"⚠️ Your booking on {weekday} at {b_hour:02d}:00 was {notify_reason}"),
            )
        except Exception:
            log.exception(
                "Failed to notify user about admin booking cancellation",
                extra={
                    "booking_id": booking_id,
                    "user_id": user_id,
                    "tg_user_id": user.tg_user_id,
                },
            )

    return success


async def _do_delete_booking(db, booking, bot=None, is_admin_cancel=False) -> bool:
    b_date = booking.date
    b_hour = booking.hour
    user_id = booking.user_id

    now = now_tz()
    booking_dt = datetime.combine(b_date, time(b_hour)).replace(
        tzinfo=ZoneInfo(TIMEZONE)
    )

    if booking_dt <= now and not is_admin_cancel:
        return False

    send_warning = not is_admin_cancel and (booking_dt - now) <= timedelta(hours=1)

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()

    # Delete with verify exactly one row was removed.
    delete_result = await db.execute(delete(Booking).where(Booking.id == booking.id))
    if int(delete_result.rowcount or 0) != 1:
        await db.rollback()
        return False

    await db.commit()
    log.info(
        "Booking cancelled",
        extra={
            "booking_id": booking.id,
            "user_id": user_id,
            "date": b_date.isoformat(),
            "hour": b_hour,
            "is_admin_cancel": is_admin_cancel,
            "late_warning": send_warning,
        },
    )

    # warning (best-effort)
    if send_warning and bot:
        try:
            await add_warning(
                db=db,
                bot=bot,
                user_id=user_id,
                reason="Late cancellation (less than 1 hour before booking)",
                appeal_allowed=False,
            )
        except Exception:
            log.exception(
                "Failed to add late-cancellation warning",
                extra={"booking_id": booking.id, "user_id": user_id},
            )

    # notify member chat (best-effort) — skip for admin cancellations
    if bot and not is_admin_cancel:
        member_chat_id = await get_runtime_config("member_chat_id")
        member_topic_id = await get_runtime_config("member_topic_id")

        if member_chat_id:
            from app.bot.keyboards.inline_kb import flash_book_kb

            weekday = WEEKDAYS[b_date.weekday()]
            name = user.full_name or user.tg_username or "Unknown user"
            text = f"❌ {name} cancelled a slot: {weekday}, {b_hour:02d}:00"

            from app.bot.flash_book_store import register as register_flash_message

            kb = flash_book_kb(b_date, b_hour)
            try:
                if member_topic_id:
                    sent = await bot.send_message(
                        member_chat_id,
                        text,
                        message_thread_id=member_topic_id,
                        reply_markup=kb,
                    )
                else:
                    sent = await bot.send_message(member_chat_id, text, reply_markup=kb)
                register_flash_message(
                    b_date,
                    b_hour,
                    int(member_chat_id),
                    sent.message_id,
                    int(member_topic_id) if member_topic_id else None,
                )
            except Exception:
                log.exception(
                    "Failed to notify member chat about cancelled slot",
                    extra={
                        "booking_id": booking.id,
                        "user_id": user_id,
                        "chat_id": member_chat_id,
                        "topic_id": member_topic_id,
                        "date": b_date.isoformat(),
                        "hour": b_hour,
                    },
                )

    return True


async def weekly_reset(db) -> None:
    """
    Deletes old non-weekly bookings safely.
    """
    cutoff_date = get_current_week_dates()[0]
    q = await db.execute(
        select(Booking.id).where(
            Booking.is_weekly == False,  # noqa: E712
            Booking.date < cutoff_date,
        )
    )
    booking_ids = [row[0] for row in q.all()]

    if booking_ids:
        await db.execute(delete(Booking).where(Booking.id.in_(booking_ids)))

    await db.commit()
    log.info(
        "Weekly reset completed",
        extra={
            "deleted_bookings": len(booking_ids),
            "cutoff_date": cutoff_date.isoformat(),
        },
    )


# -------------------------
# Concurrency-safe booking
# -------------------------


async def _weekly_limit_value() -> int:
    return await weekly_limit_value()


def _start_and_end_of_week(b_date: date) -> tuple[date, date]:
    return start_and_end_of_week(b_date)


async def safe_create_booking(
    db,
    user_id: int,
    b_date: date,
    b_hour: int,
    *,
    booking_source: str = "manual",
) -> tuple[str, Booking | None]:
    """
    Attempts to create a booking in a concurrency-safe way using the DB UNIQUE constraint.
    Returns:
      ("success", booking)
      ("taken", None)
      ("limit", None)
    """
    metric_labels = {"source": booking_source}
    with timed("booking_create_seconds", labels=metric_labels):
        return await _safe_create_booking(
            db,
            user_id,
            b_date,
            b_hour,
            booking_source=booking_source,
        )


async def _safe_create_booking(
    db,
    user_id: int,
    b_date: date,
    b_hour: int,
    *,
    booking_source: str,
) -> tuple[str, Booking | None]:
    weekly_limit_i = await _weekly_limit_value()

    if await is_weekly_reserved_on_date(db, b_date, b_hour):
        increment(
            "booking_create_total",
            labels={"source": booking_source, "status": "taken"},
        )
        return ("taken", None)

    # Count bookings in the bookable week (Mon..Mon+7)
    start_week, end_week = _start_and_end_of_week(b_date)
    await lock_user_week_booking_limit(
        db,
        user_id=user_id,
        week_start=start_week,
    )

    cnt = await count_user_bookings_in_week(
        db,
        user_id=user_id,
        start_week=start_week,
        end_week=end_week,
    )

    if cnt >= weekly_limit_i:
        increment(
            "booking_create_total",
            labels={"source": booking_source, "status": "limit"},
        )
        return ("limit", None)

    try:
        stmt = (
            insert(Booking)
            .values(
                user_id=user_id,
                date=b_date,
                hour=b_hour,
                is_weekly=False,
                booking_source=booking_source,
                assigned_at=func.now(),
                location_prompted=False,
                absence_reported=False,
                attendance_verified=False,
                attendance_lat=None,
                attendance_lon=None,
                attendance_recorded_at=None,
            )
            .returning(Booking.id)
        )

        result = await db.execute(stmt)
        new_id = result.scalar_one_or_none()

        if not new_id:
            await db.rollback()
            increment(
                "booking_create_total",
                labels={"source": booking_source, "status": "taken"},
            )
            return ("taken", None)

        await db.commit()
        booking = await db.get(Booking, new_id)
        increment(
            "booking_create_total",
            labels={"source": booking_source, "status": "success"},
        )
        log.info(
            "Booking created",
            extra={
                "booking_id": new_id,
                "user_id": user_id,
                "date": b_date.isoformat(),
                "hour": b_hour,
                "booking_source": booking_source,
            },
        )
        return ("success", booking)

    except IntegrityError:
        await db.rollback()
        increment(
            "booking_create_total",
            labels={"source": booking_source, "status": "taken"},
        )
        log.info(
            "Booking create conflict",
            extra={"user_id": user_id, "date": b_date.isoformat(), "hour": b_hour},
        )
        return ("taken", None)


async def has_user_booking_for_slot(
    db, user_id: int, b_date: date, b_hour: int
) -> bool:
    q = await db.execute(
        select(Booking.id).where(
            Booking.user_id == user_id,
            Booking.date == b_date,
            Booking.hour == b_hour,
        )
    )
    return q.scalar_one_or_none() is not None


async def get_consecutive_slot_option(
    db, user_id: int, b_date: date, b_hour: int
) -> tuple[date, int] | None:
    next_hour = b_hour + 1
    if next_hour >= 24:
        return None

    start_hour, end_hour = await get_working_hours(db, WEEKDAYS[b_date.weekday()])
    if not start_hour <= next_hour < end_hour:
        return None

    now = now_tz()
    booking_dt = datetime.combine(b_date, time(next_hour)).replace(
        tzinfo=ZoneInfo(TIMEZONE)
    )
    if booking_dt <= now:
        return None

    if await is_weekly_reserved_on_date(db, b_date, next_hour):
        return None
    if not await is_slot_free(db, b_date, next_hour):
        return None

    weekly_limit_i = await _weekly_limit_value()
    current_count = await count_user_bookings_this_week(db, user_id)
    if current_count >= weekly_limit_i:
        return None

    return (b_date, next_hour)
