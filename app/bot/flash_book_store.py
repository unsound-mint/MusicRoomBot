# app/bot/flash_book_store.py
from datetime import date

# Maps (date, hour) -> (chat_id, message_id, thread_id | None)
_pending: dict[tuple[date, int], tuple[int, int, int | None]] = {}


def register(b_date: date, hour: int, chat_id: int, message_id: int, thread_id: int | None = None) -> None:
    _pending[(b_date, hour)] = (chat_id, message_id, thread_id)


def pop(b_date: date, hour: int) -> tuple[int, int, int | None] | None:
    return _pending.pop((b_date, hour), None)
