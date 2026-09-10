from datetime import date, datetime, timezone
from unittest import TestCase
from unittest.mock import patch

from app.services import date_service


class DateServiceTests(TestCase):
    def test_current_week_rolls_after_sunday_22(self) -> None:
        fake_now = datetime(2026, 3, 29, 22, 5, tzinfo=timezone.utc)  # noqa: UP017

        with (
            patch.object(date_service, "today_tz", return_value=fake_now.date()),
            patch.object(date_service, "now_tz", return_value=fake_now),
        ):
            self.assertEqual(date_service.get_current_week_date(0), date(2026, 3, 30))
            self.assertEqual(
                date_service.get_current_week_dates()[0], date(2026, 3, 30)
            )

    def test_is_future_slot_checks_same_day_hour(self) -> None:
        fake_now = datetime(2026, 3, 24, 10, 15, tzinfo=timezone.utc)  # noqa: UP017

        with patch.object(date_service, "now_tz", return_value=fake_now):
            self.assertTrue(date_service.is_future_slot(date(2026, 3, 24), 11))
            self.assertFalse(date_service.is_future_slot(date(2026, 3, 24), 10))
