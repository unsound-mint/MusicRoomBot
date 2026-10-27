import logging
import unittest

from app.core.logging import RecentIssuesHandler, format_recent_issues, recent_issues


class RecentIssuesTests(unittest.TestCase):
    def setUp(self) -> None:
        recent_issues.records.clear()
        self.logger = logging.getLogger("recent_issues_test")
        self.logger.propagate = False
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(recent_issues)

    def tearDown(self) -> None:
        self.logger.removeHandler(recent_issues)
        recent_issues.records.clear()

    def test_captures_warnings_and_ignores_info(self) -> None:
        self.logger.info("noise")
        self.logger.warning("member_chat_id is not configured")
        text = format_recent_issues()
        self.assertIn("member_chat_id is not configured", text)
        self.assertNotIn("noise", text)

    def test_includes_exception_type_and_is_newest_first(self) -> None:
        self.logger.error("first")
        try:
            raise ValueError("boom")
        except ValueError:
            self.logger.exception("second")
        text = format_recent_issues()
        self.assertIn("ValueError: boom", text)
        self.assertLess(text.index("second"), text.index("first"))

    def test_buffer_is_bounded(self) -> None:
        handler = RecentIssuesHandler(capacity=3)
        for i in range(5):
            handler.records.append((None, "WARNING", "x", str(i)))  # type: ignore[arg-type]
        self.assertEqual(len(handler.records), 3)
