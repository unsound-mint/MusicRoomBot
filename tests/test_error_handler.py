from datetime import UTC, datetime
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from aiogram.types import CallbackQuery, Chat, ErrorEvent, Message, Update, User

from app.bot.error_handler import GENERIC_ERROR_TEXT, on_error

CHAT = Chat(id=42, type="private")
USER = User(id=42, is_bot=False, first_name="T")


def _message_update() -> Update:
    message = Message(message_id=1, date=datetime(2026, 5, 19, tzinfo=UTC), chat=CHAT, from_user=USER)
    return Update(update_id=10, message=message)


class ErrorHandlerTests(IsolatedAsyncioTestCase):
    async def test_message_update_logs_and_replies_in_chat(self) -> None:
        bot = AsyncMock()
        event = ErrorEvent(update=_message_update(), exception=RuntimeError("boom"))

        with self.assertLogs("app.bot.error_handler", level="ERROR") as logs:
            handled = await on_error(event, bot)

        self.assertTrue(handled)
        bot.send_message.assert_awaited_once_with(42, GENERIC_ERROR_TEXT)
        self.assertIn("Unhandled error", logs.output[0])

    async def test_callback_update_answers_the_callback(self) -> None:
        bot = AsyncMock()
        message = Message(message_id=1, date=datetime(2026, 5, 19, tzinfo=UTC), chat=CHAT)
        callback = CallbackQuery(
            id="c1", from_user=USER, chat_instance="x", message=message, data="d"
        )
        answer = AsyncMock()
        object.__setattr__(callback, "answer", answer)
        update = Update(update_id=11, callback_query=callback)

        with self.assertLogs("app.bot.error_handler", level="ERROR"):
            handled = await on_error(ErrorEvent(update=update, exception=ValueError()), bot)

        self.assertTrue(handled)
        answer.assert_awaited_once_with(GENERIC_ERROR_TEXT, show_alert=True)
        bot.send_message.assert_not_awaited()

    async def test_update_without_chat_only_logs(self) -> None:
        bot = AsyncMock()
        update = Update(update_id=12)

        with self.assertLogs("app.bot.error_handler", level="ERROR"):
            handled = await on_error(ErrorEvent(update=update, exception=ValueError()), bot)

        self.assertTrue(handled)
        bot.send_message.assert_not_awaited()

    async def test_failure_to_notify_user_does_not_raise(self) -> None:
        bot = AsyncMock()
        bot.send_message.side_effect = RuntimeError("blocked")

        with self.assertLogs("app.bot.error_handler", level="WARNING"):
            handled = await on_error(
                ErrorEvent(update=_message_update(), exception=ValueError()), bot
            )

        self.assertTrue(handled)
