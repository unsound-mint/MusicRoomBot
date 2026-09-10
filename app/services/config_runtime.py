# app/services/config_runtime.py
import asyncio
import logging
import os
from time import monotonic
from typing import Literal, overload

from app.core.config import RUNTIME_CONFIG_CACHE_TTL
from app.core.database import AsyncSessionLocal
from app.services.config_service import get_config_values

log = logging.getLogger(__name__)

type RuntimeConfigValue = str | int | float | None
type FloatRuntimeConfigKey = Literal["geo_radius"]
type IntRuntimeConfigKey = Literal[
    "reminder_hours",
    "late_minutes",
    "weekly_limit",
    "slot_length",
]
type OptionalIntRuntimeConfigKey = Literal[
    "admin_chat_id",
    "warning_chat_id",
    "access_chat_id",
    "member_chat_id",
    "member_topic_id",
    "equipment_topic_id",
]
type OptionalStrRuntimeConfigKey = Literal["geo_center_lat", "geo_center_lon"]
type StrRuntimeConfigKey = Literal["rules_text"]


def _get_optional_int_env(name: str, default: int | None) -> int | None:
    raw = os.environ.get(name)
    if raw is None:
        return default
    s = str(raw).strip()
    if s == "" or s.lower() == "none":
        return None
    try:
        return int(s)
    except Exception:
        return default

DEFAULTS: dict[str, RuntimeConfigValue] = {
    "geo_radius": 50.0,
    "geo_center_lat": None,
    "geo_center_lon": None,
    "reminder_hours": 2,
    "late_minutes": 10,
    "weekly_limit": 2,
    "slot_length": 60,
    "admin_chat_id": None,
    "warning_chat_id": None,
    "access_chat_id": None,
    "member_chat_id": None,
    "member_topic_id": None,
    "equipment_topic_id": _get_optional_int_env("EQUIPMENT_TOPIC_ID", None),
    "rules_text": "Need to be updated.",
}
OPTIONAL_INT_CONFIG_KEYS = {"equipment_topic_id"}

_CACHE: dict[str, tuple[RuntimeConfigValue, float]] = {}
_CACHE_LOCK = asyncio.Lock()


def invalidate_runtime_config_cache(key: str | None = None) -> None:
    """
    Clears cached runtime config value(s).

    Called after config updates to avoid serving stale values.
    """
    if key is None:
        _CACHE.clear()
    else:
        _CACHE.pop(key, None)


def _parse_optional_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if s == "" or s.lower() == "none":
        return None
    try:
        return int(s)
    except Exception:
        return None


def _cast_value(key: str, raw: str | None) -> RuntimeConfigValue:
    if raw is None:
        return DEFAULTS[key]

    # int-or-none for chat/topic ids
    if key.endswith("_chat_id") or key.endswith("_topic_id"):
        v = _parse_optional_int(raw)
        if v is not None:
            return v
        if key in OPTIONAL_INT_CONFIG_KEYS:
            return None
        return DEFAULTS.get(key)

    default_val = DEFAULTS[key]
    try:
        if default_val is None:
            return raw
        return type(default_val)(raw)
    except Exception:
        log.warning(
            "Failed to cast config key=%r raw=%r to %s", key, raw, type(default_val)
        )
        return default_val


def _get_cached_value(
    key: str,
    ttl: int,
    now: float,
) -> tuple[bool, RuntimeConfigValue]:
    if ttl <= 0:
        return False, None

    cached = _CACHE.get(key)
    if cached is None:
        return False, None

    value, expires_at = cached
    if now < expires_at:
        return True, value

    return False, None


@overload
async def get_runtime_config(key: FloatRuntimeConfigKey) -> float: ...


@overload
async def get_runtime_config(key: IntRuntimeConfigKey) -> int: ...


@overload
async def get_runtime_config(key: OptionalIntRuntimeConfigKey) -> int | None: ...


@overload
async def get_runtime_config(key: OptionalStrRuntimeConfigKey) -> str | None: ...


@overload
async def get_runtime_config(key: StrRuntimeConfigKey) -> str: ...


@overload
async def get_runtime_config(key: str) -> RuntimeConfigValue: ...


async def get_runtime_config(key: str) -> RuntimeConfigValue:
    """
    Load config from DB. If not present, return fallback default.

    Improvements:
      - Logs unknown keys (helps catch typos)
      - Treat *_chat_id and *_topic_id as int-or-None
      - Safe casting based on DEFAULTS type
    """
    values = await get_many([key])
    return values[key]


async def get_many(keys: list[str]) -> dict[str, RuntimeConfigValue]:
    result: dict[str, RuntimeConfigValue] = {}
    valid_missing_keys: list[str] = []
    ttl = max(int(RUNTIME_CONFIG_CACHE_TTL or 0), 0)
    now = monotonic()

    for key in keys:
        if key not in DEFAULTS:
            log.warning("Unknown runtime config key requested: %r", key)
            result[key] = None
            continue

        has_cached, cached = _get_cached_value(key, ttl, now)
        if has_cached:
            result[key] = cached
            continue

        valid_missing_keys.append(key)

    if not valid_missing_keys:
        return result

    # Avoid stampede under bursty traffic.
    async with _CACHE_LOCK:
        query_keys: list[str] = []
        locked_now = monotonic()
        for key in valid_missing_keys:
            has_cached, cached = _get_cached_value(key, ttl, locked_now)
            if has_cached:
                result[key] = cached
                continue
            query_keys.append(key)

        rows: dict[str, str] = {}
        if query_keys:
            async with AsyncSessionLocal() as db:
                rows = await get_config_values(db, query_keys)

        expires_at = monotonic() + ttl
        for key in query_keys:
            value = _cast_value(key, rows.get(key))
            result[key] = value
            if ttl > 0:
                _CACHE[key] = (value, expires_at)

    return result


async def get_runtime_all() -> dict[str, RuntimeConfigValue]:
    return await get_many(list(DEFAULTS))
