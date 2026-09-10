from app.bot.constants.dates import WEEKDAYS
from app.bot.markdown import markdown_display


def remove_booking_picker_text() -> str:
    return "🗓 *Remove booking*\n\nSelect a day to see bookings."


def no_bookings_to_remove_text() -> str:
    return "📭 *No bookings to remove*"


def bookings_for_day_text(weekday_idx: int, target_date) -> str:
    return f"🗓 *{WEEKDAYS[weekday_idx]}* ({target_date})\n\nSelect a booking to remove."


def remove_booking_confirm_text(info: str) -> str:
    return f"⚠️ *Remove booking?*\n\n{markdown_display(info)}"


def removed_booking_picker_text(info: str) -> str:
    return f"✅ *Booking removed*\n\n{markdown_display(info)}\n\nSelect a day to see bookings."


def bookings_menu_text() -> str:
    return "🗓 *Bookings*\n\nChoose an action."


def add_booking_picker_text() -> str:
    return "➕ *Add booking*\n\nSelect a day."


def add_booking_no_dates_text() -> str:
    return "📭 *No free booking days*"


def add_booking_pick_hour_text(target_date) -> str:
    return (
        "➕ *Add booking*\n\n"
        f"🗓 *Day:* {WEEKDAYS[target_date.weekday()]} ({target_date})\n\n"
        "Select a time."
    )


def add_booking_no_hours_text(target_date) -> str:
    return (
        "📭 *No free slots*\n\n"
        f"{WEEKDAYS[target_date.weekday()]} ({target_date}) has no free slots."
    )


def add_booking_username_prompt_text(target_date, hour: int) -> str:
    return (
        "➕ *Add booking*\n\n"
        f"🗓 *Day:* {WEEKDAYS[target_date.weekday()]} ({target_date})\n"
        f"⏰ *Time:* {hour:02d}:00\n\n"
        "Send the member username, for example @username."
    )


def add_booking_success_text(username: str, target_date, hour: int) -> str:
    return (
        "✅ *Booking added*\n\n"
        f"👤 @{markdown_display(username)}\n"
        f"🗓 *Day:* {WEEKDAYS[target_date.weekday()]} ({target_date})\n"
        f"⏰ *Time:* {hour:02d}:00"
    )


def no_weekly_slots_text() -> str:
    return "🔁 *Weekly slots*\n\n📭 No weekly slots configured."


def weekly_slots_pick_remove_text() -> str:
    return "🔁 *Weekly slots*\n\nSelect a slot to remove."


def weekly_slot_info(slot) -> str:
    return f"{WEEKDAYS[slot.weekday]} {slot.hour:02d}:00 — {slot.group_name}"


def weekly_slot_not_found_text() -> str:
    return "⚠️ Weekly slot not found."


def weekly_slot_invalid_text() -> str:
    return "⚠️ Weekly slot is invalid."


def weekly_slot_remove_confirm_text(info: str) -> str:
    return f"⚠️ *Remove weekly slot?*\n\n{markdown_display(info)}"


def weekly_slot_removed_text(info: str) -> str:
    return f"✅ *Weekly slot removed*\n\n{markdown_display(info)}"


def weekly_add_pick_weekday_text() -> str:
    return "🔁 *Add weekly slot*\n\nChoose a weekday."


def weekly_add_pick_hour_text(weekday_idx: int) -> str:
    return f"🔁 *Add weekly slot*\n\n🗓 {WEEKDAYS[weekday_idx]}\n\nChoose a time."


def weekly_group_prompt_text(weekday_idx: int, hour: int) -> str:
    return (
        "🔁 *Weekly slot draft*\n\n"
        f"🗓 *Day:* {WEEKDAYS[weekday_idx]}\n"
        f"⏰ *Time:* {hour:02d}:00\n\n"
        "Send the group name."
    )


def weekly_create_confirm_text(weekday_idx: int, hour: int, group_name: str, conflict_text: str) -> str:
    return (
        "⚠️ *Create weekly slot?*\n\n"
        f"🗓 *Day:* {WEEKDAYS[weekday_idx]}\n"
        f"⏰ *Time:* {hour:02d}:00\n"
        f"👥 *Group:* {markdown_display(group_name)}"
        f"{conflict_text}"
    )


def weekly_draft_expired_text() -> str:
    return "⚠️ Weekly slot draft expired. Start again."


def weekly_slot_set_text(weekday_idx: int, hour: int, group_name: str, cancelled_count: int) -> str:
    lines = [
        "✅ *Weekly slot set*",
        "",
        f"🗓 *Day:* {WEEKDAYS[weekday_idx]}",
        f"⏰ *Time:* {hour:02d}:00",
        f"👥 *Group:* {markdown_display(group_name)}",
    ]
    if cancelled_count:
        lines += ["", f"⚠️ Conflicting bookings cancelled: {cancelled_count}"]
    return "\n".join(lines)
