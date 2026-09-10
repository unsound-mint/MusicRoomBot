# app/bot/keyboards/inline_kb.py
from collections.abc import Sequence
from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.constants.dates import WEEKDAYS
from app.bot.constants.links import FORMS_LINK
from app.bot.ui import format_slot_button


def access_form_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Open form", url=FORMS_LINK)]
        ]
    )


def day_selection_kb(
    available_days: list[int],
    *,
    callback_prefix: str = "book_day",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    weekday_labels = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    for idx in available_days:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{weekday_labels[idx]}",
                    callback_data=f"{callback_prefix}_{idx}",
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def hour_selection_kb(
    hours: list[int],
    weekday_idx: int,
    day_date: date,
    *,
    callback_prefix: str = "book_hour",
    include_back: bool = True,
    back_callback: str = "book_back_days",
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{hour:02d}:00",
                callback_data=(
                    f"{callback_prefix}_{weekday_idx}_{day_date.isoformat()}_{hour}"
                ),
            )
        ]
        for hour in hours
    ]
    if include_back:
        rows.append(
            [InlineKeyboardButton(text="⬅️ Back", callback_data=back_callback)]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def booking_success_kb(
    *,
    calendar_link: str,
    consecutive_callback: str | None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if consecutive_callback:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Book next hour",
                    callback_data=consecutive_callback,
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="Add to calendar", url=calendar_link)]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bookings_hub_kb(*, confirmed) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for booking in confirmed:
        rows.append(
            [
                InlineKeyboardButton(
                    text=format_slot_button(booking.date, booking.hour),
                    callback_data=f"myb_booking_{booking.id}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def booking_detail_kb(
    booking_id: int,
    *,
    calendar_link: str,
    can_swap: bool = True,
    can_cancel: bool = True,
    can_gift: bool = True,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="Add to calendar",
                url=calendar_link,
            )
        ],
    ]
    if can_cancel:
        rows.insert(
            0,
            [
                InlineKeyboardButton(
                    text="Cancel booking",
                    callback_data=f"myb_cancel_{booking_id}",
                )
            ],
        )
    if can_swap:
        rows.insert(
            1,
            [
                InlineKeyboardButton(
                    text="Swap booking",
                    callback_data=f"myb_swap_{booking_id}",
                )
            ],
        )
    if can_gift:
        rows.insert(
            2,
            [
                InlineKeyboardButton(
                    text="Gift booking",
                    callback_data=f"myb_gift_{booking_id}",
                )
            ],
        )
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="myb_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_confirm_kb(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Yes, cancel", callback_data=f"myb_confirm_cancel_{booking_id}")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data=f"myb_booking_{booking_id}")],
        ]
    )


def gift_username_prompt_kb(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back", callback_data=f"myb_booking_{booking_id}")],
        ]
    )


def gift_offer_response_kb(offer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Accept booking",
                    callback_data=f"gift_accept_{offer_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Decline",
                    callback_data=f"gift_decline_{offer_id}",
                )
            ],
        ]
    )


def google_calendar_kb(link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Add to calendar", url=link)]
        ]
    )


def club_list_kb(clubs) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=club.name, callback_data=f"club_view_{club.id}")]
            for club in clubs
        ]
    )


def club_week_kb(club_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="This week", callback_data=f"club_week_{club_id}_this")],
            [InlineKeyboardButton(text="Next week", callback_data=f"club_week_{club_id}_next")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="club_back")],
        ]
    )


def club_slots_kb(club_id: int, week_key: str, occurrences) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for occurrence in occurrences:
        status = "cancelled" if occurrence.is_cancelled else "active"
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"{WEEKDAYS[occurrence.slot.weekday][:3]} "
                        f"{occurrence.slot.hour:02d}:00 - {status}"
                    ),
                    callback_data=f"club_slot_{club_id}_{week_key}_{occurrence.slot.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data=f"club_view_{club_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def club_slot_detail_kb(
    club_id: int,
    week_key: str,
    slot_id: int,
    *,
    can_cancel: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_cancel:
        label = "Cancel next week" if week_key == "next" else "Cancel this week"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"club_cancel_{club_id}_{week_key}_{slot_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data=f"club_week_{club_id}_{week_key}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def remove_booking_day_selection_kb(available_days: Sequence[int | date]) -> InlineKeyboardMarkup:
    weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    rows: list[list[InlineKeyboardButton]] = []

    for item in available_days:
        if isinstance(item, date):
            label = f"{weekday_labels[item.weekday()]} {item:%m-%d}"
            callback_data = f"rmbday_{item.isoformat()}"
        else:
            label = weekday_labels[item]
            callback_data = f"rmbday_{item}"
        rows.append([InlineKeyboardButton(text=label, callback_data=callback_data)])

    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="rmb_back_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def inline_location_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Send Location", callback_data="loc_send")]
        ]
    )


def flash_book_kb(b_date: date, hour: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚡ Book this slot",
                    callback_data=f"flash_book_{b_date.isoformat()}_{hour}",
                )
            ]
        ]
    )


def warning_appeal_kb(user_db_id: int, *, text: str = "Appeal warning") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=f"warn_appeal_start_{user_db_id}")]
        ]
    )


def warning_appeal_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Cancel", callback_data="warn_appeal_cancel")]
        ]
    )


def equipment_request_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Cancel", callback_data="equip_cancel")]
        ]
    )


def equipment_request_rules_agreement_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="I agree", callback_data="equip_rules_agree")],
            [InlineKeyboardButton(text="Cancel", callback_data="equip_cancel")],
        ]
    )


def equipment_request_confirmation_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Submit", callback_data="equip_submit")],
            [InlineKeyboardButton(text="Edit details", callback_data="equip_edit_details")],
            [InlineKeyboardButton(text="Cancel", callback_data="equip_cancel")],
        ]
    )


def equipment_request_edit_fields_kb(
    fields: list[tuple[str, str]],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=label,
                callback_data=f"equip_edit_field_{field_name}",
            )
        ]
        for field_name, label in fields
    ]
    rows.append([InlineKeyboardButton(text="Cancel", callback_data="equip_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def equipment_request_hub_kb(
    requests,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{request.event_name} · {request.needed_at_text.splitlines()[0].removeprefix('- ')}",
                callback_data=f"equip_view_{request.id}",
            )
        ]
        for request in requests
    ]
    rows.append([InlineKeyboardButton(text="Submit new request", callback_data="equip_new")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def equipment_request_detail_kb(
    request_id: int,
    *,
    can_edit: bool,
) -> InlineKeyboardMarkup:
    rows = []
    if can_edit:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Edit details",
                    callback_data=f"equipreq_edit_{request_id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="equip_home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def equipment_request_day_kb(
    days: list[date],
    *,
    callback_prefix: str,
    back_callback: str | None = None,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=day.strftime("%a %Y-%m-%d"),
                callback_data=f"{callback_prefix}_{day.isoformat()}",
            )
        ]
        for day in days
    ]
    if back_callback:
        rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data=back_callback)])
    rows.append([InlineKeyboardButton(text="Cancel", callback_data="equip_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def equipment_request_hour_kb(
    target_date: date,
    hours: list[int],
    *,
    callback_prefix: str,
    back_callback: str,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{hour:02d}:00",
                callback_data=f"{callback_prefix}_{target_date.isoformat()}_{hour}",
            )
        ]
        for hour in hours
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data=back_callback)])
    rows.append([InlineKeyboardButton(text="Cancel", callback_data="equip_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def equipment_request_range_actions_kb(
    *,
    has_ranges: bool,
    back_callback: str | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if has_ranges:
        rows.append([InlineKeyboardButton(text="Continue", callback_data="equip_ranges_done")])
    rows.append([InlineKeyboardButton(text="Add another range", callback_data="equip_ranges_add")])
    if back_callback:
        rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data=back_callback)])
    rows.append([InlineKeyboardButton(text="Cancel", callback_data="equip_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def equipment_request_admin_review_kb(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Accept",
                    callback_data=f"equipreq_accept_{request_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Decline",
                    callback_data=f"equipreq_decline_{request_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Edit details",
                    callback_data=f"equipreq_edit_{request_id}",
                )
            ],
        ]
    )


def equipment_request_admin_edit_fields_kb(
    request_id: int,
    fields: list[tuple[str, str]],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=label,
                callback_data=f"equipreq_editfield_{request_id}_{field_name}",
            )
        ]
        for field_name, label in fields
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="Back",
                callback_data=f"equipreq_refresh_{request_id}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def equipment_request_admin_status_kb(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Edit details",
                    callback_data=f"equipreq_edit_{request_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Refresh",
                    callback_data=f"equipreq_refresh_{request_id}",
                )
            ]
        ]
    )
