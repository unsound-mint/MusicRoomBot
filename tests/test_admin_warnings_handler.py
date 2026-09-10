from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.bot.handlers.admin_warnings import (
    admin_warn_remove_direct,
    admin_warn_reset_direct,
    admin_warn_revert_direct,
)


def _session_cm(db):
    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = db
    session_cm.__aexit__.return_value = False
    return session_cm


class AdminWarningsHandlerTests(IsolatedAsyncioTestCase):
    async def test_remove_direct_uses_full_username_and_renders_user_summary(self) -> None:
        callback = SimpleNamespace(
            data="admin_warn_remove_direct_jane_doe",
            bot=SimpleNamespace(),
            from_user=SimpleNamespace(id=1),
        )
        db = SimpleNamespace()
        user = SimpleNamespace(id=7, tg_username="jane_doe", warnings=2)

        with (
            patch("app.bot.handlers.admin_warnings.check_admin_callback", new=AsyncMock(return_value=True)),
            patch("app.bot.handlers.admin_warnings.safe_answer_callback", new=AsyncMock()),
            patch("app.bot.handlers.admin_warnings.AsyncSessionLocal", return_value=_session_cm(db)),
            patch("app.bot.handlers.admin_warnings.get_user_by_username", new=AsyncMock(return_value=user)) as get_user,
            patch("app.bot.handlers.admin_warnings.remove_warning", new=AsyncMock(return_value=1)) as remove_warning,
            patch("app.bot.handlers.admin_warnings.render_user_summary", new=AsyncMock()) as render_user_summary,
        ):
            await admin_warn_remove_direct(callback)

        get_user.assert_awaited_once_with(db, "jane_doe")
        remove_warning.assert_awaited_once_with(db=db, user_id=7)
        self.assertEqual(user.warnings, 1)
        render_user_summary.assert_awaited_once_with(callback, user)

    async def test_revert_direct_uses_full_username_and_renders_user_summary(self) -> None:
        callback = SimpleNamespace(
            data="admin_warn_revert_direct_jane_doe",
            bot=SimpleNamespace(),
            from_user=SimpleNamespace(id=1),
        )
        db = SimpleNamespace()
        user = SimpleNamespace(
            id=7,
            tg_username="jane_doe",
            warnings=3,
            ban_count=2,
            banned=True,
            banned_until=object(),
        )
        result = SimpleNamespace(warnings=2, ban_count=1)

        with (
            patch("app.bot.handlers.admin_warnings.check_admin_callback", new=AsyncMock(return_value=True)),
            patch("app.bot.handlers.admin_warnings.safe_answer_callback", new=AsyncMock()),
            patch("app.bot.handlers.admin_warnings.AsyncSessionLocal", return_value=_session_cm(db)),
            patch("app.bot.handlers.admin_warnings.get_user_by_username", new=AsyncMock(return_value=user)) as get_user,
            patch("app.bot.handlers.admin_warnings.revert_latest_warning", new=AsyncMock(return_value=result)) as revert_latest_warning,
            patch("app.bot.handlers.admin_warnings.render_user_summary", new=AsyncMock()) as render_user_summary,
        ):
            await admin_warn_revert_direct(callback)

        get_user.assert_awaited_once_with(db, "jane_doe")
        revert_latest_warning.assert_awaited_once_with(
            db=db,
            bot=callback.bot,
            user_db_id=7,
            decrement_ban_count=True,
        )
        self.assertEqual(user.warnings, 2)
        self.assertEqual(user.ban_count, 1)
        self.assertFalse(user.banned)
        self.assertIsNone(user.banned_until)
        render_user_summary.assert_awaited_once_with(callback, user)

    async def test_reset_direct_uses_full_username_and_renders_user_summary(self) -> None:
        callback = SimpleNamespace(
            data="admin_warn_reset_direct_jane_doe",
            bot=SimpleNamespace(),
            from_user=SimpleNamespace(id=1),
        )
        db = SimpleNamespace()
        user = SimpleNamespace(id=7, tg_username="jane_doe", warnings=2)

        with (
            patch("app.bot.handlers.admin_warnings.check_admin_callback", new=AsyncMock(return_value=True)),
            patch("app.bot.handlers.admin_warnings.safe_answer_callback", new=AsyncMock()),
            patch("app.bot.handlers.admin_warnings.AsyncSessionLocal", return_value=_session_cm(db)),
            patch("app.bot.handlers.admin_warnings.get_user_by_username", new=AsyncMock(return_value=user)) as get_user,
            patch("app.bot.handlers.admin_warnings.reset_user_warnings", new=AsyncMock(return_value=2)) as reset_user_warnings,
            patch("app.bot.handlers.admin_warnings.render_user_summary", new=AsyncMock()) as render_user_summary,
        ):
            await admin_warn_reset_direct(callback)

        get_user.assert_awaited_once_with(db, "jane_doe")
        reset_user_warnings.assert_awaited_once_with(db=db, user_id=7)
        self.assertEqual(user.warnings, 0)
        render_user_summary.assert_awaited_once_with(callback, user)
