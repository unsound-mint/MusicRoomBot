# app/services/reminder_service.py
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy import select, update

from app.bot.constants.dates import WEEKDAYS
from app.core.database import AsyncSessionLocal
from app.models.booking import Booking
from app.models.user import User
from app.services.config_runtime import get_runtime_config
from app.services.time_service import now_tz

if TYPE_CHECKING:
    from aiogram import Bot

log = logging.getLogger(__name__)

# A reminder is due from its nominal time until this long after it, so a missed or
# slow scheduler tick still delivers it. The 15-minute reminder stops at the start.
HOURLY_REMINDER_GRACE = timedelta(minutes=15)
FIFTEEN_MIN_OFFSET = timedelta(minutes=15)
# Errors that retrying cannot fix (user blocked the bot, chat not found).
_PERMANENT_SEND_ERRORS = (TelegramForbiddenError, TelegramBadRequest)


def due_slot_start(
    now: datetime, offset: timedelta, grace: timedelta
) -> datetime | None:
    """
    Start of the slot whose reminder (sent `offset` before the slot) is due now,
    or None. Slots start on the hour and `grace` is under an hour, so at most one
    slot hour can be due at a time.
    """
    start = (now + offset).replace(minute=0, second=0, microsecond=0)
    if now + offset - start < grace:
        return start
    return None


def _build_chain_start_hours(hours_sorted: list[int]) -> dict[int, list[int]]:
    """
    Given sorted hours like [10, 11, 12, 15, 16],
    returns mapping from chain start -> chain hours:
      {10: [10,11,12], 15: [15,16]}
    """
    chains: dict[int, list[int]] = {}
    if not hours_sorted:
        return chains

    start = hours_sorted[0]
    current = [start]

    for h in hours_sorted[1:]:
        if h == current[-1] + 1:
            current.append(h)
        else:
            chains[start] = current
            start = h
            current = [h]

    chains[start] = current
    return chains


async def _mark_reminded(booking_id: int, is_15_min: bool, sent_at: datetime) -> None:
    column = Booking.reminded_15_at if is_15_min else Booking.reminded_hourly_at
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(Booking)
            .where(Booking.id == booking_id)
            .values({column.key: sent_at})
        )
        await db.commit()


async def process_reminders(bot: Bot) -> None:
    """
    Run every minute from scheduler.
    1) Configurable hours reminder (due at minute 00, `reminder_hours` ahead).
    2) Mandatory 15-minute reminder (due at minute 45 for the next hour).

    Each reminder is selected by time window and recorded on the booking
    (`reminded_hourly_at` / `reminded_15_at`), so a missed tick is caught up on the
    next one and a restart or repeated tick never sends it twice.
    """

    now = now_tz().replace(second=0, microsecond=0)

    reminder_hours = await get_runtime_config("reminder_hours")
    try:
        reminder_hours_i = int(reminder_hours or 0)
    except Exception:
        reminder_hours_i = 0

    await _send_due_reminders(
        bot,
        now,
        is_15_min=False,
        offset=timedelta(hours=reminder_hours_i),
        grace=HOURLY_REMINDER_GRACE,
    )
    await _send_due_reminders(
        bot,
        now,
        is_15_min=True,
        offset=FIFTEEN_MIN_OFFSET,
        grace=FIFTEEN_MIN_OFFSET,
    )


async def _send_due_reminders(
    bot: Bot,
    now: datetime,
    *,
    is_15_min: bool,
    offset: timedelta,
    grace: timedelta,
) -> None:
    target_dt = due_slot_start(now, offset, grace)
    if target_dt is None:
        return

    marker = Booking.reminded_15_at if is_15_min else Booking.reminded_hourly_at
    target_date = target_dt.date()
    target_hour = target_dt.hour

    async with AsyncSessionLocal() as db:
        # 1) Load all not-yet-reminded bookings that start at the target hour
        q = (
            select(Booking, User)
            .join(User, Booking.user_id == User.id)
            .where(Booking.date == target_date)
            .where(Booking.hour == target_hour)
            .where(marker.is_(None))
        )
        rows = (await db.execute(q)).all()
        if not rows:
            return

        candidates: list[tuple[Booking, User]] = []
        user_ids: set[int] = set()

        for booking, user in rows:
            if not user.tg_user_id:
                continue
            candidates.append((booking, user))
            user_ids.add(user.id)

        if not candidates:
            return

        # 2) Fetch all bookings for these users on that date (for chain text)
        q2 = (
            select(Booking.user_id, Booking.hour)
            .where(Booking.date == target_date)
            .where(Booking.user_id.in_(user_ids))
        )
        all_user_hours_rows = (await db.execute(q2)).all()

    # Build mapping: user_id -> sorted hours list
    user_hours: dict[int, list[int]] = {}
    for uid, hour in all_user_hours_rows:
        user_hours.setdefault(uid, []).append(hour)
    for uid in list(user_hours.keys()):
        user_hours[uid].sort()

    # Dedup: (user_id, chain_start_hour)
    sent: set[tuple[int, int]] = set()

    for booking, user in candidates:
        hours_sorted = user_hours.get(user.id, [booking.hour])
        chains = _build_chain_start_hours(hours_sorted)

        # Determine which chain contains target_hour
        chain_start = None
        chain_hours: list[int] | None = None
        for start, hrs in chains.items():
            if booking.hour in hrs:
                chain_start = start
                chain_hours = hrs
                break

        if chain_start is None or chain_hours is None:
            chain_start = booking.hour
            chain_hours = [booking.hour]

        # Only remind for FIRST slot of that chain
        if chain_start != booking.hour:
            continue

        key = (user.id, chain_start)
        if key in sent:
            continue
        sent.add(key)

        weekday = WEEKDAYS[booking.date.weekday()]
        times_str = ", ".join(f"{h:02d}:00" for h in chain_hours)

        if is_15_min:
            title = "⏳ *15-minute reminder*"
            footer = "Send your location at the start time to confirm attendance."
        else:
            title = "🔔 *Session reminder*"
            footer = "Send your location at the start time to confirm attendance."

        text = (
            f"{title}\n\n"
            f"⏰ *Time:* {times_str}\n"
            f"📅 *Day:* {weekday}\n\n"
            f"{footer}"
        )

        try:
            await bot.send_message(user.tg_user_id, text, parse_mode="Markdown")
        except _PERMANENT_SEND_ERRORS:
            log.warning(
                "Booking reminder undeliverable, marking as handled",
                extra={"booking_id": booking.id, "tg_user_id": user.tg_user_id},
            )
            await _mark_reminded(booking.id, is_15_min, now)
            continue
        except Exception:
            log.exception(
                "Failed to send booking reminder",
                extra={
                    "booking_id": booking.id,
                    "user_id": user.id,
                    "tg_user_id": user.tg_user_id,
                    "target_date": target_date.isoformat(),
                    "target_hour": target_hour,
                    "is_15_min": is_15_min,
                },
            )
            continue

        await _mark_reminded(booking.id, is_15_min, now)
