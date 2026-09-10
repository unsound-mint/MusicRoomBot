# app/bot/handlers/equipment_request_ranges.py
from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from app.bot.handlers.equipment_request_messages import (
    range_end_date_text,
    range_end_hour_text,
    range_start_date_text,
    range_start_hour_text,
    range_summary_text,
)
from app.bot.keyboards.inline_kb import (
    equipment_request_day_kb,
    equipment_request_hour_kb,
    equipment_request_range_actions_kb,
)
from app.bot.ui import edit_or_answer
from app.services.equipment_request_service import (
    format_equipment_range,
    summarize_equipment_ranges,
)
from app.services.time_service import now_tz


def state_ranges(data: dict[str, Any]) -> list[dict[str, str]]:
    raw = data.get("ranges")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def parse_state_range(item: dict[str, str]) -> dict[str, datetime]:
    return {
        "start_at": datetime.fromisoformat(item["start_at"]),
        "end_at": datetime.fromisoformat(item["end_at"]),
    }


def parsed_state_ranges(data: dict[str, Any]) -> list[dict[str, datetime]]:
    return [parse_state_range(item) for item in state_ranges(data)]


def serialize_range(start_at: datetime, end_at: datetime) -> dict[str, str]:
    return {
        "start_at": start_at.isoformat(),
        "end_at": end_at.isoformat(),
    }


def range_summary_from_state(data: dict[str, Any]) -> str:
    return summarize_equipment_ranges(
        [
            SimpleNamespace(**parse_state_range(item))
            for item in state_ranges(data)
        ]
    )


def ranges_needed_at_text(ranges: list[dict[str, str]]) -> str | None:
    return (
        "\n".join(
            format_equipment_range(
                datetime.fromisoformat(item["start_at"]),
                datetime.fromisoformat(item["end_at"]),
            )
            for item in ranges
        )
        or None
    )


async def render_range_step(target: Any, text: str, *, reply_markup: Any) -> None:
    if hasattr(target, "message"):
        await edit_or_answer(target, text, reply_markup=reply_markup)
        return
    await target.answer(text, reply_markup=reply_markup)


def equipment_picker_days() -> list[date]:
    today = now_tz().date()
    return [today + timedelta(days=offset) for offset in range(30)]


def equipment_picker_hours(target_date: date) -> list[int]:
    now = now_tz()
    if target_date == now.date():
        start_hour = now.hour + 1
        return [hour for hour in range(start_hour, 24)]
    return list(range(24))


async def render_range_start_day_picker(target: Any) -> None:
    await render_range_step(
        target,
        range_start_date_text(),
        reply_markup=equipment_request_day_kb(
            equipment_picker_days(),
            callback_prefix="equip_rngstartday",
            back_callback="equip_rngback_prev",
        ),
    )


async def render_range_start_hour_picker(callback: Any, target_date: date) -> None:
    hours = equipment_picker_hours(target_date)
    if not hours:
        return await callback.message.answer("⚠️ No future hours left for that date.")
    await edit_or_answer(
        callback,
        range_start_hour_text(target_date.isoformat()),
        reply_markup=equipment_request_hour_kb(
            target_date,
            hours,
            callback_prefix="equip_rngstarthour",
            back_callback="equip_rngback_startdays",
        ),
    )


async def render_range_end_day_picker(target: Any, start_at: datetime) -> None:
    start_date = start_at.date()
    max_end_date = start_date + timedelta(days=4)
    days = [
        day
        for day in equipment_picker_days()
        if start_date <= day <= max_end_date
    ]
    await render_range_step(
        target,
        range_end_date_text(),
        reply_markup=equipment_request_day_kb(
            days,
            callback_prefix="equip_rngendday",
            back_callback=f"equip_rngback_starthour_{start_at.date().isoformat()}_{start_at.hour}",
        ),
    )


async def render_range_end_hour_picker(
    callback: Any,
    start_at: datetime,
    target_date: date,
) -> None:
    hours = equipment_picker_hours(target_date)
    if target_date == start_at.date():
        hours = [hour for hour in hours if hour > start_at.hour]
    if not hours:
        return await callback.message.answer("⚠️ No valid end hours left for that date.")
    await edit_or_answer(
        callback,
        range_end_hour_text(target_date.isoformat()),
        reply_markup=equipment_request_hour_kb(
            target_date,
            hours,
            callback_prefix="equip_rngendhour",
            back_callback="equip_rngback_enddays",
        ),
    )


async def render_range_summary(target: Any, state: Any) -> None:
    data = await state.get_data()
    await render_range_step(
        target,
        range_summary_text(range_summary_from_state(data)),
        reply_markup=equipment_request_range_actions_kb(
            has_ranges=bool(state_ranges(data)),
            back_callback="equip_rngback_summary",
        ),
    )
