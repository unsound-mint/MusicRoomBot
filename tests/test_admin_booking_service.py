from datetime import date
from unittest import TestCase

from app.services.admin_booking_service import (
    admin_bookable_dates,
    weekly_conflict_dates,
)


class AdminBookingServiceTests(TestCase):
    def test_admin_bookable_dates_include_current_and_next_week_from_today(self) -> None:
        current_week = [date(2026, 3, 23 + offset) for offset in range(7)]

        dates = admin_bookable_dates(current_week, today=date(2026, 3, 25))

        self.assertNotIn(date(2026, 3, 23), dates)
        self.assertNotIn(date(2026, 3, 24), dates)
        self.assertIn(date(2026, 3, 25), dates)
        self.assertIn(date(2026, 3, 30), dates)
        self.assertIn(date(2026, 4, 5), dates)

    def test_weekly_conflict_dates_cover_current_and_next_bookable_weekday(self) -> None:
        current_week = [date(2026, 3, 23 + offset) for offset in range(7)]

        dates = weekly_conflict_dates(
            weekday_idx=2,
            current_week_dates=current_week,
            today=date(2026, 3, 24),
        )

        self.assertEqual(dates, [date(2026, 3, 25), date(2026, 4, 1)])

    def test_weekly_conflict_dates_skip_past_current_weekday(self) -> None:
        current_week = [date(2026, 3, 23 + offset) for offset in range(7)]

        dates = weekly_conflict_dates(
            weekday_idx=0,
            current_week_dates=current_week,
            today=date(2026, 3, 24),
        )

        self.assertEqual(dates, [date(2026, 3, 30)])
