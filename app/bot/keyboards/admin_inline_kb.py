# app/bot/keyboards/admin_inline_kb.py
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.constants.dates import WEEKDAYS


def _markup(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_home_kb() -> InlineKeyboardMarkup:
    return _markup(
        [
            [InlineKeyboardButton(text="Users", callback_data="admin_users")],
            [InlineKeyboardButton(text="Bookings", callback_data="admin_bookings")],
            [InlineKeyboardButton(text="Clubs", callback_data="admin_clubs")],
            [InlineKeyboardButton(text="Config", callback_data="admin_cfg")],
            [InlineKeyboardButton(text="System", callback_data="admin_sys")],
            [InlineKeyboardButton(text="Bulk sync", callback_data="admin_bulk")],
        ]
    )


def admin_back_kb(callback_data: str = "admin_home") -> InlineKeyboardMarkup:
    return _markup([[InlineKeyboardButton(text="⬅️ Back", callback_data=callback_data)]])


def admin_next_actions_kb(
    actions: list[tuple[str, str]],
    *,
    back_data: str,
    back_text: str = "⬅️ Back",
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=text, callback_data=callback_data)]
        for text, callback_data in actions
    ]
    rows.append([InlineKeyboardButton(text=back_text, callback_data=back_data)])
    return _markup(rows)


def admin_users_kb() -> InlineKeyboardMarkup:
    return _markup(
        [
            [InlineKeyboardButton(text="Find user", callback_data="admin_users_find")],
            [InlineKeyboardButton(text="List users", callback_data="admin_users_list")],
            [InlineKeyboardButton(text="Unban all users", callback_data="admin_users_unban_all")],
            [InlineKeyboardButton(text="List warned users", callback_data="admin_users_warn_list")],
            [InlineKeyboardButton(text="Reset all warnings", callback_data="admin_users_warn_reset_all")],
            [InlineKeyboardButton(text="Admins", callback_data="admin_users_admins")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="admin_home")],
        ]
    )


def admin_admins_kb() -> InlineKeyboardMarkup:
    return _markup(
        [
            [InlineKeyboardButton(text="List admins", callback_data="admin_users_admins_list")],
            [InlineKeyboardButton(text="Add admin", callback_data="admin_users_admins_add")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="admin_users")],
        ]
    )


def admin_user_actions_kb(username: str, *, banned: bool, allowed: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="Allow access" if not allowed else "Revoke access",
                callback_data=(
                    f"admin_users_allow_direct_{username}"
                    if not allowed
                    else f"admin_users_unallow_direct_{username}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="Ban" if not banned else "Unban",
                callback_data=(
                    f"admin_users_ban_direct_{username}"
                    if not banned
                    else f"admin_users_unban_direct_{username}"
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="Add warning",
                callback_data=f"admin_warn_add_direct_{username}",
            )
        ],
        [
            InlineKeyboardButton(
                text="Remove warning",
                callback_data=f"admin_warn_remove_direct_{username}",
            )
        ],
        [
            InlineKeyboardButton(
                text="Revert warning/ban",
                callback_data=f"admin_warn_revert_direct_{username}",
            )
        ],
        [
            InlineKeyboardButton(
                text="Reset warnings",
                callback_data=f"admin_warn_reset_direct_{username}",
            ),
        ],
        [
            InlineKeyboardButton(
                text="Delete user",
                callback_data=f"admin_users_delete_direct_{username}",
            )
        ],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="admin_users")],
    ]
    return _markup(rows)


def admin_confirm_kb(confirm_data: str, back_data: str) -> InlineKeyboardMarkup:
    return _markup(
        [
            [InlineKeyboardButton(text="Confirm", callback_data=confirm_data)],
            [InlineKeyboardButton(text="⬅️ Back", callback_data=back_data)],
        ]
    )


def admin_bookings_kb() -> InlineKeyboardMarkup:
    return _markup(
        [
            [InlineKeyboardButton(text="Add booking", callback_data="admin_bookings_add")],
            [InlineKeyboardButton(text="Remove booking", callback_data="admin_bookings_remove")],
            [InlineKeyboardButton(text="Weekly slots", callback_data="admin_bookings_weekly")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="admin_home")],
        ]
    )


def admin_booking_date_kb(dates, *, callback_prefix: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in dates:
        label = f"{WEEKDAYS[item.weekday()][:3]} {item:%m-%d}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"{callback_prefix}_{item.isoformat()}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="admin_bookings")])
    return _markup(rows)


def admin_booking_hour_kb(
    target_date,
    hours: list[int],
    *,
    callback_prefix: str,
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
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="admin_bookings_add")])
    return _markup(rows)


def admin_weekly_kb() -> InlineKeyboardMarkup:
    return _markup(
        [
            [InlineKeyboardButton(text="List weekly slots", callback_data="admin_weekly_list")],
            [InlineKeyboardButton(text="Add weekly slot", callback_data="admin_weekly_add")],
            [InlineKeyboardButton(text="Remove weekly slot", callback_data="admin_weekly_remove")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="admin_bookings")],
        ]
    )


def admin_clubs_kb() -> InlineKeyboardMarkup:
    return _markup(
        [
            [InlineKeyboardButton(text="List clubs", callback_data="admin_clubs_list")],
            [InlineKeyboardButton(text="Add club", callback_data="admin_clubs_add")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="admin_home")],
        ]
    )


def admin_club_list_kb(clubs) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=club.name, callback_data=f"admin_club_view_{club.id}")]
        for club in clubs
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="admin_clubs")])
    return _markup(rows)


def admin_club_detail_kb(club_id: int) -> InlineKeyboardMarkup:
    return _markup(
        [
            [InlineKeyboardButton(text="Add leader", callback_data=f"admin_club_leader_add_{club_id}")],
            [InlineKeyboardButton(text="Assign weekly slot", callback_data=f"admin_club_slot_add_{club_id}")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="admin_clubs_list")],
        ]
    )


def weekday_kb(prefix: str, *, back_data: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for idx, label in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
        row.append(
            InlineKeyboardButton(text=label, callback_data=f"{prefix}_{idx}")
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data=back_data)])
    return _markup(rows)


def hour_kb(prefix: str, hours: list[int], *, back_data: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{hour:02d}:00", callback_data=f"{prefix}_{hour}")]
        for hour in hours
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data=back_data)])
    return _markup(rows)


def warning_appeal_review_kb(user_db_id: int) -> InlineKeyboardMarkup:
    return _markup(
        [
            [InlineKeyboardButton(text="Approve", callback_data=f"warn_appeal_approve_{user_db_id}")],
            [InlineKeyboardButton(text="Decline", callback_data=f"warn_appeal_decline_{user_db_id}")],
        ]
    )


def warning_revert_kb(user_db_id: int) -> InlineKeyboardMarkup:
    return _markup(
        [[InlineKeyboardButton(text="Revert", callback_data=f"warn_revert_{user_db_id}")]]
    )


def admin_config_kb() -> InlineKeyboardMarkup:
    return _markup(
        [
            [InlineKeyboardButton(text="Weekly limit", callback_data="admin_cfg_weekly_limit")],
            [InlineKeyboardButton(text="Slot length", callback_data="admin_cfg_slot_length")],
            [InlineKeyboardButton(text="Reminder hours", callback_data="admin_cfg_reminder_hours")],
            [InlineKeyboardButton(text="Late minutes", callback_data="admin_cfg_late_minutes")],
            [InlineKeyboardButton(text="Geo radius", callback_data="admin_cfg_geo_radius")],
            [InlineKeyboardButton(text="Geo center", callback_data="admin_cfg_geo_center")],
            [InlineKeyboardButton(text="Chat IDs", callback_data="admin_cfg_chat_ids")],
            [InlineKeyboardButton(text="Rules", callback_data="admin_cfg_rules")],
            [InlineKeyboardButton(text="Working hours", callback_data="admin_cfg_working_hours")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="admin_home")],
        ]
    )


def numeric_value_kb(prefix: str, values: list[int], *, back_data: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=str(value), callback_data=f"{prefix}_{value}")] for value in values]
    rows.append([InlineKeyboardButton(text="Custom", callback_data=f"{prefix}_custom")])
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data=back_data)])
    return _markup(rows)


def admin_chat_ids_kb() -> InlineKeyboardMarkup:
    return _markup(
        [
            [InlineKeyboardButton(text="Admin chat ID", callback_data="admin_cfg_chat_admin_chat_id")],
            [InlineKeyboardButton(text="Warning chat ID", callback_data="admin_cfg_chat_warning_chat_id")],
            [InlineKeyboardButton(text="Member chat ID", callback_data="admin_cfg_chat_member_chat_id")],
            [InlineKeyboardButton(text="Member topic ID", callback_data="admin_cfg_chat_member_topic_id")],
            [InlineKeyboardButton(text="Equipment topic ID", callback_data="admin_cfg_chat_equipment_topic_id")],
            [InlineKeyboardButton(text="Access chat ID", callback_data="admin_cfg_chat_access_chat_id")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="admin_cfg")],
        ]
    )


def working_hours_weekday_kb() -> InlineKeyboardMarkup:
    return weekday_kb("admin_cfg_hours", back_data="admin_cfg")


def working_hours_value_kb(weekday_idx: int) -> InlineKeyboardMarkup:
    presets = [(9, 23), (10, 22), (12, 24)]
    rows = [
        [
            InlineKeyboardButton(
                text=f"{start}:00-{end}:00",
                callback_data=f"admin_cfg_hourspreset_{weekday_idx}_{start}_{end}",
            )
        ]
        for start, end in presets
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="Custom",
                callback_data=f"admin_cfg_hourscustom_{weekday_idx}",
            )
        ]
    )
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="admin_cfg")])
    return _markup(rows)


def admin_system_kb() -> InlineKeyboardMarkup:
    return _markup(
        [
            [InlineKeyboardButton(text="Status", callback_data="admin_sys_status")],
            [InlineKeyboardButton(text="Scheduler", callback_data="admin_sys_scheduler")],
            [InlineKeyboardButton(text="Run weekly reset now", callback_data="admin_sys_reset")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="admin_home")],
        ]
    )


def admin_bulk_kb() -> InlineKeyboardMarkup:
    return _markup(
        [
            [InlineKeyboardButton(text="Upload members CSV", callback_data="admin_bulk_upload")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="admin_home")],
        ]
    )


def weekly_list_kb(slots) -> InlineKeyboardMarkup:
    rows = []
    for slot in slots:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{WEEKDAYS[slot.weekday][:3]} {slot.hour:02d}:00 - {slot.group_name}",
                    callback_data=f"admin_weekly_delete_{slot.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="admin_bookings_weekly")])
    return _markup(rows)
