import asyncio
import os
from time import monotonic


def _get_float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(str(raw).strip())
    except Exception:
        return default


# Per-user cooldown for bursty entry points.
BOOKING_USER_COOLDOWN_S = _get_float_env("BOOKING_USER_COOLDOWN_S", 2.0)

_lock = asyncio.Lock()
_last_seen: dict[int, float] = {}


async def allow_booking_start(user_tg_id: int) -> bool:
    """
    Simple per-user cooldown for the 'Book a slot' message handler.
    In-process only (resets on restart). Designed to stop spam bursts.
    """
    cooldown = max(float(BOOKING_USER_COOLDOWN_S or 0.0), 0.0)
    if cooldown <= 0:
        return True

    now = monotonic()
    async with _lock:
        last = _last_seen.get(user_tg_id)
        if last is not None and (now - last) < cooldown:
            return False
        _last_seen[user_tg_id] = now

        # Cheap best-effort cleanup to avoid unbounded growth.
        if len(_last_seen) > 50_000:
            cutoff = now - (cooldown * 10)
            for k, t in list(_last_seen.items()):
                if t < cutoff:
                    _last_seen.pop(k, None)

    return True
