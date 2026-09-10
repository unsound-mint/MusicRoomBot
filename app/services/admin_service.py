# app/services/admin_service.py
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import Admin

log = logging.getLogger(__name__)


async def is_admin(db: AsyncSession, tg_user_id: int) -> bool:
    q = await db.execute(select(Admin).where(Admin.tg_user_id == tg_user_id))
    return q.scalar_one_or_none() is not None


async def add_admin(
    db: AsyncSession,
    tg_user_id: int,
    tg_username: str | None = None,
) -> Admin:
    admin = Admin()
    admin.tg_user_id = tg_user_id
    admin.tg_username = tg_username
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    log.info(
        "Admin added",
        extra={"admin_id": admin.id, "tg_user_id": tg_user_id, "tg_username": tg_username},
    )
    return admin


async def list_admins(db: AsyncSession) -> list[Admin]:
    q = await db.execute(select(Admin))
    return list(q.scalars().all())
