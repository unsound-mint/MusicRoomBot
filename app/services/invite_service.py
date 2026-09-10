from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram import Bot

from app.services.config_runtime import get_runtime_config

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AccessGrantedDmResult:
    delivered: bool
    already_in_chat: bool
    invite_link_sent: bool
    invite_link_available: bool


async def create_member_invite(bot: Bot) -> str | None:
    member_chat_id = await get_runtime_config("member_chat_id")
    if not member_chat_id:
        return None

    invite = await bot.create_chat_invite_link(
        chat_id=member_chat_id,
        member_limit=1,  # one person only
        creates_join_request=False,
    )
    return invite.invite_link


async def is_user_in_member_chat(bot: Bot, tg_user_id: int) -> bool | None:
    """
    Return True if Telegram reports the user is already in the members chat.

    None means membership could not be checked, usually because member_chat_id is
    not configured or Telegram rejected the lookup. Callers should treat None as
    unknown and still send an invite link when possible.
    """
    member_chat_id = await get_runtime_config("member_chat_id")
    if not member_chat_id:
        return None

    try:
        member = await bot.get_chat_member(chat_id=member_chat_id, user_id=tg_user_id)
    except Exception:
        log.exception("Failed to check member chat membership", extra={"tg_user_id": tg_user_id})
        return None

    status = str(getattr(member, "status", "")).lower()
    if status in {"creator", "administrator", "member"}:
        return True
    if status == "restricted":
        return bool(getattr(member, "is_member", False))
    if status in {"left", "kicked"}:
        return False
    return None


async def send_access_granted_dm(
    bot: Bot,
    tg_user_id: int | None,
    *,
    intro: str = "✅ *Access granted*",
) -> AccessGrantedDmResult:
    """
    DM an access-granted notice and include a members-chat link only when needed.
    """
    if tg_user_id is None:
        return AccessGrantedDmResult(
            delivered=False,
            already_in_chat=False,
            invite_link_sent=False,
            invite_link_available=False,
        )

    already_in_chat = await is_user_in_member_chat(bot, tg_user_id)
    invite_link: str | None = None
    if already_in_chat is not True:
        try:
            invite_link = await create_member_invite(bot)
        except Exception:
            log.exception("Failed to create member invite", extra={"tg_user_id": tg_user_id})

    lines = [intro, "", "Send /start to begin using the bot."]
    if already_in_chat is True:
        lines.extend(["", "You are already in the members chat."])
    elif invite_link:
        lines.extend(["", "Members chat link:", invite_link])
    else:
        lines.extend(["", "Ask an admin for the members chat link."])

    try:
        await bot.send_message(tg_user_id, "\n".join(lines), parse_mode="Markdown")
    except Exception:
        log.exception("Failed to DM access grant", extra={"tg_user_id": tg_user_id})
        return AccessGrantedDmResult(
            delivered=False,
            already_in_chat=already_in_chat is True,
            invite_link_sent=False,
            invite_link_available=invite_link is not None,
        )

    return AccessGrantedDmResult(
        delivered=True,
        already_in_chat=already_in_chat is True,
        invite_link_sent=invite_link is not None,
        invite_link_available=invite_link is not None,
    )
