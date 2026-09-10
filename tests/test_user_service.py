from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.models.user import User
from app.services.user_service import list_users, resolve_start_user


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ExecuteResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _ScalarResult(self._values)


class _RecordingDb:
    def __init__(self, values):
        self.values = values
        self.statement = None
        self.added = []
        self.commit = AsyncMock()
        self.refresh = AsyncMock()

    async def execute(self, statement):
        self.statement = statement
        return _ExecuteResult(self.values)

    def add(self, value):
        self.added.append(value)


class UserServiceTests(IsolatedAsyncioTestCase):
    async def test_list_users_orders_by_full_name_with_fallbacks(self) -> None:
        db = _RecordingDb(["kept"])

        result = await list_users(db)

        self.assertEqual(result, ["kept"])
        self.assertIsNotNone(db.statement)

        compiled = str(db.statement.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("ORDER BY", compiled)
        self.assertIn("lower(coalesce(users.full_name, ''))", compiled)
        self.assertIn("lower(coalesce(users.tg_username, ''))", compiled)

    async def test_resolve_start_user_creates_new_user_when_no_match(self) -> None:
        db = _RecordingDb([])
        created_user = User(tg_user_id=10, tg_username="jane", full_name="Jane Doe")

        with (
            patch("app.services.user_service.get_user_by_tg_id", new=AsyncMock(return_value=None)),
            patch(
                "app.services.user_service.create_or_update_user",
                new=AsyncMock(return_value=created_user),
            ) as create_or_update_user,
        ):
            result = await resolve_start_user(
                db,
                tg_user_id=10,
                tg_username="jane",
                telegram_full_name="Jane Doe",
            )

        self.assertTrue(result.created)
        self.assertIs(result.user, created_user)
        create_or_update_user.assert_awaited_once_with(
            db,
            tg_user_id=10,
            tg_username="jane",
            full_name="Jane Doe",
            allowed=False,
        )

    async def test_resolve_start_user_binds_latest_placeholder(self) -> None:
        older = User(id=1, tg_user_id=None, tg_username="jane", full_name="Older")
        latest = User(id=2, tg_user_id=None, tg_username="jane", full_name="Admin Name")
        db = _RecordingDb([latest, older])

        with patch(
            "app.services.user_service.get_user_by_tg_id",
            new=AsyncMock(return_value=None),
        ):
            result = await resolve_start_user(
                db,
                tg_user_id=10,
                tg_username="jane",
                telegram_full_name="Jane Telegram",
            )

        self.assertFalse(result.created)
        self.assertIs(result.user, latest)
        self.assertEqual(latest.tg_user_id, 10)
        self.assertEqual(latest.full_name, "Admin Name")
        self.assertEqual(db.added, [latest, latest])
        self.assertEqual(db.commit.await_count, 2)
        db.refresh.assert_awaited_once_with(latest)

    async def test_resolve_start_user_preserves_existing_full_name(self) -> None:
        user = User(id=5, tg_user_id=10, tg_username="old", full_name="Admin Name")
        db = _RecordingDb([])

        with (
            patch(
                "app.services.user_service.get_user_by_tg_id",
                new=AsyncMock(return_value=user),
            ),
            self.assertLogs("app.services.user_service", level="INFO"),
        ):
            result = await resolve_start_user(
                db,
                tg_user_id=10,
                tg_username="new",
                telegram_full_name="Telegram Name",
            )

        self.assertFalse(result.created)
        self.assertIs(result.user, user)
        self.assertEqual(user.tg_username, "new")
        self.assertEqual(user.full_name, "Admin Name")
        self.assertEqual(db.added, [user])
        db.commit.assert_awaited_once()
