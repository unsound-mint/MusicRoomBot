from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.services.invite_service import (
    is_user_in_member_chat,
    send_access_granted_dm,
)


class InviteServiceTests(IsolatedAsyncioTestCase):
    async def test_send_access_granted_dm_sends_invite_when_user_not_in_chat(self) -> None:
        bot = SimpleNamespace(
            get_chat_member=AsyncMock(return_value=SimpleNamespace(status="left")),
            create_chat_invite_link=AsyncMock(
                return_value=SimpleNamespace(invite_link="https://t.me/+invite")
            ),
            send_message=AsyncMock(),
        )

        with patch("app.services.invite_service.get_runtime_config", new=AsyncMock(return_value=-100)):
            result = await send_access_granted_dm(bot, 123)

        self.assertTrue(result.delivered)
        self.assertFalse(result.already_in_chat)
        self.assertTrue(result.invite_link_sent)
        bot.get_chat_member.assert_awaited_once_with(chat_id=-100, user_id=123)
        bot.create_chat_invite_link.assert_awaited_once_with(
            chat_id=-100,
            member_limit=1,
            creates_join_request=False,
        )
        text = bot.send_message.await_args.args[1]
        self.assertIn("Members chat link", text)
        self.assertIn("https://t.me/+invite", text)

    async def test_send_access_granted_dm_skips_invite_when_user_already_in_chat(self) -> None:
        bot = SimpleNamespace(
            get_chat_member=AsyncMock(return_value=SimpleNamespace(status="member")),
            create_chat_invite_link=AsyncMock(),
            send_message=AsyncMock(),
        )

        with patch("app.services.invite_service.get_runtime_config", new=AsyncMock(return_value=-100)):
            result = await send_access_granted_dm(bot, 123)

        self.assertTrue(result.delivered)
        self.assertTrue(result.already_in_chat)
        self.assertFalse(result.invite_link_sent)
        bot.create_chat_invite_link.assert_not_awaited()
        text = bot.send_message.await_args.args[1]
        self.assertIn("already in the members chat", text)
        self.assertNotIn("Members chat link", text)

    async def test_is_user_in_member_chat_handles_restricted_membership_flag(self) -> None:
        bot = SimpleNamespace(
            get_chat_member=AsyncMock(return_value=SimpleNamespace(status="restricted", is_member=True)),
        )

        with patch("app.services.invite_service.get_runtime_config", new=AsyncMock(return_value=-100)):
            self.assertTrue(await is_user_in_member_chat(bot, 123))
