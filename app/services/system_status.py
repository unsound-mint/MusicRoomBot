# app/services/system_status.py

from typing import TypedDict

from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.core.metrics import CounterSample, TimingSample, snapshot
from app.models.booking import Booking
from app.models.user import User
from app.services.config_runtime import get_runtime_all
from app.services.date_service import get_current_week_dates

type RuntimeConfigSnapshot = dict[str, str | int | float | None]


class SystemStatus(TypedDict):
    config: RuntimeConfigSnapshot
    total_users: int | None
    allowed_users: int | None
    week_bookings: int | None
    metrics: dict[str, list[CounterSample] | list[TimingSample]]


async def collect_system_status() -> SystemStatus:
    data: SystemStatus = {
        "config": {},
        "total_users": None,
        "allowed_users": None,
        "week_bookings": None,
        "metrics": snapshot(),
    }

    # Load config
    config = await get_runtime_all()
    data["config"] = config

    async with AsyncSessionLocal() as db:
        # Users total
        q = await db.execute(select(func.count(User.id)))
        data["total_users"] = q.scalar()

        # Allowed users
        q = await db.execute(select(func.count(User.id)).where(User.allowed.is_(True)))
        data["allowed_users"] = q.scalar()

        # Bookings this week
        week = get_current_week_dates()
        monday, sunday = week[0], week[-1]

        q = await db.execute(
            select(func.count(Booking.id))
            .where(Booking.date >= monday)
            .where(Booking.date <= sunday)
        )
        data["week_bookings"] = q.scalar()

    return data
