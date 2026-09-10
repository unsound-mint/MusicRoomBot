import asyncio
import os
import subprocess
import sys
from typing import Any

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.admin import Admin
from app.models.config_model import Config
from app.models.user import User
from app.models.weekly_slot import WeeklySlot
from app.services.config_runtime import DEFAULTS

INITIAL_WEEKLY_SLOTS = [
    {"weekday": 0, "hour": 18, "group_name": "Art Revolution"},
    {"weekday": 0, "hour": 19, "group_name": "Art Revolution"},
    {"weekday": 2, "hour": 18, "group_name": "Art Revolution"},
    {"weekday": 2, "hour": 19, "group_name": "Art Revolution"},
    {"weekday": 4, "hour": 18, "group_name": "Art Revolution"},
    {"weekday": 4, "hour": 19, "group_name": "Art Revolution"},
    {"weekday": 6, "hour": 15, "group_name": "Art Revolution"},
    {"weekday": 6, "hour": 16, "group_name": "Art Revolution"},
    {"weekday": 1, "hour": 19, "group_name": "Vocal Club"},
    {"weekday": 1, "hour": 20, "group_name": "Vocal Club"},
    {"weekday": 3, "hour": 19, "group_name": "Vocal Club"},
    {"weekday": 3, "hour": 20, "group_name": "Vocal Club"},
    {"weekday": 5, "hour": 17, "group_name": "Vocal Club"},
    {"weekday": 5, "hour": 18, "group_name": "Vocal Club"},
    {"weekday": 6, "hour": 17, "group_name": "Vocal Club"},
    {"weekday": 6, "hour": 18, "group_name": "Vocal Club"},
    {"weekday": 5, "hour": 12, "group_name": "Orchestra"},
    {"weekday": 5, "hour": 13, "group_name": "Orchestra"},
    {"weekday": 0, "hour": 13, "group_name": "Acoustic Night"},
    {"weekday": 0, "hour": 14, "group_name": "Acoustic Night"},
    {"weekday": 5, "hour": 10, "group_name": "Acoustic Night"},
    {"weekday": 5, "hour": 11, "group_name": "Acoustic Night"},
]


def _env_int(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    return int(raw.strip())


def _env_str(name: str, default: str | None = None) -> str | None:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip()
    return value or default


def _config_defaults() -> dict[str, Any]:
    values = dict(DEFAULTS)
    for key in values:
        env_name = f"BOOTSTRAP_CONFIG_{key.upper()}"
        if env_name in os.environ:
            values[key] = os.environ[env_name]
    return values


def run_migrations() -> None:
    print("Running alembic upgrade head ...")
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"])


async def insert_missing_config(session: Any, key: str, value: Any) -> None:
    result = await session.execute(select(Config).where(Config.key == key))
    row = result.scalar_one_or_none()
    if row:
        return

    str_value = "" if value is None else str(value)
    session.add(Config(key=key, value=str_value))


async def seed_runtime_config(session: Any) -> None:
    for key, value in _config_defaults().items():
        await insert_missing_config(session, key, value)


async def seed_weekly_slots(session: Any) -> None:
    existing = (await session.execute(select(WeeklySlot))).scalars().all()
    existing_pairs = {(slot.weekday, slot.hour) for slot in existing}

    for slot in INITIAL_WEEKLY_SLOTS:
        pair = (slot["weekday"], slot["hour"])
        if pair in existing_pairs:
            continue
        session.add(
            WeeklySlot(
                weekday=slot["weekday"],
                hour=slot["hour"],
                group_name=slot["group_name"],
            )
        )


async def seed_initial_admin(session: Any) -> None:
    tg_user_id = _env_int("BOOTSTRAP_ADMIN_TG_ID")
    if tg_user_id is None:
        print("Skipping admin seed: BOOTSTRAP_ADMIN_TG_ID is not set.")
        return

    username = _env_str("BOOTSTRAP_ADMIN_TG_USERNAME")
    full_name = _env_str("BOOTSTRAP_ADMIN_FULL_NAME", "Bootstrap Admin")

    admin_result = await session.execute(
        select(Admin).where(Admin.tg_user_id == tg_user_id)
    )
    admin = admin_result.scalar_one_or_none()
    if admin:
        admin.tg_username = username
    else:
        session.add(Admin(tg_user_id=tg_user_id, tg_username=username))

    user_result = await session.execute(
        select(User).where(User.tg_user_id == tg_user_id)
    )
    user = user_result.scalar_one_or_none()
    if user:
        user.tg_username = username
        user.allowed = True
        if full_name:
            user.full_name = full_name
    else:
        session.add(
            User(
                tg_user_id=tg_user_id,
                tg_username=username,
                allowed=True,
                full_name=full_name,
            )
        )


async def seed_database() -> None:
    print("Seeding runtime config, weekly slots, and optional initial admin ...")
    async with AsyncSessionLocal() as session:
        await seed_runtime_config(session)
        await seed_weekly_slots(session)
        await seed_initial_admin(session)
        await session.commit()


def main() -> None:
    run_migrations()
    asyncio.run(seed_database())
    print("Bootstrap complete.")


if __name__ == "__main__":
    main()
