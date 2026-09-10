# app/services/config_service.py

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.config_model import Config

DEFAULT_WORKING_HOURS = (9, 22)


def _invalidate_runtime_cache(key: str) -> None:
    # Avoid import cycles; best-effort cache invalidation.
    try:
        from app.services.config_runtime import invalidate_runtime_config_cache

        invalidate_runtime_config_cache(key)
    except Exception:
        pass


async def get_config_value(db: AsyncSession, key: str) -> str | None:
    q = await db.execute(select(Config).where(Config.key == key))
    row = q.scalar_one_or_none()
    return row.value if row else None


async def get_config_values(db: AsyncSession, keys: list[str]) -> dict[str, str]:
    if not keys:
        return {}

    q = await db.execute(select(Config.key, Config.value).where(Config.key.in_(keys)))
    return {key: value for key, value in q.all()}


async def set_config_value(db: AsyncSession, key: str, value: str) -> Config:
    q = await db.execute(select(Config).where(Config.key == key))
    row = q.scalar_one_or_none()
    if row:
        await db.execute(update(Config).where(Config.key == key).values(value=value))
        await db.commit()
        _invalidate_runtime_cache(key)
        q2 = await db.execute(select(Config).where(Config.key == key))
        return q2.scalar_one()
    else:
        conf = Config()
        conf.key = key
        conf.value = value
        db.add(conf)
        await db.commit()
        _invalidate_runtime_cache(key)
        await db.refresh(conf)
        return conf


async def get_all_config(db: AsyncSession) -> dict[str, str]:
    q = await db.execute(select(Config))
    rows = q.scalars().all()
    return {r.key: r.value for r in rows}


def parse_working_hours(value: str | None) -> tuple[int, int]:
    if not value:
        return DEFAULT_WORKING_HOURS

    try:
        start, end = value.split("-", 1)
        return int(start), int(end)
    except (TypeError, ValueError):
        return DEFAULT_WORKING_HOURS


async def get_working_hours(db: AsyncSession, weekday: str) -> tuple[int, int]:
    key = f"working_hours_{weekday}"
    value = await get_config_value(db, key)
    return parse_working_hours(value)


async def get_working_hours_bulk(
    db: AsyncSession,
    weekdays: list[str],
) -> dict[str, tuple[int, int]]:
    """
    Fetch working hours for many weekdays in a single query.
    Keys are stored as working_hours_{weekday}.
    """
    keys = [f"working_hours_{w}" for w in weekdays]
    res = await db.execute(select(Config.key, Config.value).where(Config.key.in_(keys)))
    rows = {k: v for k, v in res.all()}

    out: dict[str, tuple[int, int]] = {}
    for w in weekdays:
        out[w] = parse_working_hours(rows.get(f"working_hours_{w}"))
    return out
