from unittest import TestCase

from app.services.reminder_service import _build_chain_start_hours


class ReminderServiceTests(TestCase):
    def test_build_chain_start_hours_groups_consecutive_slots(self) -> None:
        self.assertEqual(
            _build_chain_start_hours([10, 11, 12, 15, 16]),
            {10: [10, 11, 12], 15: [15, 16]},
        )

    def test_build_chain_start_hours_handles_empty_input(self) -> None:
        self.assertEqual(_build_chain_start_hours([]), {})
