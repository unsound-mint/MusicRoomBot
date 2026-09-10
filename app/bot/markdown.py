from typing import Any

MARKDOWN_PARSE_MODE = "Markdown"
MARKDOWN_SPECIAL_CHARS = "\\_*`["


def escape_markdown(value: Any) -> str:
    text = "" if value is None else str(value)
    return "".join(
        f"\\{char}" if char in MARKDOWN_SPECIAL_CHARS else char
        for char in text
    )


def markdown_display(value: Any, *, fallback: str = "-") -> str:
    text = "" if value is None else str(value).strip()
    return escape_markdown(text) if text else fallback
