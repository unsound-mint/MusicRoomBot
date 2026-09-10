from app.bot.constants.dates import WEEKDAYS


def build_numeric_prompt(label: str, current) -> str:
    return f"⚙️ *{label}*\n\n*Current:* {current}\n\nChoose a new value."


def build_chat_id_prompt(label: str, current, *, clear_hint: str) -> str:
    return f"⚙️ *{label}*\n\n*Current:* {current}\n\nSend a new numeric value.{clear_hint}"


def build_working_hours_prompt(weekday_idx: int, start: int, end: int) -> str:
    return (
        f"⚙️ *Working hours — {WEEKDAYS[weekday_idx]}*\n\n"
        f"*Current:* {start:02d}:00 – {end:02d}:00\n\n"
        "Choose a preset or enter a custom range."
    )


def build_working_hours_confirm_text(weekday_idx: int, start: int, end: int) -> str:
    return (
        "⚠️ *Update working hours?*\n\n"
        f"🗓 *Day:* {WEEKDAYS[weekday_idx]}\n"
        f"⏰ *New hours:* {start:02d}:00 – {end:02d}:00"
    )
