# app/bot/handlers/admin_shared.py
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select

from app.bot.constants.dates import WEEKDAYS
from app.bot.keyboards.admin_inline_kb import (
    admin_bookings_kb,
    admin_bulk_kb,
    admin_clubs_kb,
    admin_config_kb,
    admin_home_kb,
    admin_system_kb,
    admin_user_actions_kb,
    admin_users_kb,
    admin_weekly_kb,
)
from app.bot.markdown import MARKDOWN_PARSE_MODE
from app.bot.ui import edit_or_answer
from app.core.database import AsyncSessionLocal
from app.models.booking import Booking
from app.models.user import User
from app.services.admin_service import is_admin
from app.services.user_service import list_users
from app.services.warning_service import format_effective_unban_at

USERS_PER_PAGE = 50


class BulkStates(StatesGroup):
    waiting_csv = State()


class AdminInputStates(StatesGroup):
    waiting_username = State()
    waiting_reason = State()
    waiting_full_name = State()
    waiting_custom_value = State()
    waiting_equipment_request_value = State()
    waiting_rules = State()
    waiting_geocenter = State()
    waiting_working_hours = State()
    waiting_weekly_group = State()
    waiting_booking_username = State()
    waiting_club_name = State()
    waiting_club_leader_username = State()


async def check_admin_and_reply(message: types.Message) -> bool:
    async with AsyncSessionLocal() as db:
        is_admin_user = await is_admin(db, message.from_user.id)

    if not is_admin_user:
        await message.answer("You do not have permission to use this command.")
        return False

    return True


async def check_admin_callback(callback: types.CallbackQuery) -> bool:
    async with AsyncSessionLocal() as db:
        allowed = await is_admin(db, callback.from_user.id)
    if not allowed:
        await callback.answer("Admin only.", show_alert=True)
        return False
    return True


async def is_admin_by_tg_id(tg_user_id: int) -> bool:
    async with AsyncSessionLocal() as db:
        return await is_admin(db, tg_user_id)


def extract_username(text: str) -> str | None:
    parts = text.split()
    if len(parts) < 2:
        return None
    return parts[1].lstrip("@").lower()


def canon_username(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    return value.lstrip("@").lower()


def parse_username_and_optional_name(text: str) -> tuple[str | None, str | None]:
    parts = (text or "").split(maxsplit=2)
    if len(parts) < 2:
        return (None, None)

    username = canon_username(parts[1])
    if not username:
        return (None, None)

    full_name = None
    if len(parts) >= 3:
        value = parts[2].strip()
        if value:
            full_name = value

    return (username, full_name)


def parse_username_input_and_optional_name(text: str) -> tuple[str | None, str | None]:
    parts = (text or "").strip().split(maxsplit=1)
    if not parts:
        return (None, None)

    username = canon_username(parts[0])
    if not username:
        return (None, None)

    full_name = None
    if len(parts) == 2:
        value = parts[1].strip()
        if value:
            full_name = value

    return (username, full_name)


async def get_user_by_username(db, username: str) -> User | None:
    return (
        await db.execute(select(User).where(User.tg_username == username))
    ).scalar_one_or_none()


async def find_users_by_full_name(db, query: str) -> list[User]:
    value = (query or "").strip()
    if not value:
        return []

    return list(
        (
            await db.execute(
                select(User)
                .where(User.full_name.is_not(None))
                .where(func.lower(User.full_name).contains(value.lower()))
                .order_by(
                    func.lower(func.coalesce(User.full_name, "")),
                    func.lower(func.coalesce(User.tg_username, "")),
                    User.id,
                )
            )
        ).scalars()
    )


async def render_admin_home(target: types.Message | types.CallbackQuery):
    return await edit_or_answer(
        target,
        "Admin\n\nChoose an area.",
        reply_markup=admin_home_kb(),
    )


async def render_users_menu(target: types.Message | types.CallbackQuery):
    return await edit_or_answer(
        target,
        "Users\n\nChoose an action.",
        reply_markup=admin_users_kb(),
    )


async def render_bookings_menu(target: types.Message | types.CallbackQuery):
    return await edit_or_answer(
        target,
        "Bookings\n\nChoose an action.",
        reply_markup=admin_bookings_kb(),
    )


async def render_clubs_menu(target: types.Message | types.CallbackQuery):
    return await edit_or_answer(
        target,
        "Clubs\n\nCreate clubs, assign leaders, and attach weekly slots.",
        reply_markup=admin_clubs_kb(),
    )


async def render_weekly_menu(target: types.Message | types.CallbackQuery):
    return await edit_or_answer(
        target,
        "Weekly slots\n\nChoose an action.",
        reply_markup=admin_weekly_kb(),
    )


async def render_config_menu(target: types.Message | types.CallbackQuery):
    return await edit_or_answer(
        target,
        "Config\n\nChoose a setting.",
        reply_markup=admin_config_kb(),
    )


async def render_system_menu(target: types.Message | types.CallbackQuery):
    return await edit_or_answer(
        target,
        "System\n\nChoose an action.",
        reply_markup=admin_system_kb(),
    )


async def render_bulk_menu(target: types.Message | types.CallbackQuery):
    return await edit_or_answer(
        target,
        "Bulk sync\n\nUpload the latest members CSV to update access.",
        reply_markup=admin_bulk_kb(),
    )


async def render_user_summary(target: types.Message | types.CallbackQuery, user: User):
    async with AsyncSessionLocal() as db:
        next_booking = (
            await db.execute(
                select(Booking)
                .where(Booking.user_id == user.id)
                .order_by(Booking.date, Booking.hour)
            )
        ).scalars().first()

    next_text = (
        f"{WEEKDAYS[next_booking.date.weekday()]}, {next_booking.date} at {next_booking.hour:02d}:00"
        if next_booking
        else "None"
    )

    return await edit_or_answer(
        target,
        (
            "User\n\n"
            f"Username: @{user.tg_username or '-'}\n"
            f"Full name: {user.full_name or '-'}\n"
            f"Access: {'allowed' if user.allowed else 'not allowed'}\n"
            f"Banned: {'yes' if user.banned else 'no'}\n"
            f"Ban count: {user.ban_count or 0}\n"
            f"Banned until: {format_effective_unban_at(user.banned_until) if user.banned_until else '-'}\n"
            f"Warnings: {user.warnings or 0}/3\n"
            f"Next booking: {next_text}"
        ),
        reply_markup=admin_user_actions_kb(
            user.tg_username or "",
            banned=bool(user.banned),
            allowed=bool(user.allowed),
        ),
    )


async def prompt_for_text(
    callback: types.CallbackQuery,
    state: FSMContext,
    *,
    action: str,
    prompt: str,
    next_state: State,
    reply_markup,
    extra: dict | None = None,
):
    await state.set_state(next_state)
    payload = {"admin_action": action}
    if extra:
        payload.update(extra)
    await state.update_data(**payload)
    return await edit_or_answer(
        callback,
        prompt,
        reply_markup=reply_markup,
        parse_mode=MARKDOWN_PARSE_MODE,
    )


def user_list_kb(page: int, total_pages: int):
    kb = InlineKeyboardBuilder()
    if page > 1:
        kb.button(text="« Prev", callback_data=f"userlist_prev_{page - 1}")
    if page < total_pages:
        kb.button(text="Next »", callback_data=f"userlist_next_{page + 1}")
    kb.button(text="Close", callback_data="userlist_close")
    kb.adjust(3)
    return kb.as_markup()


def format_user_page(users, page: int):
    start = (page - 1) * USERS_PER_PAGE
    end = start + USERS_PER_PAGE
    chunk = users[start:end]
    lines = [f"Users (page {page}/{(len(users) - 1) // USERS_PER_PAGE + 1}):\n"]
    for user in chunk:
        uname = f"@{user.tg_username}" if user.tg_username else "(no username)"
        fname = user.full_name or "(no name)"
        lines.append(f"- {fname} {uname} — allowed={user.allowed}")
    return "\n".join(lines)


async def render_user_page(target: types.CallbackQuery, page: int) -> None:
    async with AsyncSessionLocal() as db:
        users = await list_users(db)
    total_pages = (len(users) - 1) // USERS_PER_PAGE + 1 if users else 1
    page = max(1, min(page, total_pages))
    await target.message.edit_text(
        format_user_page(users, page) if users else "Users\n\nNo users found.",
        reply_markup=user_list_kb(page, total_pages),
    )
