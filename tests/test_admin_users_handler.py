from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.bot.handlers.admin_users import (
    admin_users_confirm_add_admin,
    admin_users_confirm_unallow,
    admin_users_direct_action,
)
from app.models.user import User
from app.services.admin_user_commands import AddAdminResult, RevokeAccessResult


def _session_cm(db):
    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = db
    session_cm.__aexit__.return_value = False
    return session_cm


class AdminUsersHandlerTests(IsolatedAsyncioTestCase):
    async def test_direct_allow_uses_service_and_renders_existing_summary(self) -> None:
        callback = SimpleNamespace(
            data="admin_users_allow_direct_jane",
            bot=SimpleNamespace(),
            from_user=SimpleNamespace(id=1),
        )
        db = SimpleNamespace()
        user = User(tg_username="jane", allowed=True)

        with (
            patch("app.bot.handlers.admin_users.check_admin_callback", new=AsyncMock(return_value=True)),
            patch("app.bot.handlers.admin_users.safe_answer_callback", new=AsyncMock()),
            patch("app.bot.handlers.admin_users.AsyncSessionLocal", return_value=_session_cm(db)),
            patch("app.bot.handlers.admin_users.allow_user", new=AsyncMock(return_value=user)) as allow_user,
            patch("app.bot.handlers.admin_users.send_access_granted_dm", new=AsyncMock()) as send_dm,
            patch("app.bot.handlers.admin_users.render_user_summary", new=AsyncMock()) as render_user_summary,
            patch("app.bot.handlers.admin_users.edit_or_answer", new=AsyncMock()) as edit_or_answer,
        ):
            await admin_users_direct_action(callback)

        allow_user.assert_awaited_once_with(db, "jane")
        send_dm.assert_awaited_once_with(callback.bot, user.tg_user_id)
        render_user_summary.assert_awaited_once_with(callback, user)
        edit_or_answer.assert_not_awaited()

    async def test_confirm_unallow_kicks_returned_telegram_user_id(self) -> None:
        callback = SimpleNamespace(
            data="admin_users_confirm_unallow_jane",
            bot=SimpleNamespace(),
            from_user=SimpleNamespace(id=1),
        )
        db = SimpleNamespace()

        with (
            patch("app.bot.handlers.admin_users.check_admin_callback", new=AsyncMock(return_value=True)),
            patch("app.bot.handlers.admin_users.safe_answer_callback", new=AsyncMock()),
            patch("app.bot.handlers.admin_users.AsyncSessionLocal", return_value=_session_cm(db)),
            patch(
                "app.bot.handlers.admin_users.revoke_user_access",
                new=AsyncMock(return_value=RevokeAccessResult(user_found=True, tg_user_id=123)),
            ) as revoke_user_access,
            patch("app.bot.handlers.admin_users.kick_from_members_chat", new=AsyncMock()) as kick_from_members_chat,
            patch("app.bot.handlers.admin_users.edit_or_answer", new=AsyncMock()) as edit_or_answer,
        ):
            await admin_users_confirm_unallow(callback)

        revoke_user_access.assert_awaited_once_with(db, "jane")
        kick_from_members_chat.assert_awaited_once_with(callback.bot, 123)
        edit_or_answer.assert_awaited_once()
        self.assertEqual(edit_or_answer.await_args.args[1], "🚫 *Access revoked* — @jane")

    async def test_confirm_unallow_skips_kick_when_user_has_no_telegram_id(self) -> None:
        callback = SimpleNamespace(
            data="admin_users_confirm_unallow_jane",
            bot=SimpleNamespace(),
            from_user=SimpleNamespace(id=1),
        )
        db = SimpleNamespace()

        with (
            patch("app.bot.handlers.admin_users.check_admin_callback", new=AsyncMock(return_value=True)),
            patch("app.bot.handlers.admin_users.safe_answer_callback", new=AsyncMock()),
            patch("app.bot.handlers.admin_users.AsyncSessionLocal", return_value=_session_cm(db)),
            patch(
                "app.bot.handlers.admin_users.revoke_user_access",
                new=AsyncMock(return_value=RevokeAccessResult(user_found=True, tg_user_id=None)),
            ),
            patch("app.bot.handlers.admin_users.kick_from_members_chat", new=AsyncMock()) as kick_from_members_chat,
            patch("app.bot.handlers.admin_users.edit_or_answer", new=AsyncMock()),
        ):
            await admin_users_confirm_unallow(callback)

        kick_from_members_chat.assert_not_awaited()

    async def test_confirm_add_admin_maps_already_admin_result_to_existing_message(self) -> None:
        callback = SimpleNamespace(
            data="admin_users_confirm_addadmin_jane",
            bot=SimpleNamespace(),
            from_user=SimpleNamespace(id=1),
        )
        db = SimpleNamespace()

        with (
            patch("app.bot.handlers.admin_users.check_admin_callback", new=AsyncMock(return_value=True)),
            patch("app.bot.handlers.admin_users.safe_answer_callback", new=AsyncMock()),
            patch("app.bot.handlers.admin_users.AsyncSessionLocal", return_value=_session_cm(db)),
            patch(
                "app.bot.handlers.admin_users.add_admin_by_username",
                new=AsyncMock(return_value=AddAdminResult.ALREADY_ADMIN),
            ) as add_admin_by_username,
            patch("app.bot.handlers.admin_users.edit_or_answer", new=AsyncMock()) as edit_or_answer,
        ):
            await admin_users_confirm_add_admin(callback)

        add_admin_by_username.assert_awaited_once_with(db, "jane")
        edit_or_answer.assert_awaited_once()
        self.assertEqual(edit_or_answer.await_args.args[1], "This user is already an admin.")
