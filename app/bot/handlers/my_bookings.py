# app/bot/handlers/my_bookings.py
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select

from app.bot.handlers.booking_messages import build_booking_cancelled_text
from app.bot.keyboards.inline_kb import (
    booking_detail_kb,
    bookings_hub_kb,
    cancel_confirm_kb,
    gift_offer_response_kb,
    gift_username_prompt_kb,
)
from app.bot.markdown import markdown_display
from app.bot.ui import (
    edit_or_answer,
    format_slot_text,
    safe_answer_callback,
)
from app.core.config import TIMEZONE
from app.core.database import AsyncSessionLocal
from app.models.booking import Booking
from app.models.user import User
from app.services.booking_queries import get_user_bookings
from app.services.booking_service import (
    accept_gift_offer,
    decline_gift_offer,
    delete_booking,
    gift_booking_to_username,
)
from app.services.calendar_service import get_google_calendar_link
from app.services.config_runtime import get_runtime_config
from app.services.time_service import now_tz

log = logging.getLogger(__name__)

router = Router()


class GiftBookingStates(StatesGroup):
    waiting_username = State()


async def _current_user(db, tg_user_id: int) -> User | None:
    return (
        await db.execute(select(User).where(User.tg_user_id == tg_user_id))
    ).scalar_one_or_none()


async def _render_bookings_hub(
    target: types.Message | types.CallbackQuery,
    *,
    db,
    user: User,
    force_new: bool = False,
    note: str | None = None,
):
    confirmed = await get_user_bookings(db, user.id)
    text = "🎸 *My bookings*\n\nSelect a booking to view details or cancel."
    if not confirmed:
        text = (
            "🎸 *My bookings*\n\n"
            "📭 Nothing booked yet.\n\n"
            "Use Book a slot to reserve your next session."
        )
        reply_markup = None
    else:
        reply_markup = bookings_hub_kb(confirmed=confirmed)

    if note:
        text = f"{note}\n\n{text}"

    if force_new:
        message = target.message if isinstance(target, types.CallbackQuery) else target
        return await message.answer(
            text,
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )

    return await edit_or_answer(
        target,
        text,
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


@router.message(
    F.text == "🎵 Book a slot"
)  # This will be overridden by booking.py, but keeping it consistent
@router.message(F.text == "🎸 My bookings")
@router.message(F.text == "Cancel booking")
async def my_bookings(message: types.Message):
    async with AsyncSessionLocal() as db:
        user = await _current_user(db, message.from_user.id)
        if not user:
            return await message.answer("Account not found. Please send /start.")
        return await _render_bookings_hub(message, db=db, user=user)


@router.callback_query(F.data == "myb_back")
async def my_bookings_back(callback: types.CallbackQuery, state: FSMContext):
    await safe_answer_callback(callback)
    await state.clear()
    async with AsyncSessionLocal() as db:
        user = await _current_user(db, callback.from_user.id)
        if not user:
            return await edit_or_answer(
                callback, "Account not found. Please send /start."
            )
        return await _render_bookings_hub(callback, db=db, user=user)


@router.callback_query(F.data == "myb_back_new")
async def my_bookings_back_new(callback: types.CallbackQuery, state: FSMContext):
    await safe_answer_callback(callback)
    await state.clear()
    async with AsyncSessionLocal() as db:
        user = await _current_user(db, callback.from_user.id)
        if not user:
            return await callback.message.answer(
                "Account not found. Please send /start."
            )
        return await _render_bookings_hub(callback, db=db, user=user, force_new=True)


@router.callback_query(F.data.startswith("myb_booking_"))
async def my_booking_detail(callback: types.CallbackQuery, state: FSMContext):
    await safe_answer_callback(callback)
    await state.clear()
    booking_id = int(callback.data.split("_")[2])

    async with AsyncSessionLocal() as db:
        user = await _current_user(db, callback.from_user.id)
        if not user:
            return await edit_or_answer(
                callback, "Account not found. Please send /start."
            )

        booking = await db.get(Booking, booking_id)
        if not booking or booking.user_id != user.id:
            return await _render_bookings_hub(
                callback,
                db=db,
                user=user,
                note="⚠️ That booking is no longer available.",
            )

        slot_length = await get_runtime_config("slot_length")
        try:
            slot_length_i = int(slot_length)
        except Exception:
            slot_length_i = 60

        link = get_google_calendar_link(
            booking.date,
            booking.hour,
            slot_length_minutes=slot_length_i,
        )

        booking_dt = datetime.combine(booking.date, time(booking.hour)).replace(
            tzinfo=ZoneInfo(TIMEZONE)
        )
        from app.bot.constants.dates import WEEKDAYS

        return await edit_or_answer(
            callback,
            (
                "🎸 *My bookings*\n\n"
                f"📅 {WEEKDAYS[booking.date.weekday()]}, {booking.hour:02d}:00"
            ),
            reply_markup=booking_detail_kb(
                booking.id,
                calendar_link=link,
                can_swap=booking_dt > now_tz(),
                can_cancel=booking_dt > now_tz(),
                can_gift=booking_dt > now_tz(),
            ),
            parse_mode="Markdown",
        )


@router.callback_query(F.data.startswith("myb_gift_"))
async def gift_slot(callback: types.CallbackQuery, state: FSMContext):
    await safe_answer_callback(callback)
    booking_id = int(callback.data.split("_")[2])

    async with AsyncSessionLocal() as db:
        user = await _current_user(db, callback.from_user.id)
        if not user:
            return await edit_or_answer(
                callback, "Account not found. Please send /start."
            )

        booking = await db.get(Booking, booking_id)
        if not booking or booking.user_id != user.id:
            return await _render_bookings_hub(
                callback,
                db=db,
                user=user,
                note="⚠️ That booking is no longer available.",
            )

        booking_dt = datetime.combine(booking.date, time(booking.hour)).replace(
            tzinfo=ZoneInfo(TIMEZONE)
        )
        if booking_dt <= now_tz():
            return await edit_or_answer(callback, "⏰ Past bookings can't be gifted.")

        slot_text = format_slot_text(booking.date, booking.hour)

    await state.set_state(GiftBookingStates.waiting_username)
    await state.update_data(gift_booking_id=booking_id)
    return await edit_or_answer(
        callback,
        (
            "🎁 *Gift booking*\n\n"
            f"⏰ {slot_text}\n\n"
            "Send the recipient's Telegram username, for example @username."
        ),
        reply_markup=gift_username_prompt_kb(booking_id),
        parse_mode="Markdown",
    )


def _gift_error_text(status: str) -> str:
    messages = {
        "invalid_username": "Send a Telegram username like @username.",
        "booking_not_found": "This booking is no longer available.",
        "past_booking": "Past bookings can't be gifted.",
        "recipient_not_found": "I couldn't find that username in the bot.",
        "recipient_not_allowed": "That user does not currently have room access.",
        "recipient_banned": "That user is banned.",
        "same_user": "You can't gift a booking to yourself.",
        "recipient_limit_reached": "That user has already reached the weekly booking limit.",
        "pending_offer_exists": "This booking already has a pending gift offer.",
    }
    return messages.get(status, "Gift failed. Please try again.")


def _gift_decision_error_text(status: str) -> str:
    messages = {
        "offer_not_found": "This gift offer is no longer available.",
        "not_recipient": "This gift offer was sent to another user.",
        "booking_not_found": "This booking is no longer available.",
        "past_booking": "Past bookings can't be accepted.",
        "recipient_not_allowed": "You do not currently have room access.",
        "recipient_banned": "You are banned.",
        "recipient_limit_reached": "You have already reached the weekly booking limit.",
    }
    return messages.get(status, "Gift offer failed. Please try again.")


def _display_user(user: User) -> str:
    if user.full_name:
        return markdown_display(user.full_name)
    if user.tg_username:
        return "@" + markdown_display(user.tg_username)
    return f"id={user.id}"


def _display_username(user: User) -> str:
    if user.tg_username:
        return "@" + markdown_display(user.tg_username)
    return f"id={user.id}"


async def _notify_gift_recipient(
    *,
    bot,
    recipient: User,
    giver: User,
    booking: Booking,
    offer_id: int,
) -> None:
    if not recipient.tg_user_id:
        return

    slot_text = format_slot_text(booking.date, booking.hour)
    giver_name = _display_username(giver)
    try:
        await bot.send_message(
            recipient.tg_user_id,
            (
                "🎁 *Booking gift offer*\n\n"
                f"👤 From: {giver_name}\n"
                f"⏰ {slot_text}\n\n"
                "Accept this booking to add it to My bookings."
            ),
            reply_markup=gift_offer_response_kb(offer_id),
            parse_mode="Markdown",
        )
    except Exception:
        log.exception(
            "Failed to notify gift recipient",
            extra={
                "booking_id": booking.id,
                "recipient_user_id": recipient.id,
                "recipient_tg_user_id": recipient.tg_user_id,
                "giver_user_id": giver.id,
            },
        )


@router.message(GiftBookingStates.waiting_username)
async def handle_gift_username(message: types.Message, state: FSMContext):
    data = await state.get_data()
    booking_id = data.get("gift_booking_id")
    if not isinstance(booking_id, int):
        await state.clear()
        return await message.answer("Session expired. Open My bookings to try again.")

    username = message.text or ""

    async with AsyncSessionLocal() as db:
        user = await _current_user(db, message.from_user.id)
        if not user:
            await state.clear()
            return await message.answer("Account not found. Please send /start.")

        result = await gift_booking_to_username(
            db,
            booking_id=booking_id,
            giver_user_id=user.id,
            recipient_username=username,
        )

        if result.status != "pending":
            if result.status in {"booking_not_found", "past_booking"}:
                await state.clear()
            return await message.answer(_gift_error_text(result.status))

        assert result.booking is not None
        assert result.recipient is not None
        assert result.offer is not None
        slot_text = format_slot_text(result.booking.date, result.booking.hour)
        recipient_name = _display_user(result.recipient)
        await _notify_gift_recipient(
            bot=message.bot,
            recipient=result.recipient,
            giver=user,
            booking=result.booking,
            offer_id=result.offer.id,
        )

    await state.clear()
    return await message.answer(
        (f"✅ *Gift offer sent*\n\n⏰ {slot_text}\n👤 To: {recipient_name}"),
        reply_markup=None,
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("gift_accept_"))
async def handle_gift_accept(callback: types.CallbackQuery):
    await safe_answer_callback(callback)
    offer_id = int(callback.data.split("_")[2])

    async with AsyncSessionLocal() as db:
        user = await _current_user(db, callback.from_user.id)
        if not user:
            return await edit_or_answer(
                callback, "Account not found. Please send /start."
            )

        result = await accept_gift_offer(
            db,
            offer_id=offer_id,
            recipient_user_id=user.id,
        )
        if result.status != "success":
            return await edit_or_answer(
                callback, _gift_decision_error_text(result.status)
            )

        assert result.booking is not None
        slot_text = format_slot_text(result.booking.date, result.booking.hour)
        if result.giver and result.giver.tg_user_id:
            try:
                await callback.bot.send_message(
                    result.giver.tg_user_id,
                    f"✅ Your gift offer was accepted.\n\n⏰ {slot_text}",
                )
            except Exception:
                log.exception(
                    "Failed to notify gift giver about acceptance",
                    extra={"offer_id": offer_id, "giver_user_id": result.giver.id},
                )

    return await edit_or_answer(
        callback,
        f"✅ *Booking accepted*\n\n⏰ {slot_text}",
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("gift_decline_"))
async def handle_gift_decline(callback: types.CallbackQuery):
    await safe_answer_callback(callback)
    offer_id = int(callback.data.split("_")[2])

    async with AsyncSessionLocal() as db:
        user = await _current_user(db, callback.from_user.id)
        if not user:
            return await edit_or_answer(
                callback, "Account not found. Please send /start."
            )

        result = await decline_gift_offer(
            db,
            offer_id=offer_id,
            recipient_user_id=user.id,
        )
        if result.status != "success":
            return await edit_or_answer(
                callback, _gift_decision_error_text(result.status)
            )

        slot_text = None
        if result.booking is not None:
            slot_text = format_slot_text(result.booking.date, result.booking.hour)
        if result.giver and result.giver.tg_user_id:
            try:
                text = "↩️ Your gift offer was declined."
                if slot_text:
                    text = f"{text}\n\n⏰ {slot_text}"
                await callback.bot.send_message(result.giver.tg_user_id, text)
            except Exception:
                log.exception(
                    "Failed to notify gift giver about decline",
                    extra={"offer_id": offer_id, "giver_user_id": result.giver.id},
                )

    text = "↩️ *Gift offer declined*"
    if slot_text:
        text = f"{text}\n\n⏰ {slot_text}"
    return await edit_or_answer(callback, text, parse_mode="Markdown")


@router.callback_query(F.data.startswith("myb_cancel_"))
async def cancel_slot(callback: types.CallbackQuery):
    await safe_answer_callback(callback)
    booking_id = int(callback.data.split("_")[2])

    async with AsyncSessionLocal() as db:
        user = await _current_user(db, callback.from_user.id)
        if not user:
            return await edit_or_answer(
                callback, "Account not found. Please send /start."
            )

        booking = await db.get(Booking, booking_id)
        if not booking or booking.user_id != user.id:
            return await _render_bookings_hub(
                callback,
                db=db,
                user=user,
                note="⚠️ That booking is no longer available.",
            )

        booking_dt = datetime.combine(booking.date, time(booking.hour)).replace(
            tzinfo=ZoneInfo(TIMEZONE)
        )
        if booking_dt <= now_tz():
            return await edit_or_answer(
                callback, "⏰ Past bookings can't be cancelled."
            )

        slot_text = format_slot_text(booking.date, booking.hour)

    return await edit_or_answer(
        callback,
        f"❓ Cancel booking?\n\n⏰ {slot_text}",
        reply_markup=cancel_confirm_kb(booking_id),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("myb_confirm_cancel_"))
async def confirm_cancel_slot(callback: types.CallbackQuery):
    await safe_answer_callback(callback)
    booking_id = int(callback.data.split("_")[3])

    async with AsyncSessionLocal() as db:
        user = await _current_user(db, callback.from_user.id)
        if not user:
            return await edit_or_answer(
                callback, "Account not found. Please send /start."
            )

        booking = await db.get(Booking, booking_id)
        if not booking or booking.user_id != user.id:
            return await _render_bookings_hub(
                callback,
                db=db,
                user=user,
                note="⚠️ That booking is no longer available.",
            )

        booking_dt = datetime.combine(booking.date, time(booking.hour)).replace(
            tzinfo=ZoneInfo(TIMEZONE)
        )
        if booking_dt <= now_tz():
            return await edit_or_answer(
                callback, "⏰ Past bookings can't be cancelled."
            )

        slot_text = format_slot_text(booking.date, booking.hour)
        success = await delete_booking(db, booking_id, user.id, bot=callback.bot)
        if not success:
            return await edit_or_answer(
                callback, "⚠️ Cancellation failed. Please try again."
            )

    return await edit_or_answer(
        callback,
        build_booking_cancelled_text(slot_text),
        reply_markup=None,
        parse_mode="Markdown",
    )
