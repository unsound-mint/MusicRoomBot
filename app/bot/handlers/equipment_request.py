# app/bot/handlers/equipment_request.py
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.bot.handlers.equipment_request_messages import (
    EQUIPMENT_REQUEST_RULES_TEXT,
    MISSING_FULL_NAME_TEXT,
    approved_requests_hub_text,
    build_confirmation_text,
    cleared_ranges_text,
    edit_ranges_text,
)
from app.bot.handlers.equipment_request_ranges import (
    parse_state_range,
    parsed_state_ranges,
    range_summary_from_state,
    ranges_needed_at_text,
    render_range_end_day_picker,
    render_range_end_hour_picker,
    render_range_start_day_picker,
    render_range_start_hour_picker,
    render_range_step,
    render_range_summary,
    serialize_range,
    state_ranges,
)
from app.bot.keyboards.inline_kb import (
    equipment_request_admin_review_kb,
    equipment_request_cancel_kb,
    equipment_request_confirmation_kb,
    equipment_request_detail_kb,
    equipment_request_edit_fields_kb,
    equipment_request_hub_kb,
    equipment_request_rules_agreement_kb,
)
from app.bot.ui import (
    edit_or_answer,
    get_main_menu_kb,
    safe_answer_callback,
)
from app.core.database import AsyncSessionLocal
from app.services.admin_service import is_admin
from app.services.config_runtime import get_runtime_config
from app.services.equipment_request_service import (
    check_equipment_ranges_overlap,
    create_equipment_request,
    get_future_approved_equipment_requests,
    get_future_approved_request,
    record_equipment_request_review_message,
    render_admin_equipment_request_detail,
    render_equipment_request_review,
    render_requester_equipment_request_detail,
)
from app.services.time_service import now_tz
from app.services.user_service import get_user_by_tg_id

log = logging.getLogger(__name__)
router = Router()
EDIT_FIELD_CALLBACK_PREFIX = "equip_edit_field_"

FIELD_PROMPTS = {
    "club_name": {
        "label": "Club name",
        "prompt": "Send the club name.",
    },
    "event_name": {
        "label": "Event name",
        "prompt": "Send the event name.",
    },
    "venue": {
        "label": "Venue",
        "prompt": "Send the venue.",
    },
    "equipment_text": {
        "label": "Equipment list",
        "prompt": "Send the equipment list.",
    },
    "needed_at_text": {
        "label": "Time ranges",
        "prompt": "Add one or more start/end time ranges.",
    },
    "reason_text": {
        "label": "Why exactly this time and equipment?",
        "prompt": "Explain why exactly this time and equipment are needed.",
    },
    "comments": {
        "label": "Comments",
        "prompt": "Send any comments, or - to skip.",
    },
}


class EquipmentRequestStates(StatesGroup):
    waiting_club_name = State()
    waiting_event_name = State()
    waiting_venue = State()
    waiting_equipment_text = State()
    waiting_needed_at_text = State()
    waiting_reason_text = State()
    waiting_comments = State()
    waiting_edit_value = State()


STATE_BY_FIELD = {
    "club_name": EquipmentRequestStates.waiting_club_name,
    "event_name": EquipmentRequestStates.waiting_event_name,
    "venue": EquipmentRequestStates.waiting_venue,
    "equipment_text": EquipmentRequestStates.waiting_equipment_text,
    "needed_at_text": EquipmentRequestStates.waiting_needed_at_text,
    "reason_text": EquipmentRequestStates.waiting_reason_text,
    "comments": EquipmentRequestStates.waiting_comments,
}

CREATE_FLOW = (
    "club_name",
    "event_name",
    "venue",
    "equipment_text",
    "needed_at_text",
    "reason_text",
    "comments",
)

REQUIRED_DRAFT_FIELDS = (
    "full_name",
    "club_name",
    "event_name",
    "venue",
    "equipment_text",
    "ranges",
    "reason_text",
)


def _field_label(field_name: str) -> str:
    return FIELD_PROMPTS[field_name]["label"]


def _field_prompt(field_name: str) -> str:
    return FIELD_PROMPTS[field_name]["prompt"]


def _creation_prompt(field_name: str) -> str:
    step_number = CREATE_FLOW.index(field_name) + 1
    return f"*Step {step_number} of {len(CREATE_FLOW)}*\n\n📝 {_field_prompt(field_name)}"


def _requester_editable_fields() -> list[tuple[str, str]]:
    return [(field_name, _field_label(field_name)) for field_name in CREATE_FLOW]


def _has_valid_equipment_request_draft(data: dict[str, Any]) -> bool:
    for field_name in REQUIRED_DRAFT_FIELDS:
        if field_name == "ranges":
            if not state_ranges(data):
                return False
            continue
        value = data.get(field_name)
        if value is None:
            return False
        if not str(value).strip():
            return False
    return True


def build_equipment_request_confirmation_text(data: dict[str, Any]) -> str:
    return build_confirmation_text(data, range_summary_from_state(data))


def _edit_prompt(field_name: str) -> str:
    return f"📝 {_field_prompt(field_name)}"


def _normalize_input(field_name: str, raw_text: str | None) -> str | None:
    text = (raw_text or "").strip()
    if field_name == "comments":
        if text in {"", "-"}:
            return None
        return text
    if not text:
        raise ValueError("This field cannot be empty.")
    return text



async def _render_prompt_message(
    source: Any,
    state: FSMContext,
    text: str,
    *,
    reply_markup=None,
    parse_mode: str | None = None,
):
    return await source.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)


async def _render_equipment_hub(target):
    async with AsyncSessionLocal() as db:
        requests = await get_future_approved_equipment_requests(db)
    text = approved_requests_hub_text(has_requests=bool(requests))
    return await edit_or_answer(
        target,
        text,
        reply_markup=equipment_request_hub_kb(requests),
        parse_mode="Markdown",
    )


async def _start_equipment_request_wizard(callback: types.CallbackQuery, state: FSMContext) -> Any:
    async with AsyncSessionLocal() as db:
        user = await get_user_by_tg_id(db, callback.from_user.id)
        if not user:
            return await callback.message.answer("Send /start to register first.")
        if not user.full_name or not user.full_name.strip():
            return await callback.message.answer(
                MISSING_FULL_NAME_TEXT,
                reply_markup=await get_main_menu_kb(db, callback.from_user.id),
            )

    await state.update_data(
        requester_tg_user_id=callback.from_user.id,
        requester_username=callback.from_user.username,
        full_name=user.full_name.strip(),
        club_name=None,
        event_name=None,
        venue=None,
        equipment_text=None,
        ranges=[],
        needed_at_text=None,
        reason_text=None,
        comments=None,
        pending_range_start=None,
    )
    await state.set_state(EquipmentRequestStates.waiting_club_name)
    return await callback.message.answer(
        _creation_prompt("club_name"),
        reply_markup=equipment_request_cancel_kb(),
        parse_mode="Markdown",
    )


async def _enter_range_flow(target, state: FSMContext, *, reset_existing: bool) -> None:
    data = await state.get_data()
    await state.set_state(EquipmentRequestStates.waiting_needed_at_text)
    updates: dict[str, Any] = {"pending_range_start": None}
    if reset_existing:
        updates["ranges"] = []
        updates["needed_at_text"] = None
    await state.update_data(updates)
    if reset_existing and data.get("edit_field_name") == "needed_at_text":
        await render_range_step(
            target,
            edit_ranges_text(),
            reply_markup=equipment_request_cancel_kb(),
        )
    await render_range_start_day_picker(target)


async def _finalize_ranges_and_continue(target, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("edit_field_name") == "needed_at_text":
        await state.update_data(edit_field_name=None)
        await state.set_state(None)
        updated = await state.get_data()
        await target.answer(
            build_equipment_request_confirmation_text(updated),
            reply_markup=equipment_request_confirmation_kb(),
            parse_mode="Markdown",
        )
        return
    await state.set_state(EquipmentRequestStates.waiting_reason_text)
    await target.answer(
        _creation_prompt("reason_text"),
        reply_markup=equipment_request_cancel_kb(),
        parse_mode="Markdown",
    )


async def _advance_wizard(message: types.Message, state: FSMContext, field_name: str) -> None:
    try:
        value = _normalize_input(field_name, message.text)
    except ValueError as exc:
        await _render_prompt_message(message, state, str(exc), reply_markup=equipment_request_cancel_kb())
        return
    await state.update_data({field_name: value})

    current_index = CREATE_FLOW.index(field_name)
    next_index = current_index + 1
    if next_index >= len(CREATE_FLOW):
        await state.set_state(None)
        data = await state.get_data()
        await _render_prompt_message(
            message,
            state,
            build_equipment_request_confirmation_text(data),
            reply_markup=equipment_request_confirmation_kb(),
            parse_mode="Markdown",
        )
        return

    next_field = CREATE_FLOW[next_index]
    await state.set_state(STATE_BY_FIELD[next_field])
    if next_field == "needed_at_text":
        await _enter_range_flow(message, state, reset_existing=False)
        return
    await _render_prompt_message(
        message,
        state,
        _creation_prompt(next_field),
        reply_markup=equipment_request_cancel_kb(),
        parse_mode="Markdown",
    )


@router.message(F.text == "🎤 Equipment")
async def start_equipment_request(message: types.Message, state: FSMContext):
    await state.clear()
    async with AsyncSessionLocal() as db:
        user = await get_user_by_tg_id(db, message.from_user.id)
        if not user:
            return await message.answer("Send /start to register first.")
    return await _render_equipment_hub(message)


@router.callback_query(F.data == "equip_home")
async def equipment_request_home(callback: types.CallbackQuery, state: FSMContext):
    await safe_answer_callback(callback)
    await state.clear()
    return await _render_equipment_hub(callback)


@router.callback_query(F.data == "equip_new")
async def equipment_request_new(callback: types.CallbackQuery, state: FSMContext):
    await safe_answer_callback(callback)
    await state.clear()
    return await callback.message.answer(
        EQUIPMENT_REQUEST_RULES_TEXT,
        reply_markup=equipment_request_rules_agreement_kb(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "equip_rules_agree")
async def equipment_request_rules_agree(callback: types.CallbackQuery, state: FSMContext) -> Any:
    await safe_answer_callback(callback)
    await state.clear()
    return await _start_equipment_request_wizard(callback, state)


@router.message(EquipmentRequestStates.waiting_club_name)
async def equipment_request_club_name_input(message: types.Message, state: FSMContext):
    return await _advance_wizard(message, state, "club_name")


@router.message(EquipmentRequestStates.waiting_event_name)
async def equipment_request_event_name_input(message: types.Message, state: FSMContext):
    return await _advance_wizard(message, state, "event_name")


@router.message(EquipmentRequestStates.waiting_venue)
async def equipment_request_venue_input(message: types.Message, state: FSMContext):
    return await _advance_wizard(message, state, "venue")


@router.message(EquipmentRequestStates.waiting_equipment_text)
async def equipment_request_equipment_input(message: types.Message, state: FSMContext):
    return await _advance_wizard(message, state, "equipment_text")


@router.message(EquipmentRequestStates.waiting_needed_at_text)
async def equipment_request_needed_at_input(message: types.Message, state: FSMContext):
    return await message.answer("Use the picker buttons to choose start and end ranges.")


@router.message(EquipmentRequestStates.waiting_reason_text)
async def equipment_request_reason_input(message: types.Message, state: FSMContext):
    return await _advance_wizard(message, state, "reason_text")


@router.message(EquipmentRequestStates.waiting_comments)
async def equipment_request_comments_input(message: types.Message, state: FSMContext):
    return await _advance_wizard(message, state, "comments")


@router.callback_query(F.data == "equip_rngback_startdays")
async def equipment_request_range_back_start_days(callback: types.CallbackQuery):
    await safe_answer_callback(callback)
    return await render_range_start_day_picker(callback)


@router.callback_query(F.data == "equip_rngback_prev")
async def equipment_request_range_back_previous(callback: types.CallbackQuery, state: FSMContext):
    await safe_answer_callback(callback)
    data = await state.get_data()
    if data.get("edit_field_name") == "needed_at_text":
        await state.set_state(None)
        return await edit_or_answer(
            callback,
            "✏️ Pick a field to edit.",
            reply_markup=equipment_request_edit_fields_kb(_requester_editable_fields()),
        )

    await state.update_data(
        ranges=[],
        needed_at_text=None,
        pending_range_start=None,
    )
    await state.set_state(EquipmentRequestStates.waiting_equipment_text)
    return await edit_or_answer(
        callback,
        cleared_ranges_text(_creation_prompt("equipment_text")),
        reply_markup=equipment_request_cancel_kb(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "equip_rngback_summary")
async def equipment_request_range_back_summary(callback: types.CallbackQuery, state: FSMContext):
    await safe_answer_callback(callback)
    data = await state.get_data()
    ranges = state_ranges(data)
    if not ranges:
        return await render_range_start_day_picker(callback)

    last_range = ranges[-1]
    remaining_ranges = ranges[:-1]
    start_at = datetime.fromisoformat(last_range["start_at"])
    end_at = datetime.fromisoformat(last_range["end_at"])
    await state.update_data(
        ranges=remaining_ranges,
        needed_at_text=ranges_needed_at_text(remaining_ranges),
        pending_range_start=start_at.isoformat(),
    )
    return await render_range_end_hour_picker(callback, start_at, end_at.date())


@router.callback_query(F.data.startswith("equip_rngback_starthour_"))
async def equipment_request_range_back_start_hour(callback: types.CallbackQuery):
    await safe_answer_callback(callback)
    _, _, _, date_str, hour_str = callback.data.split("_")
    target_date = datetime.fromisoformat(date_str).date()
    return await render_range_start_hour_picker(callback, target_date)


@router.callback_query(F.data == "equip_rngback_enddays")
async def equipment_request_range_back_end_days(callback: types.CallbackQuery, state: FSMContext):
    await safe_answer_callback(callback)
    data = await state.get_data()
    pending_start = data.get("pending_range_start")
    if not isinstance(pending_start, str):
        return await render_range_start_day_picker(callback)
    return await render_range_end_day_picker(
        callback,
        datetime.fromisoformat(pending_start),
    )


@router.callback_query(F.data.startswith("equip_rngstartday_"))
async def equipment_request_pick_range_start_day(callback: types.CallbackQuery):
    await safe_answer_callback(callback)
    target_date = datetime.fromisoformat(callback.data.removeprefix("equip_rngstartday_")).date()
    return await render_range_start_hour_picker(callback, target_date)


@router.callback_query(F.data.startswith("equip_rngstarthour_"))
async def equipment_request_pick_range_start_hour(callback: types.CallbackQuery, state: FSMContext):
    await safe_answer_callback(callback)
    _, _, date_str, hour_str = callback.data.split("_")
    start_at = datetime.fromisoformat(f"{date_str}T{int(hour_str):02d}:00:00").replace(
        tzinfo=now_tz().tzinfo
    )
    await state.update_data(pending_range_start=start_at.isoformat())
    return await render_range_end_day_picker(callback, start_at)


@router.callback_query(F.data.startswith("equip_rngendday_"))
async def equipment_request_pick_range_end_day(callback: types.CallbackQuery, state: FSMContext):
    await safe_answer_callback(callback)
    data = await state.get_data()
    pending_start = data.get("pending_range_start")
    if not isinstance(pending_start, str):
        return await render_range_start_day_picker(callback)
    start_at = datetime.fromisoformat(pending_start)
    target_date = datetime.fromisoformat(callback.data.removeprefix("equip_rngendday_")).date()
    return await render_range_end_hour_picker(callback, start_at, target_date)


@router.callback_query(F.data.startswith("equip_rngendhour_"))
async def equipment_request_pick_range_end_hour(callback: types.CallbackQuery, state: FSMContext):
    await safe_answer_callback(callback)
    data = await state.get_data()
    pending_start = data.get("pending_range_start")
    if not isinstance(pending_start, str):
        return await render_range_start_day_picker(callback)
    start_at = datetime.fromisoformat(pending_start)
    _, _, date_str, hour_str = callback.data.split("_")
    end_at = datetime.fromisoformat(f"{date_str}T{int(hour_str):02d}:00:00").replace(
        tzinfo=now_tz().tzinfo
    )
    if end_at <= start_at:
        return await callback.message.answer("⚠️ End must be after start.")

    ranges = state_ranges(data)
    new_range = serialize_range(start_at, end_at)

    # Check for overlap with existing ranges
    try:
        check_equipment_ranges_overlap(
            [parse_state_range(r) for r in ranges] + [parse_state_range(new_range)]
        )
    except ValueError as exc:
        return await callback.message.answer(f"⚠️ {str(exc)}")

    ranges.append(new_range)
    await state.update_data(
        ranges=ranges,
        needed_at_text=ranges_needed_at_text(ranges),
        pending_range_start=None,
    )
    return await render_range_summary(callback, state)


@router.callback_query(F.data == "equip_ranges_add")
async def equipment_request_add_another_range(callback: types.CallbackQuery, state: FSMContext):
    await safe_answer_callback(callback)
    await _enter_range_flow(callback, state, reset_existing=False)


@router.callback_query(F.data == "equip_ranges_done")
async def equipment_request_ranges_done(callback: types.CallbackQuery, state: FSMContext):
    await safe_answer_callback(callback)
    data = await state.get_data()
    if not state_ranges(data):
        return await callback.message.answer("⚠️ Add at least one time range.")
    return await _finalize_ranges_and_continue(callback.message, state)


@router.callback_query(F.data == "equip_edit_details")
async def equipment_request_edit_details(
    callback: types.CallbackQuery,
    state: FSMContext,
):
    await safe_answer_callback(callback)
    data = await state.get_data()
    if not _has_valid_equipment_request_draft(data):
        await state.clear()
        await callback.message.answer("⚠️ Equipment request draft not found.")
        return None

    return await callback.message.answer(
        "✏️ Pick a field to edit.",
        reply_markup=equipment_request_edit_fields_kb(_requester_editable_fields()),
    )


@router.callback_query(F.data.startswith(EDIT_FIELD_CALLBACK_PREFIX))
async def equipment_request_pick_edit_field(
    callback: types.CallbackQuery,
    state: FSMContext,
):
    await safe_answer_callback(callback)
    data = await state.get_data()
    field_name = callback.data[len(EDIT_FIELD_CALLBACK_PREFIX):]
    if field_name not in FIELD_PROMPTS:
        return await callback.message.answer("⚠️ Unknown field.")
    if not _has_valid_equipment_request_draft(data):
        await state.clear()
        await callback.message.answer("⚠️ Equipment request draft not found.")
        return None

    await state.update_data(edit_field_name=field_name)
    if field_name == "needed_at_text":
        await _enter_range_flow(callback, state, reset_existing=True)
        return None

    await state.set_state(EquipmentRequestStates.waiting_edit_value)
    return await callback.message.answer(
        _edit_prompt(field_name),
        reply_markup=equipment_request_cancel_kb(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("equip_view_"))
async def equipment_request_view(callback: types.CallbackQuery):
    await safe_answer_callback(callback)
    request_id = int(callback.data.rsplit("_", 1)[1])
    async with AsyncSessionLocal() as db:
        request = await get_future_approved_request(db, request_id=request_id)
        if not request:
            return await edit_or_answer(callback, "Equipment request not found.")
        can_edit = await is_admin(db, callback.from_user.id)
    return await edit_or_answer(
        callback,
        render_admin_equipment_request_detail(request)
        if can_edit
        else render_requester_equipment_request_detail(request),
        reply_markup=equipment_request_detail_kb(request.id, can_edit=can_edit),
    )


@router.message(EquipmentRequestStates.waiting_edit_value)
async def equipment_request_edit_value_input(message: types.Message, state: FSMContext):
    data = await state.get_data()
    field_name = data.get("edit_field_name")
    if field_name not in FIELD_PROMPTS:
        await state.clear()
        return await message.answer("⚠️ Equipment request draft not found.")
    if not _has_valid_equipment_request_draft(data):
        await state.clear()
        return await message.answer("⚠️ Equipment request draft not found.")

    try:
        value = _normalize_input(field_name, message.text)
    except ValueError as exc:
        return await _render_prompt_message(message, state, str(exc), reply_markup=equipment_request_cancel_kb())
    await state.update_data({field_name: value, "edit_field_name": None})
    await state.set_state(None)
    updated = await state.get_data()
    return await _render_prompt_message(
        message,
        state,
        build_equipment_request_confirmation_text(updated),
        reply_markup=equipment_request_confirmation_kb(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "equip_submit")
async def equipment_request_submit(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not _has_valid_equipment_request_draft(data):
        await state.clear()
        await safe_answer_callback(callback)
        return await callback.message.answer("⚠️ Equipment request draft not found.")

    access_chat_id = await get_runtime_config("access_chat_id")
    if not access_chat_id:
        await safe_answer_callback(callback)
        return await callback.message.answer("⚠️ Equipment request submission is unavailable right now.")

    async with AsyncSessionLocal() as db:
        request = await create_equipment_request(
            db,
            requester_tg_user_id=data["requester_tg_user_id"],
            requester_username=data.get("requester_username"),
            full_name=data["full_name"],
            club_name=data["club_name"],
            event_name=data["event_name"],
            venue=data["venue"],
            equipment_text=data["equipment_text"],
            needed_at_text=data["needed_at_text"],
            reason_text=data["reason_text"],
            comments=data.get("comments"),
            ranges=parsed_state_ranges(data),
        )

        try:
            review_message = await callback.bot.send_message(
                int(access_chat_id),
                render_equipment_request_review(request),
                reply_markup=equipment_request_admin_review_kb(request.id),
            )
        except Exception:
            log.exception(
                "Failed to send equipment request review message",
                extra={
                    "equipment_request_id": request.id,
                    "access_chat_id": access_chat_id,
                    "requester_tg_user_id": data["requester_tg_user_id"],
                },
            )
            await safe_answer_callback(callback)
            return await callback.message.answer(
                "⚠️ Request saved, but admin notification failed. Contact an admin."
            )
        await record_equipment_request_review_message(
            db,
            request,
            chat_id=review_message.chat.id,
            message_id=review_message.message_id,
        )

    await state.clear()
    await safe_answer_callback(callback)
    await callback.message.answer("✅ Request submitted.")


@router.callback_query(F.data == "equip_cancel")
async def equipment_request_cancel(callback: types.CallbackQuery, state: FSMContext):
    await safe_answer_callback(callback)
    await state.clear()
    await callback.message.answer("❌ Request cancelled.")
