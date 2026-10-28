# app/bot/error_handler.py
import logging

from aiogram import Bot
from aiogram.types import ErrorEvent
from aiogram.types.update import UpdateTypeLookupError

log = logging.getLogger(__name__)

GENERIC_ERROR_TEXT = "Something went wrong. Please try again in a moment."


async def on_error(event: ErrorEvent, bot: Bot) -> bool:
    """Log any unhandled handler exception and tell the user something failed."""
    update = event.update
    message = update.message or (
        update.callback_query.message if update.callback_query else None
    )
    chat_id = message.chat.id if message else None
    try:
        update_type = update.event_type
    except UpdateTypeLookupError:
        update_type = "unknown"

    log.error(
        "Unhandled error while processing update",
        exc_info=event.exception,
        extra={
            "update_id": update.update_id,
            "update_type": update_type,
            "chat_id": chat_id,
        },
    )

    if update.callback_query:
        try:
            await update.callback_query.answer(GENERIC_ERROR_TEXT, show_alert=True)
            return True
        except Exception:
            log.warning("Failed to answer callback query after error", exc_info=True)

    if chat_id is not None:
        try:
            await bot.send_message(chat_id, GENERIC_ERROR_TEXT)
        except Exception:
            log.warning("Failed to send error message to chat", exc_info=True)

    return True
