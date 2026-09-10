from types import SimpleNamespace
from unittest import TestCase

from app.bot.handlers.admin_config import is_admin_config_callback


class AdminConfigRoutingTests(TestCase):
    def test_admin_cfg_hours_confirm_state_is_not_matched_by_generic_handler(self) -> None:
        callback = SimpleNamespace(data="admin_cfg_hours_confirm_state")

        self.assertFalse(is_admin_config_callback(callback))

    def test_regular_admin_cfg_callbacks_are_matched(self) -> None:
        callback = SimpleNamespace(data="admin_cfg_working_hours")

        self.assertTrue(is_admin_config_callback(callback))
