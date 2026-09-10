from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from app.bot.constants.dates import WEEKDAYS
from app.bot.handlers.admin_shared import (
    AdminInputStates,
    check_admin_and_reply,
    check_admin_callback,
)
from app.bot.keyboards.admin_inline_kb import (
    admin_back_kb,
    admin_club_detail_kb,
    admin_club_list_kb,
    admin_confirm_kb,
    admin_next_actions_kb,
    hour_kb,
    weekday_kb,
)
from app.bot.markdown import markdown_display
from app.bot.ui import edit_or_answer, safe_answer_callback
from app.core.database import AsyncSessionLocal
from app.services.club_service import (
    add_leader_by_username,
    assign_weekly_slot_to_club,
    create_club,
    get_club,
    get_club_leaders,
    get_club_slots,
    list_clubs,
)
from app.services.config_service import get_working_hours

router = Router()


def _club_created_kb() -> types.InlineKeyboardMarkup:
    return admin_next_actions_kb(
        [("Add another club", "admin_clubs_add")],
        back_data="admin_clubs",
        back_text="⬅️ Back to clubs",
    )


def _club_detail_next_kb(club_id: int) -> types.InlineKeyboardMarkup:
    return admin_next_actions_kb(
        [
            ("Add another leader", f"admin_club_leader_add_{club_id}"),
            ("Assign weekly slot", f"admin_club_slot_add_{club_id}"),
        ],
        back_data=f"admin_club_view_{club_id}",
        back_text="⬅️ Back to club",
    )


async def _render_club_list(target: types.Message | types.CallbackQuery):
    async with AsyncSessionLocal() as db:
        clubs = await list_clubs(db)
    if not clubs:
        return await edit_or_answer(
            target,
            "Clubs\n\nNo clubs created yet.",
            reply_markup=admin_back_kb("admin_clubs"),
        )
    return await edit_or_answer(
        target,
        "Clubs\n\nChoose a club.",
        reply_markup=admin_club_list_kb(clubs),
    )


async def _render_club_detail(target: types.Message | types.CallbackQuery, club_id: int):
    async with AsyncSessionLocal() as db:
        club = await get_club(db, club_id)
        if club is None:
            return await edit_or_answer(
                target,
                "Club not found.",
                reply_markup=admin_back_kb("admin_clubs_list"),
            )
        leaders = await get_club_leaders(db, club_id)
        slots = await get_club_slots(db, club_id)

    leader_lines = [
        f"• {markdown_display(user.full_name or user.tg_username or str(user.id))}"
        for user in leaders
    ]
    slot_lines = [
        f"• {WEEKDAYS[slot.weekday]} {slot.hour:02d}:00"
        for slot in slots
    ]
    text = (
        f"Clubs\n\n*{markdown_display(club.name)}*\n\n"
        "*Leaders:*\n"
        f"{chr(10).join(leader_lines) if leader_lines else '_No leaders assigned._'}\n\n"
        "*Weekly slots:*\n"
        f"{chr(10).join(slot_lines) if slot_lines else '_No weekly slots assigned._'}"
    )
    return await edit_or_answer(
        target,
        text,
        reply_markup=admin_club_detail_kb(club_id),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "admin_clubs_list")
async def admin_clubs_list(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    await _render_club_list(callback)


@router.callback_query(F.data == "admin_clubs_add")
async def admin_clubs_add(callback: types.CallbackQuery, state: FSMContext):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    await state.set_state(AdminInputStates.waiting_club_name)
    await edit_or_answer(
        callback,
        "Clubs\n\nSend the club name.",
        reply_markup=admin_back_kb("admin_clubs"),
    )


@router.message(AdminInputStates.waiting_club_name)
async def admin_club_name_input(message: types.Message, state: FSMContext):
    if not await check_admin_and_reply(message):
        await state.clear()
        return
    async with AsyncSessionLocal() as db:
        status, club = await create_club(db, message.text or "")
    await state.clear()
    if status == "invalid":
        return await message.answer(
            "Club name cannot be empty.",
            reply_markup=admin_back_kb("admin_clubs"),
        )
    if status == "exists" and club is not None:
        return await message.answer(
            f"Club already exists: {club.name}",
            reply_markup=admin_next_actions_kb(
                [("View clubs", "admin_clubs_list")],
                back_data="admin_clubs",
                back_text="⬅️ Back to clubs",
            ),
        )
    assert club is not None
    return await message.answer(
        f"Club created: {club.name}",
        reply_markup=_club_created_kb(),
    )


@router.callback_query(F.data.startswith("admin_club_view_"))
async def admin_club_view(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    club_id = int(callback.data.split("_")[3])
    await _render_club_detail(callback, club_id)


@router.callback_query(F.data.startswith("admin_club_leader_add_"))
async def admin_club_leader_add(callback: types.CallbackQuery, state: FSMContext):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    club_id = int(callback.data.split("_")[4])
    await state.set_state(AdminInputStates.waiting_club_leader_username)
    await state.update_data(admin_club_id=club_id)
    await edit_or_answer(
        callback,
        "Clubs\n\nSend the leader's Telegram username, for example @username.",
        reply_markup=admin_back_kb(f"admin_club_view_{club_id}"),
    )


@router.message(AdminInputStates.waiting_club_leader_username)
async def admin_club_leader_username_input(message: types.Message, state: FSMContext):
    if not await check_admin_and_reply(message):
        await state.clear()
        return
    data = await state.get_data()
    club_id = int(data["admin_club_id"])
    async with AsyncSessionLocal() as db:
        status, user = await add_leader_by_username(db, club_id, message.text or "")
    await state.clear()
    if status == "invalid_username":
        return await message.answer(
            "Send a Telegram username like @username.",
            reply_markup=admin_back_kb(f"admin_club_view_{club_id}"),
        )
    if status == "user_not_found":
        return await message.answer(
            "I couldn't find that username in the bot.",
            reply_markup=admin_back_kb(f"admin_club_view_{club_id}"),
        )
    if status == "already_leader":
        return await message.answer(
            "That user is already a leader for this club.",
            reply_markup=admin_back_kb(f"admin_club_view_{club_id}"),
        )
    assert user is not None
    display = user.full_name or user.tg_username or str(user.id)
    return await message.answer(
        f"Leader added: {display}",
        reply_markup=_club_detail_next_kb(club_id),
    )


@router.callback_query(F.data.startswith("admin_club_slot_add_"))
async def admin_club_slot_add(callback: types.CallbackQuery, state: FSMContext):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    club_id = int(callback.data.split("_")[4])
    await state.update_data(admin_club_id=club_id)
    await edit_or_answer(
        callback,
        "Clubs\n\nChoose a weekday for this club slot.",
        reply_markup=weekday_kb("admin_club_slot_day", back_data=f"admin_club_view_{club_id}"),
    )


@router.callback_query(F.data.startswith("admin_club_slot_day_"))
async def admin_club_slot_day(callback: types.CallbackQuery, state: FSMContext):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    weekday_idx = int(callback.data.split("_")[4])
    data = await state.get_data()
    club_id = int(data["admin_club_id"])
    async with AsyncSessionLocal() as db:
        start_hour, end_hour = await get_working_hours(db, WEEKDAYS[weekday_idx])
    await state.update_data(admin_club_slot_weekday=weekday_idx)
    await edit_or_answer(
        callback,
        f"Clubs\n\n{WEEKDAYS[weekday_idx]}\nChoose an hour.",
        reply_markup=hour_kb(
            "admin_club_slot_hour",
            list(range(start_hour, end_hour)),
            back_data=f"admin_club_view_{club_id}",
        ),
    )


@router.callback_query(F.data.startswith("admin_club_slot_hour_"))
async def admin_club_slot_hour(callback: types.CallbackQuery, state: FSMContext):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    hour = int(callback.data.split("_")[4])
    data = await state.get_data()
    club_id = int(data["admin_club_id"])
    weekday_idx = int(data["admin_club_slot_weekday"])
    await edit_or_answer(
        callback,
        f"Assign {WEEKDAYS[weekday_idx]} {hour:02d}:00 to this club?",
        reply_markup=admin_confirm_kb(
            f"admin_club_slot_confirm_{club_id}_{weekday_idx}_{hour}",
            f"admin_club_view_{club_id}",
        ),
    )


@router.callback_query(F.data.startswith("admin_club_slot_confirm_"))
async def admin_club_slot_confirm(callback: types.CallbackQuery, state: FSMContext):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    _, _, _, _, club_id_s, weekday_s, hour_s = callback.data.split("_")
    club_id = int(club_id_s)
    weekday_idx = int(weekday_s)
    hour = int(hour_s)
    async with AsyncSessionLocal() as db:
        status, _slot = await assign_weekly_slot_to_club(
            db,
            club_id=club_id,
            weekday=weekday_idx,
            hour=hour,
        )
    await state.clear()
    if status != "assigned":
        return await edit_or_answer(
            callback,
            "Could not assign weekly slot.",
            reply_markup=admin_back_kb(f"admin_club_view_{club_id}"),
        )
    return await _render_club_detail(callback, club_id)
