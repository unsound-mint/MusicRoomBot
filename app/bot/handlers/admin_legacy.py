# app/bot/handlers/admin_legacy.py
from aiogram import Router, types
from aiogram.filters import Command

from app.bot.handlers.admin_legacy_config import router as config_router
from app.bot.handlers.admin_legacy_users import router as users_router
from app.bot.handlers.admin_legacy_warnings import router as warnings_router
from app.bot.handlers.admin_shared import check_admin_and_reply
from app.services.scheduler_service import get_scheduler_jobs
from app.services.system_status import collect_system_status
from app.services.time_service import now_tz

router = Router()
router.include_router(users_router)
router.include_router(warnings_router)


def _format_metric_labels(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    return " " + ",".join(f"{key}={value}" for key, value in sorted(labels.items()))


def _metric_lines(status) -> list[str]:
    metrics = status.get("metrics", {})
    counters = metrics.get("counters", [])
    timings = metrics.get("timings", [])
    lines = ["", "Metrics:"]
    if not counters and not timings:
        return lines + ["• No metrics recorded yet"]

    for sample in counters[:8]:
        lines.append(
            f"• {sample.name}{_format_metric_labels(sample.labels)}: {sample.value}"
        )
    for sample in timings[:8]:
        avg = sample.total_seconds / sample.count if sample.count else 0.0
        lines.append(
            f"• {sample.name}{_format_metric_labels(sample.labels)}: "
            f"count={sample.count}, avg={avg:.3f}s, max={sample.max_seconds:.3f}s"
        )
    return lines


@router.message(Command("system_status"))
async def cmd_system_status(message: types.Message):
    if not await check_admin_and_reply(message):
        return

    status = await collect_system_status()
    config = status.get("config", {})
    jobs = get_scheduler_jobs()
    sched_lines = ["Scheduler:"]
    for job in jobs:
        sched_lines.append(
            f"• {job['id']}: next at {job['next_run_time']}, trigger={job['trigger']}"
        )
    sched_lines.append("")

    text = (
        [
            "System Status:\n",
            f"Time now ({config.get('TIMEZONE', '')}): {now_tz().strftime('%Y-%m-%d %H:%M:%S')}\n",
            "Bot:",
            "• Running",
            "",
            "Database:",
            "• Connection: OK",
            "",
        ]
        + sched_lines
        + [
            "Users:",
            f"• Total users: {status.get('total_users')}",
            f"• Allowed users: {status.get('allowed_users')}",
            "",
            "Bookings:",
            f"• This week: {status.get('week_bookings')}",
            "",
            "Config:",
            f"• Weekly limit: {config.get('weekly_limit')}",
            f"• Reminder hours: {config.get('reminder_hours')}",
            f"• Late minutes: {config.get('late_minutes')}",
            f"• Slot length: {config.get('slot_length')} minutes",
            f"• Geo radius: {config.get('geo_radius')} meters",
            f"• Geo center: {config.get('geo_center_lat')}, {config.get('geo_center_lon')}",
            f"• Admin chat ID: {config.get('admin_chat_id')}",
        ]
        + _metric_lines(status)
    )
    await message.answer("\n".join(text))


router.include_router(config_router)
