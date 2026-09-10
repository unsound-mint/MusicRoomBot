from unittest import TestCase

from app.bot.start_messages import (
    build_approved_start_text,
    build_new_user_start_text,
    build_pending_access_start_text,
)


class StartHandlerTextTests(TestCase):
    def test_new_user_start_text_explains_access_flow(self) -> None:
        text = build_new_user_start_text()

        self.assertIn("🎵 *Music Room*", text)
        self.assertIn("Practice room booking for approved members.", text)
        self.assertIn("1️⃣ Fill out the access form", text)
        self.assertIn("Tap below to begin.", text)

    def test_pending_access_start_text_has_status_and_form_prompt(self) -> None:
        text = build_pending_access_start_text()

        self.assertIn("🟡 *Access pending*", text)
        self.assertIn("You'll get a message here once your access is approved.", text)
        self.assertIn("Tap below to open the form.", text)

    def test_approved_start_text_adds_menu_guidance(self) -> None:
        text = build_approved_start_text("🎵 *Music Room*\n\n📅 *Bookings:* 0 / 3")

        self.assertIn("🎵 *Music Room*", text)
        self.assertIn("Use the menu below to book a slot", text)
        self.assertNotIn("Admin mode enabled", text)

    def test_approved_start_text_mentions_admin_mode_for_admins(self) -> None:
        text = build_approved_start_text(
            "🎵 *Music Room*\n\n📅 *Bookings:* 0 / 3",
            is_admin_user=True,
        )

        self.assertIn("🛠 *Admin mode enabled*", text)
