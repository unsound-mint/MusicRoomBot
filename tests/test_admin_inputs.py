from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.bot.handlers.admin_inputs import admin_custom_value_input, admin_username_input


class AdminInputsTests(IsolatedAsyncioTestCase):
    async def test_admin_username_input_finds_user_by_partial_full_name(self) -> None:
        state = AsyncMock()
        state.get_data.return_value = {"admin_action": "user_find"}

        message = SimpleNamespace(text="john doe", answer=AsyncMock(), from_user=SimpleNamespace(id=1))
        db = SimpleNamespace()
        user = SimpleNamespace(id=7, tg_username="jdoe", full_name="John Doe")
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = db
        session_cm.__aexit__.return_value = False

        with (
            patch("app.bot.handlers.admin_inputs.check_admin_and_reply", new=AsyncMock(return_value=True)),
            patch("app.bot.handlers.admin_inputs.AsyncSessionLocal", return_value=session_cm),
            patch("app.bot.handlers.admin_inputs.get_user_by_username", new=AsyncMock(return_value=None)),
            patch("app.bot.handlers.admin_inputs.find_users_by_full_name", new=AsyncMock(return_value=[user])),
            patch("app.bot.handlers.admin_inputs.render_user_summary", new=AsyncMock()) as render_user_summary,
        ):
            await admin_username_input(message, state)

        state.clear.assert_awaited_once()
        render_user_summary.assert_awaited_once_with(message, user)
        message.answer.assert_not_awaited()

    async def test_admin_username_input_lists_ambiguous_full_name_matches(self) -> None:
        state = AsyncMock()
        state.get_data.return_value = {"admin_action": "user_find"}

        message = SimpleNamespace(text="john", answer=AsyncMock(), from_user=SimpleNamespace(id=1))
        db = SimpleNamespace()
        matches = [
            SimpleNamespace(tg_username="john1", full_name="John One"),
            SimpleNamespace(tg_username="john2", full_name="John Two"),
        ]
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = db
        session_cm.__aexit__.return_value = False

        with (
            patch("app.bot.handlers.admin_inputs.check_admin_and_reply", new=AsyncMock(return_value=True)),
            patch("app.bot.handlers.admin_inputs.AsyncSessionLocal", return_value=session_cm),
            patch("app.bot.handlers.admin_inputs.get_user_by_username", new=AsyncMock(return_value=None)),
            patch("app.bot.handlers.admin_inputs.find_users_by_full_name", new=AsyncMock(return_value=matches)),
            patch("app.bot.handlers.admin_inputs.render_user_summary", new=AsyncMock()) as render_user_summary,
        ):
            await admin_username_input(message, state)

        state.clear.assert_awaited_once()
        render_user_summary.assert_not_awaited()
        message.answer.assert_awaited_once_with(
            "⚠️ *Multiple matches* — be more specific.\n\n"
            "• John One (@john1)\n"
            "• John Two (@john2)",
            parse_mode="Markdown",
        )

    async def test_admin_username_input_lists_ambiguous_matches_with_missing_optional_fields(self) -> None:
        state = AsyncMock()
        state.get_data.return_value = {"admin_action": "user_find"}

        message = SimpleNamespace(text="john", answer=AsyncMock(), from_user=SimpleNamespace(id=1))
        db = SimpleNamespace()
        matches = [
            SimpleNamespace(tg_username=None, full_name="John One"),
            SimpleNamespace(tg_username="john2", full_name=None),
        ]
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = db
        session_cm.__aexit__.return_value = False

        with (
            patch("app.bot.handlers.admin_inputs.check_admin_and_reply", new=AsyncMock(return_value=True)),
            patch("app.bot.handlers.admin_inputs.AsyncSessionLocal", return_value=session_cm),
            patch("app.bot.handlers.admin_inputs.get_user_by_username", new=AsyncMock(return_value=None)),
            patch("app.bot.handlers.admin_inputs.find_users_by_full_name", new=AsyncMock(return_value=matches)),
            patch("app.bot.handlers.admin_inputs.render_user_summary", new=AsyncMock()) as render_user_summary,
        ):
            await admin_username_input(message, state)

        state.clear.assert_awaited_once()
        render_user_summary.assert_not_awaited()
        message.answer.assert_awaited_once_with(
            "⚠️ *Multiple matches* — be more specific.\n\n"
            "• John One (@-)\n"
            "• - (@john2)",
            parse_mode="Markdown",
        )

    async def test_admin_username_input_prefers_exact_username_for_find(self) -> None:
        state = AsyncMock()
        state.get_data.return_value = {"admin_action": "user_find"}

        message = SimpleNamespace(text="@jdoe", answer=AsyncMock(), from_user=SimpleNamespace(id=1))
        db = SimpleNamespace()
        user = SimpleNamespace(id=7, tg_username="jdoe", full_name="John Doe")
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = db
        session_cm.__aexit__.return_value = False

        with (
            patch("app.bot.handlers.admin_inputs.check_admin_and_reply", new=AsyncMock(return_value=True)),
            patch("app.bot.handlers.admin_inputs.AsyncSessionLocal", return_value=session_cm),
            patch("app.bot.handlers.admin_inputs.get_user_by_username", new=AsyncMock(return_value=user)),
            patch("app.bot.handlers.admin_inputs.find_users_by_full_name", new=AsyncMock()) as find_users_by_full_name,
            patch("app.bot.handlers.admin_inputs.render_user_summary", new=AsyncMock()) as render_user_summary,
        ):
            await admin_username_input(message, state)

        state.clear.assert_awaited_once()
        find_users_by_full_name.assert_not_awaited()
        render_user_summary.assert_awaited_once_with(message, user)
        message.answer.assert_not_awaited()

    async def test_admin_custom_value_input_clears_equipment_topic_id_with_none(self) -> None:
        state = AsyncMock()
        state.get_data.return_value = {
            "admin_action": "cfg_chat_id",
            "admin_config_key": "equipment_topic_id",
        }

        message = SimpleNamespace(text="none", answer=AsyncMock())
        db = SimpleNamespace()
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = db
        session_cm.__aexit__.return_value = False

        with (
            patch("app.bot.handlers.admin_inputs.check_admin_and_reply", new=AsyncMock(return_value=True)),
            patch("app.bot.handlers.admin_inputs.AsyncSessionLocal", return_value=session_cm),
            patch("app.bot.handlers.admin_inputs.set_config_value", new=AsyncMock()) as set_config_value,
        ):
            await admin_custom_value_input(message, state)

        set_config_value.assert_awaited_once_with(db, "equipment_topic_id", "")
        state.clear.assert_awaited_once()
        message.answer.assert_awaited_once()
        self.assertEqual(message.answer.await_args.args[0], "equipment_topic_id cleared.")
        reply_markup = message.answer.await_args.kwargs["reply_markup"]
        buttons = [button for row in reply_markup.inline_keyboard for button in row]
        self.assertEqual(
            [(button.text, button.callback_data) for button in buttons],
            [
                ("Change another setting", "admin_cfg_chat_ids"),
                ("⬅️ Back to config", "admin_cfg"),
            ],
        )

    async def test_admin_custom_value_input_rejects_blank_for_required_chat_id(self) -> None:
        await self._assert_required_chat_id_rejects_clear_value("")

    async def test_admin_custom_value_input_rejects_none_for_required_chat_id(self) -> None:
        await self._assert_required_chat_id_rejects_clear_value("none")

    async def _assert_required_chat_id_rejects_clear_value(self, value_text: str) -> None:
        state = AsyncMock()
        state.get_data.return_value = {
            "admin_action": "cfg_chat_id",
            "admin_config_key": "member_topic_id",
        }

        message = SimpleNamespace(text=value_text, answer=AsyncMock())

        with (
            patch("app.bot.handlers.admin_inputs.check_admin_and_reply", new=AsyncMock(return_value=True)),
            patch("app.bot.handlers.admin_inputs.set_config_value", new=AsyncMock()) as set_config_value,
        ):
            await admin_custom_value_input(message, state)

        set_config_value.assert_not_awaited()
        state.clear.assert_not_awaited()
        message.answer.assert_awaited_once_with("Value must be numeric.")
