# app/services/kick_service.py
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aiogram import Bot
else:
    Bot = Any

from app.services.config_runtime import get_runtime_config

log = logging.getLogger(__name__)


async def kick_from_members_chat(bot: Bot, tg_user_id: int):
    member_chat_id = await get_runtime_config("member_chat_id")
    if not member_chat_id or not tg_user_id:
        return

    try:
        await bot.ban_chat_member(member_chat_id, tg_user_id)
        await bot.unban_chat_member(member_chat_id, tg_user_id)
    except Exception:
        log.exception("Kick failed", extra={"tg_user_id": tg_user_id})
