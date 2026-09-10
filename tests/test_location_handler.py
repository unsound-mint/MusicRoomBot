from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

from app.bot.handlers.location import handle_location, location_permission_error
from app.core.config import TIMEZONE
from app.services.geo_service import GeoConfig
from app.services.time_service import now_tz


class LocationHandlerTests(IsolatedAsyncioTestCase):
    async def test_location_without_accuracy_can_confirm_check_in(self) -> None:
        now = now_tz()
        message = SimpleNamespace(
            location=SimpleNamespace(
                latitude=0.0,
                longitude=0.0,
                horizontal_accuracy=None,
            ),
            from_user=SimpleNamespace(id=10),
            answer=AsyncMock(),
        )
        user = SimpleNamespace(id=20)
        booking = SimpleNamespace(
            id=30,
            user_id=user.id,
            date=now.date(),
            hour=now.astimezone(ZoneInfo(TIMEZONE)).hour,
            absence_reported=False,
            attendance_verified=False,
        )
        session = AsyncMock()
        session.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=user))
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = session
        session_cm.__aexit__.return_value = False
        menu = SimpleNamespace(keyboard=[])

        with (
            patch("app.bot.handlers.location.AsyncSessionLocal", return_value=session_cm),
            patch("app.bot.handlers.location.is_admin", new=AsyncMock(return_value=False)),
            patch(
                "app.bot.handlers.location.get_geo_config",
                new=AsyncMock(return_value=GeoConfig(0.0, 0.0, 50.0)),
            ),
            patch("app.bot.handlers.location.get_runtime_config", new=AsyncMock(return_value="60")),
            patch("app.bot.handlers.location.get_current_booking", new=AsyncMock(return_value=booking)),
            patch("app.bot.handlers.location.get_main_menu_kb", new=AsyncMock(return_value=menu)),
            patch("app.bot.handlers.location.mark_attendance_chain_verified", new=AsyncMock()) as mark_attendance,
        ):
            await handle_location(message)

        mark_attendance.assert_awaited_once()
        session.commit.assert_not_awaited()
        self.assertIn("✅ *Check-in confirmed*", message.answer.await_args.args[0])
        self.assertIs(message.answer.await_args.kwargs["reply_markup"], menu)

    async def test_location_at_deadline_is_closed(self) -> None:
        now = now_tz()
        message = SimpleNamespace(
            location=SimpleNamespace(latitude=0.0, longitude=0.0),
            from_user=SimpleNamespace(id=10),
            answer=AsyncMock(),
        )
        user = SimpleNamespace(id=20)
        booking = SimpleNamespace(
            id=30,
            user_id=user.id,
            date=now.date(),
            hour=now.astimezone(ZoneInfo(TIMEZONE)).hour,
            absence_reported=False,
            attendance_verified=False,
        )
        session = AsyncMock()
        session.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=user))
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = session
        session_cm.__aexit__.return_value = False
        menu = SimpleNamespace(keyboard=[])

        with (
            patch("app.bot.handlers.location.AsyncSessionLocal", return_value=session_cm),
            patch("app.bot.handlers.location.is_admin", new=AsyncMock(return_value=False)),
            patch(
                "app.bot.handlers.location.get_geo_config",
                new=AsyncMock(return_value=GeoConfig(0.0, 0.0, 50.0)),
            ),
            patch("app.bot.handlers.location.get_runtime_config", new=AsyncMock(return_value="0")),
            patch("app.bot.handlers.location.get_current_booking", new=AsyncMock(return_value=booking)),
            patch("app.bot.handlers.location.get_main_menu_kb", new=AsyncMock(return_value=menu)),
            patch("app.bot.handlers.location.record_absence", new=AsyncMock()) as record_absence,
            patch("app.bot.handlers.location.add_warning", new=AsyncMock()) as add_warning,
            patch("app.bot.handlers.location.mark_attendance_chain_verified", new=AsyncMock()) as mark_attendance,
        ):
            await handle_location(message)

        record_absence.assert_awaited_once_with(session, booking.id, user.id)
        add_warning.assert_awaited_once()
        mark_attendance.assert_not_awaited()
        self.assertIn("Check-in closed", message.answer.await_args.args[0])

    async def test_permission_error_restores_main_menu(self) -> None:
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=10),
            answer=AsyncMock(),
        )
        session = AsyncMock()
        session.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=None))
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = session
        session_cm.__aexit__.return_value = False
        menu = SimpleNamespace(keyboard=[])

        with (
            patch("app.bot.handlers.location.AsyncSessionLocal", return_value=session_cm),
            patch("app.bot.handlers.location.get_main_menu_kb", new=AsyncMock(return_value=menu)),
        ):
            await location_permission_error(message)

        message.answer.assert_awaited_once()
        self.assertIs(message.answer.await_args.kwargs["reply_markup"], menu)
        self.assertEqual(message.answer.await_args.kwargs["parse_mode"], "Markdown")
