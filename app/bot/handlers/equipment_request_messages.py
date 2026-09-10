from typing import Any

from app.bot.markdown import markdown_display

MISSING_FULL_NAME_TEXT = "👤 Full name missing\n\nPlease ask an admin to add it first."


EQUIPMENT_REQUEST_RULES_TEXT = (
    "*Rules and regulations regarding equipment requests*\n\n"
    "1. All equipment requests for the upcoming week must be submitted *by Sunday at 18:00*.\n"
    "2. If you borrow anything from the Music Room, you are responsible for returning the "
    "equipment *by the designated time* and in *fully usable condition*, regardless of its "
    "previous state. For example, carpets should be laid out, drums fully assembled, "
    "speakers connected properly, etc.\n"
    "3. Any damage or malfunction of the equipment must be reported *immediately*.\n"
    "4. Upon returning, you must *send a picture* to the Music Room chat (or to @unsound\\_mint "
    "if you are not in the chat) *before your booking time ends* to confirm that everything "
    "was returned on time and in good condition.\n"
    "5. You have a right to *interrupt rehearsals* in the Music Room to return equipment on "
    "time. Resistance to this by Music Room users will be considered a *violation* and you "
    "can refer them to these rules if needed.\n\n"
    "*Violations of these rules will result in reduced weekly slots and/or "
    "denial of future requests, for a period and extent determined by the Ministry of Culture.*\n\n"
    "*What to do if I missed the deadline for booking?*\n\n"
    "1. Find the contacts of people during whose slots you need equipment (you can "
    "contact @unsound\\_mint for this).\n"
    "2. Ask each of them if they are okay with the equipment you need being unavailable "
    "during their slot. *If they are not, you are not allowed to take it.*\n"
    "3. Describe which equipment you took and for what time period in the Music Room chat "
    "(or send the information to @unsound\\_mint if you are not in the chat)."
)


def display_value(value: Any) -> str:
    return markdown_display(value)


def build_confirmation_text(data: dict[str, Any], range_summary: str) -> str:
    lines = [
        "🎤 *Equipment request*",
        "",
        f"🏷 *Club:* {display_value(data.get('club_name'))}",
        f"🎫 *Event:* {display_value(data.get('event_name'))}",
        f"📍 *Venue:* {display_value(data.get('venue'))}",
        "⏰ *Requested time ranges:*",
        range_summary,
        "🎛 *Equipment:*",
        f"{display_value(data.get('equipment_text'))}",
        f"📝 *Reason:* {display_value(data.get('reason_text'))}",
        f"💬 *Comments:* {display_value(data.get('comments'))}",
        "",
        "Review carefully — you'll be notified once it's approved.",
    ]
    return "\n".join(lines)


def main_menu_prompt() -> str:
    return "🎤 *Equipment requests*\n\nSubmit a new request or view approved ones."


def approved_requests_hub_text(*, has_requests: bool) -> str:
    if has_requests:
        return "🎤 *Approved equipment requests*\n\nSelect a request to view details, or submit a new one."
    return (
        "🎤 *Approved equipment requests*\n\n"
        "📭 No approved requests yet.\n\n"
        "Tap *Submit new request* to send your equipment request for review."
    )


def range_start_date_text() -> str:
    return "📅 *Pick start date*"


def range_start_hour_text(target_date_iso: str) -> str:
    return f"⏰ *Pick start time*\n\n📅 {target_date_iso}"


def range_end_date_text() -> str:
    return "📅 *Pick end date*"


def range_end_hour_text(target_date_iso: str) -> str:
    return f"⏰ *Pick end time*\n\n📅 {target_date_iso}"


def range_summary_text(range_summary: str) -> str:
    return "⏰ *Requested time ranges:*\n" + range_summary


def edit_ranges_text() -> str:
    return "⏰ *Edit time ranges*\n\nPick new ranges."


def cleared_ranges_text(equipment_prompt: str) -> str:
    return f"{equipment_prompt}\n\n⚠️ Previous time ranges were cleared."
