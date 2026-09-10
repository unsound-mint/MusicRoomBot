from __future__ import annotations

import inspect
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.models.equipment_request import EquipmentRequest
from app.models.equipment_request_range import EquipmentRequestRange
from app.services.time_service import now_tz

log = logging.getLogger(__name__)

UPDATABLE_EQUIPMENT_REQUEST_FIELDS = {
    "requester_username",
    "full_name",
    "club_name",
    "event_name",
    "venue",
    "equipment_text",
    "needed_at_text",
    "reason_text",
    "comments",
    "equipment_post_chat_id",
    "equipment_post_message_id",
}


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _requester_line(request: EquipmentRequest) -> str:
    if request.requester_username:
        return f"From: @{request.requester_username}"
    return "From: (no username)"


def format_equipment_datetime(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def format_equipment_range(start_at: datetime, end_at: datetime) -> str:
    return f"{format_equipment_datetime(start_at)} -> {format_equipment_datetime(end_at)}"


def summarize_equipment_ranges(ranges) -> str:
    if not ranges:
        return "-"
    return "\n".join(
        f"- {format_equipment_range(item.start_at, item.end_at)}"
        for item in ranges
    )


def _equipment_block(request: EquipmentRequest) -> str:
    return "Equipment:\n" f"{request.equipment_text.strip()}"


def _format_shared_request_details(request: EquipmentRequest) -> str:
    lines = [
        _requester_line(request),
        f"Full name: {request.full_name}",
        f"Club: {request.club_name}",
        f"Event: {request.event_name}",
        f"Venue: {request.venue}",
        "Requested time ranges:",
        summarize_equipment_ranges(request.ranges),
        _equipment_block(request),
        f"Reason: {request.reason_text}",
    ]
    if request.comments:
        lines.append(f"Comments: {request.comments}")
    return "\n".join(lines)


def _format_status_request_details(request: EquipmentRequest) -> str:
    lines = [
        _requester_line(request),
        f"Club: {request.club_name}",
        f"Event: {request.event_name}",
        f"Venue: {request.venue}",
        "Requested time ranges:",
        summarize_equipment_ranges(request.ranges),
        _equipment_block(request),
        f"Reason: {request.reason_text}",
    ]
    if request.comments:
        lines.append(f"Comments: {request.comments}")
    return "\n".join(lines)


def _ensure_decidable(request: EquipmentRequest) -> None:
    if request.status in {"approved", "declined"}:
        raise ValueError("Equipment request has already been decided")


def render_equipment_request_review(request: EquipmentRequest) -> str:
    return "New equipment request\n\n" + _format_shared_request_details(request)


def render_equipment_request_status(request: EquipmentRequest) -> str:
    if request.status == "approved":
        lines = ["Equipment request approved", "", _format_status_request_details(request), ""]
        lines.append(f"DM sent: {'yes' if request.requester_dm_sent else 'no'}")
        if not request.requester_dm_sent and request.requester_dm_error:
            lines.append(f"DM error: {request.requester_dm_error}")
        lines.append(
            f"Equipment topic post sent: {'yes' if request.equipment_post_sent else 'no'}"
        )
        if not request.equipment_post_sent and request.equipment_post_error:
            lines.append(f"Equipment post error: {request.equipment_post_error}")
        return "\n".join(lines)

    if request.status == "declined":
        lines = ["Equipment request declined", "", _format_status_request_details(request), ""]
        lines.append(f"DM sent: {'yes' if request.requester_dm_sent else 'no'}")
        if not request.requester_dm_sent and request.requester_dm_error:
            lines.append(f"DM error: {request.requester_dm_error}")
        return "\n".join(lines)

    return render_equipment_request_review(request)


def render_equipment_topic_post(request: EquipmentRequest) -> str:
    return (
        "🎤 Approved equipment request\n\n"
        "Requested time ranges:\n"
        f"{summarize_equipment_ranges(request.ranges)}\n"
        f"{_equipment_block(request)}"
    )


def render_requester_equipment_request_detail(request: EquipmentRequest) -> str:
    return (
        "Equipment request\n\n"
        "Requested time ranges:\n"
        f"{summarize_equipment_ranges(request.ranges)}\n"
        f"{_equipment_block(request)}"
    )


def render_admin_equipment_request_detail(request: EquipmentRequest) -> str:
    lines = [
        "Equipment request",
        "",
        f"Status: {request.status}",
        _requester_line(request),
        f"Club: {request.club_name}",
        f"Event: {request.event_name}",
        f"Venue: {request.venue}",
        "Requested time ranges:",
        summarize_equipment_ranges(request.ranges),
        "Equipment:",
        request.equipment_text.strip(),
        f"Reason: {request.reason_text}",
    ]
    if request.comments:
        lines.append(f"Comments: {request.comments}")
    return "\n".join(lines)


def check_equipment_ranges_overlap(ranges: list[dict[str, datetime]]) -> None:
    """Check if any of the time ranges overlap with each other.

    Raises:
        ValueError: if an overlap is detected.
    """
    sorted_ranges = sorted(ranges, key=lambda x: x["start_at"])
    for i in range(len(sorted_ranges) - 1):
        current_end = sorted_ranges[i]["end_at"]
        next_start = sorted_ranges[i + 1]["start_at"]
        if next_start < current_end:
            raise ValueError(
                f"Time ranges overlap: {sorted_ranges[i]['start_at'].strftime('%H:%M')}-"
                f"{current_end.strftime('%H:%M')} and "
                f"{next_start.strftime('%H:%M')}-{sorted_ranges[i + 1]['end_at'].strftime('%H:%M')}."
            )


async def get_future_approved_equipment_requests(db) -> list[EquipmentRequest]:
    now = now_tz()
    subquery = (
        select(EquipmentRequestRange.equipment_request_id)
        .where(EquipmentRequestRange.end_at >= now)
        .group_by(EquipmentRequestRange.equipment_request_id)
        .subquery()
    )
    rows = await _maybe_await(
        db.execute(
            select(EquipmentRequest)
            .options(selectinload(EquipmentRequest.ranges))
            .where(EquipmentRequest.status == "approved")
            .where(EquipmentRequest.id.in_(select(subquery.c.equipment_request_id)))
            .order_by(EquipmentRequest.id.desc())
        )
    )
    return rows.scalars().all()


async def get_future_approved_request(
    db,
    *,
    request_id: int,
) -> EquipmentRequest | None:
    now = now_tz()
    request = (
        await _maybe_await(
            db.execute(
                select(EquipmentRequest)
                .options(selectinload(EquipmentRequest.ranges))
                .where(EquipmentRequest.id == request_id)
                .where(EquipmentRequest.status == "approved")
            )
        )
    ).scalar_one_or_none()
    if not request:
        return None
    if not any(item.end_at >= now for item in request.ranges):
        return None
    return request


async def get_equipment_request_with_ranges(db, request_id: int) -> EquipmentRequest | None:
    return (
        await _maybe_await(
            db.execute(
                select(EquipmentRequest)
                .options(selectinload(EquipmentRequest.ranges))
                .where(EquipmentRequest.id == request_id)
            )
        )
    ).scalar_one_or_none()


async def create_equipment_request(db, *, ranges: list[dict[str, Any]], **fields: Any) -> EquipmentRequest:
    fields.setdefault("status", "submitted")
    # Avoid passing needed_at_text in fields as it is calculated below
    fields.pop("needed_at_text", None)
    
    request = EquipmentRequest(**fields, needed_at_text="")
    db.add(request)
    await _maybe_await(db.flush())
    
    range_rows = [
        EquipmentRequestRange(
            equipment_request_id=request.id,
            sort_order=index,
            start_at=item["start_at"],
            end_at=item["end_at"],
        )
        for index, item in enumerate(ranges)
    ]
    request.needed_at_text = summarize_equipment_ranges(range_rows)
    db.add_all(range_rows)
    db.add(request)
    await _maybe_await(db.commit())
    reloaded = await get_equipment_request_with_ranges(db, request.id)
    if reloaded is None:
        raise RuntimeError("Equipment request was created but could not be reloaded.")
    log.info(
        "Equipment request created",
        extra={
            "equipment_request_id": reloaded.id,
            "requester_tg_user_id": reloaded.requester_tg_user_id,
            "range_count": len(reloaded.ranges),
        },
    )
    return reloaded


async def record_equipment_request_review_message(
    db,
    request: EquipmentRequest,
    *,
    chat_id: int,
    message_id: int,
) -> EquipmentRequest:
    request.review_chat_id = chat_id
    request.review_message_id = message_id
    db.add(request)
    await _maybe_await(db.commit())
    await _maybe_await(db.refresh(request))
    log.info(
        "Equipment request submitted for review",
        extra={
            "equipment_request_id": request.id,
            "review_chat_id": request.review_chat_id,
            "review_message_id": request.review_message_id,
        },
    )
    return request


async def update_equipment_request_field(
    db,
    request: EquipmentRequest,
    field_name: str,
    value: Any,
) -> EquipmentRequest:
    if field_name not in UPDATABLE_EQUIPMENT_REQUEST_FIELDS:
        raise AttributeError(f"EquipmentRequest has no field named {field_name!r}")

    setattr(request, field_name, value)
    db.add(request)
    await _maybe_await(db.commit())
    await _maybe_await(db.refresh(request))
    await _maybe_await(db.refresh(request, attribute_names=["ranges"]))
    log.info(
        "Equipment request field updated",
        extra={"equipment_request_id": request.id, "field_name": field_name},
    )
    return request


async def replace_equipment_request_ranges(
    db,
    request: EquipmentRequest,
    *,
    ranges: list[dict[str, datetime]],
) -> EquipmentRequest:
    await _maybe_await(
        db.execute(
            delete(EquipmentRequestRange).where(
                EquipmentRequestRange.equipment_request_id == request.id
            )
        )
    )
    range_rows = [
        EquipmentRequestRange(
            equipment_request_id=request.id,
            sort_order=index,
            start_at=item["start_at"],
            end_at=item["end_at"],
        )
        for index, item in enumerate(ranges)
    ]
    request.needed_at_text = summarize_equipment_ranges(range_rows)
    db.add_all(range_rows)
    db.add(request)
    await _maybe_await(db.commit())
    reloaded = await get_equipment_request_with_ranges(db, request.id)
    if reloaded is None:
        raise RuntimeError("Equipment request ranges were updated but could not be reloaded.")
    log.info(
        "Equipment request ranges replaced",
        extra={"equipment_request_id": reloaded.id, "range_count": len(reloaded.ranges)},
    )
    return reloaded


async def record_equipment_request_dm_result(
    db,
    request: EquipmentRequest,
    *,
    ok: bool,
    error: str | None,
) -> EquipmentRequest:
    request.requester_dm_sent = ok
    request.requester_dm_error = error
    db.add(request)
    await _maybe_await(db.commit())
    await _maybe_await(db.refresh(request))
    log.info(
        "Equipment request DM result recorded",
        extra={
            "equipment_request_id": request.id,
            "requester_tg_user_id": request.requester_tg_user_id,
            "ok": ok,
            "error": error,
        },
    )
    return request


async def record_equipment_request_topic_post_result(
    db,
    request: EquipmentRequest,
    *,
    ok: bool,
    error: str | None,
    chat_id: int | None = None,
    message_id: int | None = None,
) -> EquipmentRequest:
    request.equipment_post_sent = ok
    request.equipment_post_error = error
    if ok:
        request.equipment_post_chat_id = chat_id
        request.equipment_post_message_id = message_id
    db.add(request)
    await _maybe_await(db.commit())
    await _maybe_await(db.refresh(request))
    log.info(
        "Equipment request topic post result recorded",
        extra={
            "equipment_request_id": request.id,
            "ok": ok,
            "chat_id": chat_id,
            "message_id": message_id,
            "error": error,
        },
    )
    return request


async def approve_equipment_request(
    db,
    request: EquipmentRequest,
    *,
    admin_tg_user_id: int,
) -> EquipmentRequest:
    _ensure_decidable(request)
    request.status = "approved"
    request.admin_tg_user_id = admin_tg_user_id
    request.decided_at = now_tz()
    db.add(request)
    await _maybe_await(db.commit())
    await _maybe_await(db.refresh(request))
    await _maybe_await(db.refresh(request, attribute_names=["ranges"]))
    log.info(
        "Equipment request approved",
        extra={
            "equipment_request_id": request.id,
            "admin_tg_user_id": admin_tg_user_id,
        },
    )
    return request


async def decline_equipment_request(
    db,
    request: EquipmentRequest,
    *,
    admin_tg_user_id: int,
) -> EquipmentRequest:
    _ensure_decidable(request)
    request.status = "declined"
    request.admin_tg_user_id = admin_tg_user_id
    request.decided_at = now_tz()
    db.add(request)
    await _maybe_await(db.commit())
    await _maybe_await(db.refresh(request))
    await _maybe_await(db.refresh(request, attribute_names=["ranges"]))
    log.info(
        "Equipment request declined",
        extra={
            "equipment_request_id": request.id,
            "admin_tg_user_id": admin_tg_user_id,
        },
    )
    return request


def parse_equipment_ranges_text(raw_text: str) -> list[dict[str, datetime]]:
    ranges: list[dict[str, datetime]] = []
    for index, line in enumerate((raw_text or "").splitlines(), start=1):
        text = line.strip()
        if not text:
            continue
        parts = text.split("->", 1)
        if len(parts) != 2:
            raise ValueError(f"Line {index}: use `YYYY-MM-DD HH:MM -> YYYY-MM-DD HH:MM`.")
        try:
            start_at = datetime.strptime(parts[0].strip(), "%Y-%m-%d %H:%M").replace(
                tzinfo=now_tz().tzinfo
            )
            end_at = datetime.strptime(parts[1].strip(), "%Y-%m-%d %H:%M").replace(
                tzinfo=now_tz().tzinfo
            )
        except ValueError:
            raise ValueError(
                f"Line {index}: use `YYYY-MM-DD HH:MM -> YYYY-MM-DD HH:MM`."
            ) from None
        if end_at <= start_at:
            raise ValueError(f"Line {index}: end must be after start.")
        ranges.append({"start_at": start_at, "end_at": end_at})
    if not ranges:
        raise ValueError("Add at least one time range.")
    check_equipment_ranges_overlap(ranges)
    return ranges
