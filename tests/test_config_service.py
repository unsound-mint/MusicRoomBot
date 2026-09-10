from unittest import TestCase

from app.services.config_service import parse_working_hours


class ConfigServiceTests(TestCase):
    def test_parse_working_hours_returns_configured_range(self) -> None:
        self.assertEqual(parse_working_hours("8-23"), (8, 23))

    def test_parse_working_hours_defaults_missing_value(self) -> None:
        self.assertEqual(parse_working_hours(None), (9, 22))

    def test_parse_working_hours_defaults_malformed_value(self) -> None:
        self.assertEqual(parse_working_hours("bad"), (9, 22))
