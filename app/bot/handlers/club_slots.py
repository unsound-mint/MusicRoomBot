from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router, types

from app.bot.constants.dates import WEEKDAYS
from app.bot.keyboards.inline_kb import (
    club_list_kb,
    club_slot_detail_kb,
    club_slots_kb,
    club_week_kb,
)
from app.bot.ui import edit_or_answer, safe_answer_callback
from app.core.config import TIMEZONE
from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.services.club_service import (
    cancel_club_slot_occurrence,
    get_club,
    get_club_slot_occurrences,
    get_user_clubs,
)
from app.services.date_service import get_current_week_dates
from app.services.time_service import now_tz

router = Router()


async def _current_user(db, tg_user_id: int) -> User | None:
    from sqlalchemy import select

    return (
        await db.execute(select(User).where(User.tg_user_id == tg_user_id))
    ).scalar_one_or_none()


def _week_dates(week_key: str) -> list[date]:
    dates = list(get_current_week_dates())
    if week_key == "next":
        return [week_date + timedelta(days=7) for week_date in dates]
    return dates


def _week_title(week_key: str) -> str:
    return "Next week" if week_key == "next" else "This week"


async def _render_club_week_picker(
    target: types.Message | types.CallbackQuery,
    club_id: int,
    user: User,
):
    async with AsyncSessionLocal() as db:
        clubs = await get_user_clubs(db, user.id)
        if club_id not in {club.id for club in clubs}:
            return await edit_or_answer(target, "You do not manage this club.")
        club = await get_club(db, club_id)
        if club is None:
            return await edit_or_answer(target, "Club not found.")

    return await edit_or_answer(
        target,
        f"🎼 *{club.name}*\n\nChoose a week.",
        reply_markup=club_week_kb(club_id),
        parse_mode="Markdown",
    )


async def _render_club(
    target: types.Message | types.CallbackQuery,
    club_id: int,
    user: User,
    week_key: str,
):
    async with AsyncSessionLocal() as db:
        clubs = await get_user_clubs(db, user.id)
        if club_id not in {club.id for club in clubs}:
            return await edit_or_answer(target, "You do not manage this club.")
        club = await get_club(db, club_id)
        if club is None:
            return await edit_or_answer(target, "Club not found.")
        occurrences = await get_club_slot_occurrences(
            db,
            club_id,
            _week_dates(week_key),
        )

    if not occurrences:
        return await edit_or_answer(target, f"🎼 *{club.name}*\n\nNo weekly slots assigned.", parse_mode="Markdown")

    return await edit_or_answer(
        target,
        f"🎼 *{club.name}*\n\n{_week_title(week_key)}\nChoose a slot.",
        reply_markup=club_slots_kb(club_id, week_key, occurrences),
        parse_mode="Markdown",
    )


@router.message(F.text == "🎼 Club slots")
async def club_slots_home(message: types.Message):
    async with AsyncSessionLocal() as db:
        user = await _current_user(db, message.from_user.id)
        if user is None:
            return await message.answer("Account not found. Please send /start.")
        clubs = await get_user_clubs(db, user.id)

    if not clubs:
        return await message.answer("You are not assigned as a club leader.")
    if len(clubs) == 1:
        return await _render_club_week_picker(message, clubs[0].id, user)

    return await message.answer(
        "🎼 *Club slots*\n\nChoose a club.",
        reply_markup=club_list_kb(clubs),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "club_back")
async def club_back(callback: types.CallbackQuery):
    await safe_answer_callback(callback)
    async with AsyncSessionLocal() as db:
        user = await _current_user(db, callback.from_user.id)
        if user is None:
            return await edit_or_answer(callback, "Account not found. Please send /start.")
        clubs = await get_user_clubs(db, user.id)
    if len(clubs) == 1:
        return await _render_club_week_picker(callback, clubs[0].id, user)
    return await edit_or_answer(
        callback,
        "🎼 *Club slots*\n\nChoose a club.",
        reply_markup=club_list_kb(clubs),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("club_view_"))
async def club_view(callback: types.CallbackQuery):
    await safe_answer_callback(callback)
    club_id = int(callback.data.split("_")[2])
    async with AsyncSessionLocal() as db:
        user = await _current_user(db, callback.from_user.id)
    if user is None:
        return await edit_or_answer(callback, "Account not found. Please send /start.")
    return await _render_club_week_picker(callback, club_id, user)


@router.callback_query(F.data.startswith("club_week_"))
async def club_week(callback: types.CallbackQuery):
    await safe_answer_callback(callback)
    _, _, club_id_s, week_key = callback.data.split("_")
    club_id = int(club_id_s)
    async with AsyncSessionLocal() as db:
        user = await _current_user(db, callback.from_user.id)
    if user is None:
        return await edit_or_answer(callback, "Account not found. Please send /start.")
    return await _render_club(callback, club_id, user, week_key)


@router.callback_query(F.data.startswith("club_slot_"))
async def club_slot_detail(callback: types.CallbackQuery):
    await safe_answer_callback(callback)
    _, _, club_id_s, week_key, slot_id_s = callback.data.split("_")
    club_id = int(club_id_s)
    slot_id = int(slot_id_s)

    async with AsyncSessionLocal() as db:
        user = await _current_user(db, callback.from_user.id)
        if user is None:
            return await edit_or_answer(callback, "Account not found. Please send /start.")

        clubs = await get_user_clubs(db, user.id)
        club = next((item for item in clubs if item.id == club_id), None)
        if club is None:
            return await edit_or_answer(callback, "You do not manage this club.")
        occurrences = await get_club_slot_occurrences(db, club.id, _week_dates(week_key))
        for occurrence in occurrences:
            if occurrence.slot.id != slot_id:
                continue
            slot_dt = datetime.combine(
                occurrence.target_date,
                time(occurrence.slot.hour),
            ).replace(tzinfo=ZoneInfo(TIMEZONE))
            can_cancel = (
                slot_dt > now_tz()
                and not occurrence.is_cancelled
                and not occurrence.has_booking
            )
            status = f"cancelled {_week_title(week_key).lower()}" if occurrence.is_cancelled else "active"
            return await edit_or_answer(
                callback,
                (
                    f"🎼 *{club.name}*\n\n"
                    f"{_week_title(week_key)}\n"
                    f"{WEEKDAYS[occurrence.slot.weekday]}, "
                    f"{occurrence.slot.hour:02d}:00\n"
                    f"Status: {status}"
                ),
                reply_markup=club_slot_detail_kb(
                    club.id,
                    week_key,
                    occurrence.slot.id,
                    can_cancel=can_cancel,
                ),
                parse_mode="Markdown",
            )

    return await edit_or_answer(callback, "Slot not found.")


@router.callback_query(F.data.startswith("club_cancel_"))
async def club_cancel(callback: types.CallbackQuery):
    await safe_answer_callback(callback)
    _, _, club_id_s, week_key, slot_id_s = callback.data.split("_")
    club_id = int(club_id_s)
    slot_id = int(slot_id_s)

    async with AsyncSessionLocal() as db:
        user = await _current_user(db, callback.from_user.id)
        if user is None:
            return await edit_or_answer(callback, "Account not found. Please send /start.")
        occurrences = await get_club_slot_occurrences(db, club_id, _week_dates(week_key))
        occurrence = next((item for item in occurrences if item.slot.id == slot_id), None)
        if occurrence is None:
            return await edit_or_answer(callback, "Slot not found.")
        result = await cancel_club_slot_occurrence(
            db,
            club_id=club_id,
            weekly_slot_id=slot_id,
            target_date=occurrence.target_date,
            cancelled_by_user_id=user.id,
            require_leader=True,
        )

    if result == "cancelled":
        return await edit_or_answer(
            callback,
            f"✅ Club slot cancelled for {_week_title(week_key).lower()}.",
            parse_mode="Markdown",
        )
    messages = {
        "already_cancelled": f"This club slot is already cancelled for {_week_title(week_key).lower()}.",
        "past_slot": "Past club slots cannot be cancelled.",
        "booking_exists": "This slot already has a booking and cannot be cancelled as a club slot.",
        "not_allowed": "You do not manage this club.",
    }
    return await edit_or_answer(callback, messages.get(result, "Cancellation failed."))
