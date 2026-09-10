# app/bot/handlers/admin_users.py
from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from app.bot.handlers.admin_shared import (
    AdminInputStates,
    check_admin_and_reply,
    check_admin_callback,
    format_user_page,
    get_user_by_username,
    prompt_for_text,
    render_user_page,
    render_user_summary,
    user_list_kb,
)
from app.bot.handlers.admin_user_messages import (
    add_admin_prompt_text,
    added_admin_text,
    admins_list_text,
    admins_menu_text,
    ban_confirm_text,
    banned_user_text,
    delete_confirm_text,
    deleted_user_text,
    find_user_prompt_text,
    revoked_access_text,
    unallow_confirm_text,
    user_list_empty_text,
)
from app.bot.keyboards.admin_inline_kb import (
    admin_admins_kb,
    admin_back_kb,
    admin_confirm_kb,
    admin_next_actions_kb,
)
from app.bot.markdown import MARKDOWN_PARSE_MODE
from app.bot.ui import edit_or_answer, safe_answer_callback
from app.core.database import AsyncSessionLocal
from app.services.admin_service import list_admins
from app.services.admin_user_commands import (
    AddAdminResult,
    add_admin_by_username,
    allow_user,
    ban_user,
    delete_user_by_username,
    revoke_user_access,
    unban_user,
)
from app.services.invite_service import send_access_granted_dm
from app.services.kick_service import kick_from_members_chat
from app.services.user_service import list_users
from app.services.warning_service import (
    format_effective_unban_at,
    unban_all_users,
)

router = Router()


def _users_next_kb():
    return admin_next_actions_kb(
        [
            ("Find user", "admin_users_find"),
            ("List users", "admin_users_list"),
        ],
        back_data="admin_users",
        back_text="⬅️ Back to users",
    )


def _admins_next_kb():
    return admin_next_actions_kb(
        [
            ("Add another admin", "admin_users_admins_add"),
            ("List admins", "admin_users_admins_list"),
        ],
        back_data="admin_users_admins",
        back_text="⬅️ Back to admins",
    )


@router.message(Command("unban_all_users"))
async def cmd_unban_all_users(message: types.Message):
    if not await check_admin_and_reply(message):
        return
    await message.answer(
        "Unban all banned users?\n\nAccess is not restored automatically.",
        reply_markup=admin_confirm_kb("admin_users_unban_all_confirm", "admin_users"),
    )


@router.callback_query(F.data == "admin_users_unban_all")
async def admin_users_unban_all_prompt(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    await edit_or_answer(
        callback,
        "Unban all banned users?\n\nAccess is not restored automatically.",
        reply_markup=admin_confirm_kb("admin_users_unban_all_confirm", "admin_users"),
    )


@router.callback_query(F.data == "admin_users_unban_all_confirm")
async def admin_users_unban_all_confirm(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    async with AsyncSessionLocal() as db:
        count = await unban_all_users(db=db)
    await edit_or_answer(
        callback,
        f"All users unbanned.\nUsers updated: {count}\n\nAccess was not restored automatically.",
        reply_markup=_users_next_kb(),
    )


@router.callback_query(F.data == "admin_users_admins")
async def admin_admins_menu(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    await edit_or_answer(
        callback,
        admins_menu_text(),
        reply_markup=admin_admins_kb(),
        parse_mode=MARKDOWN_PARSE_MODE,
    )


@router.callback_query(F.data == "admin_users_admins_list")
async def admin_admins_list(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    async with AsyncSessionLocal() as db:
        admins = await list_admins(db)
    text = admins_list_text(admins)
    await edit_or_answer(
        callback,
        text,
        reply_markup=admin_back_kb("admin_users_admins"),
        parse_mode=MARKDOWN_PARSE_MODE,
    )


@router.callback_query(F.data == "admin_users_admins_add")
async def admin_admins_add(callback: types.CallbackQuery, state: FSMContext):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    await prompt_for_text(
        callback,
        state,
        action="admin_add_admin",
        prompt=add_admin_prompt_text(),
        next_state=AdminInputStates.waiting_username,
        reply_markup=admin_back_kb("admin_users_admins"),
    )


@router.callback_query(F.data == "admin_users_find")
async def admin_users_find(callback: types.CallbackQuery, state: FSMContext):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    await prompt_for_text(
        callback,
        state,
        action="user_find",
        prompt=find_user_prompt_text(),
        next_state=AdminInputStates.waiting_username,
        reply_markup=admin_back_kb("admin_users"),
    )


@router.callback_query(F.data.startswith("admin_users_view_"))
async def admin_users_view(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    username = callback.data.removeprefix("admin_users_view_")
    async with AsyncSessionLocal() as db:
        user = await get_user_by_username(db, username)
    if user is None:
        return await edit_or_answer(
            callback,
            "User not found.",
            reply_markup=admin_back_kb("admin_users"),
        )
    await render_user_summary(callback, user)


@router.callback_query(F.data == "admin_users_list")
async def admin_users_list_menu(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    async with AsyncSessionLocal() as db:
        users = await list_users(db)
    await edit_or_answer(
        callback,
        format_user_page(users, 1) if users else user_list_empty_text(),
        reply_markup=user_list_kb(1, (len(users) - 1) // 50 + 1 if users else 1),
        parse_mode=MARKDOWN_PARSE_MODE if not users else None,
    )


@router.callback_query(F.data.startswith("userlist_prev_"))
async def userlist_prev(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    await render_user_page(callback, page)
    await callback.answer()


@router.callback_query(F.data.startswith("userlist_next_"))
async def userlist_next(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    await render_user_page(callback, page)
    await callback.answer()


@router.callback_query(F.data == "userlist_close")
async def userlist_close(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data.startswith("admin_users_allow_direct_"))
@router.callback_query(F.data.startswith("admin_users_unallow_direct_"))
@router.callback_query(F.data.startswith("admin_users_ban_direct_"))
@router.callback_query(F.data.startswith("admin_users_unban_direct_"))
@router.callback_query(F.data.startswith("admin_users_delete_direct_"))
async def admin_users_direct_action(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    action = ""
    username = ""
    for candidate in ("allow", "unallow", "ban", "unban", "delete"):
        prefix = f"admin_users_{candidate}_direct_"
        if callback.data.startswith(prefix):
            action = candidate
            username = callback.data.removeprefix(prefix)
            break

    if action == "delete":
        return await edit_or_answer(
            callback,
            delete_confirm_text(username),
            reply_markup=admin_confirm_kb(
                f"admin_users_confirm_delete_{username}",
                f"admin_users_view_{username}",
            ),
            parse_mode=MARKDOWN_PARSE_MODE,
        )
    if action == "unallow":
        return await edit_or_answer(
            callback,
            unallow_confirm_text(username),
            reply_markup=admin_confirm_kb(
                f"admin_users_confirm_unallow_{username}",
                f"admin_users_view_{username}",
            ),
            parse_mode=MARKDOWN_PARSE_MODE,
        )
    if action == "ban":
        return await edit_or_answer(
            callback,
            ban_confirm_text(username),
            reply_markup=admin_confirm_kb(
                f"admin_users_confirm_ban_{username}",
                f"admin_users_view_{username}",
            ),
            parse_mode=MARKDOWN_PARSE_MODE,
        )

    async with AsyncSessionLocal() as db:
        if action == "allow":
            user = await allow_user(db, username)
        elif action == "unban":
            user = await unban_user(db, username)
        else:
            user = None
        if user is None:
            return await edit_or_answer(
                callback,
                "User not found.",
                reply_markup=admin_back_kb("admin_users"),
            )
        if action == "allow":
            await send_access_granted_dm(callback.bot, user.tg_user_id)
        return await render_user_summary(callback, user)


@router.callback_query(F.data.startswith("admin_users_confirm_delete_"))
async def admin_users_confirm_delete(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    username = callback.data.removeprefix("admin_users_confirm_delete_")
    async with AsyncSessionLocal() as db:
        deleted = await delete_user_by_username(db, username)
        if not deleted:
            return await edit_or_answer(
                callback,
                "User not found.",
                reply_markup=admin_back_kb("admin_users"),
            )
    await edit_or_answer(
        callback,
        deleted_user_text(username),
        reply_markup=_users_next_kb(),
        parse_mode=MARKDOWN_PARSE_MODE,
    )


@router.callback_query(F.data.startswith("admin_users_confirm_unallow_"))
async def admin_users_confirm_unallow(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    username = callback.data.removeprefix("admin_users_confirm_unallow_")
    async with AsyncSessionLocal() as db:
        result = await revoke_user_access(db, username)
        if not result.user_found:
            return await edit_or_answer(
                callback,
                "User not found.",
                reply_markup=admin_back_kb("admin_users"),
            )
    if result.tg_user_id is not None:
        await kick_from_members_chat(callback.bot, result.tg_user_id)
    await edit_or_answer(
        callback,
        revoked_access_text(username),
        reply_markup=_users_next_kb(),
        parse_mode=MARKDOWN_PARSE_MODE,
    )


@router.callback_query(F.data.startswith("admin_users_confirm_ban_"))
async def admin_users_confirm_ban(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    username = callback.data.removeprefix("admin_users_confirm_ban_")
    async with AsyncSessionLocal() as db:
        result = await ban_user(db, username=username, bot=callback.bot, reason=None)
        if not result.user_found or result.ban_result is None:
            return await edit_or_answer(
                callback,
                "User not found.",
                reply_markup=admin_back_kb("admin_users"),
            )
    ban_result = result.ban_result
    await edit_or_answer(
        callback,
        banned_user_text(username)
        + f"\nBan #{ban_result.ban_count}: {ban_result.duration_months} month(s)."
        + f"\nUntil: {format_effective_unban_at(ban_result.banned_until)}",
        reply_markup=_users_next_kb(),
        parse_mode=MARKDOWN_PARSE_MODE,
    )


@router.callback_query(F.data.startswith("admin_users_confirm_addadmin_"))
async def admin_users_confirm_add_admin(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    username = callback.data.removeprefix("admin_users_confirm_addadmin_")
    async with AsyncSessionLocal() as db:
        result = await add_admin_by_username(db, username)
        if result is AddAdminResult.USER_NOT_FOUND:
            return await edit_or_answer(
                callback,
                "User not found in database.",
                reply_markup=admin_back_kb("admin_users_admins"),
            )
        if result is AddAdminResult.USER_NOT_STARTED:
            return await edit_or_answer(
                callback,
                "User must send /start before becoming admin.",
                reply_markup=admin_back_kb("admin_users_admins"),
            )
        if result is AddAdminResult.ALREADY_ADMIN:
            return await edit_or_answer(
                callback,
                "This user is already an admin.",
                reply_markup=admin_back_kb("admin_users_admins"),
            )
    await edit_or_answer(
        callback,
        added_admin_text(username),
        reply_markup=_admins_next_kb(),
        parse_mode=MARKDOWN_PARSE_MODE,
    )

