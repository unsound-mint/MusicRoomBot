import io
import json
import logging
from unittest import TestCase

from app.core.logging import JsonFormatter, configure_logging


class JsonLoggingTests(TestCase):
    def setUp(self) -> None:
        root = logging.getLogger()
        self._root_handlers = list(root.handlers)
        self._root_level = root.level

    def tearDown(self) -> None:
        root = logging.getLogger()
        root.handlers = self._root_handlers
        root.setLevel(self._root_level)

    def test_json_formatter_emits_structured_record_with_extra_fields(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonFormatter())
        logger = logging.getLogger("tests.json_logging")
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.INFO)

        logger.info(
            "Booking created",
            extra={"event": "booking.created", "booking_id": 42, "status": "success"},
        )

        payload = json.loads(stream.getvalue())
        self.assertEqual(payload["level"], "INFO")
        self.assertEqual(payload["logger"], "tests.json_logging")
        self.assertEqual(payload["event"], "booking.created")
        self.assertEqual(payload["message"], "Booking created")
        self.assertEqual(payload["booking_id"], 42)
        self.assertEqual(payload["status"], "success")
        self.assertIn("timestamp", payload)
        self.assertIn("module", payload)
        self.assertIn("function", payload)
        self.assertIn("line", payload)

    def test_json_formatter_derives_stable_event_from_template_message(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonFormatter())
        logger = logging.getLogger("tests.derived_event")
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.WARNING)

        logger.warning("Unknown runtime config key requested: %r", "private")

        payload = json.loads(stream.getvalue())
        self.assertEqual(
            payload["event"],
            "tests.derived_event.unknown_runtime_config_key_requested_r",
        )
        self.assertEqual(payload["message"], "Unknown runtime config key requested: 'private'")

    def test_json_formatter_includes_exception_trace(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JsonFormatter())
        logger = logging.getLogger("tests.exception")
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.ERROR)

        try:
            raise RuntimeError("boom")
        except RuntimeError:
            logger.exception("Operation failed", extra={"event": "operation.failed"})

        payload = json.loads(stream.getvalue())
        self.assertEqual(payload["event"], "operation.failed")
        self.assertIn("RuntimeError: boom", payload["exception"])

    def test_configure_logging_uses_json_formatter_only(self) -> None:
        configure_logging("INFO")

        root = logging.getLogger()

        self.assertEqual(len(root.handlers), 1)
        self.assertIsInstance(root.handlers[0].formatter, JsonFormatter)
