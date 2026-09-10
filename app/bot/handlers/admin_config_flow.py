from app.bot.constants.dates import WEEKDAYS
from app.bot.handlers.admin_config_messages import (
    build_chat_id_prompt,
    build_numeric_prompt,
    build_working_hours_confirm_text,
    build_working_hours_prompt,
)
from app.bot.handlers.admin_shared import (
    AdminInputStates,
    render_config_menu,
)
from app.bot.keyboards.admin_inline_kb import (
    admin_back_kb,
    admin_chat_ids_kb,
    admin_confirm_kb,
    admin_next_actions_kb,
    numeric_value_kb,
    working_hours_value_kb,
    working_hours_weekday_kb,
)
from app.bot.markdown import MARKDOWN_PARSE_MODE
from app.bot.ui import edit_or_answer
from app.core.database import AsyncSessionLocal
from app.services.config_runtime import DEFAULTS, get_runtime_config
from app.services.config_service import get_working_hours, set_config_value

NUMERIC_PRESETS = {
    "admin_cfg_weekly_limit": ("weekly_limit", "Weekly limit", [1, 2, 3, 4]),
    "admin_cfg_slot_length": ("slot_length", "Slot length", [30, 60, 90, 120]),
    "admin_cfg_reminder_hours": ("reminder_hours", "Reminder hours", [0, 1, 2, 4]),
    "admin_cfg_late_minutes": ("late_minutes", "Late minutes", [5, 10, 15, 20]),
    "admin_cfg_geo_radius": ("geo_radius", "Geo radius", [30, 50, 75, 100]),
}

CHAT_ID_LABELS = {
    "admin_chat_id": "Admin chat ID",
    "warning_chat_id": "Warning chat ID",
    "member_chat_id": "Member chat ID",
    "member_topic_id": "Member topic ID",
    "equipment_topic_id": "Equipment topic ID",
    "access_chat_id": "Access chat ID",
}

NUMERIC_PRESET_SUFFIXES = {"limit", "length", "hours", "minutes", "radius"}


def _config_next_kb(*, action_text: str = "Change another setting", action_data: str = "admin_cfg"):
    return admin_next_actions_kb(
        [(action_text, action_data)],
        back_data="admin_cfg",
        back_text="⬅️ Back to config",
    )


def _numeric_prefix(data: str) -> str:
    parts = data.split("_")
    if len(parts) > 3 and parts[3] in NUMERIC_PRESET_SUFFIXES:
        return "_".join(parts[:4])
    return "_".join(parts[:3])


async def _handle_numeric_config(callback, state, data: str):
    if data in NUMERIC_PRESETS:
        key, label, values = NUMERIC_PRESETS[data]
        current = await get_runtime_config(key)
        return await edit_or_answer(
            callback,
            build_numeric_prompt(label, current),
            reply_markup=numeric_value_kb(data, values, back_data="admin_cfg"),
            parse_mode=MARKDOWN_PARSE_MODE,
        )

    if not any(data.startswith(prefix + "_") for prefix in NUMERIC_PRESETS):
        return None

    prefix = _numeric_prefix(data)
    if data.endswith("_custom"):
        key, label, _ = NUMERIC_PRESETS[prefix]
        await state.set_state(AdminInputStates.waiting_custom_value)
        await state.update_data(
            admin_action="cfg_custom",
            admin_config_key=key,
            admin_back="admin_cfg",
        )
        return await edit_or_answer(
            callback,
            f"Send a custom value for {label}.",
            reply_markup=admin_back_kb("admin_cfg"),
        )

    value = data.split("_")[-1]
    key, label, _ = NUMERIC_PRESETS[prefix]
    async with AsyncSessionLocal() as db:
        await set_config_value(db, key, str(value))
    return await edit_or_answer(
        callback,
        f"{label} updated to {value}.",
        reply_markup=_config_next_kb(),
    )


async def _handle_chat_ids(callback, state, data: str):
    if data == "admin_cfg_chat_ids":
        return await edit_or_answer(
            callback,
            "Chat IDs\n\nChoose a setting.",
            reply_markup=admin_chat_ids_kb(),
        )

    if not data.startswith("admin_cfg_chat_"):
        return None

    key = data.removeprefix("admin_cfg_chat_")
    current = await get_runtime_config(key)
    label = CHAT_ID_LABELS.get(key, key.replace("_", " ").title())
    clear_hint = " Send `none` to clear." if DEFAULTS.get(key) is None else ""
    await state.set_state(AdminInputStates.waiting_custom_value)
    await state.update_data(
        admin_action="cfg_chat_id",
        admin_config_key=key,
        admin_back="admin_cfg_chat_ids",
    )
    return await edit_or_answer(
        callback,
        build_chat_id_prompt(label, current, clear_hint=clear_hint),
        reply_markup=admin_back_kb("admin_cfg_chat_ids"),
        parse_mode=MARKDOWN_PARSE_MODE,
    )


async def _handle_working_hours(callback, state, data: str):
    if data == "admin_cfg_working_hours":
        return await edit_or_answer(
            callback,
            "Working hours\n\nChoose a weekday.",
            reply_markup=working_hours_weekday_kb(),
        )

    if data.startswith("admin_cfg_hours_"):
        weekday_idx = int(data.split("_")[3])
        async with AsyncSessionLocal() as db:
            current_start, current_end = await get_working_hours(db, WEEKDAYS[weekday_idx])
        return await edit_or_answer(
            callback,
            build_working_hours_prompt(weekday_idx, current_start, current_end),
            reply_markup=working_hours_value_kb(weekday_idx),
            parse_mode=MARKDOWN_PARSE_MODE,
        )

    if data.startswith("admin_cfg_hourspreset_"):
        _, _, _, weekday_s, start_s, end_s = data.split("_")
        weekday_idx = int(weekday_s)
        start = int(start_s)
        end = int(end_s)
        return await edit_or_answer(
            callback,
            build_working_hours_confirm_text(weekday_idx, start, end),
            reply_markup=admin_confirm_kb(
                f"admin_cfg_hoursconfirm_{weekday_idx}_{start}_{end}",
                "admin_cfg",
            ),
            parse_mode=MARKDOWN_PARSE_MODE,
        )

    if data.startswith("admin_cfg_hourscustom_"):
        weekday_idx = int(data.split("_")[3])
        await state.set_state(AdminInputStates.waiting_working_hours)
        await state.update_data(
            admin_action="cfg_working_hours",
            admin_weekday_idx=weekday_idx,
        )
        return await edit_or_answer(
            callback,
            (
                f"Working hours for {WEEKDAYS[weekday_idx]}\n\n"
                "Send a custom range like `9-23`."
            ),
            reply_markup=admin_back_kb("admin_cfg"),
        )

    if data.startswith("admin_cfg_hoursconfirm_"):
        _, _, _, weekday_s, start_s, end_s = data.split("_")
        weekday_idx = int(weekday_s)
        start = int(start_s)
        end = int(end_s)
        async with AsyncSessionLocal() as db:
            await set_config_value(
                db,
                f"working_hours_{WEEKDAYS[weekday_idx]}",
                f"{start}-{end}",
            )
        return await edit_or_answer(
            callback,
            f"Working hours for {WEEKDAYS[weekday_idx]} updated to {start}:00 - {end}:00",
            reply_markup=_config_next_kb(
                action_text="Change working hours",
                action_data="admin_cfg_working_hours",
            ),
        )

    return None


async def handle_admin_config_callback(callback, state, data: str):
    numeric_response = await _handle_numeric_config(callback, state, data)
    if numeric_response is not None:
        return numeric_response

    chat_response = await _handle_chat_ids(callback, state, data)
    if chat_response is not None:
        return chat_response

    working_hours_response = await _handle_working_hours(callback, state, data)
    if working_hours_response is not None:
        return working_hours_response

    if data == "admin_cfg_geo_center":
        await state.set_state(AdminInputStates.waiting_geocenter)
        await state.update_data(admin_action="cfg_geo_center")
        return await edit_or_answer(
            callback,
            "Geo center\n\nSend `lat lon`.",
            reply_markup=admin_back_kb("admin_cfg"),
        )

    if data == "admin_cfg_rules":
        current = await get_runtime_config("rules_text")
        await state.set_state(AdminInputStates.waiting_rules)
        await state.update_data(admin_action="cfg_rules")
        return await edit_or_answer(
            callback,
            f"Rules\n\nCurrent rules:\n{current}\n\nSend the new rules text.",
            reply_markup=admin_back_kb("admin_cfg"),
        )

    if data == "admin_cfg_rules_confirm":
        rules_text = (await state.get_data()).get("admin_rules_preview")
        if not rules_text:
            await state.clear()
            return await edit_or_answer(
                callback,
                "Rules update expired.",
                reply_markup=admin_back_kb("admin_cfg"),
            )
        async with AsyncSessionLocal() as db:
            await set_config_value(db, "rules_text", rules_text)
        await state.clear()
        return await edit_or_answer(
            callback,
            "Rules updated successfully.",
            reply_markup=_config_next_kb(
                action_text="Edit rules again",
                action_data="admin_cfg_rules",
            ),
        )

    if data == "admin_cfg":
        return await render_config_menu(callback)

    return None
