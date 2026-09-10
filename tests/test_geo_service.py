from datetime import datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from app.core.config import TIMEZONE
from app.models.booking import Booking
from app.services.geo_service import GeoConfig, normalize_geo_config, process_geo_checks


class GeoServiceTests(TestCase):
    def test_normalize_geo_config_parses_numeric_values(self) -> None:
        self.assertEqual(
            normalize_geo_config("51.1", "71.2", "80"),
            GeoConfig(center_lat=51.1, center_lon=71.2, radius=80.0),
        )

    def test_normalize_geo_config_defaults_invalid_center_together(self) -> None:
        self.assertEqual(
            normalize_geo_config("bad", "71.2", "80"),
            GeoConfig(center_lat=0.0, center_lon=0.0, radius=80.0),
        )

    def test_normalize_geo_config_defaults_invalid_radius(self) -> None:
        self.assertEqual(
            normalize_geo_config("51.1", "71.2", None),
            GeoConfig(center_lat=51.1, center_lon=71.2, radius=50.0),
        )


class GeoPromptTests(IsolatedAsyncioTestCase):
    async def test_geo_prompt_uses_location_request_keyboard(self) -> None:
        query_result = SimpleNamespace(
            all=lambda: [(7, 3, 10, "Student", None)],
        )
        read_session = AsyncMock()
        read_session.execute.return_value = query_result
        read_cm = AsyncMock()
        read_cm.__aenter__.return_value = read_session
        read_cm.__aexit__.return_value = False

        write_session = AsyncMock()
        write_cm = AsyncMock()
        write_cm.__aenter__.return_value = write_session
        write_cm.__aexit__.return_value = False

        bot = AsyncMock()

        with (
            patch("app.services.geo_service.AsyncSessionLocal", side_effect=[read_cm, write_cm]),
            patch(
                "app.services.geo_service.now_tz",
                return_value=datetime(2026, 5, 19, 14, 0, tzinfo=ZoneInfo(TIMEZONE)),
            ),
            patch("app.services.geo_service.get_runtime_config", new=AsyncMock(return_value="120")),
            patch("app.services.geo_service.is_first_in_chain", new=AsyncMock(return_value=True)),
        ):
            await process_geo_checks(bot)

        bot.send_message.assert_awaited_once()
        reply_markup = bot.send_message.await_args.kwargs["reply_markup"]
        button = reply_markup.keyboard[0][0]
        self.assertEqual(button.text, "📍 Send Location")
        self.assertTrue(button.request_location)
        write_session.commit.assert_awaited_once()

    async def test_geo_expiry_query_excludes_already_verified_bookings(self) -> None:
        read_session = AsyncMock()
        read_session.execute.return_value = SimpleNamespace(all=lambda: [])
        read_cm = AsyncMock()
        read_cm.__aenter__.return_value = read_session
        read_cm.__aexit__.return_value = False

        bot = AsyncMock()

        with (
            patch("app.services.geo_service.AsyncSessionLocal", return_value=read_cm),
            patch(
                "app.services.geo_service.now_tz",
                return_value=datetime(2026, 5, 19, 14, 11, tzinfo=ZoneInfo(TIMEZONE)),
            ),
            patch("app.services.geo_service.get_runtime_config", new=AsyncMock(return_value="10")),
        ):
            await process_geo_checks(bot)

        expiry_stmt = read_session.execute.await_args_list[-1].args[0]
        where_criteria = expiry_stmt.whereclause
        self.assertIn(str(Booking.attendance_verified == False), str(where_criteria))  # noqa: E712
