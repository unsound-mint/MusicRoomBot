from unittest import TestCase

from app.bot.keyboards.admin_inline_kb import (
    admin_bookings_kb,
    admin_chat_ids_kb,
    admin_home_kb,
    admin_next_actions_kb,
    admin_user_actions_kb,
    admin_users_kb,
    warning_revert_kb,
    working_hours_value_kb,
)
from app.services.config_runtime import DEFAULTS, _cast_value


class AdminInlineKeyboardTests(TestCase):
    def test_chat_ids_keyboard_includes_equipment_topic_id(self) -> None:
        keyboard = admin_chat_ids_kb()

        texts = [button.text for row in keyboard.inline_keyboard for button in row]
        callback_data = [button.callback_data for row in keyboard.inline_keyboard for button in row]

        self.assertIn("Equipment topic ID", texts)
        self.assertIn("admin_cfg_chat_equipment_topic_id", callback_data)

    def test_chat_ids_keyboard_includes_warning_chat_id(self) -> None:
        keyboard = admin_chat_ids_kb()

        buttons = [button for row in keyboard.inline_keyboard for button in row]

        self.assertIn(
            ("Warning chat ID", "admin_cfg_chat_warning_chat_id"),
            [(button.text, button.callback_data) for button in buttons],
        )

    def test_runtime_defaults_include_equipment_topic_id(self) -> None:
        self.assertIn("equipment_topic_id", DEFAULTS)

    def test_runtime_defaults_include_warning_chat_id(self) -> None:
        self.assertIn("warning_chat_id", DEFAULTS)

    def test_equipment_topic_id_casts_blank_and_none_to_disabled(self) -> None:
        self.assertIsNone(_cast_value("equipment_topic_id", ""))
        self.assertIsNone(_cast_value("equipment_topic_id", "none"))

    def test_equipment_topic_id_casts_numeric_values(self) -> None:
        self.assertEqual(_cast_value("equipment_topic_id", "1337"), 1337)

    def test_working_hours_value_keyboard_exposes_presets_and_custom(self) -> None:
        keyboard = working_hours_value_kb(4)

        texts = [button.text for row in keyboard.inline_keyboard for button in row]
        callback_data = [button.callback_data for row in keyboard.inline_keyboard for button in row]

        self.assertEqual(
            texts,
            [
                "9:00-23:00",
                "10:00-22:00",
                "12:00-24:00",
                "Custom",
                "⬅️ Back",
            ],
        )
        self.assertIn("admin_cfg_hourspreset_4_9_23", callback_data)
        self.assertIn("admin_cfg_hourscustom_4", callback_data)

    def test_admin_back_buttons_use_directional_label(self) -> None:
        keyboard = admin_chat_ids_kb()

        texts = [button.text for row in keyboard.inline_keyboard for button in row]

        self.assertIn("⬅️ Back", texts)
        self.assertNotIn("Back", texts)

    def test_admin_home_has_top_level_clubs_button(self) -> None:
        keyboard = admin_home_kb()

        buttons = [button for row in keyboard.inline_keyboard for button in row]

        self.assertIn(
            ("Clubs", "admin_clubs"),
            [(button.text, button.callback_data) for button in buttons],
        )

    def test_admin_home_does_not_have_top_level_warnings_button(self) -> None:
        keyboard = admin_home_kb()

        buttons = [button for row in keyboard.inline_keyboard for button in row]

        self.assertNotIn(
            ("Warnings", "admin_warn"),
            [(button.text, button.callback_data) for button in buttons],
        )

    def test_admin_bookings_keyboard_exposes_add_booking(self) -> None:
        keyboard = admin_bookings_kb()

        buttons = [button for row in keyboard.inline_keyboard for button in row]

        self.assertIn(
            ("Add booking", "admin_bookings_add"),
            [(button.text, button.callback_data) for button in buttons],
        )

    def test_admin_next_actions_keyboard_appends_back_button(self) -> None:
        keyboard = admin_next_actions_kb(
            [("Add another club", "admin_clubs_add")],
            back_data="admin_clubs",
            back_text="⬅️ Back to clubs",
        )

        buttons = [button for row in keyboard.inline_keyboard for button in row]

        self.assertEqual(
            [(button.text, button.callback_data) for button in buttons],
            [
                ("Add another club", "admin_clubs_add"),
                ("⬅️ Back to clubs", "admin_clubs"),
            ],
        )

    def test_admin_users_keyboard_exposes_unban_all(self) -> None:
        keyboard = admin_users_kb()

        buttons = [button for row in keyboard.inline_keyboard for button in row]

        self.assertIn(
            ("Unban all users", "admin_users_unban_all"),
            [(button.text, button.callback_data) for button in buttons],
        )

    def test_admin_users_keyboard_exposes_all_user_warning_tools(self) -> None:
        keyboard = admin_users_kb()

        buttons = [button for row in keyboard.inline_keyboard for button in row]

        self.assertEqual(
            [
                ("Find user", "admin_users_find"),
                ("List users", "admin_users_list"),
                ("Unban all users", "admin_users_unban_all"),
                ("List warned users", "admin_users_warn_list"),
                ("Reset all warnings", "admin_users_warn_reset_all"),
                ("Admins", "admin_users_admins"),
                ("⬅️ Back", "admin_home"),
            ],
            [(button.text, button.callback_data) for button in buttons],
        )

    def test_admin_user_actions_keyboard_exposes_username_scoped_warning_actions(self) -> None:
        keyboard = admin_user_actions_kb("jane", banned=False, allowed=True)

        buttons = [button for row in keyboard.inline_keyboard for button in row]

        self.assertEqual(
            [
                ("Revoke access", "admin_users_unallow_direct_jane"),
                ("Ban", "admin_users_ban_direct_jane"),
                ("Add warning", "admin_warn_add_direct_jane"),
                ("Remove warning", "admin_warn_remove_direct_jane"),
                ("Revert warning/ban", "admin_warn_revert_direct_jane"),
                ("Reset warnings", "admin_warn_reset_direct_jane"),
                ("Delete user", "admin_users_delete_direct_jane"),
                ("⬅️ Back", "admin_users"),
            ],
            [(button.text, button.callback_data) for button in buttons],
        )

    def test_warning_revert_keyboard_targets_user(self) -> None:
        keyboard = warning_revert_kb(42)

        buttons = [button for row in keyboard.inline_keyboard for button in row]

        self.assertEqual(
            [(button.text, button.callback_data) for button in buttons],
            [("Revert", "warn_revert_42")],
        )
