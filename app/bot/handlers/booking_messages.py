from app.bot.constants.dates import WEEKDAYS


def build_weekly_limit_text(bookings, weekly_limit: int) -> str:
    lines = [
        "⚠️ *Weekly limit reached*",
        "",
        "*This week's bookings:*",
    ]
    lines.extend(
        f"• {WEEKDAYS[item.date.weekday()]} · {item.hour:02d}:00"
        for item in bookings
    )
    lines += [
        "",
        "Cancel a booking if your plans change.",
    ]
    return "\n".join(lines)


def build_no_free_slots_text() -> str:
    return (
        "📅 *No free slots this week*\n\n"
        "All slots are taken. Check back later or review the schedule."
    )


def build_pick_day_text(*, booked_count: int, weekly_limit: int, title: str) -> str:
    return f"*{title}*\n\n*Weekly usage:* {booked_count} / {weekly_limit}"


def build_booking_success_text(slot_text: str) -> str:
    return (
        f"✅ *Booking confirmed*\n\n"
        f"⏰ {slot_text}\n\n"
        "Have a great session!"
    )


def build_booking_success_two_slots_text(slot_text_1: str, slot_text_2: str) -> str:
    return (
        f"✅ *Booking confirmed*\n\n"
        f"⏰ {slot_text_1}\n"
        f"⏰ {slot_text_2}\n\n"
        "Have a great session!"
    )


def build_booking_cancelled_text(slot_text: str) -> str:
    return (
        f"❌ *Booking cancelled*\n\n"
        f"⏰ {slot_text}\n\n"
        "Please cancel early whenever plans change — it helps others book."
    )
