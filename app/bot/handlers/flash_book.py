# app/bot/handlers/flash_book.py
import logging
from contextlib import suppress
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router, types
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select

from app.bot.constants.dates import WEEKDAYS
from app.bot.flash_book_store import pop as pop_flash_message
from app.core.config import TIMEZONE
from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.services.booking_service import safe_create_booking
from app.services.time_service import now_tz

log = logging.getLogger(__name__)
router = Router()


def _parse_flash_callback(data: str) -> tuple[date, int] | None:
    # flash_book_{YYYY-MM-DD}_{hour}
    try:
        parts = data.removeprefix("flash_book_").rsplit("_", 1)
        return date.fromisoformat(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return None


def _slot_text(b_date: date, b_hour: int) -> str:
    return f"{WEEKDAYS[b_date.weekday()]} · {b_hour:02d}:00"


async def notify_slot_taken(bot: Bot, b_date: date, b_hour: int, booker_name: str) -> None:
    """Edit the flash-book group message to show the slot was booked. No-op if no message is registered."""
    entry = pop_flash_message(b_date, b_hour)
    if not entry:
        return
    chat_id, message_id, thread_id = entry
    slot = _slot_text(b_date, b_hour)
    try:
        await bot.edit_message_text(
            f"✅ Freed slot taken: {slot}\nBooked by {booker_name}",
            chat_id=chat_id,
            message_id=message_id,
        )
    except Exception:
        log.exception(
            "Failed to edit flash-book message after booking",
            extra={
                "chat_id": chat_id,
                "message_id": message_id,
                "thread_id": thread_id,
                "date": b_date.isoformat(),
                "hour": b_hour,
            },
        )


@router.callback_query(F.data.startswith("flash_book_"))
async def handle_flash_book(callback: types.CallbackQuery) -> None:
    parsed = _parse_flash_callback(callback.data)
    if not parsed:
        await callback.answer("Invalid slot data.", show_alert=True)
        return

    b_date, b_hour = parsed

    booking_dt = datetime.combine(b_date, time(b_hour)).replace(tzinfo=ZoneInfo(TIMEZONE))
    if booking_dt <= now_tz():
        await callback.answer("⏰ This slot is in the past.", show_alert=True)
        pop_flash_message(b_date, b_hour)
        with suppress(TelegramBadRequest):
            await callback.message.edit_reply_markup(reply_markup=None)
        return

    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(
                select(User).where(User.tg_user_id == callback.from_user.id)
            )
        ).scalar_one_or_none()

        if not user:
            await callback.answer("You're not registered.", show_alert=True)
            return
        if not user.allowed:
            await callback.answer("You don't have access yet.", show_alert=True)
            return
        if user.banned:
            await callback.answer("Your account is suspended.", show_alert=True)
            return

        status, _ = await safe_create_booking(
            db, user.id, b_date, b_hour, booking_source="flash"
        )

    slot = _slot_text(b_date, b_hour)
    name = user.full_name or user.tg_username or "Unknown user"

    if status == "success":
        await callback.answer(f"✅ Booked: {slot}")
        await notify_slot_taken(callback.bot, b_date, b_hour, name)
    elif status == "taken":
        await callback.answer("⚡ Already taken!", show_alert=True)
        # Someone else already booked it — strip the button; notify_slot_taken
        # may have already edited the text, so just clear markup if entry is gone.
        entry = pop_flash_message(b_date, b_hour)
        if entry:
            try:
                await callback.bot.edit_message_reply_markup(
                    chat_id=entry[0], message_id=entry[1], reply_markup=None
                )
            except Exception:
                log.exception(
                    "Failed to clear flash-book message markup",
                    extra={
                        "chat_id": entry[0],
                        "message_id": entry[1],
                        "date": b_date.isoformat(),
                        "hour": b_hour,
                    },
                )
    elif status == "limit":
        await callback.answer("You've reached your weekly booking limit.", show_alert=True)
