# app/services/warning_service.py
import logging
from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from sqlalchemy import func, select, update

from app.models.user import User
from app.services.config_runtime import RuntimeConfigValue, get_many
from app.services.invite_service import send_access_granted_dm
from app.services.time_service import now_tz

log = logging.getLogger(__name__)

MAX_WARNINGS = 3
BAN_DURATIONS_MONTHS = (1, 3, 6)


@dataclass(frozen=True)
class BanResult:
    ban_count: int
    duration_months: int
    banned_until: datetime


@dataclass(frozen=True)
class WarningRevertResult:
    warnings: int
    was_banned: bool
    ban_count: int


async def _get_warning_notification_chat_id() -> RuntimeConfigValue:
    config = await get_many(["warning_chat_id", "admin_chat_id"])
    return config["warning_chat_id"] or config["admin_chat_id"]


def _add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _ban_duration_months(ban_count: int) -> int:
    index = min(max(ban_count, 1), len(BAN_DURATIONS_MONTHS)) - 1
    return BAN_DURATIONS_MONTHS[index]


def effective_unban_at(banned_until: datetime) -> datetime:
    """Return the next scheduler run that can actually lift this ban."""
    midnight = datetime.combine(
        banned_until.date(),
        time.min,
        tzinfo=banned_until.tzinfo,
    )
    if banned_until <= midnight:
        return midnight
    return midnight + timedelta(days=1)


def format_effective_unban_at(banned_until: datetime) -> str:
    return effective_unban_at(banned_until).strftime("%Y-%m-%d 00:00")


async def apply_progressive_ban(*, db, user: User, reason: str | None) -> BanResult:
    ban_count = (user.ban_count or 0) + 1
    duration_months = _ban_duration_months(ban_count)
    banned_until = _add_months(now_tz(), duration_months)

    user.allowed = False
    user.banned = True
    user.ban_reason = reason
    user.ban_count = ban_count
    user.banned_until = banned_until
    db.add(user)
    await db.commit()
    return BanResult(
        ban_count=ban_count,
        duration_months=duration_months,
        banned_until=banned_until,
    )


async def notify_manual_ban(
    *,
    bot,
    user: User,
    ban_result: BanResult,
    reason: str | None,
) -> None:
    if user.tg_user_id is None:
        return
    message = (
        "⛔ Access suspended\n\n"
        f"Reason: {reason or 'Manual admin ban'}\n"
        f"Ban duration: {ban_result.duration_months} month(s)\n"
        f"Until: {format_effective_unban_at(ban_result.banned_until)}"
    )
    try:
        await bot.send_message(user.tg_user_id, message)
    except Exception:
        log.exception(
            "Failed to notify user about manual ban",
            extra={"user_id": user.id, "tg_user_id": user.tg_user_id},
        )


async def unban_expired_users(*, db, bot) -> int:
    now = now_tz()
    users = list(
        (
            await db.execute(
                select(User)
                .where(User.banned.is_(True))
                .where(User.banned_until.is_not(None))
                .where(User.banned_until <= now)
            )
        ).scalars()
    )
    for user in users:
        user.banned = False
        user.ban_reason = None
        user.banned_until = None
        db.add(user)
    await db.commit()

    for user in users:
        if user.tg_user_id is None:
            continue
        try:
            await bot.send_message(
                user.tg_user_id,
                "✅ Your ban has expired and has been lifted automatically.\n\n"
                "Access is not restored automatically; contact an admin if you need access restored.",
            )
        except Exception:
            log.exception(
                "Failed to notify user about automatic unban",
                extra={"user_id": user.id, "tg_user_id": user.tg_user_id},
            )

    return len(users)


async def add_warning(
    *,
    db,
    bot,
    user_id: int,
    reason: str,
    appeal_allowed: bool = True,
) -> int | None:
    """
    Atomically add +1 warning to user (by user_id).
    Auto-bans on MAX_WARNINGS.
    Sends notifications.
    Returns new warning count, or None if user not found / already banned.
    """

    # Load minimal fields first (inside SAME session)
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if not user:
        return None

    if user.banned:
        return None  # already banned, no-op

    # ---- Atomic increment (prevents lost updates) ----
    res = await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(warnings=(func.coalesce(User.warnings, 0) + 1))
        .returning(
            User.warnings,
            User.allowed,
            User.banned,
            User.tg_user_id,
            User.tg_username,
            User.full_name,
        )
    )
    row = res.first()
    if not row:
        return None

    new_warnings = row[0]
    tg_user_id = row[3]
    tg_username = row[4]
    full_name = row[5]

    # ---- Auto-ban if reached limit ----
    if new_warnings >= MAX_WARNINGS:
        user = (
            await db.execute(select(User).where(User.id == user_id))
        ).scalar_one()
        ban_result = await apply_progressive_ban(
            db=db,
            user=user,
            reason=f"Reached {MAX_WARNINGS} warnings",
        )
        log.warning(
            "User auto-banned after warnings limit",
            extra={
                "user_id": user_id,
                "tg_user_id": tg_user_id,
                "warnings": new_warnings,
                "ban_count": ban_result.ban_count,
                "banned_until": ban_result.banned_until.isoformat(),
                "reason": reason,
            },
        )

        warning_chat_id = await _get_warning_notification_chat_id()

        # Notify user (best-effort)
        try:
            if tg_user_id:
                reply_markup = None
                if appeal_allowed:
                    from app.bot.keyboards.inline_kb import warning_appeal_kb

                    reply_markup = warning_appeal_kb(user_id, text="Appeal ban")

                await bot.send_message(
                    tg_user_id,
                    "⛔ Access suspended\n\n"
                    f"Reason: {reason}\n"
                    f"Warnings: {new_warnings}/{MAX_WARNINGS}\n"
                    f"Ban duration: {ban_result.duration_months} month(s)\n"
                    f"Until: {format_effective_unban_at(ban_result.banned_until)}",
                    reply_markup=reply_markup,
                )
        except Exception:
            log.exception(
                "Failed to notify user about auto-ban",
                extra={"user_id": user_id},
            )

        # Notify warning chat
        if warning_chat_id:
            try:
                from app.bot.keyboards.admin_inline_kb import warning_revert_kb

                display = full_name or (
                    f"@{tg_username}" if tg_username else f"id={user_id}"
                )
                await bot.send_message(
                    warning_chat_id,
                    "⛔ USER AUTO-BANNED\n"
                    f"User: {display}\n"
                    f"Reason: Reached {MAX_WARNINGS} warnings\n"
                    f"Ban: #{ban_result.ban_count}, {ban_result.duration_months} month(s)\n"
                    f"Until: {format_effective_unban_at(ban_result.banned_until)}",
                    reply_markup=warning_revert_kb(user_id),
                )
            except Exception:
                log.exception(
                    "Failed to notify warning chat about auto-ban",
                    extra={"user_id": user_id},
                )

        return new_warnings

    # Normal case: just commit warning increment
    await db.commit()  # commit before any network I/O
    log.info(
        "Warning issued",
        extra={
            "user_id": user_id,
            "tg_user_id": tg_user_id,
            "warnings": new_warnings,
            "reason": reason,
        },
    )

    warning_chat_id = await _get_warning_notification_chat_id()

    # Notify user (best-effort)
    try:
        if tg_user_id:
            reply_markup = None
            appeal_text = ""
            if appeal_allowed:
                from app.bot.keyboards.inline_kb import warning_appeal_kb

                reply_markup = warning_appeal_kb(user_id)
                appeal_text = "\nIf this is a mistake, tap Appeal warning."

            await bot.send_message(
                tg_user_id,
                f"⚠️ Warning {new_warnings}/{MAX_WARNINGS}\n\n"
                f"Reason: {reason}\n\n"
                f"At {MAX_WARNINGS} warnings, room access is temporarily suspended."
                f"{appeal_text}",
                reply_markup=reply_markup,
            )
    except Exception:
        log.exception("Failed to notify user about warning", extra={"user_id": user_id})

    # Warning chat notification
    if warning_chat_id:
        try:
            from app.bot.keyboards.admin_inline_kb import warning_revert_kb

            display = full_name or (
                f"@{tg_username}" if tg_username else f"id={user_id}"
            )
            await bot.send_message(
                warning_chat_id,
                "⚠️ Warning issued\n"
                f"User: {display}\n"
                f"Warnings: {new_warnings}/{MAX_WARNINGS}\n"
                f"Reason: {reason}",
                reply_markup=warning_revert_kb(user_id),
            )
        except Exception:
            log.exception(
                "Failed to notify warning chat about warning",
                extra={"user_id": user_id},
            )

    return new_warnings


async def approve_warning_appeal(*, db, bot, user_db_id: int) -> bool:
    """
    Removes one warning from the user. If they were banned, also unbans and
    sends an invite link. Returns False if user not found.
    """
    result = await revert_latest_warning(
        db=db,
        bot=bot,
        user_db_id=user_db_id,
        decrement_ban_count=False,
        user_notice="appeal",
    )
    if result is None:
        return False

    log.info(
        "Warning appeal approved",
        extra={
            "user_id": user_db_id,
            "warnings": result.warnings,
            "was_banned": result.was_banned,
        },
    )
    return True


async def revert_latest_warning(
    *,
    db,
    bot,
    user_db_id: int,
    decrement_ban_count: bool = True,
    user_notice: str = "revert",
) -> WarningRevertResult | None:
    """
    Removes one warning from the user. If they were banned, also unbans and
    restores access. When decrement_ban_count is true, also compensates the
    progressive ban counter for an auto-ban caused by the reverted warning.
    """
    user = (
        await db.execute(select(User).where(User.id == user_db_id))
    ).scalar_one_or_none()
    if not user:
        return None

    was_banned = bool(user.banned)
    new_warnings = max(0, (user.warnings or 0) - 1)
    new_ban_count = user.ban_count or 0

    user.warnings = new_warnings
    if was_banned:
        user.banned = False
        user.allowed = True
        user.ban_reason = None
        user.banned_until = None
        if decrement_ban_count:
            new_ban_count = max(0, new_ban_count - 1)
            user.ban_count = new_ban_count

    db.add(user)
    await db.commit()
    log.info(
        "Warning reverted",
        extra={
            "user_id": user_db_id,
            "warnings": new_warnings,
            "was_banned": was_banned,
            "ban_count": new_ban_count,
            "decrement_ban_count": decrement_ban_count,
        },
    )

    tg_user_id = user.tg_user_id
    if not tg_user_id:
        return WarningRevertResult(
            warnings=new_warnings,
            was_banned=was_banned,
            ban_count=new_ban_count,
        )

    if was_banned:
        if user_notice == "appeal":
            intro = "✅ Your warning appeal was approved and your ban has been lifted."
        else:
            intro = "✅ Your warning was reverted and your ban has been lifted."
        await send_access_granted_dm(bot, tg_user_id, intro=intro)
    else:
        try:
            notice_text = (
                "✅ Your warning appeal was approved."
                if user_notice == "appeal"
                else "✅ Your warning was reverted."
            )
            await bot.send_message(
                tg_user_id,
                f"{notice_text} Warnings: {new_warnings}/{MAX_WARNINGS}.",
            )
        except Exception:
            log.exception(
                "Failed to notify user of warning revert",
                extra={"user_db_id": user_db_id},
            )

    return WarningRevertResult(
        warnings=new_warnings,
        was_banned=was_banned,
        ban_count=new_ban_count,
    )

async def remove_warning(*, db, user_id: int) -> int | None:
    """
    Removes exactly ONE warning from a user (min = 0).
    Returns new warning count or None if user not found.
    """

    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()

    if not user:
        return None

    if not user.warnings or user.warnings <= 0:
        return 0

    res = await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(warnings=User.warnings - 1)
        .returning(User.warnings)
    )

    row = res.first()
    await db.commit()

    return row[0] if row else 0


async def reset_user_warnings(*, db, user_id: int) -> int | None:
    """Reset warnings for one user. Returns previous warning count."""
    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if not user:
        return None

    old_warnings = user.warnings or 0
    user.warnings = 0
    db.add(user)
    await db.commit()
    return old_warnings


async def reset_all_warnings(*, db) -> int:
    """Reset warning counts for all users that currently have warnings."""
    res = await db.execute(
        update(User)
        .where(User.warnings > 0)
        .values(warnings=0)
        .returning(User.id)
    )
    count = len(res.fetchall())
    await db.commit()
    return count


async def unban_all_users(*, db) -> int:
    """Clear bans for all banned users without restoring access."""
    res = await db.execute(
        update(User)
        .where(User.banned.is_(True))
        .values(banned=False, ban_reason=None, banned_until=None)
        .returning(User.id)
    )
    count = len(res.fetchall())
    await db.commit()
    return count
