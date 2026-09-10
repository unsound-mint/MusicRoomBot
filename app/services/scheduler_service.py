# app/services/scheduler_service.py
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from hashlib import sha256
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers import SchedulerNotRunningError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text

from app.core.config import TIMEZONE
from app.core.database import AsyncSessionLocal
from app.core.metrics import increment, timed
from app.core.reset_gate import set_reset_in_progress
from app.services.booking_service import weekly_reset
from app.services.config_runtime import get_runtime_config
from app.services.geo_service import process_geo_checks
from app.services.reminder_service import process_reminders
from app.services.warning_service import unban_expired_users

if TYPE_CHECKING:
    from aiogram import Bot

log = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone=ZoneInfo(TIMEZONE))


def _advisory_lock_key(job_name: str) -> int:
    digest = sha256(f"musicroom:scheduler:{job_name}".encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


async def _run_with_advisory_lock(
    job_name: str,
    job: Callable[[], Awaitable[None]],
) -> bool:
    lock_key = _advisory_lock_key(job_name)
    async with AsyncSessionLocal() as db:
        lock_result = await db.execute(
            text("SELECT pg_try_advisory_lock(:lock_key)"),
            {"lock_key": lock_key},
        )
        acquired = bool(lock_result.scalar())
        if not acquired:
            increment(
                "scheduler_job_total",
                labels={"job": job_name, "status": "skipped_lock"},
            )
            log.info(
                "Skipping scheduled job because advisory lock is held",
                extra={"job": job_name},
            )
            return False

        try:
            with timed("scheduler_job_seconds", labels={"job": job_name}):
                await job()
            increment(
                "scheduler_job_total",
                labels={"job": job_name, "status": "success"},
            )
            return True
        except Exception:
            increment(
                "scheduler_job_total",
                labels={"job": job_name, "status": "failed"},
            )
            raise
        finally:
            try:
                await db.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": lock_key},
                )
            except Exception:
                log.exception(
                    "Failed to release scheduled job advisory lock",
                    extra={"job": job_name},
                )


async def weekly_reset_job(bot: Bot | None) -> None:
    if bot is None:
        log.warning("Skipping weekly reset job because bot is missing")
        return

    async def run() -> None:
        set_reset_in_progress(True)
        try:
            async with AsyncSessionLocal() as db:
                await weekly_reset(db)
        except Exception:
            log.exception("Weekly reset job failed")
            raise
        finally:
            set_reset_in_progress(False)

        admin_chat_id = await get_runtime_config("admin_chat_id")
        if admin_chat_id:
            try:
                await bot.send_message(admin_chat_id, "Weekly reset completed.")
            except Exception:
                log.exception(
                    "Failed to send weekly reset admin notification",
                    extra={"chat_id": admin_chat_id},
                )

        member_chat_id = await get_runtime_config("member_chat_id")
        member_topic_id = await get_runtime_config("member_topic_id")

        if member_chat_id:
            text = "Weekly reset completed. Old non-weekly bookings were cleared."
            try:
                if member_topic_id:
                    await bot.send_message(
                        member_chat_id, text, message_thread_id=member_topic_id
                    )
                else:
                    await bot.send_message(member_chat_id, text)
            except Exception:
                log.exception(
                    "Failed to send weekly reset member notification",
                    extra={"chat_id": member_chat_id, "topic_id": member_topic_id},
                )

    await _run_with_advisory_lock("weekly_reset", run)


async def reminder_job(bot: Bot | None) -> None:
    if bot is None:
        log.warning("Skipping reminder job because bot is missing")
        return

    async def run() -> None:
        try:
            await process_reminders(bot)
        except Exception:
            log.exception("Reminder job failed")
            raise

    await _run_with_advisory_lock("reminders", run)


async def geo_job(bot: Bot | None) -> None:
    if bot is None:
        log.warning("Skipping geo job because bot is missing")
        return

    async def run() -> None:
        try:
            await process_geo_checks(bot)
        except Exception:
            log.exception("Geo job failed")
            raise

    await _run_with_advisory_lock("geo_checks", run)


async def expired_bans_job(bot: Bot | None) -> None:
    if bot is None:
        log.warning("Skipping expired bans job because bot is missing")
        return

    async def run() -> None:
        try:
            async with AsyncSessionLocal() as db:
                count = await unban_expired_users(db=db, bot=bot)
            if count:
                log.info("Expired bans lifted", extra={"count": count})
        except Exception:
            log.exception("Expired bans job failed")
            raise

    await _run_with_advisory_lock("expired_bans", run)


def setup_scheduler(bot: Bot) -> None:
    """
    Register all scheduled tasks with explicit bot argument.
    Uses stable job IDs to avoid duplicates if setup_scheduler() runs twice.
    """
    scheduler.add_job(
        weekly_reset_job,
        CronTrigger(day_of_week="sun", hour=22, minute=0),
        kwargs={"bot": bot},
        id="weekly_reset",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    scheduler.add_job(
        reminder_job,
        CronTrigger(minute="*"),
        kwargs={"bot": bot},
        id="reminders",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    scheduler.add_job(
        geo_job,
        CronTrigger(minute="*"),
        kwargs={"bot": bot},
        id="geo_checks",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    scheduler.add_job(
        expired_bans_job,
        CronTrigger(hour=0, minute=0),
        kwargs={"bot": bot},
        id="expired_bans",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    if not scheduler.running:
        scheduler.start()
        log.info("Scheduler started", extra={"timezone": TIMEZONE})
    log.info(
        "Scheduler jobs configured",
        extra={"job_ids": ",".join(job.id for job in scheduler.get_jobs())},
    )


def shutdown_scheduler(*, wait: bool = False) -> None:
    with suppress(SchedulerNotRunningError):
        scheduler.shutdown(wait=wait)
        log.info("Scheduler stopped", extra={"wait": wait})


def get_scheduler_jobs() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for job in scheduler.get_jobs():
        result.append(
            {
                "id": job.id,
                "next_run_time": job.next_run_time,
                "trigger": str(job.trigger),
            }
        )
    return result
