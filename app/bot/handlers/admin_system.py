# app/bot/handlers/admin_system.py
from aiogram import F, Router, types

from app.bot.handlers.admin_shared import check_admin_callback
from app.bot.keyboards.admin_inline_kb import (
    admin_back_kb,
    admin_confirm_kb,
    admin_next_actions_kb,
)
from app.bot.ui import edit_or_answer, safe_answer_callback
from app.core.database import AsyncSessionLocal
from app.services.booking_service import weekly_reset
from app.services.scheduler_service import get_scheduler_jobs
from app.services.system_status import collect_system_status
from app.services.time_service import now_tz

router = Router()


def _format_metric_labels(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    return " " + ",".join(f"{key}={value}" for key, value in sorted(labels.items()))


def _format_metrics(status) -> list[str]:
    metrics = status.get("metrics", {})
    counters = metrics.get("counters", [])
    timings = metrics.get("timings", [])
    lines = ["", "Metrics:"]
    if not counters and not timings:
        return lines + ["No metrics recorded yet."]

    for sample in counters[:8]:
        lines.append(
            f"{sample.name}{_format_metric_labels(sample.labels)}: {sample.value}"
        )
    for sample in timings[:8]:
        avg = sample.total_seconds / sample.count if sample.count else 0.0
        lines.append(
            f"{sample.name}{_format_metric_labels(sample.labels)}: "
            f"count={sample.count}, avg={avg:.3f}s, max={sample.max_seconds:.3f}s"
        )
    return lines


def _system_next_kb():
    return admin_next_actions_kb(
        [
            ("Status", "admin_sys_status"),
            ("Scheduler", "admin_sys_scheduler"),
        ],
        back_data="admin_sys",
        back_text="⬅️ Back to system",
    )


@router.callback_query(F.data == "admin_sys_status")
async def admin_system_status(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    status = await collect_system_status()
    config = status.get("config", {})
    text = (
        "System status\n\n"
        f"Time now ({config.get('TIMEZONE', '')}): {now_tz().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Total users: {status.get('total_users')}\n"
        f"Allowed users: {status.get('allowed_users')}\n"
        f"Week bookings: {status.get('week_bookings')}\n"
        f"Weekly limit: {config.get('weekly_limit')}\n"
        f"Reminder hours: {config.get('reminder_hours')}\n"
        f"Late minutes: {config.get('late_minutes')}\n"
        f"Slot length: {config.get('slot_length')} minutes\n"
        f"Geo radius: {config.get('geo_radius')} meters"
    )
    text = "\n".join([text, *_format_metrics(status)])
    return await edit_or_answer(
        callback,
        text,
        reply_markup=admin_back_kb("admin_sys"),
    )


@router.callback_query(F.data == "admin_sys_scheduler")
async def admin_system_scheduler(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    jobs = get_scheduler_jobs()
    lines = ["Scheduler", ""]
    for job in jobs:
        lines.append(
            f"{job['id']}: next at {job['next_run_time']}, trigger={job['trigger']}"
        )
    return await edit_or_answer(
        callback,
        "\n".join(lines),
        reply_markup=admin_back_kb("admin_sys"),
    )


@router.callback_query(F.data == "admin_sys_reset")
async def admin_system_reset_prompt(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    return await edit_or_answer(
        callback,
        "Run weekly reset now?\n\nThis clears old non-weekly bookings.",
        reply_markup=admin_confirm_kb("admin_sys_reset_confirm", "admin_sys"),
    )


@router.callback_query(F.data == "admin_sys_reset_confirm")
async def admin_system_reset_confirm(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    async with AsyncSessionLocal() as db:
        await weekly_reset(db)
    return await edit_or_answer(
        callback,
        "Weekly reset completed.",
        reply_markup=_system_next_kb(),
    )
