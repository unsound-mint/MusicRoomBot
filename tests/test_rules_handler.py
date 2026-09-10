from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.bot.handlers.rules import rules_handler


class RulesHandlerTests(IsolatedAsyncioTestCase):
    async def test_rules_handler_escapes_runtime_rules_text(self) -> None:
        message = SimpleNamespace(answer=AsyncMock())

        with patch(
            "app.bot.handlers.rules.get_runtime_config",
            new=AsyncMock(return_value="Use @music_room *carefully* [ok]"),
        ):
            await rules_handler(message)

        message.answer.assert_awaited_once_with(
            "📜 *MUSIC ROOM RULES*\n\nUse @music\\_room \\*carefully\\* \\[ok]",
            parse_mode="Markdown",
        )
