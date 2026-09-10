from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, Mock, patch

from app.bot.handlers.equipment_request import (
    CREATE_FLOW,
    EQUIPMENT_REQUEST_RULES_TEXT,
    FIELD_PROMPTS,
    MISSING_FULL_NAME_TEXT,
    build_equipment_request_confirmation_text,
    equipment_request_cancel,
    equipment_request_club_name_input,
    equipment_request_edit_details,
    equipment_request_edit_value_input,
    equipment_request_home,
    equipment_request_new,
    equipment_request_pick_edit_field,
    equipment_request_rules_agree,
    equipment_request_submit,
)
from app.bot.keyboards.inline_kb import (
    equipment_request_confirmation_kb,
    equipment_request_edit_fields_kb,
    equipment_request_rules_agreement_kb,
)
from app.bot.keyboards.main_menu import build_main_menu


class _FakeState:
    def __init__(self, data=None) -> None:
        self.data = dict(data or {})
        self.current_state = None

    async def clear(self) -> None:
        self.data.clear()
        self.current_state = None

    async def update_data(self, *args, **kwargs) -> None:
        if args:
            self.data.update(args[0])
        self.data.update(kwargs)

    async def get_data(self):
        return dict(self.data)

    async def set_state(self, state) -> None:
        self.current_state = state


class EquipmentRequestMenuTests(TestCase):
    def test_main_menu_keeps_rules_and_equipment_request_entries(self) -> None:
        keyboard = build_main_menu()
        rows = [[button.text for button in row] for row in keyboard.keyboard]

        flat = [text for row in rows for text in row]
        self.assertIn("📜 Rules", flat)
        self.assertIn("🎤 Equipment", flat)

    def test_main_menu_shows_club_slots_for_leaders_only(self) -> None:
        regular = build_main_menu()
        leader = build_main_menu(has_club_slots=True)

        regular_flat = [button.text for row in regular.keyboard for button in row]
        leader_flat = [button.text for row in leader.keyboard for button in row]

        self.assertNotIn("🎼 Club slots", regular_flat)
        self.assertIn("🎼 Club slots", leader_flat)
        self.assertEqual(
            [[button.text for button in row] for row in leader.keyboard],
            [
                ["🎵 Book a slot", "🎸 My bookings"],
                ["🎼 Club slots", "📅 Schedule"],
                ["🎤 Equipment", "📜 Rules"],
            ],
        )

    def test_confirmation_keyboard_has_submit_edit_and_cancel(self) -> None:
        keyboard = equipment_request_confirmation_kb()
        texts = [button.text for row in keyboard.inline_keyboard for button in row]

        self.assertEqual(texts, ["Submit", "Edit details", "Cancel"])

    def test_rules_agreement_keyboard_has_agree_and_cancel(self) -> None:
        keyboard = equipment_request_rules_agreement_kb()
        buttons = [button for row in keyboard.inline_keyboard for button in row]

        self.assertEqual(
            [(button.text, button.callback_data) for button in buttons],
            [("I agree", "equip_rules_agree"), ("Cancel", "equip_cancel")],
        )

    def test_requester_edit_field_picker_includes_only_allowed_fields(self) -> None:
        editable_fields = [
            (field_name, FIELD_PROMPTS[field_name]["label"])
            for field_name in CREATE_FLOW
        ]
        keyboard = equipment_request_edit_fields_kb(editable_fields)

        field_buttons = [
            button
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data and button.callback_data.startswith("equip_edit_field_")
        ]

        self.assertEqual(
            [(button.callback_data.removeprefix("equip_edit_field_"), button.text) for button in field_buttons],
            editable_fields,
        )


class EquipmentRequestFlowTests(IsolatedAsyncioTestCase):
    async def test_equipment_hub_uses_markdown_parse_mode(self) -> None:
        state = _FakeState({"stale": "value"})
        callback = SimpleNamespace(
            data="equip_home",
            message=SimpleNamespace(edit_text=AsyncMock()),
        )
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = AsyncMock()
        session_cm.__aexit__.return_value = False

        with (
            patch("app.bot.handlers.equipment_request.safe_answer_callback", new=AsyncMock()),
            patch("app.bot.handlers.equipment_request.AsyncSessionLocal", return_value=session_cm),
            patch("app.bot.handlers.equipment_request.get_future_approved_equipment_requests", new=AsyncMock(return_value=[])),
            patch("app.bot.handlers.equipment_request.edit_or_answer", new=AsyncMock()) as edit_or_answer,
        ):
            await equipment_request_home(callback, state)

        edit_or_answer.assert_awaited_once()
        self.assertIs(edit_or_answer.await_args.args[0], callback)
        self.assertIn("🎤 *Approved equipment requests*", edit_or_answer.await_args.args[1])
        self.assertIn("Tap *Submit new request*", edit_or_answer.await_args.args[1])
        self.assertEqual(edit_or_answer.await_args.kwargs["parse_mode"], "Markdown")
        self.assertEqual(state.data, {})

    async def test_wizard_advances_with_prompt_renderer(self) -> None:
        state = _FakeState({"full_name": "John Smith"})
        message = SimpleNamespace(text="Jazz Club", answer=AsyncMock(), bot=SimpleNamespace())

        with patch("app.bot.handlers.equipment_request._render_prompt_message", new=AsyncMock()) as render_prompt:
            await equipment_request_club_name_input(message, state)

        self.assertEqual(state.data["club_name"], "Jazz Club")
        self.assertIsNotNone(state.current_state)
        render_prompt.assert_awaited_once()
        self.assertEqual(
            render_prompt.await_args.args[2],
            "*Step 2 of 7*\n\n📝 Send the event name.",
        )
        self.assertEqual(render_prompt.await_args.kwargs["parse_mode"], "Markdown")

    async def test_new_request_starts_with_rules_agreement(self) -> None:
        state = _FakeState({"stale": "value"})
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=101, username="john"),
            message=SimpleNamespace(answer=AsyncMock()),
            bot=SimpleNamespace(),
        )

        with patch("app.bot.handlers.equipment_request.safe_answer_callback", new=AsyncMock()):
            await equipment_request_new(callback, state)

        self.assertEqual(state.data, {})
        self.assertIsNone(state.current_state)
        callback.message.answer.assert_awaited_once()
        self.assertEqual(
            callback.message.answer.await_args.args[0],
            EQUIPMENT_REQUEST_RULES_TEXT,
        )
        self.assertIn("1. All equipment requests", EQUIPMENT_REQUEST_RULES_TEXT)
        self.assertIn("5. You have a right", EQUIPMENT_REQUEST_RULES_TEXT)
        self.assertIn("*What to do if I missed the deadline for booking?*", EQUIPMENT_REQUEST_RULES_TEXT)
        self.assertIn("@unsound\\_mint", EQUIPMENT_REQUEST_RULES_TEXT)
        self.assertIn("3. Describe which equipment", EQUIPMENT_REQUEST_RULES_TEXT)
        self.assertEqual(callback.message.answer.await_args.kwargs["parse_mode"], "Markdown")
        reply_markup = callback.message.answer.await_args.kwargs["reply_markup"]
        texts = [button.text for row in reply_markup.inline_keyboard for button in row]
        self.assertEqual(texts, ["I agree", "Cancel"])

    async def test_rules_agreement_starts_with_creation_step_label(self) -> None:
        state = _FakeState({"stale": "value"})
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=101, username="john"),
            message=SimpleNamespace(answer=AsyncMock()),
            bot=SimpleNamespace(),
        )
        session = AsyncMock()
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = session
        session_cm.__aexit__.return_value = False

        with (
            patch("app.bot.handlers.equipment_request.safe_answer_callback", new=AsyncMock()),
            patch("app.bot.handlers.equipment_request.AsyncSessionLocal", return_value=session_cm),
            patch(
                "app.bot.handlers.equipment_request.get_user_by_tg_id",
                new=AsyncMock(return_value=SimpleNamespace(full_name="John Smith")),
            ),
        ):
            await equipment_request_rules_agree(callback, state)

        callback.message.answer.assert_awaited_once()
        self.assertEqual(
            callback.message.answer.await_args.args[0],
            "*Step 1 of 7*\n\n📝 Send the club name.",
        )
        self.assertEqual(callback.message.answer.await_args.kwargs["parse_mode"], "Markdown")

    async def test_requester_edit_round_trip_updates_one_field_and_sends_confirmation(self) -> None:
        state = _FakeState(
            {
                "full_name": "John Smith",
                "club_name": "Jazz Club",
                "event_name": "Spring Jam",
                "venue": "Main Hall",
                "equipment_text": "- 2 microphones",
                "needed_at_text": "March 30, 18:00",
                "reason_text": "Soundcheck",
                "comments": None,
                "edit_field_name": "venue",
                "ranges": [{"start_at": "2026-03-30T10:00:00", "end_at": "2026-03-30T12:00:00"}],
            }
        )
        message = SimpleNamespace(
            text="Side Stage",
            answer=AsyncMock(),
            bot=SimpleNamespace(),
            from_user=SimpleNamespace(id=101),
        )

        await equipment_request_edit_value_input(message, state)

        self.assertEqual(state.data["venue"], "Side Stage")
        self.assertIsNone(state.data["edit_field_name"])
        self.assertIsNone(state.current_state)
        message.answer.assert_awaited_once()
        rendered_text = message.answer.await_args.args[0]
        self.assertIn("📍 *Venue:* Side Stage", rendered_text)
        self.assertIn("🎫 *Event:* Spring Jam", rendered_text)
        self.assertNotIn("Full name:", rendered_text)

        reply_markup = message.answer.await_args.kwargs["reply_markup"]
        texts = [button.text for row in reply_markup.inline_keyboard for button in row]
        self.assertEqual(texts, ["Submit", "Edit details", "Cancel"])

    async def test_edit_field_prompt_has_no_creation_step_label(self) -> None:
        state = _FakeState(
            {
                "full_name": "John Smith",
                "club_name": "Jazz Club",
                "event_name": "Spring Jam",
                "venue": "Main Hall",
                "equipment_text": "- 2 microphones",
                "needed_at_text": "March 30, 18:00",
                "reason_text": "Soundcheck",
                "comments": None,
                "ranges": [{"start_at": "2026-03-30T10:00:00", "end_at": "2026-03-30T12:00:00"}],
            }
        )
        callback = SimpleNamespace(
            data="equip_edit_field_venue",
            from_user=SimpleNamespace(id=303),
            message=SimpleNamespace(answer=AsyncMock()),
        )

        with patch("app.bot.handlers.equipment_request.safe_answer_callback", new=AsyncMock()):
            await equipment_request_pick_edit_field(callback, state)

        callback.message.answer.assert_awaited_once()
        self.assertEqual(callback.message.answer.await_args.args[0], "📝 Send the venue.")
        self.assertNotIn("Step", callback.message.answer.await_args.args[0])
        self.assertEqual(callback.message.answer.await_args.kwargs["parse_mode"], "Markdown")

    async def test_edit_field_callback_without_existing_draft_is_rejected(self) -> None:
        state = _FakeState({})
        callback = SimpleNamespace(
            data="equip_edit_field_venue",
            from_user=SimpleNamespace(id=303),
            message=SimpleNamespace(answer=AsyncMock()),
        )

        with patch("app.bot.handlers.equipment_request.safe_answer_callback", new=AsyncMock()):
            await equipment_request_pick_edit_field(callback, state)

        self.assertEqual(state.data, {})
        self.assertIsNone(state.current_state)
        callback.message.answer.assert_awaited_once_with("⚠️ Equipment request draft not found.")

    async def test_edit_details_without_valid_draft_is_rejected(self) -> None:
        state = _FakeState(
            {
                "full_name": "John Smith",
                "club_name": "Jazz Club",
                "event_name": "Spring Jam",
                "venue": "Main Hall",
                "equipment_text": None,
                "needed_at_text": "March 30, 18:00",
                "reason_text": "Soundcheck",
                "comments": None,
                "ranges": [],
            }
        )
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=304),
            message=SimpleNamespace(answer=AsyncMock()),
        )

        with patch("app.bot.handlers.equipment_request.safe_answer_callback", new=AsyncMock()):
            await equipment_request_edit_details(callback, state)

        self.assertEqual(state.data, {})
        self.assertIsNone(state.current_state)
        callback.message.answer.assert_awaited_once_with("⚠️ Equipment request draft not found.")

    async def test_edit_value_submission_with_missing_required_draft_data_is_rejected(self) -> None:
        state = _FakeState(
            {
                "full_name": "John Smith",
                "club_name": "Jazz Club",
                "event_name": "Spring Jam",
                "venue": "Main Hall",
                "equipment_text": None,
                "needed_at_text": "March 30, 18:00",
                "reason_text": "Soundcheck",
                "comments": None,
                "edit_field_name": "venue",
                "ranges": [],
            }
        )
        message = SimpleNamespace(
            text="Side Stage",
            from_user=SimpleNamespace(id=305),
            answer=AsyncMock(),
            bot=SimpleNamespace(),
        )

        await equipment_request_edit_value_input(message, state)

        self.assertEqual(state.data, {})
        self.assertIsNone(state.current_state)
        message.answer.assert_awaited_once_with("⚠️ Equipment request draft not found.")

    async def test_submit_rejects_partial_draft_state(self) -> None:
        state = _FakeState(
            {
                "full_name": "John Smith",
                "club_name": "Jazz Club",
                "event_name": "Spring Jam",
                "venue": "Main Hall",
                "equipment_text": None,
                "needed_at_text": "March 30, 18:00",
                "reason_text": "Soundcheck",
                "comments": None,
                "ranges": [],
            }
        )
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=404),
            message=SimpleNamespace(answer=AsyncMock()),
        )

        with patch("app.bot.handlers.equipment_request.safe_answer_callback", new=AsyncMock()) as safe_answer_callback:
            await equipment_request_submit(callback, state)

        self.assertEqual(state.data, {})
        self.assertIsNone(state.current_state)
        safe_answer_callback.assert_awaited_once_with(callback)
        callback.message.answer.assert_awaited_once_with("⚠️ Equipment request draft not found.")

    async def test_submit_persists_request_and_posts_review_message(self) -> None:
        state = _FakeState(
            {
                "requester_tg_user_id": 123,
                "requester_username": "john",
                "full_name": "John Smith",
                "club_name": "Jazz Club",
                "event_name": "Spring Jam",
                "venue": "Main Hall",
                "equipment_text": "- 2 microphones",
                "needed_at_text": "March 30, 18:00",
                "reason_text": "Soundcheck",
                "comments": None,
                "ranges": [{"start_at": "2026-03-30T10:00:00", "end_at": "2026-03-30T12:00:00"}],
            }
        )
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=404),
            message=SimpleNamespace(answer=AsyncMock()),
            bot=SimpleNamespace(
                send_message=AsyncMock(
                    return_value=SimpleNamespace(
                        chat=SimpleNamespace(id=-1001),
                        message_id=77,
                    )
                )
            ),
        )
        request = SimpleNamespace(
            id=55,
            requester_tg_user_id=123,
            requester_username="john",
            full_name="John Smith",
            club_name="Jazz Club",
            event_name="Spring Jam",
            venue="Main Hall",
            equipment_text="- 2 microphones",
            needed_at_text="March 30, 18:00",
            reason_text="Soundcheck",
            comments=None,
            review_chat_id=None,
            review_message_id=None,
        )
        db = SimpleNamespace()
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = db
        session_cm.__aexit__.return_value = False

        async def _record_review_message(_, req, *, chat_id, message_id):
            req.review_chat_id = chat_id
            req.review_message_id = message_id
            return req

        with (
            patch("app.bot.handlers.equipment_request.AsyncSessionLocal", return_value=session_cm),
            patch("app.bot.handlers.equipment_request.get_runtime_config", new=AsyncMock(return_value=-100500)),
            patch("app.bot.handlers.equipment_request.create_equipment_request", new=AsyncMock(return_value=request)),
            patch(
                "app.bot.handlers.equipment_request.record_equipment_request_review_message",
                new=AsyncMock(side_effect=_record_review_message),
            ) as record_review_message,
            patch("app.bot.handlers.equipment_request.render_equipment_request_review", return_value="review text"),
            patch("app.services.admin_service.is_admin", new=AsyncMock(return_value=False)),
            patch("app.bot.handlers.equipment_request.safe_answer_callback", new=AsyncMock()) as safe_answer_callback,
        ):
            await equipment_request_submit(callback, state)

        callback.bot.send_message.assert_awaited_once()
        self.assertEqual(callback.bot.send_message.await_args.args[:2], (-100500, "review text"))
        self.assertEqual(request.review_chat_id, -1001)
        self.assertEqual(request.review_message_id, 77)
        record_review_message.assert_awaited_once_with(
            db,
            request,
            chat_id=-1001,
            message_id=77,
        )
        safe_answer_callback.assert_awaited_once_with(callback)
        callback.message.answer.assert_awaited_once_with("✅ Request submitted.")
        self.assertEqual(state.data, {})

    async def test_missing_stored_full_name_blocks_wizard_with_guidance(self) -> None:
        state = _FakeState({"stale": "value"})
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=101, username="john"),
            message=SimpleNamespace(answer=AsyncMock()),
            bot=SimpleNamespace(),
        )
        session = AsyncMock()
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = session
        session_cm.__aexit__.return_value = False

        with (
            patch("app.bot.handlers.equipment_request.safe_answer_callback", new=AsyncMock()),
            patch("app.bot.handlers.equipment_request.AsyncSessionLocal", return_value=session_cm),
            patch("app.bot.handlers.equipment_request.get_user_by_tg_id",
                new=AsyncMock(return_value=SimpleNamespace(full_name=None)),
            ),
            patch("app.services.admin_service.is_admin", new=AsyncMock(return_value=False)),
            patch("app.bot.handlers.equipment_request.get_main_menu_kb", new=AsyncMock()),
        ):
            await equipment_request_rules_agree(callback, state)

        self.assertEqual(state.data, {})
        callback.message.answer.assert_awaited_once()
        sent_text = callback.message.answer.await_args.kwargs.get("text") or callback.message.answer.await_args.args[0]
        self.assertEqual(sent_text, MISSING_FULL_NAME_TEXT)

    async def test_abandoning_before_submit_never_creates_db_row(self) -> None:
        db = AsyncMock(add=Mock(), commit=AsyncMock(), refresh=AsyncMock())
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = db
        session_cm.__aexit__.return_value = False

        state = _FakeState(
            {
                "full_name": "John Smith",
                "club_name": "Jazz Club",
                "event_name": "Spring Jam",
            }
        )
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=202),
            message=SimpleNamespace(answer=AsyncMock()),
        )

        with (
            patch("app.bot.handlers.equipment_request.AsyncSessionLocal", return_value=session_cm),
            patch("app.bot.handlers.equipment_request.safe_answer_callback", new=AsyncMock()),
            patch("app.services.admin_service.is_admin", new=AsyncMock(return_value=False)),
        ):
            await equipment_request_cancel(callback, state)

        db.add.assert_not_called()
        db.commit.assert_not_called()
        db.refresh.assert_not_called()
        self.assertEqual(state.data, {})
        callback.message.answer.assert_awaited_once_with("❌ Request cancelled.")

    def test_confirmation_renderer_keeps_only_changed_field_different(self) -> None:
        original = {
            "full_name": "John Smith",
            "club_name": "Jazz Club",
            "event_name": "Spring Jam",
            "venue": "Main Hall",
            "equipment_text": "- 2 microphones",
            "needed_at_text": "March 30, 18:00",
            "reason_text": "Soundcheck",
            "comments": None,
            "ranges": [],
        }
        updated = dict(original, venue="Side Stage")

        original_text = build_equipment_request_confirmation_text(original)
        updated_text = build_equipment_request_confirmation_text(updated)

        self.assertNotIn("Full name:", updated_text)
        self.assertIn("🏷 *Club:* Jazz Club", updated_text)
        self.assertIn("🎫 *Event:* Spring Jam", updated_text)
        self.assertIn("📍 *Venue:* Main Hall", original_text)
        self.assertIn("📍 *Venue:* Side Stage", updated_text)
        self.assertIn("🎛 *Equipment:*\n- 2 microphones", updated_text)
        self.assertIn("⏰ *Requested time ranges:*\n-", updated_text)
        self.assertIn("📝 *Reason:* Soundcheck", updated_text)

    def test_confirmation_renderer_escapes_markdown_user_input(self) -> None:
        text = build_equipment_request_confirmation_text(
            {
                "club_name": "Club_Name",
                "event_name": "Jam *Night*",
                "venue": "`Main` [Hall]",
                "equipment_text": "mic_1 and *stand*",
                "reason_text": "Need [sound]",
                "comments": "ask @unsound_mint",
                "ranges": [],
            }
        )

        self.assertIn("🏷 *Club:* Club\\_Name", text)
        self.assertIn("🎫 *Event:* Jam \\*Night\\*", text)
        self.assertIn("📍 *Venue:* \\`Main\\` \\[Hall]", text)
        self.assertIn("mic\\_1 and \\*stand\\*", text)
        self.assertIn("📝 *Reason:* Need \\[sound]", text)
        self.assertIn("💬 *Comments:* ask @unsound\\_mint", text)
