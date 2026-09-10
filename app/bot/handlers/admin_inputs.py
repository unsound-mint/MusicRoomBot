# app/bot/handlers/admin_inputs.py
import logging

from aiogram import Router, types
from aiogram.fsm.context import FSMContext

from app.bot.constants.dates import WEEKDAYS
from app.bot.handlers.admin_shared import (
    AdminInputStates,
    canon_username,
    check_admin_and_reply,
    check_admin_callback,
    find_users_by_full_name,
    get_user_by_username,
    render_user_summary,
)
from app.bot.handlers.admin_user_messages import find_user_ambiguous_text
from app.bot.keyboards.admin_inline_kb import (
    admin_back_kb,
    admin_confirm_kb,
    admin_next_actions_kb,
)
from app.bot.keyboards.inline_kb import (
    equipment_request_admin_review_kb,
    equipment_request_admin_status_kb,
)
from app.bot.markdown import MARKDOWN_PARSE_MODE
from app.bot.ui import edit_or_answer, safe_answer_callback
from app.core.database import AsyncSessionLocal
from app.services.config_runtime import OPTIONAL_INT_CONFIG_KEYS
from app.services.config_service import set_config_value
from app.services.config_utils import parse_float, parse_int
from app.services.equipment_request_service import (
    get_equipment_request_with_ranges,
    parse_equipment_ranges_text,
    render_equipment_request_review,
    render_equipment_request_status,
    render_equipment_topic_post,
    replace_equipment_request_ranges,
    update_equipment_request_field,
)

log = logging.getLogger(__name__)
router = Router()


def _config_next_kb(back_data: str = "admin_cfg"):
    return admin_next_actions_kb(
        [("Change another setting", back_data)],
        back_data="admin_cfg",
        back_text="⬅️ Back to config",
    )


def _equipment_request_next_kb(request_id: int):
    return admin_next_actions_kb(
        [("Edit another field", f"equipreq_edit_{request_id}")],
        back_data=f"equipreq_refresh_{request_id}",
        back_text="⬅️ Back to request",
    )


@router.message(AdminInputStates.waiting_username)
async def admin_username_input(message: types.Message, state: FSMContext):
    if not await check_admin_and_reply(message):
        await state.clear()
        return
    data = await state.get_data()
    action = data.get("admin_action")
    if action == "user_find":
        search_text = (message.text or "").strip()
        if not search_text:
            return await message.answer("Send a username or full name.")
        username = canon_username(search_text)
    else:
        username = canon_username(message.text or "")
        if not username:
            return await message.answer("Send a valid username like @username.")
    if username is None:
        await state.clear()
        return await message.answer("Send a valid username like @username.")
    async with AsyncSessionLocal() as db:
        user = await get_user_by_username(db, username)
        if action == "admin_add_admin":
            if not user:
                await state.clear()
                return await message.answer(
                    "User not found in database.",
                    reply_markup=admin_back_kb("admin_users_admins"),
                )
            if user.tg_user_id is None:
                await state.clear()
                return await message.answer(
                    "User must send /start before becoming admin.",
                    reply_markup=admin_back_kb("admin_users_admins"),
                )
            await state.clear()
            return await message.answer(
                f"Add @{username} as admin?",
                reply_markup=admin_confirm_kb(
                    f"admin_users_confirm_addadmin_{username}",
                    "admin_users_admins",
                ),
            )
        if action == "user_find":
            await state.clear()
            if user:
                return await render_user_summary(message, user)
            matches = await find_users_by_full_name(db, search_text)
            if not matches:
                return await message.answer(
                    "User not found.",
                    reply_markup=admin_back_kb("admin_users"),
                )
            if len(matches) > 1:
                return await message.answer(
                    find_user_ambiguous_text(matches),
                    parse_mode=MARKDOWN_PARSE_MODE,
                )
            user = matches[0]
            return await render_user_summary(message, user)
    await state.clear()
    await message.answer("Unsupported admin action.")


@router.message(AdminInputStates.waiting_reason)
async def admin_reason_input(message: types.Message, state: FSMContext):
    if not await check_admin_and_reply(message):
        await state.clear()
        return
    data = await state.get_data()
    action = data.get("admin_action")
    username = data.get("admin_username")
    reason = (message.text or "").strip()
    if reason == "-" or not reason:
        reason = None
    if not username:
        await state.clear()
        return await message.answer("Admin action expired.")
    async with AsyncSessionLocal() as db:
        user = await get_user_by_username(db, username)
        if not user:
            await state.clear()
            return await message.answer("User not found.", reply_markup=admin_back_kb("admin_users"))
        if action == "warn_add_reason":
            if user.id is None:
                await state.clear()
                return await message.answer(
                    "User record is invalid.",
                    reply_markup=admin_back_kb("admin_users"),
                )
            await state.update_data(admin_reason=reason)
            return await message.answer(
                "Add warning?\n\n"
                f"User: @{username}\n"
                f"Reason: {reason or 'Manual admin warning'}",
                reply_markup=admin_confirm_kb(
                    "admin_warn_confirm_add_state",
                    f"admin_users_view_{username}",
                ),
            )
    await state.clear()
    await message.answer("Unsupported admin action.")


@router.message(AdminInputStates.waiting_custom_value)
async def admin_custom_value_input(message: types.Message, state: FSMContext):
    if not await check_admin_and_reply(message):
        await state.clear()
        return
    data = await state.get_data()
    action = data.get("admin_action")
    key = data.get("admin_config_key")
    value_text = (message.text or "").strip()
    if action == "cfg_custom":
        if key in {"weekly_limit", "slot_length", "reminder_hours", "late_minutes"}:
            int_value, err = parse_int(value_text)
            if err:
                return await message.answer(f"Invalid value: {err}")
            async with AsyncSessionLocal() as db:
                await set_config_value(db, key, str(int_value))
            await state.clear()
            return await message.answer(
                f"{key} updated to {int_value}.",
                reply_markup=_config_next_kb(),
            )
        float_value, err = parse_float(value_text)
        if err:
            return await message.answer(f"Invalid value: {err}")
        async with AsyncSessionLocal() as db:
            await set_config_value(db, key, str(float_value))
        await state.clear()
        return await message.answer(
            f"{key} updated to {float_value}.",
            reply_markup=_config_next_kb(),
        )
    if action == "cfg_chat_id":
        if value_text.lower() in {"", "none"}:
            if key in OPTIONAL_INT_CONFIG_KEYS:
                async with AsyncSessionLocal() as db:
                    await set_config_value(db, key, "")
                await state.clear()
                return await message.answer(
                    f"{key} cleared.",
                    reply_markup=_config_next_kb("admin_cfg_chat_ids"),
                )
            return await message.answer("Value must be numeric.")
        try:
            value_int = int(value_text)
        except Exception:
            return await message.answer("Value must be numeric.")
        async with AsyncSessionLocal() as db:
            await set_config_value(db, key, str(value_int))
        await state.clear()
        return await message.answer(
            f"{key} updated to {value_int}.",
            reply_markup=_config_next_kb("admin_cfg_chat_ids"),
        )
    await state.clear()
    await message.answer("Unsupported admin action.")


@router.message(AdminInputStates.waiting_equipment_request_value)
async def admin_equipment_request_value_input(message: types.Message, state: FSMContext):
    if not await check_admin_and_reply(message):
        await state.clear()
        return

    data = await state.get_data()
    if data.get("admin_action") != "equipreq_field":
        await state.clear()
        return await message.answer("Equipment request update expired.")

    request_id = data.get("equipment_request_id")
    field_name = data.get("equipment_request_field")
    if not isinstance(request_id, int) or not isinstance(field_name, str):
        await state.clear()
        return await message.answer("Equipment request update expired.")

    value_text = (message.text or "").strip()
    value = None if field_name == "comments" and value_text in {"", "-"} else value_text
    if field_name != "comments" and not value_text:
        return await message.answer("This field cannot be empty.")

    async with AsyncSessionLocal() as db:
        request = await get_equipment_request_with_ranges(db, request_id)
        if not request:
            await state.clear()
            return await message.answer("Equipment request not found.")
        if request.status not in {"submitted", "approved"}:
            await state.clear()
            return await message.answer("Equipment request has already been decided.")

        if field_name == "needed_at_text":
            try:
                ranges = parse_equipment_ranges_text(value_text)
            except ValueError as exc:
                return await message.answer(str(exc))
            request = await replace_equipment_request_ranges(
                db,
                request,
                ranges=ranges,
            )
        else:
            request = await update_equipment_request_field(db, request, field_name, value)

        if request.review_chat_id is not None and request.review_message_id is not None:
            review_text = (
                render_equipment_request_review(request)
                if request.status == "submitted"
                else render_equipment_request_status(request)
            )
            review_markup = (
                equipment_request_admin_review_kb(request.id)
                if request.status == "submitted"
                else equipment_request_admin_status_kb(request.id)
            )
            await message.bot.edit_message_text(
                review_text,
                chat_id=request.review_chat_id,
                message_id=request.review_message_id,
                reply_markup=review_markup,
            )

        if (
            request.status == "approved"
            and request.equipment_post_chat_id is not None
            and request.equipment_post_message_id is not None
        ):
            try:
                await message.bot.edit_message_text(
                    render_equipment_topic_post(request),
                    chat_id=request.equipment_post_chat_id,
                    message_id=request.equipment_post_message_id,
                )
            except Exception:
                log.exception(
                    "Failed to update equipment topic post after admin edit",
                    extra={
                        "equipment_request_id": request.id,
                        "chat_id": request.equipment_post_chat_id,
                        "message_id": request.equipment_post_message_id,
                    },
                )

    await state.clear()
    await message.answer(
        "Equipment request updated.",
        reply_markup=_equipment_request_next_kb(request_id),
    )


@router.message(AdminInputStates.waiting_rules)
async def admin_rules_input(message: types.Message, state: FSMContext):
    if not await check_admin_and_reply(message):
        await state.clear()
        return
    new_rules = (message.text or "").strip()
    if not new_rules:
        return await message.answer("Rules text cannot be empty.")
    await state.update_data(admin_rules_preview=new_rules)
    await message.answer(
        f"Update rules?\n\nPreview:\n{new_rules}",
        reply_markup=admin_confirm_kb("admin_cfg_rules_confirm", "admin_cfg"),
    )


@router.message(AdminInputStates.waiting_geocenter)
async def admin_geocenter_input(message: types.Message, state: FSMContext):
    if not await check_admin_and_reply(message):
        await state.clear()
        return
    parts = (message.text or "").split()
    if len(parts) != 2:
        return await message.answer("Send `lat lon`.")
    lat, err = parse_float(parts[0], minimum=-90, maximum=90)
    if err:
        return await message.answer("Invalid latitude: " + err)
    lon, err = parse_float(parts[1], minimum=-180, maximum=180)
    if err:
        return await message.answer("Invalid longitude: " + err)
    async with AsyncSessionLocal() as db:
        await set_config_value(db, "geo_center_lat", str(lat))
        await set_config_value(db, "geo_center_lon", str(lon))
    await state.clear()
    await message.answer(
        f"Geo center set to {lat}, {lon}.",
        reply_markup=_config_next_kb(),
    )


@router.message(AdminInputStates.waiting_working_hours)
async def admin_working_hours_input(message: types.Message, state: FSMContext):
    if not await check_admin_and_reply(message):
        await state.clear()
        return
    data = await state.get_data()
    weekday_idx = data.get("admin_weekday_idx")
    hours = (message.text or "").strip()
    if weekday_idx is None or "-" not in hours:
        return await message.answer("Send a range like `9-23`.")
    try:
        start_s, end_s = hours.split("-", 1)
        start = int(start_s)
        end = int(end_s)
    except ValueError:
        return await message.answer("Start and end must be integers.")
    if not (0 <= start <= 23 and 1 <= end <= 24 and start < end):
        return await message.answer("Invalid time range. Example: 9-23")
    await state.update_data(admin_working_start=start, admin_working_end=end)
    await message.answer(
        "Update working hours?\n\n"
        f"Day: {WEEKDAYS[int(weekday_idx)]}\n"
        f"New value: {start}:00 - {end}:00",
        reply_markup=admin_confirm_kb("admin_cfg_hours_confirm_state", "admin_cfg"),
    )


@router.callback_query(lambda c: c.data == "admin_cfg_hours_confirm_state")
async def admin_cfg_hours_confirm_state(callback: types.CallbackQuery, state: FSMContext):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    data = await state.get_data()
    weekday_idx = data.get("admin_weekday_idx")
    start = data.get("admin_working_start")
    end = data.get("admin_working_end")
    if weekday_idx is None or start is None or end is None:
        await state.clear()
        return await edit_or_answer(
            callback,
            "Working hours update expired.",
            reply_markup=admin_back_kb("admin_cfg"),
        )
    async with AsyncSessionLocal() as db:
        await set_config_value(db, f"working_hours_{WEEKDAYS[int(weekday_idx)]}", f"{start}-{end}")
    await state.clear()
    await edit_or_answer(
        callback,
        f"Working hours for {WEEKDAYS[int(weekday_idx)]} updated to {start}:00 - {end}:00",
        reply_markup=admin_back_kb("admin_cfg"),
    )
