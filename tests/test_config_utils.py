from unittest import TestCase

from app.services.config_utils import parse_float, parse_int


class ConfigUtilsTests(TestCase):
    def test_parse_int_validates_bounds(self) -> None:
        self.assertEqual(parse_int("42", minimum=0, maximum=100), (42, None))
        self.assertEqual(parse_int("-1", minimum=0), (None, "must be >= 0"))
        self.assertEqual(parse_int("101", maximum=100), (None, "must be <= 100"))

    def test_parse_float_validates_input(self) -> None:
        self.assertEqual(parse_float("1.5", minimum=0.0), (1.5, None))
        self.assertEqual(parse_float("bad"), (None, "not a number"))
