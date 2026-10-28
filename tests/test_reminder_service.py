from datetime import datetime, timedelta
from unittest import TestCase
from zoneinfo import ZoneInfo

from app.services.reminder_service import _build_chain_start_hours, due_slot_start


class ReminderServiceTests(TestCase):
    def test_build_chain_start_hours_groups_consecutive_slots(self) -> None:
        self.assertEqual(
            _build_chain_start_hours([10, 11, 12, 15, 16]),
            {10: [10, 11, 12], 15: [15, 16]},
        )

    def test_build_chain_start_hours_handles_empty_input(self) -> None:
        self.assertEqual(_build_chain_start_hours([]), {})


class DueSlotStartTests(TestCase):
    TZ = ZoneInfo("Asia/Almaty")

    def _due(self, hour: int, minute: int, offset_min: int, grace_min: int):
        return due_slot_start(
            datetime(2026, 5, 19, hour, minute, tzinfo=self.TZ),
            timedelta(minutes=offset_min),
            timedelta(minutes=grace_min),
        )

    def test_fifteen_minute_window_covers_last_quarter_hour_only(self) -> None:
        expected = datetime(2026, 5, 19, 18, 0, tzinfo=self.TZ)
        self.assertIsNone(self._due(17, 44, 15, 15))
        for minute in (45, 50, 59):
            self.assertEqual(self._due(17, minute, 15, 15), expected)
        self.assertIsNone(self._due(18, 0, 15, 15))

    def test_hourly_window_allows_catch_up_after_nominal_time(self) -> None:
        expected = datetime(2026, 5, 19, 18, 0, tzinfo=self.TZ)
        self.assertIsNone(self._due(15, 59, 180, 15))
        self.assertEqual(self._due(15, 0, 180, 15), expected)
        self.assertEqual(self._due(15, 14, 180, 15), expected)
        self.assertIsNone(self._due(15, 15, 180, 15))

    def test_zero_offset_reminds_at_slot_start(self) -> None:
        expected = datetime(2026, 5, 19, 18, 0, tzinfo=self.TZ)
        self.assertEqual(self._due(18, 0, 0, 15), expected)
        self.assertIsNone(self._due(18, 15, 0, 15))

    def test_window_crosses_midnight(self) -> None:
        got = due_slot_start(
            datetime(2026, 5, 19, 23, 50, tzinfo=self.TZ),
            timedelta(minutes=15),
            timedelta(minutes=15),
        )
        self.assertEqual(got, datetime(2026, 5, 20, 0, 0, tzinfo=self.TZ))
