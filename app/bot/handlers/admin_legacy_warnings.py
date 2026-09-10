from aiogram import Router, types
from aiogram.filters import Command
from sqlalchemy import select

from app.bot.handlers.admin_shared import (
    check_admin_and_reply,
    extract_username,
    get_user_by_username,
)
from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.services.warning_service import (
    add_warning,
    format_effective_unban_at,
    remove_warning,
    reset_user_warnings,
)

router = Router()


@router.message(Command("warnings"))
async def cmd_warnings(message: types.Message):
    if not await check_admin_and_reply(message):
        return

    username = extract_username(message.text or "")
    if not username:
        await message.answer("Usage: /warnings @username")
        return

    async with AsyncSessionLocal() as db:
        user = await get_user_by_username(db, username)
        if not user:
            await message.answer("User not found.")
            return

    await message.answer(
        f"👤 {user.full_name or '@' + username}\n"
        f"⚠️ Warnings: {user.warnings or 0}/3\n"
        f"🚫 Banned: {'YES' if user.banned else 'NO'}"
    )


@router.message(Command("add_warning"))
async def cmd_add_warning(message: types.Message):
    if not await check_admin_and_reply(message):
        return

    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Usage: /add_warning @username [reason]")
        return

    username = parts[1].lstrip("@").lower()
    reason = parts[2] if len(parts) == 3 else "Manual admin warning"

    async with AsyncSessionLocal() as db:
        user = await get_user_by_username(db, username)
        if not user:
            await message.answer("User not found.")
            return
        if user.banned:
            await message.answer(f"🚫 @{username} is already banned.")
            return
        if user.id is None:
            await message.answer("User record is invalid.")
            return
        new_count = await add_warning(db=db, bot=message.bot, user_id=user.id, reason=reason)

    if new_count is None:
        await message.answer("Could not add warning (user missing or already banned).")
        return
    await message.answer(f"⚠️ Warning added to @{username}.\nCurrent warnings: {new_count}/3")


@router.message(Command("remove_warning"))
async def cmd_remove_warning(message: types.Message):
    if not await check_admin_and_reply(message):
        return

    username = extract_username(message.text or "")
    if not username:
        await message.answer("Usage: /remove_warning @username")
        return

    async with AsyncSessionLocal() as db:
        user = await get_user_by_username(db, username)
        if not user:
            await message.answer("User not found.")
            return
        if user.id is None:
            await message.answer("User record is invalid.")
            return
        new_count = await remove_warning(db=db, user_id=user.id)

    if new_count is None:
        await message.answer("Failed to update warnings.")
        return
    await message.answer(f"➖ Warning removed from @{username}.\nCurrent warnings: {new_count}/3")


@router.message(Command("reset_warnings"))
async def cmd_reset_warnings(message: types.Message):
    if not await check_admin_and_reply(message):
        return

    username = extract_username(message.text or "")
    if not username:
        await message.answer("Usage: /reset_warnings @username")
        return

    async with AsyncSessionLocal() as db:
        user = await get_user_by_username(db, username)
        if not user:
            await message.answer("User not found.")
            return
        if user.id is None:
            await message.answer("User record is invalid.")
            return
        old = await reset_user_warnings(db=db, user_id=user.id)
        if old is None:
            await message.answer("Failed to reset warnings.")
            return

    await message.answer(f"✅ Warnings reset for @{username}.\nPrevious warnings: {old}")


@router.message(Command("list_warnings"))
async def cmd_list_warnings(message: types.Message):
    if not await check_admin_and_reply(message):
        return

    async with AsyncSessionLocal() as db:
        users = (
            await db.execute(
                select(User)
                .where(User.warnings > 0)
                .order_by(User.warnings.desc(), User.full_name)
            )
        ).scalars().all()
    if not users:
        await message.answer("✅ No users have warnings.")
        return

    lines = ["⚠️ Users with warnings:\n"]
    for user in users:
        name = user.full_name or (f"@{user.tg_username}" if user.tg_username else f"id={user.id}")
        status = "BANNED" if user.banned else "allowed" if user.allowed else "no access"
        until = (
            f"\n  Banned until: {format_effective_unban_at(user.banned_until)}"
            if user.banned_until
            else ""
        )
        lines.append(f"• {name}\n  Warnings: {user.warnings}/3\n  Status: {status}{until}\n")

    text = ""
    for line in lines:
        if len(text) + len(line) > 3800:
            await message.answer(text)
            text = ""
        text += line
    if text:
        await message.answer(text)
