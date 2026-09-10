# app/bot/handlers/form_passed.py
import logging

from aiogram import Router, types
from aiogram.filters import Command

from app.core.database import AsyncSessionLocal
from app.services.admin_service import is_admin
from app.services.config_runtime import get_runtime_config
from app.services.form_pass_service import (
    grant_form_pass_access,
    parse_form_pass_command,
)
from app.services.invite_service import send_access_granted_dm

log = logging.getLogger(__name__)
router = Router()


async def _is_authorized_form_pass(message: types.Message) -> bool:
    """
    Authorization:
      - Admins can run /form_pass anywhere
      - Anyone can run /form_pass if the message is inside access_chat_id
        (admin chat is treated as a trusted boundary: e.g. Apps Script posts there)
    """
    if not message.from_user:
        return False

    access_chat_id = await get_runtime_config("access_chat_id")
    if access_chat_id and message.chat.id == int(access_chat_id):
        return True

    async with AsyncSessionLocal() as db:
        return await is_admin(db, message.from_user.id)


@router.message(Command("form_pass"))
async def handle_form_pass_cmd(message: types.Message) -> types.Message | None:
    """
    Usage:
      /form_pass @username 90 Full Name...

    Notes:
      - score may be "90" or "90%"
      - full name optional
      - command may include "@botname" suffix in Telegram, aiogram handles that
    """

    authorized = await _is_authorized_form_pass(message)
    if not authorized:
        return await message.answer("You do not have permission to use this command.")

    command = parse_form_pass_command(message.text)
    if isinstance(command, str):
        return await message.answer(command)

    async with AsyncSessionLocal() as db:
        grant = await grant_form_pass_access(
            db,
            username=command.username,
            full_name=command.full_name,
        )

        if grant.status == "not_found":
            return await message.answer(
                f"⚠️ Form passed but user @{command.username} not found in DB.\n"
                "They must send /start first (or their username in the form does not match their current Telegram username)."
            )

        if grant.status == "banned":
            return await message.answer(
                f"🚫 @{command.username} passed the form but is BANNED.\nAccess was NOT granted."
            )

        if grant.status == "already_allowed":
            return await message.answer(f"ℹ️ @{command.username} already has access.")

        tg_user_id = grant.tg_user_id
        saved_name = grant.saved_name

    # DM user if possible (best-effort). The shared helper sends a chat link
    # only when Telegram does not report them as already in the members chat.
    dm_result = await send_access_granted_dm(message.bot, tg_user_id)
    if tg_user_id and not dm_result.delivered:
        log.warning(
            "Failed to deliver form-pass access grant DM",
            extra={"username": command.username, "tg_user_id": tg_user_id},
        )

    # Acknowledge in the admin chat / wherever command was run
    extra = f"\nFull name saved: {saved_name}" if (command.full_name and saved_name) else ""
    log.info(
        "Form-pass access granted",
        extra={"username": command.username, "tg_user_id": tg_user_id},
    )
    return await message.answer(
        f"✅ Access granted to @{command.username} (score: {command.score}%)" + extra
    )
