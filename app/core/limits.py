import asyncio
import os
from dataclasses import dataclass


def _get_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(str(raw).strip())
    except Exception:
        return default


@dataclass(frozen=True)
class BusySettings:
    # Max concurrent booking handlers (start booking + pick day/hour).
    booking_max_in_flight: int = _get_int_env("BOOKING_MAX_IN_FLIGHT", 10)
    # How long to wait to enter the booking gate before replying "busy".
    booking_acquire_timeout_s: float = float(
        os.environ.get("BOOKING_ACQUIRE_TIMEOUT_S", "0.05")
    )


SETTINGS = BusySettings()

# Global semaphore to provide backpressure under spam/bursts without exhausting DB pool.
BOOKING_SEM = asyncio.Semaphore(max(1, SETTINGS.booking_max_in_flight))


class BusyError(Exception):
    pass


async def acquire_booking_slot() -> None:
    try:
        await asyncio.wait_for(
            BOOKING_SEM.acquire(), timeout=SETTINGS.booking_acquire_timeout_s
        )
    except TimeoutError as e:
        raise BusyError() from e


def release_booking_slot() -> None:
    BOOKING_SEM.release()
