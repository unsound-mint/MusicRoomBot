# app/bot/handlers/admin_warnings.py
from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy import select

from app.bot.handlers.admin_shared import (
    AdminInputStates,
    check_admin_and_reply,
    check_admin_callback,
    get_user_by_username,
    render_user_summary,
)
from app.bot.keyboards.admin_inline_kb import (
    admin_back_kb,
    admin_confirm_kb,
    admin_next_actions_kb,
)
from app.bot.ui import edit_or_answer, safe_answer_callback
from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.services.warning_service import (
    MAX_WARNINGS,
    add_warning,
    format_effective_unban_at,
    remove_warning,
    reset_all_warnings,
    reset_user_warnings,
    revert_latest_warning,
)

router = Router()


def _warnings_next_kb():
    return admin_next_actions_kb(
        [
            ("List warned users", "admin_users_warn_list"),
            ("Reset all warnings", "admin_users_warn_reset_all"),
        ],
        back_data="admin_users",
        back_text="⬅️ Back to users",
    )


@router.message(Command("reset_all_warnings"))
async def cmd_reset_all_warnings(message: types.Message):
    if not await check_admin_and_reply(message):
        return
    await message.answer(
        "Reset warnings for all users?\n\nThis is intended for the annual warning reset.",
        reply_markup=admin_confirm_kb("admin_users_warn_reset_all_confirm", "admin_users"),
    )


@router.callback_query(F.data == "admin_users_warn_reset_all")
async def admin_warn_reset_all_prompt(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    await edit_or_answer(
        callback,
        "Reset warnings for all users?\n\nThis is intended for the annual warning reset.",
        reply_markup=admin_confirm_kb("admin_users_warn_reset_all_confirm", "admin_users"),
    )


@router.callback_query(F.data == "admin_users_warn_reset_all_confirm")
async def admin_warn_reset_all_confirm(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    async with AsyncSessionLocal() as db:
        count = await reset_all_warnings(db=db)
    await edit_or_answer(
        callback,
        f"All warnings reset.\nUsers updated: {count}",
        reply_markup=_warnings_next_kb(),
    )


@router.callback_query(F.data.startswith("admin_warn_add_direct_"))
async def admin_warn_add_direct(callback: types.CallbackQuery, state: FSMContext):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    username = callback.data.removeprefix("admin_warn_add_direct_")
    await state.set_state(AdminInputStates.waiting_reason)
    await state.update_data(admin_action="warn_add_reason", admin_username=username)
    await edit_or_answer(
        callback,
        f"Send a reason for warning @{username}.\n\nSend `-` to use the default reason.",
        reply_markup=admin_back_kb(f"admin_users_view_{username}"),
    )


@router.callback_query(F.data.startswith("admin_warn_remove_direct_"))
async def admin_warn_remove_direct(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    username = callback.data.removeprefix("admin_warn_remove_direct_")
    async with AsyncSessionLocal() as db:
        user = await get_user_by_username(db, username)
        if not user or user.id is None:
            return await edit_or_answer(
                callback,
                "User not found.",
                reply_markup=admin_back_kb("admin_users"),
            )
        new_count = await remove_warning(db=db, user_id=user.id)
        if new_count is None:
            return await edit_or_answer(
                callback,
                "Failed to update warnings.",
                reply_markup=admin_back_kb(f"admin_users_view_{username}"),
            )
        user.warnings = new_count
    await render_user_summary(callback, user)


@router.callback_query(F.data.startswith("admin_warn_revert_direct_"))
async def admin_warn_revert_direct(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    username = callback.data.removeprefix("admin_warn_revert_direct_")
    async with AsyncSessionLocal() as db:
        user = await get_user_by_username(db, username)
        if not user or user.id is None:
            return await edit_or_answer(
                callback,
                "User not found.",
                reply_markup=admin_back_kb("admin_users"),
            )
        revert_result = await revert_latest_warning(
            db=db,
            bot=callback.bot,
            user_db_id=user.id,
            decrement_ban_count=True,
        )
        if revert_result is None:
            return await edit_or_answer(
                callback,
                "Failed to revert warning/ban.",
                reply_markup=admin_back_kb(f"admin_users_view_{username}"),
            )
        user.warnings = revert_result.warnings
        user.ban_count = revert_result.ban_count
        user.banned = False
        user.banned_until = None
    await render_user_summary(callback, user)


@router.callback_query(F.data.startswith("admin_warn_reset_direct_"))
async def admin_warn_reset_direct(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    username = callback.data.removeprefix("admin_warn_reset_direct_")
    async with AsyncSessionLocal() as db:
        user = await get_user_by_username(db, username)
        if not user:
            return await edit_or_answer(
                callback,
                "User not found.",
                reply_markup=admin_back_kb("admin_users"),
            )
        if user.id is None:
            return await edit_or_answer(
                callback,
                "User not found.",
                reply_markup=admin_back_kb("admin_users"),
            )
        old = await reset_user_warnings(db=db, user_id=user.id)
        if old is None:
            return await edit_or_answer(
                callback,
                "Failed to reset warnings.",
                reply_markup=admin_back_kb(f"admin_users_view_{username}"),
            )
        user.warnings = 0
    await render_user_summary(callback, user)


@router.callback_query(F.data == "admin_warn_confirm_add_state")
async def admin_warn_confirm_add_state(callback: types.CallbackQuery, state: FSMContext):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    data = await state.get_data()
    username = data.get("admin_username")
    reason = data.get("admin_reason")
    if not username:
        await state.clear()
        return await edit_or_answer(
            callback,
            "Admin action expired.",
            reply_markup=admin_back_kb("admin_users"),
        )
    async with AsyncSessionLocal() as db:
        user = await get_user_by_username(db, username)
        if not user or user.id is None:
            await state.clear()
            return await edit_or_answer(
                callback,
                "User not found.",
                reply_markup=admin_back_kb("admin_users"),
            )
        new_count = await add_warning(
            db=db,
            bot=callback.bot,
            user_id=user.id,
            reason=reason or "Manual admin warning",
        )
    await state.clear()
    if new_count is None:
        return await edit_or_answer(
            callback,
            "Could not add warning.",
            reply_markup=admin_back_kb(f"admin_users_view_{username}"),
        )
    async with AsyncSessionLocal() as db:
        user = await get_user_by_username(db, username)
    if user:
        user.warnings = new_count
        await render_user_summary(callback, user)
    else:
        await edit_or_answer(
            callback,
            f"Warning added to @{username}.\nCurrent warnings: {new_count}/{MAX_WARNINGS}",
            reply_markup=admin_back_kb("admin_users"),
        )


@router.callback_query(F.data == "admin_users_warn_list")
async def admin_warn_list(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    async with AsyncSessionLocal() as db:
        users = (
            await db.execute(
                select(User)
                .where(User.warnings > 0)
                .order_by(User.warnings.desc(), User.full_name)
            )
        ).scalars().all()
    if not users:
        return await edit_or_answer(
            callback,
            "Warnings\n\nNo users have warnings.",
            reply_markup=admin_back_kb("admin_users"),
        )
    lines = ["Warnings", ""]
    for user in users:
        name = user.full_name or (f"@{user.tg_username}" if user.tg_username else f"id={user.id}")
        status = "BANNED" if user.banned else "allowed" if user.allowed else "no access"
        until = (
            f", until {format_effective_unban_at(user.banned_until)}"
            if user.banned_until
            else ""
        )
        lines.append(f"{name}: {user.warnings}/3 ({status}{until})")
    await edit_or_answer(callback, "\n".join(lines), reply_markup=admin_back_kb("admin_users"))
