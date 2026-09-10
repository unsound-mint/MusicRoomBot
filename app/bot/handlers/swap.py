# app/bot/handlers/swap.py
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select

from app.bot.constants.dates import WEEKDAYS
from app.bot.handlers.booking_guards import require_registered_user
from app.bot.keyboards.swap_kb import (
    swap_hour_kb,
    swap_offer_kb,
    swap_pick_day_kb,
)
from app.bot.markdown import markdown_display
from app.bot.ui import (
    edit_or_answer,
    safe_answer_callback,
)
from app.core.config import TIMEZONE
from app.core.database import AsyncSessionLocal
from app.models.booking import Booking
from app.models.user import User
from app.services.date_service import get_current_week_date, get_current_week_dates
from app.services.swap_service import (
    DeclinedSwapOffer,
    accept_swap_offer,
    create_swap_offer,
    decline_swap_offer,
)
from app.services.time_service import now_tz

log = logging.getLogger(__name__)
router = Router()


class SwapStates(StatesGroup):
    waiting_day = State()
    waiting_hour = State()


def _slot_line(d, hour: int) -> str:
    return f"{WEEKDAYS[d.weekday()]} {d} · {hour:02d}:00"


def _my_bookings_text(my_bookings: list) -> str:
    if not my_bookings:
        return "📭 No upcoming bookings."
    lines = "\n".join(f"• {_slot_line(b.date, b.hour)}" for b in my_bookings)
    return f"*Your bookings:*\n{lines}"




@router.message(Command("swap"))
async def handle_swap_command(message: types.Message, state: FSMContext):
    now = now_tz()
    async with AsyncSessionLocal() as db:
        user = await require_registered_user(
            message, db, message.from_user.id, use_edit=False
        )
        if not user:
            return
        my_bookings = await _load_upcoming_bookings(db, user.id, now)

    await state.set_state(SwapStates.waiting_day)
    today = now.date()
    week_dates = [d for d in get_current_week_dates() if d >= today]

    await message.answer(
        f"🔄 *Slot Swap*\n\n{_my_bookings_text(my_bookings)}\n\nPick a day you want to swap into.",
        reply_markup=swap_pick_day_kb(week_dates),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "swap_start")
@router.callback_query(F.data.startswith("myb_swap_"))
async def handle_swap_start_callback(callback: types.CallbackQuery, state: FSMContext):
    await safe_answer_callback(callback)
    now = now_tz()

    async with AsyncSessionLocal() as db:
        user = await require_registered_user(
            callback, db, callback.from_user.id, use_edit=True
        )
        if not user:
            return

        if callback.data.startswith("myb_swap_"):
            offer_booking_id = int(callback.data.split("_")[2])
            await state.update_data(offer_booking_id=offer_booking_id)
            offer_b = await db.get(Booking, offer_booking_id)
            if offer_b:
                offer_line = f"• {_slot_line(offer_b.date, offer_b.hour)}"
                text = (
                    f"🔄 *Slot Swap*\n\n"
                    f"*Offering:* {offer_line}\n\n"
                    "Pick a day you want to swap into."
                )
            else:
                text = "🔄 *Slot Swap*\n\nPick a day you want to swap into."
        else:
            await state.update_data(offer_booking_id=None)
            my_bookings = await _load_upcoming_bookings(db, user.id, now)
            text = (
                f"🔄 *Slot Swap*\n\n{_my_bookings_text(my_bookings)}\n\n"
                "Pick a day you want to swap into."
            )

    await state.set_state(SwapStates.waiting_day)
    today = now.date()
    week_dates = [d for d in get_current_week_dates() if d >= today]

    await edit_or_answer(
        callback,
        text,
        reply_markup=swap_pick_day_kb(week_dates),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("swap_day_"))
async def handle_swap_day_pick(callback: types.CallbackQuery, state: FSMContext):
    await safe_answer_callback(callback)
    weekday_idx = int(callback.data.split("_")[2])
    target_date = get_current_week_date(weekday_idx)

    await state.update_data(swap_target_date=target_date.isoformat())
    await state.set_state(SwapStates.waiting_hour)

    now = now_tz()
    data = await state.get_data()
    offer_booking_id = data.get("offer_booking_id")

    async with AsyncSessionLocal() as db:
        q = (
            select(Booking.hour)
            .where(Booking.date == target_date)
            .where(
                Booking.user_id
                != (
                    select(User.id)
                    .where(User.tg_user_id == callback.from_user.id)
                    .scalar_subquery()
                )
            )
        )
        all_hours = (await db.execute(q)).scalars().all()
        taken_hours = [
            h
            for h in all_hours
            if datetime.combine(target_date, time(h)).replace(tzinfo=ZoneInfo(TIMEZONE))
            > now
        ]

        offer_b = await db.get(Booking, offer_booking_id) if offer_booking_id else None

    offer_context = (
        f"\n*Offering:* {_slot_line(offer_b.date, offer_b.hour)}"
        if offer_b
        else ""
    )

    if not taken_hours:
        return await edit_or_answer(
            callback,
            f"🔄 *Slot Swap*\n\n"
            f"📭 No upcoming bookings on *{WEEKDAYS[weekday_idx]}* to swap with.{offer_context}",
            reply_markup=None,
            parse_mode="Markdown",
        )

    await edit_or_answer(
        callback,
        f"🔄 *Slot Swap*\n\n"
        f"📅 *{WEEKDAYS[weekday_idx]}* — pick a slot to request:{offer_context}",
        reply_markup=swap_hour_kb(taken_hours),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("swap_hour_"))
async def handle_swap_hour_pick(callback: types.CallbackQuery, state: FSMContext):
    await safe_answer_callback(callback)
    hour = int(callback.data.split("_")[2])
    data = await state.get_data()
    target_date_str = data["swap_target_date"]
    target_date = datetime.fromisoformat(target_date_str).date()

    async with AsyncSessionLocal() as db:
        # Find the booking we want to swap with
        q = (
            select(Booking, User)
            .join(User, User.id == Booking.user_id)
            .where(Booking.date == target_date, Booking.hour == hour)
        )
        res = (await db.execute(q)).first()
        if not res:
            return await edit_or_answer(
                callback,
                "🔄 *Slot Swap*\n\n"
                "That slot is no longer available for swap.\n\n"
                "Your bookings are unchanged.",
                reply_markup=None,
                parse_mode="Markdown",
            )

        target_booking, target_user = res

    offer_booking_id = data.get("offer_booking_id")
    if offer_booking_id is not None:
        async with AsyncSessionLocal() as db:
            me = (
                await db.execute(
                    select(User).where(User.tg_user_id == callback.from_user.id)
                )
            ).scalar_one_or_none()
        if me is None:
            return await edit_or_answer(
                callback,
                "Account not found. Please send /start.",
            )
        return await _do_create_swap_offer(
            callback,
            state,
            target_booking.id,
            offer_booking_id,
            giver_user_id=me.id,
        )

    async with AsyncSessionLocal() as db:
        me = (
            await db.execute(
                select(User).where(User.tg_user_id == callback.from_user.id)
            )
        ).scalar_one()
        now = now_tz()
        my_bookings = await _load_upcoming_bookings(db, me.id, now)

    if not my_bookings:
        return await edit_or_answer(
            callback,
            f"🔄 *Slot Swap*\n\n"
            f"*You want:* {_slot_line(target_date, hour)}\n\n"
            "📭 No upcoming bookings to offer in exchange.",
            reply_markup=None,
            parse_mode="Markdown",
        )

    builder = types.InlineKeyboardMarkup(inline_keyboard=[])
    for b in my_bookings:
        builder.inline_keyboard.append(
            [
                types.InlineKeyboardButton(
                    text=f"{WEEKDAYS[b.date.weekday()][:3]} {b.date} · {b.hour:02d}:00",
                    callback_data=f"swap_offer_{target_booking.id}_{b.id}",
                )
            ]
        )
    builder.inline_keyboard.append(
        [types.InlineKeyboardButton(text="⬅️ Back", callback_data="swap_start")]
    )

    await edit_or_answer(
        callback,
        f"🔄 *Slot Swap*\n\n"
        f"*You want:* {_slot_line(target_date, hour)}\n\n"
        "Which of your bookings do you offer in exchange?",
        reply_markup=builder,
        parse_mode="Markdown",
    )


async def _load_upcoming_bookings(db, user_id: int, now) -> list:
    all_b = (
        await db.execute(
            select(Booking)
            .where(Booking.user_id == user_id)
            .where(Booking.date >= now.date())
            .order_by(Booking.date, Booking.hour)
        )
    ).scalars().all()
    return [
        b for b in all_b
        if datetime.combine(b.date, time(b.hour)).replace(tzinfo=ZoneInfo(TIMEZONE)) > now
    ]


async def _do_create_swap_offer(
    callback: types.CallbackQuery,
    state: FSMContext,
    target_booking_id: int,
    my_booking_id: int,
    *,
    giver_user_id: int,
) -> None:
    async with AsyncSessionLocal() as db:
        result = await create_swap_offer(
            db,
            target_booking_id,
            my_booking_id,
            giver_user_id=giver_user_id,
        )

        if result.status == "missing_booking":
            return await edit_or_answer(
                callback,
                "🔄 *Slot Swap*\n\n"
                "One of the bookings was cancelled before the request could be sent.\n\n"
                "Your bookings are unchanged.",
                reply_markup=None,
                parse_mode="Markdown",
            )

        if result.receiver_tg_user_id and result.giver_display_name:
            try:
                await callback.bot.send_message(
                    result.receiver_tg_user_id,
                    "🔄 *Swap request*\n\n"
                    f"👤 *From:* {markdown_display(result.giver_display_name)}\n\n"
                    f"*They want:* {_slot_line(result.want_date, result.want_hour)}\n"
                    f"*They offer:* {_slot_line(result.give_date, result.give_hour)}\n\n"
                    "Accept to swap bookings instantly.",
                    reply_markup=swap_offer_kb(result.offer_id),
                    parse_mode="Markdown",
                )
            except Exception:
                log.exception("Failed to send swap offer notification")

    await state.clear()
    await edit_or_answer(
        callback,
        "✅ *Swap request sent*\n\n"
        f"*Offering:* {_slot_line(result.give_date, result.give_hour)}\n"
        f"*Requesting:* {_slot_line(result.want_date, result.want_hour)}\n\n"
        "You'll get a message when they respond.",
        reply_markup=None,
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("swap_offer_"))
async def handle_swap_offer(callback: types.CallbackQuery, state: FSMContext):
    await safe_answer_callback(callback)
    parts = callback.data.split("_")
    target_booking_id = int(parts[2])
    my_booking_id = int(parts[3])
    async with AsyncSessionLocal() as db:
        me = (
            await db.execute(select(User).where(User.tg_user_id == callback.from_user.id))
        ).scalar_one_or_none()
    if me is None:
        return await edit_or_answer(callback, "Account not found. Please send /start.")
    await _do_create_swap_offer(
        callback,
        state,
        target_booking_id,
        my_booking_id,
        giver_user_id=me.id,
    )


@router.callback_query(F.data.startswith("swap_accept_"))
async def handle_swap_accept(callback: types.CallbackQuery):
    offer_id = int(callback.data.split("_")[2])

    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.tg_user_id == callback.from_user.id))
        ).scalar_one_or_none()
        if user is None:
            await callback.answer("Account not found.", show_alert=True)
            return await edit_or_answer(
                callback,
                "Account not found. Please send /start.",
            )

        result = await accept_swap_offer(
            db,
            offer_id,
            receiver_user_id=user.id,
        )
        if result.status == "unavailable":
            await callback.answer("This offer is no longer valid.", show_alert=True)
            return await edit_or_answer(
                callback,
                "🔄 *Swap offer unavailable*\n\n"
                "This offer is no longer active. It may have expired, been cancelled, or already been handled.\n\n"
                "Your bookings are unchanged.",
                reply_markup=None,
                parse_mode="Markdown",
            )

        if result.status == "missing_booking":
            await callback.answer("One of the bookings was cancelled.", show_alert=True)
            return await edit_or_answer(
                callback,
                "🔄 *Swap offer unavailable*\n\n"
                "One of the bookings was cancelled before the swap could be completed.\n\n"
                "Your bookings are unchanged.",
                reply_markup=None,
                parse_mode="Markdown",
            )

        log.info(
            "Swap accepted",
            extra={
                "swap_offer_id": offer_id,
                "giver_user_id": result.giver_user_id,
                "receiver_user_id": result.receiver_user_id,
                "giver_new_date": result.giver_new_date.isoformat(),
                "giver_new_hour": result.giver_new_hour,
                "receiver_new_date": result.receiver_new_date.isoformat(),
                "receiver_new_hour": result.receiver_new_hour,
            },
        )

        if result.giver_tg_user_id:
            try:
                await callback.bot.send_message(
                    result.giver_tg_user_id,
                    "✅ *Swap accepted*\n\n"
                    f"*New booking:* {_slot_line(result.giver_new_date, result.giver_new_hour)}\n\n"
                    "Check My bookings to confirm.",
                    reply_markup=None,
                    parse_mode="Markdown",
                )
            except Exception:
                log.exception(
                    "Failed to notify swap giver about acceptance",
                    extra={
                        "swap_offer_id": offer_id,
                        "giver_user_id": result.giver_user_id,
                        "tg_user_id": result.giver_tg_user_id,
                    },
                )

    await edit_or_answer(
        callback,
        "✅ *Swap completed*\n\n"
        f"*New booking:* {_slot_line(result.receiver_new_date, result.receiver_new_hour)}",
        reply_markup=None,
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("swap_decline_"))
async def handle_swap_decline(callback: types.CallbackQuery):
    offer_id = int(callback.data.split("_")[2])

    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.tg_user_id == callback.from_user.id))
        ).scalar_one_or_none()
        if user is None:
            await callback.answer("Account not found.", show_alert=True)
            return await edit_or_answer(
                callback,
                "Account not found. Please send /start.",
            )

        async def notify_giver_after_commit(result: DeclinedSwapOffer) -> None:
            if not result.giver_tg_user_id:
                return
            try:
                await callback.bot.send_message(
                    result.giver_tg_user_id,
                    "❌ *Swap declined*\n\n"
                    f"*Your booking:* {_slot_line(result.give_date, result.give_hour)} — still active.",
                    reply_markup=None,
                    parse_mode="Markdown",
                )
            except Exception:
                log.exception(
                    "Failed to notify swap giver about decline",
                    extra={
                        "swap_offer_id": offer_id,
                        "giver_user_id": result.giver_user_id,
                        "tg_user_id": result.giver_tg_user_id,
                    },
                )

        result = await decline_swap_offer(
            db,
            offer_id,
            receiver_user_id=user.id,
            after_commit=notify_giver_after_commit,
        )
        if result.status == "declined":
            log.info(
                "Swap declined",
                extra={
                    "swap_offer_id": offer_id,
                    "giver_user_id": result.giver_user_id,
                },
            )

    if result.status == "declined":
        declined_text = (
            "❌ *Swap declined*\n\n"
            f"*Your booking:* {_slot_line(result.want_date, result.want_hour)} — unchanged.\n\n"
            "You can request a new swap anytime."
        )
    else:
        declined_text = (
            "🔄 *Swap offer unavailable*\n\n"
            "This offer is no longer active. It may have expired, been cancelled, or already been handled.\n\n"
            "Your bookings are unchanged."
        )

    await edit_or_answer(
        callback,
        declined_text,
        reply_markup=None,
        parse_mode="Markdown",
    )
