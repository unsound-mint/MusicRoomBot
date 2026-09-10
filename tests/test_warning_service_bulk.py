from datetime import datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

from app.services.warning_service import (
    add_warning,
    apply_progressive_ban,
    effective_unban_at,
    reset_all_warnings,
    reset_user_warnings,
    revert_latest_warning,
    unban_all_users,
    unban_expired_users,
)


class _Result:
    def __init__(self, *, value=None, row=None, rows=None) -> None:
        self.value = value
        self.row = row
        self.rows = rows or []

    def scalar_one_or_none(self):
        return self.value

    def first(self):
        return self.row

    def fetchall(self):
        return self.rows


class _FakeDb:
    def __init__(self, *results) -> None:
        self.results = list(results)
        self.add = Mock()
        self.commit = AsyncMock()

    async def execute(self, _stmt):
        return self.results.pop(0)


class WarningServiceBulkTests(IsolatedAsyncioTestCase):
    async def test_reset_all_warnings_returns_updated_count_and_commits(self) -> None:
        db = SimpleNamespace(
            execute=AsyncMock(return_value=SimpleNamespace(fetchall=lambda: [1, 2])),
            commit=AsyncMock(),
        )

        count = await reset_all_warnings(db=db)

        self.assertEqual(count, 2)
        db.execute.assert_awaited_once()
        db.commit.assert_awaited_once()

    async def test_reset_user_warnings_returns_previous_count_and_commits(self) -> None:
        user = SimpleNamespace(id=7, warnings=2)
        db = SimpleNamespace(
            execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: user)),
            add=Mock(),
            commit=AsyncMock(),
        )

        old = await reset_user_warnings(db=db, user_id=7)

        self.assertEqual(old, 2)
        self.assertEqual(user.warnings, 0)
        db.add.assert_called_once_with(user)
        db.commit.assert_awaited_once()

    async def test_unban_all_users_returns_updated_count_and_commits(self) -> None:
        db = SimpleNamespace(
            execute=AsyncMock(return_value=SimpleNamespace(fetchall=lambda: [1])),
            commit=AsyncMock(),
        )

        count = await unban_all_users(db=db)

        self.assertEqual(count, 1)
        db.execute.assert_awaited_once()
        db.commit.assert_awaited_once()

    async def test_progressive_ban_sets_first_duration_to_one_month(self) -> None:
        db = SimpleNamespace(add=Mock(), commit=AsyncMock())
        user = SimpleNamespace(
            allowed=True,
            banned=False,
            ban_reason=None,
            ban_count=0,
            banned_until=None,
        )

        with patch(
            "app.services.warning_service.now_tz",
            return_value=datetime(2026, 1, 31, 10, 0, tzinfo=ZoneInfo("UTC")),
        ):
            result = await apply_progressive_ban(db=db, user=user, reason="test")

        self.assertFalse(user.allowed)
        self.assertTrue(user.banned)
        self.assertEqual(user.ban_reason, "test")
        self.assertEqual(user.ban_count, 1)
        self.assertEqual(result.duration_months, 1)
        self.assertEqual(user.banned_until, datetime(2026, 2, 28, 10, 0, tzinfo=ZoneInfo("UTC")))
        db.commit.assert_awaited_once()

    async def test_progressive_ban_caps_duration_at_six_months(self) -> None:
        db = SimpleNamespace(add=Mock(), commit=AsyncMock())
        user = SimpleNamespace(
            allowed=True,
            banned=False,
            ban_reason=None,
            ban_count=2,
            banned_until=None,
        )

        with patch(
            "app.services.warning_service.now_tz",
            return_value=datetime(2026, 5, 19, 10, 0, tzinfo=ZoneInfo("UTC")),
        ):
            result = await apply_progressive_ban(db=db, user=user, reason=None)

        self.assertEqual(user.ban_count, 3)
        self.assertEqual(result.duration_months, 6)
        self.assertEqual(user.banned_until, datetime(2026, 11, 19, 10, 0, tzinfo=ZoneInfo("UTC")))

    async def test_effective_unban_at_matches_next_midnight_job(self) -> None:
        self.assertEqual(
            effective_unban_at(datetime(2026, 2, 28, 10, 0, tzinfo=ZoneInfo("UTC"))),
            datetime(2026, 3, 1, 0, 0, tzinfo=ZoneInfo("UTC")),
        )

    async def test_late_cancellation_warning_has_no_appeal_button(self) -> None:
        user = SimpleNamespace(id=7, banned=False)
        db = _FakeDb(
            _Result(value=user),
            _Result(row=(1, True, False, 99, "user", "User")),
        )
        bot = SimpleNamespace(send_message=AsyncMock())

        with patch(
            "app.services.warning_service.get_many",
            new=AsyncMock(return_value={"warning_chat_id": None, "admin_chat_id": None}),
        ):
            count = await add_warning(
                db=db,
                bot=bot,
                user_id=7,
                reason="Late cancellation (less than 1 hour before booking)",
                appeal_allowed=False,
            )

        self.assertEqual(count, 1)
        bot.send_message.assert_awaited_once()
        sent_text = bot.send_message.await_args.args[1]
        self.assertNotIn("Appeal warning", sent_text)
        self.assertIsNone(bot.send_message.await_args.kwargs["reply_markup"])

    async def test_warning_chat_notification_has_revert_button(self) -> None:
        user = SimpleNamespace(id=7, banned=False)
        db = _FakeDb(
            _Result(value=user),
            _Result(row=(1, True, False, 99, "user", "User")),
        )
        bot = SimpleNamespace(send_message=AsyncMock())

        with patch(
            "app.services.warning_service.get_many",
            new=AsyncMock(return_value={"warning_chat_id": 555, "admin_chat_id": 444}),
        ):
            count = await add_warning(
                db=db,
                bot=bot,
                user_id=7,
                reason="Manual admin warning",
            )

        self.assertEqual(count, 1)
        self.assertEqual(bot.send_message.await_count, 2)
        admin_call = bot.send_message.await_args_list[1]
        self.assertEqual(admin_call.args[0], 555)
        button = admin_call.kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(button.text, "Revert")
        self.assertEqual(button.callback_data, "warn_revert_7")

    async def test_warning_notification_falls_back_to_admin_chat(self) -> None:
        user = SimpleNamespace(id=7, banned=False)
        db = _FakeDb(
            _Result(value=user),
            _Result(row=(1, True, False, 99, "user", "User")),
        )
        bot = SimpleNamespace(send_message=AsyncMock())

        with patch(
            "app.services.warning_service.get_many",
            new=AsyncMock(return_value={"warning_chat_id": None, "admin_chat_id": 444}),
        ):
            count = await add_warning(
                db=db,
                bot=bot,
                user_id=7,
                reason="Manual admin warning",
            )

        self.assertEqual(count, 1)
        admin_call = bot.send_message.await_args_list[1]
        self.assertEqual(admin_call.args[0], 444)

    async def test_revert_latest_warning_unbans_restores_access_and_decrements_ban_count(self) -> None:
        user = SimpleNamespace(
            id=7,
            tg_user_id=None,
            warnings=3,
            allowed=False,
            banned=True,
            ban_reason="Reached 3 warnings",
            ban_count=2,
            banned_until=datetime(2026, 5, 1, 10, 0, tzinfo=ZoneInfo("UTC")),
        )
        db = _FakeDb(_Result(value=user))
        bot = SimpleNamespace(send_message=AsyncMock())

        result = await revert_latest_warning(db=db, bot=bot, user_db_id=7)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.warnings, 2)
        self.assertTrue(result.was_banned)
        self.assertEqual(result.ban_count, 1)
        self.assertEqual(user.warnings, 2)
        self.assertTrue(user.allowed)
        self.assertFalse(user.banned)
        self.assertIsNone(user.ban_reason)
        self.assertIsNone(user.banned_until)
        self.assertEqual(user.ban_count, 1)
        db.add.assert_called_once_with(user)
        db.commit.assert_awaited_once()

    async def test_revert_latest_warning_does_not_decrement_ban_count_when_disabled(self) -> None:
        user = SimpleNamespace(
            id=7,
            tg_user_id=None,
            warnings=3,
            allowed=False,
            banned=True,
            ban_reason="Reached 3 warnings",
            ban_count=2,
            banned_until=datetime(2026, 5, 1, 10, 0, tzinfo=ZoneInfo("UTC")),
        )
        db = _FakeDb(_Result(value=user))
        bot = SimpleNamespace(send_message=AsyncMock())

        result = await revert_latest_warning(
            db=db,
            bot=bot,
            user_db_id=7,
            decrement_ban_count=False,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.ban_count, 2)
        self.assertEqual(user.ban_count, 2)

    async def test_unban_expired_users_clears_ban_and_notifies_user(self) -> None:
        user = SimpleNamespace(
            id=7,
            tg_user_id=99,
            banned=True,
            ban_reason="expired",
            banned_until=datetime(2026, 5, 1, 10, 0, tzinfo=ZoneInfo("UTC")),
        )
        scalars = Mock(return_value=[user])
        db = SimpleNamespace(
            execute=AsyncMock(return_value=SimpleNamespace(scalars=scalars)),
            add=Mock(),
            commit=AsyncMock(),
        )
        bot = SimpleNamespace(send_message=AsyncMock())

        with patch(
            "app.services.warning_service.now_tz",
            return_value=datetime(2026, 5, 19, 10, 0, tzinfo=ZoneInfo("UTC")),
        ):
            count = await unban_expired_users(db=db, bot=bot)

        self.assertEqual(count, 1)
        self.assertFalse(user.banned)
        self.assertIsNone(user.ban_reason)
        self.assertIsNone(user.banned_until)
        db.add.assert_called_once_with(user)
        db.commit.assert_awaited_once()
        bot.send_message.assert_awaited_once()
        self.assertEqual(bot.send_message.await_args.args[0], 99)
