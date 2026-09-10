from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock

from app.models.user import User
from app.services.form_pass_service import (
    FormPassCommand,
    grant_form_pass_access,
    parse_form_pass_command,
)


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
    def __init__(self, *results):
        self.results = list(results)
        self.added = []
        self.deleted = []
        self.commit = AsyncMock()
        self.refresh = AsyncMock()

    async def execute(self, statement):
        return _ExecuteResult(self.results.pop(0))

    def add(self, value):
        self.added.append(value)

    async def delete(self, value):
        self.deleted.append(value)


class FormPassParserTests(TestCase):
    def test_parse_form_pass_command_accepts_percent_score(self) -> None:
        result = parse_form_pass_command("/form_pass @Jane 90% Jane Doe")

        self.assertEqual(result, FormPassCommand("jane", 90, "Jane Doe"))

    def test_parse_form_pass_command_rejects_missing_score(self) -> None:
        result = parse_form_pass_command("/form_pass @Jane")

        self.assertEqual(result, "Usage:\n/form_pass @username 90 Full Name")

    def test_parse_form_pass_command_rejects_non_numeric_score(self) -> None:
        result = parse_form_pass_command("/form_pass @Jane high Jane Doe")

        self.assertEqual(result, "Malformed command: score must be a number (e.g. 90).")


class FormPassGrantTests(IsolatedAsyncioTestCase):
    async def test_grant_form_pass_access_updates_real_user(self) -> None:
        user = User(id=1, tg_user_id=10, tg_username="jane", full_name=None)
        user.allowed = False
        user.banned = False
        db = _RecordingDb([user])

        result = await grant_form_pass_access(
            db,
            username="jane",
            full_name="Jane Doe",
        )

        self.assertEqual(result.status, "granted")
        self.assertTrue(user.allowed)
        self.assertEqual(user.full_name, "Jane Doe")
        self.assertEqual(db.added, [user])
        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once_with(user)

    async def test_grant_form_pass_access_binds_changed_username_by_name(self) -> None:
        placeholder = User(id=2, tg_user_id=None, tg_username="newjane", full_name=None)
        user = User(id=1, tg_user_id=10, tg_username="oldjane", full_name="Jane Doe")
        user.allowed = False
        user.banned = False
        db = _RecordingDb([placeholder], [user])

        result = await grant_form_pass_access(
            db,
            username="@NewJane",
            full_name="Jane Doe",
        )

        self.assertEqual(result.status, "granted")
        self.assertIs(result.user, user)
        self.assertEqual(user.tg_username, "newjane")
        self.assertEqual(db.deleted, [placeholder])

    async def test_grant_form_pass_access_reports_not_found(self) -> None:
        db = _RecordingDb([])

        result = await grant_form_pass_access(
            db,
            username="missing",
            full_name="Missing User",
        )

        self.assertEqual(result.status, "not_found")
        self.assertIsNone(result.user)
        db.commit.assert_not_awaited()
