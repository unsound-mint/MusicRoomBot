import asyncio

# In-process gate for weekly reset. This is intentionally simple:
# it protects DB pool from stampedes during reset and allows booking
# immediately after reset finishes.
_RESET_IN_PROGRESS = asyncio.Event()


def is_reset_in_progress() -> bool:
    return _RESET_IN_PROGRESS.is_set()


def set_reset_in_progress(v: bool) -> None:
    if v:
        _RESET_IN_PROGRESS.set()
    else:
        _RESET_IN_PROGRESS.clear()
