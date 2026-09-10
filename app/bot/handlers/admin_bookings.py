# app/bot/handlers/admin_bookings.py
from contextlib import suppress
from datetime import date, timedelta

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select

from app.bot.constants.dates import WEEKDAYS
from app.bot.handlers.admin_booking_messages import (
    add_booking_no_dates_text,
    add_booking_no_hours_text,
    add_booking_pick_hour_text,
    add_booking_picker_text,
    add_booking_success_text,
    add_booking_username_prompt_text,
    bookings_for_day_text,
    bookings_menu_text,
    no_bookings_to_remove_text,
    no_weekly_slots_text,
    remove_booking_confirm_text,
    remove_booking_picker_text,
    removed_booking_picker_text,
    weekly_add_pick_hour_text,
    weekly_add_pick_weekday_text,
    weekly_create_confirm_text,
    weekly_draft_expired_text,
    weekly_group_prompt_text,
    weekly_slot_info,
    weekly_slot_invalid_text,
    weekly_slot_not_found_text,
    weekly_slot_remove_confirm_text,
    weekly_slot_removed_text,
    weekly_slot_set_text,
    weekly_slots_pick_remove_text,
)
from app.bot.handlers.admin_shared import (
    AdminInputStates,
    check_admin_and_reply,
    check_admin_callback,
    is_admin_by_tg_id,
    render_weekly_menu,
)
from app.bot.keyboards.admin_inline_kb import (
    admin_back_kb,
    admin_booking_date_kb,
    admin_booking_hour_kb,
    admin_bookings_kb,
    admin_confirm_kb,
    admin_next_actions_kb,
    hour_kb,
    weekday_kb,
    weekly_list_kb,
)
from app.bot.keyboards.inline_kb import remove_booking_day_selection_kb
from app.bot.markdown import MARKDOWN_PARSE_MODE, markdown_display
from app.bot.ui import edit_or_answer, safe_answer_callback
from app.core.database import AsyncSessionLocal
from app.models.booking import Booking
from app.models.club import Club, ClubSlotCancellation
from app.models.user import User
from app.models.weekly_slot import WeeklySlot
from app.services.admin_booking_service import (
    admin_bookable_dates,
    weekly_conflict_dates,
)
from app.services.booking_service import cancel_booking_by_admin, safe_create_booking
from app.services.club_service import (
    cancel_club_slot_occurrence,
    delete_admin_weekly_slot,
    is_weekly_reserved_for_date,
    set_admin_weekly_slot,
)
from app.services.config_service import get_working_hours
from app.services.date_service import (
    get_current_week_date,
    get_current_week_dates,
    is_future_slot,
)
from app.services.time_service import today_tz

router = Router()


def _weekly_next_kb():
    return admin_next_actions_kb(
        [
            ("Add weekly slot", "admin_weekly_add"),
            ("List weekly slots", "admin_weekly_list"),
        ],
        back_data="admin_bookings_weekly",
        back_text="⬅️ Back to weekly slots",
    )


def _booking_next_kb():
    return admin_next_actions_kb(
        [
            ("Add another booking", "admin_bookings_add"),
            ("Remove booking", "admin_bookings_remove"),
        ],
        back_data="admin_bookings",
        back_text="⬅️ Back to bookings",
    )


def _removable_dates() -> list[date]:
    current_week = list(get_current_week_dates())
    next_week = [week_date + timedelta(days=7) for week_date in current_week]
    return current_week + next_week


def _admin_bookable_dates() -> list[date]:
    return admin_bookable_dates(list(get_current_week_dates()), today_tz())


def _parse_remove_booking_date(value: str) -> date:
    if len(value) == 1:
        return get_current_week_date(int(value))
    return date.fromisoformat(value)


def _week_scope_text(target_date: date) -> str:
    current_week = set(get_current_week_dates())
    return "this week only" if target_date in current_week else "next week only"


def _weekly_conflict_dates(weekday_idx: int) -> list[date]:
    return weekly_conflict_dates(
        weekday_idx=weekday_idx,
        current_week_dates=list(get_current_week_dates()),
        today=today_tz(),
    )


async def _remove_booking_days_with_bookings(db) -> list[date]:
    removable_dates = _removable_dates()
    booking_rows = await db.execute(
        select(Booking.date)
        .where(Booking.date.in_(removable_dates))
        .distinct()
        .order_by(Booking.date)
    )
    dates = set(booking_rows.scalars().all())

    cancellation_rows = await db.execute(
        select(ClubSlotCancellation.weekly_slot_id, ClubSlotCancellation.date).where(
            ClubSlotCancellation.date.in_(removable_dates)
        )
    )
    cancelled = {
        (weekly_slot_id, cancellation_date)
        for weekly_slot_id, cancellation_date in cancellation_rows.all()
    }
    weekly_rows = await db.execute(select(WeeklySlot.id, WeeklySlot.weekday))
    for slot_id, weekday in weekly_rows.all():
        for target_date in removable_dates:
            if target_date.weekday() == weekday and (slot_id, target_date) not in cancelled:
                dates.add(target_date)
    return sorted(dates)


async def _render_remove_booking_day_picker(
    target: types.Message | types.CallbackQuery,
    *,
    text: str = remove_booking_picker_text(),
) -> types.Message | None:
    async with AsyncSessionLocal() as db:
        available_days = await _remove_booking_days_with_bookings(db)
    if not available_days:
        return await edit_or_answer(
            target,
            no_bookings_to_remove_text(),
            parse_mode=MARKDOWN_PARSE_MODE,
        )
    return await edit_or_answer(
        target,
        text,
        reply_markup=remove_booking_day_selection_kb(available_days),
        parse_mode=MARKDOWN_PARSE_MODE,
    )


async def _free_admin_booking_hours(db, target_date: date) -> list[int]:
    start_hour, end_hour = await get_working_hours(db, WEEKDAYS[target_date.weekday()])
    booked_rows = await db.execute(select(Booking.hour).where(Booking.date == target_date))
    booked_hours = set(booked_rows.scalars().all())

    free_hours: list[int] = []
    for hour in range(start_hour, end_hour):
        if not is_future_slot(target_date, hour):
            continue
        if hour in booked_hours:
            continue
        if await is_weekly_reserved_for_date(db, target_date, hour):
            continue
        free_hours.append(hour)
    return free_hours


async def _add_booking_dates_with_free_hours(db) -> list[date]:
    dates: list[date] = []
    for target_date in _admin_bookable_dates():
        if await _free_admin_booking_hours(db, target_date):
            dates.append(target_date)
    return dates


async def _render_add_booking_day_picker(
    target: types.Message | types.CallbackQuery,
    *,
    text: str = add_booking_picker_text(),
) -> types.Message | None:
    async with AsyncSessionLocal() as db:
        available_days = await _add_booking_dates_with_free_hours(db)
    if not available_days:
        return await edit_or_answer(
            target,
            add_booking_no_dates_text(),
            reply_markup=admin_back_kb("admin_bookings"),
            parse_mode=MARKDOWN_PARSE_MODE,
        )
    return await edit_or_answer(
        target,
        text,
        reply_markup=admin_booking_date_kb(
            available_days,
            callback_prefix="admin_bookadd_day",
        ),
        parse_mode=MARKDOWN_PARSE_MODE,
    )


async def _notify_admin_booking_user(bot, user: User, target_date: date, hour: int) -> None:
    if not user.tg_user_id:
        return
    with suppress(Exception):
        await bot.send_message(
            user.tg_user_id,
            (
                "✅ Booking added by admin.\n\n"
                f"🗓 {WEEKDAYS[target_date.weekday()]} ({target_date})\n"
                f"⏰ {hour:02d}:00"
            ),
        )


@router.message(Command("remove_booking"))
async def remove_booking_start(message: types.Message):
    if not await check_admin_and_reply(message):
        return
    await _render_remove_booking_day_picker(message)


@router.callback_query(F.data == "admin_bookings_add")
async def admin_add_booking_menu(callback: types.CallbackQuery, state: FSMContext):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    await state.clear()
    await _render_add_booking_day_picker(callback)


@router.callback_query(F.data.startswith("admin_bookadd_day_"))
async def admin_add_booking_day(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    target_date = date.fromisoformat(callback.data.split("_")[3])
    async with AsyncSessionLocal() as db:
        free_hours = await _free_admin_booking_hours(db, target_date)

    if not free_hours:
        return await edit_or_answer(
            callback,
            add_booking_no_hours_text(target_date),
            reply_markup=admin_back_kb("admin_bookings_add"),
            parse_mode=MARKDOWN_PARSE_MODE,
        )

    return await edit_or_answer(
        callback,
        add_booking_pick_hour_text(target_date),
        reply_markup=admin_booking_hour_kb(
            target_date,
            free_hours,
            callback_prefix="admin_bookadd_hour",
        ),
        parse_mode=MARKDOWN_PARSE_MODE,
    )


@router.callback_query(F.data.startswith("admin_bookadd_hour_"))
async def admin_add_booking_hour(callback: types.CallbackQuery, state: FSMContext):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    _, _, _, date_s, hour_s = callback.data.split("_")
    target_date = date.fromisoformat(date_s)
    hour = int(hour_s)
    async with AsyncSessionLocal() as db:
        free_hours = await _free_admin_booking_hours(db, target_date)
    if hour not in free_hours:
        return await edit_or_answer(
            callback,
            add_booking_no_hours_text(target_date),
            reply_markup=admin_back_kb("admin_bookings_add"),
            parse_mode=MARKDOWN_PARSE_MODE,
        )

    await state.set_state(AdminInputStates.waiting_booking_username)
    await state.update_data(
        admin_booking_date=target_date.isoformat(),
        admin_booking_hour=hour,
    )
    return await edit_or_answer(
        callback,
        add_booking_username_prompt_text(target_date, hour),
        reply_markup=admin_back_kb("admin_bookings_add"),
        parse_mode=MARKDOWN_PARSE_MODE,
    )


@router.message(AdminInputStates.waiting_booking_username)
async def admin_add_booking_username(message: types.Message, state: FSMContext):
    if not await check_admin_and_reply(message):
        await state.clear()
        return

    username = (message.text or "").strip().lstrip("@").lower()
    if not username:
        return await message.answer("Send a valid username like @username.")

    data = await state.get_data()
    target_date_s = data.get("admin_booking_date")
    hour = data.get("admin_booking_hour")
    if not isinstance(target_date_s, str) or not isinstance(hour, int):
        await state.clear()
        return await message.answer(
            "Booking draft expired. Start again.",
            reply_markup=admin_back_kb("admin_bookings"),
        )
    target_date = date.fromisoformat(target_date_s)

    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(func.lower(User.tg_username) == username))
        ).scalar_one_or_none()
        if user is None:
            return await message.answer(
                "User not found.",
                reply_markup=admin_back_kb("admin_bookings_add"),
            )
        if user.banned:
            return await message.answer(
                "User is banned.",
                reply_markup=admin_back_kb("admin_bookings_add"),
            )
        if not user.allowed:
            return await message.answer(
                "User does not have room access.",
                reply_markup=admin_back_kb("admin_bookings_add"),
            )

        status, booking = await safe_create_booking(
            db,
            user.id,
            target_date,
            hour,
            booking_source="admin",
        )
        if status == "limit":
            return await message.answer(
                "User has reached the weekly booking limit.",
                reply_markup=admin_back_kb("admin_bookings_add"),
            )
        if status == "taken" or booking is None:
            return await message.answer(
                "Slot is no longer available.",
                reply_markup=admin_back_kb("admin_bookings_add"),
            )

        await _notify_admin_booking_user(message.bot, user, target_date, hour)

    await state.clear()
    return await message.answer(
        add_booking_success_text(username, target_date, hour),
        reply_markup=_booking_next_kb(),
        parse_mode=MARKDOWN_PARSE_MODE,
    )


@router.callback_query(F.data.startswith("rmbday_"))
async def handle_remove_booking_day(callback: types.CallbackQuery):
    if not await is_admin_by_tg_id(callback.from_user.id):
        return await callback.answer("Admin only.", show_alert=True)

    target_date = _parse_remove_booking_date(callback.data.split("_")[1])
    weekday_idx = target_date.weekday()

    async with AsyncSessionLocal() as db:
        q = (
            select(Booking, User)
            .join(User, User.id == Booking.user_id)
            .where(Booking.date == target_date)
            .order_by(Booking.hour)
        )
        rows = (await db.execute(q)).all()
        cancelled_rows = await db.execute(
            select(ClubSlotCancellation.weekly_slot_id).where(
                ClubSlotCancellation.date == target_date
            )
        )
        cancelled_slot_ids = set(cancelled_rows.scalars().all())
        weekly_rows = (
            await db.execute(
                select(WeeklySlot, Club.name)
                .outerjoin(Club, Club.id == WeeklySlot.club_id)
                .where(WeeklySlot.weekday == weekday_idx)
                .order_by(WeeklySlot.hour)
            )
        ).all()

    if not rows and not weekly_rows:
        return await _render_remove_booking_day_picker(callback)

    builder = InlineKeyboardBuilder()
    for booking, user in rows:
        display = user.full_name or user.tg_username or f"ID:{user.id}"
        label = f"{booking.hour:02d}:00 - {display}"
        builder.button(text=label, callback_data=f"rmbconfirm_b_{booking.id}")
    booked_hours = {booking.hour for booking, _user in rows}
    for slot, club_name in weekly_rows:
        if slot.id in cancelled_slot_ids or slot.hour in booked_hours:
            continue
        display = club_name or slot.group_name
        label = f"{slot.hour:02d}:00 - {display} (weekly, {_week_scope_text(target_date)})"
        builder.button(
            text=label,
            callback_data=f"rmbconfirm_w_{slot.id}_{target_date.isoformat()}",
        )

    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="⬅️ Back", callback_data="rmb_back"))

    await callback.message.edit_text(
        bookings_for_day_text(weekday_idx, target_date),
        reply_markup=builder.as_markup(),
        parse_mode=MARKDOWN_PARSE_MODE,
    )


@router.callback_query(F.data == "rmb_back")
async def handle_remove_booking_back(callback: types.CallbackQuery):
    if not await is_admin_by_tg_id(callback.from_user.id):
        return await callback.answer("Admin only.", show_alert=True)
    await safe_answer_callback(callback)
    await _render_remove_booking_day_picker(callback)


@router.callback_query(F.data == "rmb_back_home")
async def handle_remove_booking_back_home(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    return await edit_or_answer(
        callback,
        bookings_menu_text(),
        reply_markup=admin_bookings_kb(),
        parse_mode=MARKDOWN_PARSE_MODE,
    )


@router.callback_query(F.data.startswith("rmbconfirm_"))
async def handle_remove_booking_confirm(callback: types.CallbackQuery):
    if not await is_admin_by_tg_id(callback.from_user.id):
        return await callback.answer("Admin only.", show_alert=True)

    parts = callback.data.split("_")
    item_kind = parts[1]

    async with AsyncSessionLocal() as db:
        if item_kind == "b":
            booking_id = int(parts[2])
            booking_row = (
                await db.execute(
                    select(Booking, User)
                    .join(User, User.id == Booking.user_id)
                    .where(Booking.id == booking_id)
                )
            ).first()
            if not booking_row:
                return await callback.answer("Booking not found.", show_alert=True)
            booking, user = booking_row
            info = (
                f"{WEEKDAYS[booking.date.weekday()]} "
                f"{booking.hour:02d}:00 - "
                f"{user.full_name or user.tg_username}"
            )
            confirm_data = f"rmbdo_b_{booking_id}"
        else:
            slot_id = int(parts[2])
            target_date = parts[3]
            weekly_row = (
                await db.execute(
                    select(WeeklySlot, Club.name)
                    .outerjoin(Club, Club.id == WeeklySlot.club_id)
                    .where(WeeklySlot.id == slot_id)
                )
            ).first()
            if not weekly_row:
                return await callback.answer("Weekly slot not found.", show_alert=True)
            slot, club_name = weekly_row
            info = (
                f"{WEEKDAYS[slot.weekday]} {slot.hour:02d}:00 - "
                f"{club_name or slot.group_name} (weekly, "
                f"{_week_scope_text(date.fromisoformat(target_date))})"
            )
            confirm_data = f"rmbdo_w_{slot_id}_{target_date}"
    await callback.message.edit_text(
        remove_booking_confirm_text(info),
        reply_markup=admin_confirm_kb(
            confirm_data,
            "rmb_back",
        ),
        parse_mode=MARKDOWN_PARSE_MODE,
    )


@router.callback_query(F.data.startswith("rmbdo_"))
async def handle_remove_booking_do(callback: types.CallbackQuery):
    if not await is_admin_by_tg_id(callback.from_user.id):
        return await callback.answer("Admin only.", show_alert=True)

    parts = callback.data.split("_")
    item_kind = parts[1]
    async with AsyncSessionLocal() as db:
        if item_kind == "b":
            booking_id = int(parts[2])
            booking_row = (
                await db.execute(
                    select(Booking, User)
                    .join(User, User.id == Booking.user_id)
                    .where(Booking.id == booking_id)
                )
            ).first()
            if not booking_row:
                return await callback.answer("Booking not found.", show_alert=True)
            booking, user = booking_row
            info = (
                f"{WEEKDAYS[booking.date.weekday()]} "
                f"{booking.hour:02d}:00 - "
                f"{user.full_name or user.tg_username}"
            )
            success = await cancel_booking_by_admin(
                db,
                booking.id,
                callback.bot,
                notify_reason="cancelled by an admin.",
            )
        else:
            slot_id = int(parts[2])
            target_date = _parse_remove_booking_date(parts[3])
            weekly_row = (
                await db.execute(
                    select(WeeklySlot, Club.name)
                    .outerjoin(Club, Club.id == WeeklySlot.club_id)
                    .where(WeeklySlot.id == slot_id)
                )
            ).first()
            if not weekly_row:
                return await callback.answer("Weekly slot not found.", show_alert=True)
            slot, club_name = weekly_row
            info = (
                f"{WEEKDAYS[slot.weekday]} {slot.hour:02d}:00 - "
                f"{club_name or slot.group_name} (weekly, {_week_scope_text(target_date)})"
            )
            admin_user = (
                await db.execute(select(User).where(User.tg_user_id == callback.from_user.id))
            ).scalar_one_or_none()
            if admin_user is None:
                return await callback.answer("Admin user not found.", show_alert=True)
            result = await cancel_club_slot_occurrence(
                db,
                club_id=slot.club_id or 0,
                weekly_slot_id=slot.id,
                target_date=target_date,
                cancelled_by_user_id=admin_user.id,
                require_leader=False,
            )
            success = result in {"cancelled", "already_cancelled"}

    if success:
        await callback.answer(f"Removed: {info}")
        await _render_remove_booking_day_picker(
            callback,
            text=removed_booking_picker_text(info),
        )
        return
    await callback.answer("Failed to remove booking.", show_alert=True)


@router.callback_query(F.data == "admin_bookings_remove")
async def admin_remove_booking_menu(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    await _render_remove_booking_day_picker(callback)


@router.callback_query(F.data == "admin_bookings_weekly")
async def admin_weekly_menu(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    await render_weekly_menu(callback)


@router.message(Command("list_weekly"))
async def list_weekly(message: types.Message):
    if not await check_admin_and_reply(message):
        return
    async with AsyncSessionLocal() as db:
        slots = (await db.execute(select(WeeklySlot))).scalars().all()
    if not slots:
        return await message.answer("No weekly slots.")
    lines = ["Weekly reserved slots:"]
    for slot in slots:
        if slot.weekday is not None:
            lines.append(f"{slot.id}: {WEEKDAYS[slot.weekday]} {slot.hour}:00 - {slot.group_name}")
    await message.answer("\n".join(lines))


@router.message(Command("remove_weekly"))
async def remove_weekly(message: types.Message):
    if not await check_admin_and_reply(message):
        return
    async with AsyncSessionLocal() as db:
        slots = (
            await db.execute(
                select(WeeklySlot).order_by(WeeklySlot.weekday, WeeklySlot.hour)
            )
        ).scalars().all()
    if not slots:
        return await message.answer("No weekly slots to remove.")
    await message.answer(
        "Select a weekly slot to remove:",
        reply_markup=weekly_list_kb(slots),
    )


@router.callback_query(F.data == "admin_weekly_list")
@router.callback_query(F.data == "admin_weekly_remove")
async def admin_weekly_list(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    async with AsyncSessionLocal() as db:
        slots = (
            await db.execute(
                select(WeeklySlot).order_by(WeeklySlot.weekday, WeeklySlot.hour)
            )
        ).scalars().all()

    if not slots:
        return await edit_or_answer(
            callback,
            no_weekly_slots_text(),
            reply_markup=admin_back_kb("admin_bookings_weekly"),
            parse_mode=MARKDOWN_PARSE_MODE,
        )

    return await edit_or_answer(
        callback,
        weekly_slots_pick_remove_text(),
        reply_markup=weekly_list_kb(slots),
        parse_mode=MARKDOWN_PARSE_MODE,
    )


@router.callback_query(F.data.startswith("admin_weekly_delete_"))
@router.callback_query(F.data.startswith("rmw_"))
async def admin_weekly_delete(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    slot_id = int(callback.data.split("_")[-1])

    async with AsyncSessionLocal() as db:
        slot = await db.get(WeeklySlot, slot_id)
        if not slot:
            return await edit_or_answer(
                callback,
                weekly_slot_not_found_text(),
                reply_markup=admin_back_kb("admin_bookings_weekly"),
                parse_mode=MARKDOWN_PARSE_MODE,
            )
        if slot.weekday is None:
            return await edit_or_answer(
                callback,
                weekly_slot_invalid_text(),
                reply_markup=admin_back_kb("admin_bookings_weekly"),
                parse_mode=MARKDOWN_PARSE_MODE,
            )
        info = weekly_slot_info(slot)
    return await edit_or_answer(
        callback,
        weekly_slot_remove_confirm_text(info),
        reply_markup=admin_confirm_kb(
            f"admin_weekly_rmconfirm_{slot_id}",
            "admin_bookings_weekly",
        ),
        parse_mode=MARKDOWN_PARSE_MODE,
    )


@router.callback_query(F.data.startswith("admin_weekly_rmconfirm_"))
async def admin_weekly_delete_confirm(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    slot_id = int(callback.data.split("_")[-1])

    async with AsyncSessionLocal() as db:
        result, slot = await delete_admin_weekly_slot(db, weekly_slot_id=slot_id)
        if result == "not_found" or slot is None:
            return await edit_or_answer(
                callback,
                weekly_slot_not_found_text(),
                reply_markup=admin_back_kb("admin_bookings_weekly"),
                parse_mode=MARKDOWN_PARSE_MODE,
            )
        if result == "invalid":
            return await edit_or_answer(
                callback,
                weekly_slot_invalid_text(),
                reply_markup=admin_back_kb("admin_bookings_weekly"),
                parse_mode=MARKDOWN_PARSE_MODE,
            )
        info = weekly_slot_info(slot)
    return await edit_or_answer(
        callback,
        weekly_slot_removed_text(info),
        reply_markup=_weekly_next_kb(),
        parse_mode=MARKDOWN_PARSE_MODE,
    )


@router.callback_query(F.data == "admin_weekly_add")
async def admin_weekly_add(callback: types.CallbackQuery, state: FSMContext):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    await state.update_data(admin_action="weekly_add")
    await edit_or_answer(
        callback,
        weekly_add_pick_weekday_text(),
        reply_markup=weekday_kb("admin_weekly_pickday", back_data="admin_bookings_weekly"),
        parse_mode=MARKDOWN_PARSE_MODE,
    )


@router.callback_query(F.data.startswith("admin_weekly_pickday_"))
async def admin_weekly_pickday(callback: types.CallbackQuery, state: FSMContext):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    weekday_idx = int(callback.data.split("_")[3])
    async with AsyncSessionLocal() as db:
        start_hour, end_hour = await get_working_hours(db, WEEKDAYS[weekday_idx])
    await state.update_data(admin_weekly_weekday=weekday_idx)
    await edit_or_answer(
        callback,
        weekly_add_pick_hour_text(weekday_idx),
        reply_markup=hour_kb(
            "admin_weekly_pickhour",
            list(range(start_hour, end_hour)),
            back_data="admin_weekly_add",
        ),
        parse_mode=MARKDOWN_PARSE_MODE,
    )


@router.callback_query(F.data.startswith("admin_weekly_pickhour_"))
async def admin_weekly_pickhour(callback: types.CallbackQuery, state: FSMContext):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    hour = int(callback.data.split("_")[3])
    data = await state.get_data()
    weekday_idx = int(data["admin_weekly_weekday"])
    await state.update_data(admin_weekly_hour=hour)
    await state.set_state(AdminInputStates.waiting_weekly_group)
    await edit_or_answer(
        callback,
        weekly_group_prompt_text(weekday_idx, hour),
        reply_markup=admin_back_kb("admin_weekly_add"),
        parse_mode=MARKDOWN_PARSE_MODE,
    )


@router.message(AdminInputStates.waiting_weekly_group)
async def admin_weekly_group_input(message: types.Message, state: FSMContext):
    if not await check_admin_and_reply(message):
        await state.clear()
        return

    group_name = (message.text or "").strip()
    if not group_name:
        return await message.answer("Group name cannot be empty.")

    data = await state.get_data()
    weekday_idx = int(data["admin_weekly_weekday"])
    hour = int(data["admin_weekly_hour"])
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(Booking, User)
                .join(User, User.id == Booking.user_id)
                .where(
                    Booking.date.in_(_weekly_conflict_dates(weekday_idx)),
                    Booking.hour == hour,
                )
                .order_by(Booking.date)
            )
        ).all()

    conflict_text = ""
    if rows:
        lines = ["\nConflicting bookings:"]
        for booking, user in rows:
            display = user.full_name or (
                f"@{user.tg_username}" if user.tg_username else f"id={user.id}"
            )
            lines.append(
                f"- {markdown_display(display)} on {WEEKDAYS[booking.date.weekday()]}, "
                f"{booking.date} at {booking.hour:02d}:00 will be cancelled"
            )
        conflict_text = "\n".join(lines)

    await message.answer(
        weekly_create_confirm_text(weekday_idx, hour, group_name, conflict_text),
        reply_markup=admin_confirm_kb(
            f"admin_weekly_confirm_{weekday_idx}_{hour}",
            "admin_bookings_weekly",
        ),
        parse_mode=MARKDOWN_PARSE_MODE,
    )
    await state.update_data(admin_weekly_group=group_name)


@router.callback_query(F.data.startswith("admin_weekly_confirm_"))
async def admin_weekly_confirm(callback: types.CallbackQuery, state: FSMContext):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    _, _, _, weekday_s, hour_s = callback.data.split("_")
    weekday_idx = int(weekday_s)
    hour = int(hour_s)
    data = await state.get_data()
    group_name = data.get("admin_weekly_group")
    if not group_name:
        return await edit_or_answer(
            callback,
            weekly_draft_expired_text(),
            reply_markup=admin_back_kb("admin_bookings_weekly"),
            parse_mode=MARKDOWN_PARSE_MODE,
        )

    cancelled_count = 0
    async with AsyncSessionLocal() as db:
        await set_admin_weekly_slot(
            db,
            weekday=weekday_idx,
            hour=hour,
            group_name=group_name,
        )

        bookings = (
            await db.execute(
                select(Booking)
                .where(
                    Booking.date.in_(_weekly_conflict_dates(weekday_idx)),
                    Booking.hour == hour,
                )
                .order_by(Booking.date)
            )
        ).scalars().all()
        for booking in bookings:
            if await cancel_booking_by_admin(
                db,
                booking.id,
                callback.bot,
                notify_reason="cancelled by admin because the slot became weekly reserved.",
            ):
                cancelled_count += 1

    await state.clear()
    message = weekly_slot_set_text(weekday_idx, hour, group_name, cancelled_count)
    await edit_or_answer(
        callback,
        message,
        reply_markup=_weekly_next_kb(),
        parse_mode=MARKDOWN_PARSE_MODE,
    )
