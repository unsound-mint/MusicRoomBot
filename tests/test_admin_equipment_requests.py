from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from app.bot.handlers.admin_equipment_requests import (
    equipment_request_accept,
    equipment_request_decline,
    equipment_request_edit,
    equipment_request_refresh,
)


def _request(*, status: str = "submitted"):
    return SimpleNamespace(
        id=21,
        status=status,
        requester_tg_user_id=1001,
        requester_username="john",
        full_name="John Smith",
        club_name="Jazz Club",
        event_name="Spring Jam",
        venue="Main Hall",
        equipment_text="- 2 microphones",
        needed_at_text="March 30, 18:00",
        reason_text="Soundcheck",
        comments=None,
        ranges=[],
        requester_dm_sent=False,
        requester_dm_error=None,
        equipment_post_sent=False,
        equipment_post_error=None,
        review_chat_id=-1001,
        review_message_id=77,
    )


class AdminEquipmentRequestHandlerTests(IsolatedAsyncioTestCase):
    async def test_refresh_not_found_shows_admin_back_action(self) -> None:
        callback = SimpleNamespace(
            data="equipreq_refresh_21",
            from_user=SimpleNamespace(id=1),
        )
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = AsyncMock()
        session_cm.__aexit__.return_value = False

        with (
            patch("app.bot.handlers.admin_equipment_requests.check_admin_callback", new=AsyncMock(return_value=True)),
            patch("app.bot.handlers.admin_equipment_requests.safe_answer_callback", new=AsyncMock()),
            patch("app.bot.handlers.admin_equipment_requests.AsyncSessionLocal", return_value=session_cm),
            patch("app.bot.handlers.admin_equipment_requests.get_equipment_request_with_ranges", new=AsyncMock(return_value=None)),
            patch("app.bot.handlers.admin_equipment_requests.edit_or_answer", new=AsyncMock()) as edit_or_answer,
        ):
            await equipment_request_refresh(callback)

        edit_or_answer.assert_awaited_once()
        self.assertEqual(edit_or_answer.await_args.args[1], "Equipment request not found.")
        reply_markup = edit_or_answer.await_args.kwargs["reply_markup"]
        buttons = [button for row in reply_markup.inline_keyboard for button in row]
        self.assertEqual([(button.text, button.callback_data) for button in buttons], [("⬅️ Back", "admin_home")])

    async def test_edit_shows_field_picker_for_submitted_request(self) -> None:
        request = _request()
        callback = SimpleNamespace(
            data="equipreq_edit_21",
            from_user=SimpleNamespace(id=1),
        )
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = AsyncMock()
        session_cm.__aexit__.return_value = False
        state = AsyncMock()

        with (
            patch("app.bot.handlers.admin_equipment_requests.check_admin_callback", new=AsyncMock(return_value=True)),
            patch("app.bot.handlers.admin_equipment_requests.safe_answer_callback", new=AsyncMock()),
            patch("app.bot.handlers.admin_equipment_requests.AsyncSessionLocal", return_value=session_cm),
            patch("app.bot.handlers.admin_equipment_requests.get_equipment_request_with_ranges", new=AsyncMock(return_value=request)),
            patch("app.bot.handlers.admin_equipment_requests.edit_or_answer", new=AsyncMock()) as edit_or_answer,
        ):
            await equipment_request_edit(callback, state)

        edit_or_answer.assert_awaited_once()
        self.assertEqual(edit_or_answer.await_args.args[1], "Choose a field to edit.")

    async def test_accept_marks_request_and_sends_dm_and_topic_post(self) -> None:
        request = _request()
        post_msg = SimpleNamespace(chat=SimpleNamespace(id=-100200), message_id=42)
        bot = SimpleNamespace(send_message=AsyncMock(return_value=post_msg))
        callback = SimpleNamespace(
            data="equipreq_accept_21",
            from_user=SimpleNamespace(id=999),
            bot=bot,
        )
        db = AsyncMock()
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = db
        session_cm.__aexit__.return_value = False

        with (
            patch("app.bot.handlers.admin_equipment_requests.check_admin_callback", new=AsyncMock(return_value=True)),
            patch("app.bot.handlers.admin_equipment_requests.safe_answer_callback", new=AsyncMock()),
            patch("app.bot.handlers.admin_equipment_requests.AsyncSessionLocal", return_value=session_cm),
            patch("app.bot.handlers.admin_equipment_requests.get_equipment_request_with_ranges", new=AsyncMock(return_value=request)),
            patch("app.bot.handlers.admin_equipment_requests.approve_equipment_request", new=AsyncMock(return_value=request)) as approve,
            patch("app.bot.handlers.admin_equipment_requests.get_runtime_config", new=AsyncMock(side_effect=[-100200, 555, 666])),
            patch(
                "app.bot.handlers.admin_equipment_requests.record_equipment_request_dm_result",
                new=AsyncMock(return_value=request),
            ) as record_dm,
            patch(
                "app.bot.handlers.admin_equipment_requests.record_equipment_request_topic_post_result",
                new=AsyncMock(return_value=request),
            ) as record_post,
            patch("app.bot.handlers.admin_equipment_requests._refresh_review_message", new=AsyncMock()) as refresh,
        ):
            await equipment_request_accept(callback)

        approve.assert_awaited_once_with(db, request, admin_tg_user_id=999)
        self.assertEqual(bot.send_message.await_count, 2)
        record_dm.assert_awaited_once_with(db, request, ok=True, error=None)
        record_post.assert_awaited_once_with(db, request, ok=True, error=None, chat_id=-100200, message_id=42)
        refresh.assert_awaited_once_with(bot, request, fallback_target=callback)

    async def test_decline_marks_request_and_dm_failure_is_recorded(self) -> None:
        request = _request()
        bot = SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError("bot blocked")))
        callback = SimpleNamespace(
            data="equipreq_decline_21",
            from_user=SimpleNamespace(id=999),
            bot=bot,
        )
        db = AsyncMock()
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = db
        session_cm.__aexit__.return_value = False

        with (
            patch("app.bot.handlers.admin_equipment_requests.check_admin_callback", new=AsyncMock(return_value=True)),
            patch("app.bot.handlers.admin_equipment_requests.safe_answer_callback", new=AsyncMock()),
            patch("app.bot.handlers.admin_equipment_requests.AsyncSessionLocal", return_value=session_cm),
            patch("app.bot.handlers.admin_equipment_requests.get_equipment_request_with_ranges", new=AsyncMock(return_value=request)),
            patch("app.bot.handlers.admin_equipment_requests.decline_equipment_request", new=AsyncMock(return_value=request)) as decline,
            patch(
                "app.bot.handlers.admin_equipment_requests.record_equipment_request_dm_result",
                new=AsyncMock(return_value=request),
            ) as record_dm,
            patch("app.bot.handlers.admin_equipment_requests._refresh_review_message", new=AsyncMock()) as refresh,
            patch("app.bot.handlers.admin_equipment_requests.log.warning") as log_warning,
        ):
            await equipment_request_decline(callback)

        decline.assert_awaited_once_with(db, request, admin_tg_user_id=999)
        log_warning.assert_called_once()
        record_dm.assert_awaited_once()
        self.assertEqual(record_dm.await_args.kwargs["ok"], False)
        self.assertIn("bot blocked", record_dm.await_args.kwargs["error"])
        refresh.assert_awaited_once_with(bot, request, fallback_target=callback)
