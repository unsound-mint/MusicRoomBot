# app/bot/handlers/admin_equipment_requests.py
from __future__ import annotations

import logging

from aiogram import F, Router, types

from app.bot.handlers.admin_shared import AdminInputStates, check_admin_callback
from app.bot.keyboards.admin_inline_kb import admin_back_kb
from app.bot.keyboards.inline_kb import (
    equipment_request_admin_edit_fields_kb,
    equipment_request_admin_review_kb,
    equipment_request_admin_status_kb,
)
from app.bot.ui import edit_or_answer, safe_answer_callback
from app.core.database import AsyncSessionLocal
from app.models.equipment_request import EquipmentRequest
from app.services.config_runtime import get_runtime_config
from app.services.equipment_request_service import (
    approve_equipment_request,
    decline_equipment_request,
    get_equipment_request_with_ranges,
    record_equipment_request_dm_result,
    record_equipment_request_topic_post_result,
    render_equipment_request_review,
    render_equipment_request_status,
    render_equipment_topic_post,
)

log = logging.getLogger(__name__)
router = Router()

ADMIN_EQUIPMENT_REQUEST_FIELDS: tuple[tuple[str, str], ...] = (
    ("club_name", "Club"),
    ("event_name", "Event"),
    ("venue", "Venue"),
    ("equipment_text", "Equipment"),
    ("needed_at_text", "Date/time"),
    ("reason_text", "Reason"),
    ("comments", "Comments"),
)

ADMIN_FIELD_PROMPTS = {
    "club_name": "Send the new club name.",
    "event_name": "Send the new event name.",
    "venue": "Send the new venue.",
    "equipment_text": "Send the new equipment list.",
    "needed_at_text": (
        "Send one or more ranges, one per line, in "
        "`YYYY-MM-DD HH:MM -> YYYY-MM-DD HH:MM` format."
    ),
    "reason_text": "Send the new reason.",
    "comments": "Send the new comments, or `-` to clear them.",
}


def _review_markup(request: EquipmentRequest):
    if request.status == "submitted":
        return equipment_request_admin_review_kb(request.id)
    return equipment_request_admin_status_kb(request.id)


async def _get_request(db, request_id: int) -> EquipmentRequest | None:
    return await get_equipment_request_with_ranges(db, request_id)


async def _render_not_found(callback: types.CallbackQuery) -> None:
    await edit_or_answer(
        callback,
        "Equipment request not found.",
        reply_markup=admin_back_kb("admin_home"),
    )


async def _refresh_review_message(
    bot,
    request: EquipmentRequest,
    *,
    fallback_target: types.CallbackQuery | None = None,
) -> None:
    if request.status == "approved" and (
        request.review_chat_id is None or request.review_message_id is None
    ):
        if fallback_target is not None:
            await edit_or_answer(
                fallback_target,
                render_equipment_request_status(request),
                reply_markup=_review_markup(request),
            )
        return

    text = (
        render_equipment_request_review(request)
        if request.status == "submitted"
        else render_equipment_request_status(request)
    )
    reply_markup = _review_markup(request)

    if request.review_chat_id is not None and request.review_message_id is not None:
        await bot.edit_message_text(
            text=text,
            chat_id=request.review_chat_id,
            message_id=request.review_message_id,
            reply_markup=reply_markup,
        )
        return

    if fallback_target is not None:
        await edit_or_answer(fallback_target, text, reply_markup=reply_markup)


@router.callback_query(F.data.startswith("equipreq_refresh_"))
async def equipment_request_refresh(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    request_id = int(callback.data.rsplit("_", 1)[1])

    async with AsyncSessionLocal() as db:
        request = await _get_request(db, request_id)
        if not request:
            return await _render_not_found(callback)
        return await edit_or_answer(
            callback,
            render_equipment_request_review(request)
            if request.status == "submitted"
            else render_equipment_request_status(request),
            reply_markup=_review_markup(request),
        )


@router.callback_query(F.data.startswith("equipreq_edit_"))
async def equipment_request_edit(callback: types.CallbackQuery, state):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    request_id = int(callback.data.rsplit("_", 1)[1])

    async with AsyncSessionLocal() as db:
        request = await _get_request(db, request_id)
        if not request:
            return await _render_not_found(callback)
        if request.status not in {"submitted", "approved"}:
            return await edit_or_answer(
                callback,
                render_equipment_request_status(request),
                reply_markup=equipment_request_admin_status_kb(request.id),
            )

    return await edit_or_answer(
        callback,
        "Choose a field to edit.",
        reply_markup=equipment_request_admin_edit_fields_kb(
            request_id,
            list(ADMIN_EQUIPMENT_REQUEST_FIELDS),
        ),
    )


@router.callback_query(F.data.startswith("equipreq_editfield_"))
async def equipment_request_edit_field(callback: types.CallbackQuery, state):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    _, _, request_id_s, field_name = callback.data.split("_", 3)
    request_id = int(request_id_s)
    if field_name not in dict(ADMIN_EQUIPMENT_REQUEST_FIELDS):
        return await edit_or_answer(
            callback,
            "Unknown equipment request field.",
            reply_markup=admin_back_kb(f"equipreq_refresh_{request_id}"),
        )

    async with AsyncSessionLocal() as db:
        request = await _get_request(db, request_id)
        if not request:
            return await _render_not_found(callback)
        if request.status not in {"submitted", "approved"}:
            return await edit_or_answer(
                callback,
                render_equipment_request_status(request),
                reply_markup=equipment_request_admin_status_kb(request.id),
            )

    await state.set_state(AdminInputStates.waiting_equipment_request_value)
    await state.update_data(
        admin_action="equipreq_field",
        equipment_request_id=request_id,
        equipment_request_field=field_name,
    )
    return await edit_or_answer(
        callback,
        ADMIN_FIELD_PROMPTS[field_name],
        reply_markup=admin_back_kb(f"equipreq_refresh_{request_id}"),
    )


@router.callback_query(F.data.startswith("equipreq_accept_"))
async def equipment_request_accept(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    request_id = int(callback.data.rsplit("_", 1)[1])

    async with AsyncSessionLocal() as db:
        request = await _get_request(db, request_id)
        if not request:
            return await _render_not_found(callback)
        if request.status != "submitted":
            return await edit_or_answer(
                callback,
                render_equipment_request_status(request),
                reply_markup=equipment_request_admin_status_kb(request.id),
            )

        request = await approve_equipment_request(
            db,
            request,
            admin_tg_user_id=callback.from_user.id,
        )

        dm_error = None
        try:
            await callback.bot.send_message(
                request.requester_tg_user_id,
                "Your equipment request was approved.",
            )
            request = await record_equipment_request_dm_result(
                db, request, ok=True, error=None
            )
        except Exception as exc:
            dm_error = str(exc)
            log.warning(
                "Failed to notify requester about equipment approval",
                extra={
                    "equipment_request_id": request.id,
                    "requester_tg_user_id": request.requester_tg_user_id,
                    "error": dm_error,
                },
            )
            request = await record_equipment_request_dm_result(
                db, request, ok=False, error=dm_error
            )

        member_chat_id = await get_runtime_config("member_chat_id")
        equipment_topic_id = await get_runtime_config("equipment_topic_id")
        equipment_error = None
        try:
            if not member_chat_id or equipment_topic_id is None:
                raise RuntimeError("Equipment topic is not configured.")
            msg = await callback.bot.send_message(
                int(member_chat_id),
                render_equipment_topic_post(request),
                message_thread_id=int(equipment_topic_id),
            )
            request = await record_equipment_request_topic_post_result(
                db, request, ok=True, error=None,
                chat_id=msg.chat.id, message_id=msg.message_id
            )
        except Exception as exc:
            equipment_error = str(exc)
            log.exception(
                "Failed to post approved equipment request to topic",
                extra={
                    "equipment_request_id": request.id,
                    "member_chat_id": member_chat_id,
                    "equipment_topic_id": equipment_topic_id,
                },
            )
            request = await record_equipment_request_topic_post_result(
                db, request, ok=False, error=equipment_error
            )

        await _refresh_review_message(callback.bot, request, fallback_target=callback)


@router.callback_query(F.data.startswith("equipreq_decline_"))
async def equipment_request_decline(callback: types.CallbackQuery):
    if not await check_admin_callback(callback):
        return
    await safe_answer_callback(callback)
    request_id = int(callback.data.rsplit("_", 1)[1])

    async with AsyncSessionLocal() as db:
        request = await _get_request(db, request_id)
        if not request:
            return await _render_not_found(callback)
        if request.status != "submitted":
            return await edit_or_answer(
                callback,
                render_equipment_request_status(request),
                reply_markup=equipment_request_admin_status_kb(request.id),
            )

        request = await decline_equipment_request(
            db,
            request,
            admin_tg_user_id=callback.from_user.id,
        )

        try:
            await callback.bot.send_message(
                request.requester_tg_user_id,
                "Your equipment request was declined.",
            )
            request = await record_equipment_request_dm_result(
                db, request, ok=True, error=None
            )
        except Exception as exc:
            dm_error = str(exc)
            log.warning(
                "Failed to notify requester about equipment decline",
                extra={
                    "equipment_request_id": request.id,
                    "requester_tg_user_id": request.requester_tg_user_id,
                    "error": dm_error,
                },
            )
            request = await record_equipment_request_dm_result(
                db, request, ok=False, error=dm_error
            )

        await _refresh_review_message(callback.bot, request, fallback_target=callback)
