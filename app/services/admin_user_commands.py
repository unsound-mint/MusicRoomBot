from dataclasses import dataclass
from enum import Enum
from typing import Literal

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import Admin
from app.models.booking import Booking
from app.models.swap_offer import SwapOffer
from app.models.user import User
from app.services.admin_service import add_admin
from app.services.warning_service import (
    BanResult,
    apply_progressive_ban,
    notify_manual_ban,
)


class AddAdminResult(Enum):
    ADDED = "added"
    ALREADY_ADMIN = "already_admin"
    USER_NOT_FOUND = "user_not_found"
    USER_NOT_STARTED = "user_not_started"


AllowOrAddStatus = Literal["created", "updated", "already_allowed", "banned"]


@dataclass(frozen=True)
class AllowOrAddUserResult:
    status: AllowOrAddStatus
    user: User
    did_allow: bool
    did_rename: bool

    @property
    def tg_user_id(self) -> int | None:
        return self.user.tg_user_id


@dataclass(frozen=True)
class RevokeAccessResult:
    user_found: bool
    tg_user_id: int | None = None
    already_revoked: bool = False


@dataclass(frozen=True)
class RevokedBulkUser:
    tg_user_id: int | None
    tg_username: str | None


@dataclass(frozen=True)
class BulkMemberSyncResult:
    updated_revoked: int
    revoked_admins_skipped: int
    revoked_users: list[RevokedBulkUser]


@dataclass(frozen=True)
class BanUserResult:
    user_found: bool
    ban_result: BanResult | None = None


async def _get_user_by_username(db: AsyncSession, username: str) -> User | None:
    normalized = username.strip().lstrip("@").lower()
    return (
        await db.execute(select(User).where(func.lower(User.tg_username) == normalized))
    ).scalar_one_or_none()


async def allow_user(db: AsyncSession, username: str) -> User | None:
    user = await _get_user_by_username(db, username)
    if user is None:
        return None

    user.allowed = True
    user.banned = False
    user.ban_reason = None
    user.banned_until = None
    await db.commit()
    return user


async def allow_or_add_user(
    db: AsyncSession,
    *,
    username: str,
    full_name: str | None,
) -> AllowOrAddUserResult:
    username = username.strip().lstrip("@").lower()
    users = (
        (
            await db.execute(
                select(User)
                .where(func.lower(User.tg_username) == username)
                .order_by(User.id.desc())
            )
        )
        .scalars()
        .all()
    )

    user = next((candidate for candidate in users if candidate.tg_user_id is not None), None)
    placeholder_users = [candidate for candidate in users if candidate.tg_user_id is None]

    if user is None and placeholder_users and full_name is not None:
        candidates = (
            (
                await db.execute(
                    select(User)
                    .where(User.tg_user_id.isnot(None))
                    .where(User.full_name == full_name)
                    .order_by(User.id.desc())
                )
            )
            .scalars()
            .all()
        )
        if len(candidates) == 1:
            user = candidates[0]
            for placeholder in placeholder_users:
                await db.delete(placeholder)
            placeholder_users = []
            if user.tg_username != username:
                user.tg_username = username

    if user:
        if user.banned:
            return AllowOrAddUserResult(
                status="banned",
                user=user,
                did_allow=False,
                did_rename=False,
            )

        did_rename = False
        did_allow = False
        if full_name is not None and full_name != (user.full_name or ""):
            user.full_name = full_name
            did_rename = True
        if not user.allowed:
            user.allowed = True
            did_allow = True

        if not did_allow and not did_rename:
            return AllowOrAddUserResult(
                status="already_allowed",
                user=user,
                did_allow=False,
                did_rename=False,
            )

        for placeholder in placeholder_users:
            await db.delete(placeholder)

        await db.commit()
        return AllowOrAddUserResult(
            status="updated",
            user=user,
            did_allow=did_allow,
            did_rename=did_rename,
        )

    new_user = User()
    new_user.tg_username = username
    new_user.full_name = full_name
    new_user.allowed = True
    db.add(new_user)
    await db.commit()
    return AllowOrAddUserResult(
        status="created",
        user=new_user,
        did_allow=True,
        did_rename=full_name is not None,
    )


async def unban_user(db: AsyncSession, username: str) -> User | None:
    user = await _get_user_by_username(db, username)
    if user is None:
        return None

    user.banned = False
    user.ban_reason = None
    user.banned_until = None
    user.warnings = 0
    await db.commit()
    return user


async def sync_allowed_members_from_usernames(
    db: AsyncSession,
    allowed_usernames: set[str],
) -> BulkMemberSyncResult:
    admin_ids = set((await db.execute(select(Admin.tg_user_id))).scalars().all())
    existing_users = (await db.execute(select(User))).scalars().all()
    updated_revoked = 0
    revoked_admins_skipped = 0
    revoked_users: list[RevokedBulkUser] = []

    for user in existing_users:
        canon = user.tg_username.lstrip("@").lower() if user.tg_username else None
        if not canon:
            continue
        if user.tg_user_id and user.tg_user_id in admin_ids:
            if canon not in allowed_usernames:
                revoked_admins_skipped += 1
            continue
        if canon not in allowed_usernames:
            if user.allowed:
                updated_revoked += 1
                revoked_users.append(
                    RevokedBulkUser(
                        tg_user_id=user.tg_user_id,
                        tg_username=user.tg_username,
                    )
                )
            user.allowed = False
            db.add(user)

    await db.commit()
    return BulkMemberSyncResult(
        updated_revoked=updated_revoked,
        revoked_admins_skipped=revoked_admins_skipped,
        revoked_users=revoked_users,
    )


async def delete_user_by_username(db: AsyncSession, username: str) -> bool:
    user = await _get_user_by_username(db, username)
    if user is None or user.id is None:
        return False

    user_id = user.id
    await db.execute(
        delete(SwapOffer).where(
            (SwapOffer.giver_user_id == user_id) | (SwapOffer.receiver_user_id == user_id)
        )
    )
    await db.execute(delete(Booking).where(Booking.user_id == user_id))
    await db.delete(user)
    await db.commit()
    return True


async def revoke_user_access(db: AsyncSession, username: str) -> RevokeAccessResult:
    user = await _get_user_by_username(db, username)
    if user is None:
        return RevokeAccessResult(user_found=False)
    if not user.allowed:
        return RevokeAccessResult(
            user_found=True,
            tg_user_id=user.tg_user_id,
            already_revoked=True,
        )

    user.allowed = False
    await db.commit()
    return RevokeAccessResult(user_found=True, tg_user_id=user.tg_user_id)


async def ban_user(
    db: AsyncSession,
    *,
    username: str,
    bot,
    reason: str | None,
) -> BanUserResult:
    user = await _get_user_by_username(db, username)
    if user is None:
        return BanUserResult(user_found=False)

    ban_result = await apply_progressive_ban(db=db, user=user, reason=reason)
    await notify_manual_ban(
        bot=bot,
        user=user,
        ban_result=ban_result,
        reason=reason,
    )
    return BanUserResult(user_found=True, ban_result=ban_result)


async def add_admin_by_username(db: AsyncSession, username: str) -> AddAdminResult:
    user = await _get_user_by_username(db, username)
    if user is None:
        return AddAdminResult.USER_NOT_FOUND
    if user.tg_user_id is None:
        return AddAdminResult.USER_NOT_STARTED

    try:
        await add_admin(db, user.tg_user_id, user.tg_username)
    except IntegrityError:
        await db.rollback()
        return AddAdminResult.ALREADY_ADMIN

    return AddAdminResult.ADDED
