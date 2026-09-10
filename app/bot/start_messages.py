def build_new_user_start_text() -> str:
    return (
        "🎵 *Music Room*\n\n"
        "Practice room booking for approved members.\n\n"
        "*How to get access*\n"
        "1️⃣ Fill out the access form\n"
        "2️⃣ Wait for approval\n"
        "3️⃣ Book your first slot\n\n"
        "Tap below to begin."
    )


def build_pending_access_start_text() -> str:
    return (
        "🎵 *Music Room*\n\n"
        "🟡 *Access pending*\n\n"
        "Fill out the access form if you haven't already.\n"
        "You'll get a message here once your access is approved.\n\n"
        "Tap below to open the form."
    )


def build_approved_start_text(summary: str, *, is_admin_user: bool = False) -> str:
    admin_line = "\n\n🛠 *Admin mode enabled*" if is_admin_user else ""
    return (
        f"{summary}"
        f"{admin_line}\n\n"
        "Use the menu below to book a slot, check your bookings, view the schedule, "
        "or read the room rules."
    )
