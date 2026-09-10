from datetime import date
from unittest import TestCase
from urllib.parse import parse_qs, urlparse

from app.services.calendar_service import get_google_calendar_link


class CalendarServiceTests(TestCase):
    def test_google_calendar_link_uses_slot_length(self) -> None:
        link = get_google_calendar_link(
            date(2026, 3, 24),
            10,
            slot_length_minutes=90,
        )

        parsed = urlparse(link)
        query = parse_qs(parsed.query)

        self.assertEqual(parsed.netloc, "www.google.com")
        self.assertEqual(query["action"], ["TEMPLATE"])
        self.assertEqual(query["dates"], ["20260324T050000Z/20260324T063000Z"])
