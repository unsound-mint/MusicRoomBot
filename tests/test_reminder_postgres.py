from datetime import date, datetime
from unittest import skipUnless
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy import select

from app.models.booking import Booking
from app.models.user import User
from app.services.geo_service import process_geo_checks
from app.services.reminder_service import process_reminders
from tests.postgres_support import POSTGRES_TEST_DATABASE_URL, PostgresSchemaTestCase

TZ = ZoneInfo("Asia/Almaty")
DAY = date(2026, 5, 19)


def at(hour: int, minute: int) -> datetime:
    return datetime(2026, 5, 19, hour, minute, tzinfo=TZ)


@skipUnless(
    POSTGRES_TEST_DATABASE_URL,
    "set MUSICROOM_POSTGRES_TEST_DATABASE_URL to run Postgres tests",
)
class ReminderMarkerPostgresTests(PostgresSchemaTestCase):
    async def _seed(self, hours: list[int]) -> list[int]:
        async with self.sessionmaker() as db:
            user = User(tg_user_id=555, tg_username="u", full_name="U", allowed=True)
            db.add(user)
            await db.flush()
            bookings = [Booking(user_id=user.id, date=DAY, hour=h) for h in hours]
            db.add_all(bookings)
            await db.commit()
            return [b.id for b in bookings]

    async def _booking(self, booking_id: int) -> Booking:
        async with self.sessionmaker() as db:
            return (
                await db.execute(select(Booking).where(Booking.id == booking_id))
            ).scalar_one()

    async def _tick(self, bot: AsyncMock, now: datetime, reminder_hours: str = "2") -> None:
        with (
            patch("app.services.reminder_service.AsyncSessionLocal", self.sessionmaker),
            patch("app.services.reminder_service.now_tz", return_value=now),
            patch(
                "app.services.reminder_service.get_runtime_config",
                new=AsyncMock(return_value=reminder_hours),
            ),
        ):
            await process_reminders(bot)

    async def test_fifteen_minute_reminder_is_sent_once_across_ticks(self) -> None:
        (booking_id,) = await self._seed([18])
        bot = AsyncMock()

        await self._tick(bot, at(17, 45))
        await self._tick(bot, at(17, 45))
        await self._tick(bot, at(17, 46))

        bot.send_message.assert_awaited_once()
        booking = await self._booking(booking_id)
        self.assertIsNotNone(booking.reminded_15_at)
        self.assertIsNone(booking.reminded_hourly_at)

    async def test_missed_minute_45_tick_is_caught_up_before_start(self) -> None:
        await self._seed([18])
        bot = AsyncMock()

        await self._tick(bot, at(17, 52))
        self.assertEqual(bot.send_message.await_count, 1)

        late_bot = AsyncMock()
        await self._tick(late_bot, at(18, 0))
        late_bot.send_message.assert_not_awaited()

    async def test_hourly_reminder_uses_window_and_marker(self) -> None:
        (booking_id,) = await self._seed([18])
        bot = AsyncMock()

        await self._tick(bot, at(15, 59), reminder_hours="2")
        bot.send_message.assert_not_awaited()

        await self._tick(bot, at(16, 4), reminder_hours="2")
        await self._tick(bot, at(16, 5), reminder_hours="2")

        bot.send_message.assert_awaited_once()
        booking = await self._booking(booking_id)
        self.assertIsNotNone(booking.reminded_hourly_at)
        self.assertIsNone(booking.reminded_15_at)

    async def test_chain_is_reminded_once_via_its_first_booking(self) -> None:
        first_id, second_id = await self._seed([18, 19])
        bot = AsyncMock()

        await self._tick(bot, at(17, 45))
        await self._tick(bot, at(18, 45))

        self.assertEqual(bot.send_message.await_count, 1)
        self.assertIsNotNone((await self._booking(first_id)).reminded_15_at)
        self.assertIsNone((await self._booking(second_id)).reminded_15_at)

    async def test_transient_failure_is_retried_permanent_is_not(self) -> None:
        (booking_id,) = await self._seed([18])

        flaky = AsyncMock()
        flaky.send_message.side_effect = RuntimeError("network")
        with self.assertLogs("app.services.reminder_service", level="ERROR"):
            await self._tick(flaky, at(17, 45))
        self.assertIsNone((await self._booking(booking_id)).reminded_15_at)

        blocked = AsyncMock()
        blocked.send_message.side_effect = TelegramForbiddenError(
            method=MagicMock(), message="Forbidden: bot was blocked by the user"
        )
        with self.assertLogs("app.services.reminder_service", level="WARNING"):
            await self._tick(blocked, at(17, 46))
        self.assertIsNotNone((await self._booking(booking_id)).reminded_15_at)

        again = AsyncMock()
        await self._tick(again, at(17, 47))
        again.send_message.assert_not_awaited()


@skipUnless(
    POSTGRES_TEST_DATABASE_URL,
    "set MUSICROOM_POSTGRES_TEST_DATABASE_URL to run Postgres tests",
)
class GeoPromptCatchUpPostgresTests(PostgresSchemaTestCase):
    async def _tick(self, bot: AsyncMock, now: datetime) -> None:
        with (
            patch("app.services.geo_service.AsyncSessionLocal", self.sessionmaker),
            patch("app.services.geo_service.now_tz", return_value=now),
            patch(
                "app.services.geo_service.get_runtime_config",
                new=AsyncMock(return_value="10"),
            ),
        ):
            await process_geo_checks(bot)

    async def test_missed_hour_tick_is_prompted_once_inside_window(self) -> None:
        async with self.sessionmaker() as db:
            user = User(tg_user_id=777, tg_username="g", full_name="G", allowed=True)
            db.add(user)
            await db.flush()
            db.add(Booking(user_id=user.id, date=DAY, hour=14))
            await db.commit()

        bot = AsyncMock()
        await self._tick(bot, at(14, 3))
        await self._tick(bot, at(14, 4))
        self.assertEqual(bot.send_message.await_count, 1)

        async with self.sessionmaker() as db:
            prompted = (await db.execute(select(Booking.location_prompted))).scalar_one()
        self.assertTrue(prompted)

    async def test_no_prompt_after_check_in_window_closed(self) -> None:
        async with self.sessionmaker() as db:
            user = User(tg_user_id=778, tg_username="h", full_name="H", allowed=True)
            db.add(user)
            await db.flush()
            db.add(Booking(user_id=user.id, date=DAY, hour=14))
            await db.commit()

        bot = AsyncMock()
        await self._tick(bot, at(14, 10))
        bot.send_message.assert_not_awaited()
