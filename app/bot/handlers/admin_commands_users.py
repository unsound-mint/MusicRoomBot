import logging

from aiogram import Router, types
from aiogram.filters import Command
from sqlalchemy import select

from app.bot.handlers.admin_shared import (
    check_admin_and_reply,
    extract_username,
    format_user_page,
    get_user_by_username,
    parse_username_and_optional_name,
    user_list_kb,
)
from app.bot.markdown import markdown_display
from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.services.admin_service import list_admins
from app.services.admin_user_commands import (
    AddAdminResult,
    add_admin_by_username,
    allow_or_add_user,
    delete_user_by_username,
    revoke_user_access,
    unban_user,
)
from app.services.invite_service import send_access_granted_dm
from app.services.kick_service import kick_from_members_chat
from app.services.user_service import list_users
from app.services.warning_service import (
    apply_progressive_ban,
    format_effective_unban_at,
    notify_manual_ban,
)

router = Router()
log = logging.getLogger(__name__)


async def _send_access_granted_dm(message: types.Message, tg_user_id: int) -> bool:
    result = await send_access_granted_dm(message.bot, tg_user_id)
    return result.delivered

async def _allow_or_add_user(message: types.Message) -> None:
    if not await check_admin_and_reply(message):
        return

    username, full_name = parse_username_and_optional_name(message.text or "")
    if not username:
        await message.answer("Usage:\n/allow_user <@username> [Full Name]")
        return

    async with AsyncSessionLocal() as db:
        allow_result = await allow_or_add_user(
            db,
            username=username,
            full_name=full_name,
        )

    if allow_result.status == "banned":
        await message.answer("❌ User is banned. Unban first.")
        return
    if allow_result.status == "already_allowed":
        await message.answer(f"ℹ️ @{username} already has access.")
        return

    result = (
        f"✅ @{username} added."
        if allow_result.status == "created"
        else f"✅ @{username} updated."
    )
    if allow_result.did_allow:
        result += " Access granted."
    if allow_result.did_rename:
        result += " Full name updated."

    if not allow_result.did_allow:
        await message.answer(result)
        return

    tg_user_id = allow_result.tg_user_id
    if tg_user_id is None:
        await message.answer(
            result
            + "\n⚠️ Could not DM them the members chat link because their tg_user_id is unknown.\n"
            "They must send /start first."
        )
        return

    if await _send_access_granted_dm(message, tg_user_id):
        await message.answer(result + " Members chat link sent via DM.")
    else:
        await message.answer(
            result
            + "\n⚠️ Tried to DM the members chat link, but delivery failed (user may have blocked the bot)."
        )


@router.message(Command("add_admin"))
async def cmd_add_admin(message: types.Message):
    if not await check_admin_and_reply(message):
        return

    username = extract_username(message.text or "")
    if not username:
        await message.answer("Usage: /add_admin <@username>")
        return

    async with AsyncSessionLocal() as db:
        result = await add_admin_by_username(db, username)
        if result is AddAdminResult.USER_NOT_FOUND:
            await message.answer(
                "User not found in database.\nAsk them to send /start to the bot first."
            )
            return
        if result is AddAdminResult.USER_NOT_STARTED:
            await message.answer("User must send /start before becoming admin.")
            return
        if result is AddAdminResult.ALREADY_ADMIN:
            await message.answer("This user is already an admin.")
            return

    await message.answer(f"Admin added: @{username}")


@router.message(Command("list_admins"))
async def cmd_list_admins(message: types.Message):
    if not await check_admin_and_reply(message):
        return

    async with AsyncSessionLocal() as db:
        admins = await list_admins(db)
    if not admins:
        await message.answer("No admins found.")
        return

    text = "\n".join(f"{admin.tg_user_id} @{admin.tg_username or '-'}" for admin in admins)
    await message.answer("Admins:\n" + text)


@router.message(Command("list_users"))
async def cmd_list_users(message: types.Message):
    if not await check_admin_and_reply(message):
        return

    async with AsyncSessionLocal() as db:
        users = await list_users(db)
    if not users:
        await message.answer("No users found.")
        return

    total_pages = (len(users) - 1) // 50 + 1
    await message.answer(
        format_user_page(users, 1),
        reply_markup=user_list_kb(1, total_pages),
    )


@router.message(Command("delete_user"))
async def cmd_delete_user(message: types.Message):
    if not await check_admin_and_reply(message):
        return

    username = extract_username(message.text or "")
    if not username:
        await message.answer(
            "Usage:\n/delete_user <@username>\n\nExample:\n/delete_user @denis_shadow"
        )
        return

    if message.from_user.username and message.from_user.username.lower() == username:
        await message.answer("You cannot delete yourself.")
        return

    async with AsyncSessionLocal() as db:
        if not await delete_user_by_username(db, username):
            await message.answer("User not found in the database.")
            return

    await message.answer(f"User @{username} and all related data were deleted.")


@router.message(Command("allow_user"))
async def cmd_allow_user(message: types.Message):
    await _allow_or_add_user(message)


@router.message(Command("unallow_user"))
async def cmd_unallow_user(message: types.Message):
    if not await check_admin_and_reply(message):
        return

    username = extract_username(message.text or "")
    if not username:
        await message.answer("Usage: /unallow_user @username")
        return

    async with AsyncSessionLocal() as db:
        revoke_result = await revoke_user_access(db, username)
        if not revoke_result.user_found:
            await message.answer("User not found.")
            return
        if revoke_result.already_revoked:
            await message.answer("ℹ️ User already has no access.")
            return

    if revoke_result.tg_user_id is not None:
        await kick_from_members_chat(message.bot, revoke_result.tg_user_id)
    await message.answer(f"🚫 @{username} access revoked and user removed from members chat.")


@router.message(Command("ban_user"))
async def cmd_ban_user(message: types.Message):
    if not await check_admin_and_reply(message):
        return

    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Usage: /ban_user @username [reason]")
        return

    username = parts[1].lstrip("@").lower()
    reason = parts[2] if len(parts) == 3 else None

    async with AsyncSessionLocal() as db:
        user = await get_user_by_username(db, username)
        if not user:
            await message.answer("User not found.")
            return
        ban_result = await apply_progressive_ban(db=db, user=user, reason=reason)
        await notify_manual_ban(
            bot=message.bot,
            user=user,
            ban_result=ban_result,
            reason=reason,
        )

    await message.answer(
        f"⛔ @{username} has been BANNED."
        + (f"\nReason: {reason}" if reason else "")
        + f"\nBan #{ban_result.ban_count}: {ban_result.duration_months} month(s)."
        + f"\nUntil: {format_effective_unban_at(ban_result.banned_until)}"
    )


@router.message(Command("unban_user"))
async def cmd_unban_user(message: types.Message):
    if not await check_admin_and_reply(message):
        return

    username = extract_username(message.text or "")
    if not username:
        await message.answer("Usage: /unban_user @username")
        return

    async with AsyncSessionLocal() as db:
        user = await get_user_by_username(db, username)
        if not user:
            await message.answer("User not found.")
            return
        if not user.banned:
            await message.answer("ℹ️ User is not banned.")
            return
        await unban_user(db, username)

    await message.answer(
        f"✅ @{username} has been unbanned.\n⚠️ Access is NOT restored automatically."
    )


@router.message(Command("list_banned"))
async def cmd_list_banned(message: types.Message):
    if not await check_admin_and_reply(message):
        return

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(User).where(User.banned.is_(True)))).scalars().all()
    if not rows:
        await message.answer("✅ No banned users.")
        return

    text = "⛔ *Banned users:*\n"
    for user in rows:
        text += f"- @{markdown_display(user.tg_username, fallback='unknown')}"
        if user.ban_reason:
            text += f" — {markdown_display(user.ban_reason)}"
        if user.banned_until:
            text += f" until {format_effective_unban_at(user.banned_until)}"
        text += "\n"
    await message.answer(text, parse_mode="Markdown")
