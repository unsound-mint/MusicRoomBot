from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from app.models.user import User
from app.services.admin_user_commands import (
    AddAdminResult,
    add_admin_by_username,
    allow_or_add_user,
    allow_user,
    delete_user_by_username,
    revoke_user_access,
    sync_allowed_members_from_usernames,
    unban_user,
)


class AdminUserCommandsTests(IsolatedAsyncioTestCase):
    async def test_allow_user_restores_access_and_clears_ban(self) -> None:
        user = User(
            tg_username="jane",
            allowed=False,
            banned=True,
            ban_reason="late",
        )
        user.banned_until = SimpleNamespace()
        db = SimpleNamespace(commit=AsyncMock())

        with patch(
            "app.services.admin_user_commands._get_user_by_username",
            new=AsyncMock(return_value=user),
        ):
            result = await allow_user(db, "jane")

        self.assertIs(result, user)
        self.assertTrue(user.allowed)
        self.assertFalse(user.banned)
        self.assertIsNone(user.ban_reason)
        self.assertIsNone(user.banned_until)
        db.commit.assert_awaited_once()

    async def test_unban_user_clears_ban_and_warnings_without_granting_access(self) -> None:
        user = User(
            tg_username="jane",
            allowed=False,
            banned=True,
            ban_reason="late",
            warnings=3,
        )
        user.banned_until = SimpleNamespace()
        db = SimpleNamespace(commit=AsyncMock())

        with patch(
            "app.services.admin_user_commands._get_user_by_username",
            new=AsyncMock(return_value=user),
        ):
            result = await unban_user(db, "jane")

        self.assertIs(result, user)
        self.assertFalse(user.allowed)
        self.assertFalse(user.banned)
        self.assertIsNone(user.ban_reason)
        self.assertIsNone(user.banned_until)
        self.assertEqual(user.warnings, 0)
        db.commit.assert_awaited_once()

    async def test_revoke_user_access_returns_tg_user_id_for_chat_kick(self) -> None:
        user = User(tg_user_id=123, tg_username="jane", allowed=True)
        db = SimpleNamespace(commit=AsyncMock())

        with patch(
            "app.services.admin_user_commands._get_user_by_username",
            new=AsyncMock(return_value=user),
        ):
            result = await revoke_user_access(db, "jane")

        self.assertTrue(result.user_found)
        self.assertEqual(result.tg_user_id, 123)
        self.assertFalse(user.allowed)
        db.commit.assert_awaited_once()

    async def test_revoke_user_access_noops_when_already_revoked(self) -> None:
        user = User(tg_user_id=123, tg_username="jane", allowed=False)
        db = SimpleNamespace(commit=AsyncMock())

        with patch(
            "app.services.admin_user_commands._get_user_by_username",
            new=AsyncMock(return_value=user),
        ):
            result = await revoke_user_access(db, "jane")

        self.assertTrue(result.user_found)
        self.assertTrue(result.already_revoked)
        self.assertEqual(result.tg_user_id, 123)
        db.commit.assert_not_awaited()

    async def test_allow_or_add_user_creates_placeholder_user(self) -> None:
        scalars = SimpleNamespace(all=lambda: [])
        db = SimpleNamespace(
            execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: scalars)),
            add=Mock(),
            commit=AsyncMock(),
        )

        result = await allow_or_add_user(db, username="@Jane", full_name="Jane Doe")

        self.assertEqual(result.status, "created")
        self.assertEqual(result.user.tg_username, "jane")
        self.assertEqual(result.user.full_name, "Jane Doe")
        self.assertTrue(result.user.allowed)
        db.commit.assert_awaited_once()

    async def test_bulk_sync_revokes_non_sheet_non_admin_users(self) -> None:
        admin = User(tg_user_id=1, tg_username="admin", allowed=True)
        revoked = User(tg_user_id=2, tg_username="old", allowed=True)
        kept = User(tg_user_id=3, tg_username="kept", allowed=True)
        admin_ids = SimpleNamespace(all=lambda: [1])
        users = SimpleNamespace(all=lambda: [admin, revoked, kept])
        db = SimpleNamespace(
            execute=AsyncMock(
                side_effect=[
                    SimpleNamespace(scalars=lambda: admin_ids),
                    SimpleNamespace(scalars=lambda: users),
                ]
            ),
            add=Mock(),
            commit=AsyncMock(),
        )

        result = await sync_allowed_members_from_usernames(db, {"kept"})

        self.assertEqual(result.updated_revoked, 1)
        self.assertEqual(result.revoked_admins_skipped, 1)
        self.assertFalse(revoked.allowed)
        self.assertTrue(kept.allowed)
        self.assertTrue(admin.allowed)
        self.assertEqual(result.revoked_users[0].tg_user_id, 2)
        db.commit.assert_awaited_once()

    async def test_delete_user_removes_swap_offers_bookings_and_user(self) -> None:
        user = User(id=7, tg_username="jane")
        db = SimpleNamespace(
            execute=AsyncMock(),
            delete=AsyncMock(),
            commit=AsyncMock(),
        )

        with patch(
            "app.services.admin_user_commands._get_user_by_username",
            new=AsyncMock(return_value=user),
        ):
            deleted = await delete_user_by_username(db, "jane")

        self.assertTrue(deleted)
        self.assertEqual(db.execute.await_count, 2)
        db.delete.assert_awaited_once_with(user)
        db.commit.assert_awaited_once()

    async def test_add_admin_by_username_requires_started_user(self) -> None:
        user = User(tg_username="jane", tg_user_id=None)
        db = SimpleNamespace()

        with (
            patch(
                "app.services.admin_user_commands._get_user_by_username",
                new=AsyncMock(return_value=user),
            ),
            patch("app.services.admin_user_commands.add_admin", new=AsyncMock()) as add_admin,
        ):
            result = await add_admin_by_username(db, "jane")

        self.assertIs(result, AddAdminResult.USER_NOT_STARTED)
        add_admin.assert_not_awaited()

    async def test_add_admin_by_username_delegates_admin_creation(self) -> None:
        user = User(tg_username="jane", tg_user_id=123)
        db = SimpleNamespace()

        with (
            patch(
                "app.services.admin_user_commands._get_user_by_username",
                new=AsyncMock(return_value=user),
            ),
            patch("app.services.admin_user_commands.add_admin", new=AsyncMock()) as add_admin,
        ):
            result = await add_admin_by_username(db, "jane")

        self.assertIs(result, AddAdminResult.ADDED)
        add_admin.assert_awaited_once_with(db, 123, "jane")

    async def test_missing_user_results_do_not_commit(self) -> None:
        db = SimpleNamespace(commit=AsyncMock(), delete=AsyncMock(), execute=AsyncMock())

        with patch(
            "app.services.admin_user_commands._get_user_by_username",
            new=AsyncMock(return_value=None),
        ):
            self.assertIsNone(await allow_user(db, "missing"))
            self.assertFalse(await delete_user_by_username(db, "missing"))
            revoke_result = await revoke_user_access(db, "missing")

        self.assertFalse(revoke_result.user_found)
        db.commit.assert_not_awaited()
        db.delete.assert_not_awaited()
        db.execute.assert_not_awaited()
