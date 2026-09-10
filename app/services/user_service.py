# app/services/user_service.py
import logging
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class StartUserResult:
    user: User
    created: bool


async def get_user_by_tg_id(db: AsyncSession, tg_user_id: int) -> User | None:
    q = await db.execute(select(User).where(User.tg_user_id == tg_user_id))
    return q.scalar_one_or_none()


async def create_or_update_user(
    db: AsyncSession,
    tg_user_id: int,
    tg_username: str | None,
    full_name: str | None,
    allowed: bool = False,
) -> User:
    u = await get_user_by_tg_id(db, tg_user_id)

    if u:
        # Always update Telegram username if changed
        u.tg_username = tg_username

        # IMPORTANT:
        # Only update full_name if explicitly provided (admin action)
        if full_name is not None:
            u.full_name = full_name

        # Never downgrade allowed flag
        # (Admin may set allowed=True but user should never turn it to False)
        if allowed:
            u.allowed = True

        db.add(u)
        await db.commit()
        await db.refresh(u)
        log.info(
            "User updated",
            extra={
                "user_id": u.id,
                "tg_user_id": tg_user_id,
                "tg_username": tg_username,
                "allowed": u.allowed,
            },
        )
        return u

    # New user created
    user = User()
    user.tg_user_id = tg_user_id
    user.tg_username = tg_username
    user.full_name = full_name
    user.allowed = allowed
    db.add(user)
    await db.commit()
    await db.refresh(user)
    log.info(
        "User created",
        extra={
            "user_id": user.id,
            "tg_user_id": tg_user_id,
            "tg_username": tg_username,
            "allowed": allowed,
        },
    )
    return user


async def resolve_start_user(
    db: AsyncSession,
    *,
    tg_user_id: int,
    tg_username: str,
    telegram_full_name: str,
) -> StartUserResult:
    user = await get_user_by_tg_id(db, tg_user_id)

    if user and tg_username:
        await _delete_stale_username_placeholders(db, tg_username, keep_user_id=user.id)

    if not user and tg_username:
        user = await _bind_latest_username_placeholder(
            db,
            tg_user_id=tg_user_id,
            tg_username=tg_username,
        )

    if not user:
        user = await create_or_update_user(
            db,
            tg_user_id=tg_user_id,
            tg_username=tg_username,
            full_name=telegram_full_name,
            allowed=False,
        )
        log.info(
            "Start user resolved as new user",
            extra={"user_id": user.id, "tg_user_id": tg_user_id},
        )
        return StartUserResult(user=user, created=True)

    if tg_username and user.tg_username != tg_username:
        await _delete_stale_username_placeholders(db, tg_username, keep_user_id=user.id)
        user.tg_username = tg_username

    if not user.full_name:
        user.full_name = telegram_full_name

    db.add(user)
    await db.commit()
    log.info(
        "Start user resolved",
        extra={
            "user_id": user.id,
            "tg_user_id": tg_user_id,
            "start_user_created": False,
        },
    )
    return StartUserResult(user=user, created=False)


async def _delete_stale_username_placeholders(
    db: AsyncSession,
    tg_username: str,
    *,
    keep_user_id: int,
) -> None:
    await db.execute(
        delete(User).where(
            User.tg_user_id.is_(None),
            User.tg_username == tg_username,
            User.id != keep_user_id,
        )
    )


async def _bind_latest_username_placeholder(
    db: AsyncSession,
    *,
    tg_user_id: int,
    tg_username: str,
) -> User | None:
    result = await db.execute(
        select(User).where(User.tg_username == tg_username).order_by(User.id.desc())
    )
    user = next((u for u in result.scalars().all() if u.tg_user_id is None), None)
    if user is None:
        return None

    user.tg_user_id = tg_user_id
    user.tg_username = tg_username
    db.add(user)
    await db.commit()
    await db.refresh(user)
    log.info(
        "Username placeholder bound",
        extra={"user_id": user.id, "tg_user_id": tg_user_id, "tg_username": tg_username},
    )
    return user


async def list_users(db: AsyncSession) -> list[User]:
    q = await db.execute(
        select(User).order_by(
            func.lower(func.coalesce(User.full_name, "")),
            func.lower(func.coalesce(User.tg_username, "")),
            User.id,
        )
    )
    return list(q.scalars().all())
