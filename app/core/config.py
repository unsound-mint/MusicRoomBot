# app/core/config.py
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=False)  # loads .env in project root if present


def _read_secret_file(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _get_env(name: str, default: str | None = None) -> str | None:
    raw = os.environ.get(name)
    if raw is None:
        file_path = os.environ.get(f"{name}_FILE")
        raw = _read_secret_file(file_path) if file_path else None

    if raw is None:
        return default

    value = raw.strip()
    return value or default


def _normalize_database_url(url: str | None) -> str | None:
    if url is None:
        return None
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    return url


def _normalize_log_level(level: str | None) -> str:
    if level is None:
        return "INFO"

    normalized = level.strip().upper()
    if normalized in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}:
        return normalized

    return "INFO"


BOT_TOKEN = _get_env("BOT_TOKEN")
DATABASE_URL = _normalize_database_url(_get_env("DATABASE_URL"))
TIMEZONE = _get_env("TIMEZONE", "Asia/Almaty") or "Asia/Almaty"
LOG_LEVEL = _normalize_log_level(_get_env("LOG_LEVEL", "INFO"))
ACCESS_FORM_URL = _get_env("ACCESS_FORM_URL", "https://forms.gle/YEiqGNfKt7fAbqFP9")


def require_bot_token() -> str:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    return BOT_TOKEN


def require_database_url() -> str:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return DATABASE_URL


def _get_int_env(name: str, default: int) -> int:
    raw = _get_env(name)
    if raw is None:
        return default
    try:
        return int(str(raw).strip())
    except Exception:
        return default


# SQLAlchemy connection pool tuning.
# Defaults are conservative for Postgres on a small host, but enough to survive bursty bot traffic.
DB_POOL_SIZE = _get_int_env("DB_POOL_SIZE", 20)
DB_MAX_OVERFLOW = _get_int_env("DB_MAX_OVERFLOW", 10)
DB_POOL_TIMEOUT = _get_int_env("DB_POOL_TIMEOUT", 30)

# Runtime config values are read very frequently; cache them briefly to avoid DB pool exhaustion.
RUNTIME_CONFIG_CACHE_TTL = _get_int_env("RUNTIME_CONFIG_CACHE_TTL", 30)
