from datetime import date
from unittest import TestCase

from app.services.schedule_service import render_schedule_text


class ScheduleServiceTests(TestCase):
    def test_render_schedule_text_prefers_weekly_slot_over_booking(self) -> None:
        text = render_schedule_text(
            [date(2026, 5, 18)],
            weekly_map={(0, 10): "Band A"},
            booking_map={(date(2026, 5, 18), 10): "Jane"},
            hours_by_weekday={0: [10]},
        )

        self.assertIn("📅 *Monday*", text)
        self.assertIn("`10:00`  Band A", text)
        self.assertNotIn("Jane", text)

    def test_render_schedule_text_shows_booking_owner_when_not_weekly(self) -> None:
        text = render_schedule_text(
            [date(2026, 5, 19)],
            weekly_map={},
            booking_map={(date(2026, 5, 19), 12): "Jane"},
            hours_by_weekday={1: [11, 12]},
        )

        self.assertIn("📅 *Tuesday*", text)
        self.assertIn("`12:00`  Jane", text)
        self.assertNotIn("`11:00`", text)

    def test_render_schedule_text_shows_empty_day_message(self) -> None:
        text = render_schedule_text(
            [date(2026, 5, 20)],
            weekly_map={},
            booking_map={},
            hours_by_weekday={2: [9, 10]},
        )

        self.assertIn("📅 *Wednesday*", text)
        self.assertIn("_No sessions today._", text)

    def test_render_schedule_text_omits_cancelled_weekly_slot(self) -> None:
        text = render_schedule_text(
            [date(2026, 5, 20)],
            weekly_map={},
            booking_map={},
            hours_by_weekday={2: [10]},
        )

        self.assertIn("_No sessions today._", text)
        self.assertNotIn("`10:00`", text)

    def test_render_schedule_text_escapes_markdown_owners(self) -> None:
        text = render_schedule_text(
            [date(2026, 5, 21)],
            weekly_map={(3, 10): "Band_Name *A*"},
            booking_map={(date(2026, 5, 21), 11): "Jane_Doe [voice]"},
            hours_by_weekday={3: [10, 11]},
        )

        self.assertIn("`10:00`  Band\\_Name \\*A\\*", text)
        self.assertIn("`11:00`  Jane\\_Doe \\[voice]", text)
