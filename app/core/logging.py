import json
import logging
import re
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

_RESERVED_LOG_RECORD_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "message",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}
_EVENT_TOKEN_RE = re.compile(r"[^a-z0-9]+")


def _json_default(value: Any) -> str:
    return str(value)


def _event_from_record(record: logging.LogRecord) -> str:
    raw_event = getattr(record, "event", None)
    if raw_event:
        return str(raw_event)

    raw_message = record.msg if isinstance(record.msg, str) else record.getMessage()
    event_name = _EVENT_TOKEN_RE.sub("_", raw_message.lower()).strip("_")
    event_name = event_name or "log"
    return f"{record.name}.{event_name}"


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        event = _event_from_record(record)
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": event,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        for key, value in sorted(record.__dict__.items()):
            if key in _RESERVED_LOG_RECORD_ATTRS or key.startswith("_"):
                continue
            if key == "event":
                continue
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(payload, default=_json_default, ensure_ascii=False)


def configure_logging(level: str, *, logger_levels: Mapping[str, str] | None = None) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    for logger_name, logger_level in (logger_levels or {}).items():
        logging.getLogger(logger_name).setLevel(logger_level)
