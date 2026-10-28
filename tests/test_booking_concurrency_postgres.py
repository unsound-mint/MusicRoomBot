import asyncio
from datetime import date
from unittest import skipUnless
from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select

from app.models.booking import Booking
from app.models.user import User
from app.services.booking_service import safe_create_booking
from tests.postgres_support import POSTGRES_TEST_DATABASE_URL, PostgresSchemaTestCase


@skipUnless(
    POSTGRES_TEST_DATABASE_URL,
    "set MUSICROOM_POSTGRES_TEST_DATABASE_URL to run Postgres concurrency tests",
)
class BookingConcurrencyPostgresTests(PostgresSchemaTestCase):
    async def test_weekly_limit_is_enforced_under_concurrent_creates(self) -> None:
        async with self.sessionmaker() as db:
            user = User(
                tg_user_id=1001,
                tg_username="concurrent",
                full_name="Concurrent User",
                allowed=True,
            )
            db.add(user)
            await db.commit()
            user_id = user.id

        async def attempt(hour: int) -> str:
            async with self.sessionmaker() as db:
                status, _ = await safe_create_booking(
                    db,
                    user_id=user_id,
                    b_date=date(2026, 3, 24),
                    b_hour=hour,
                )
                return status

        with patch(
            "app.services.booking_service._weekly_limit_value",
            new=AsyncMock(return_value=1),
        ):
            statuses = await asyncio.gather(attempt(18), attempt(19))

        self.assertCountEqual(statuses, ["success", "limit"])

        async with self.sessionmaker() as db:
            count = (
                await db.execute(
                    select(func.count(Booking.id)).where(Booking.user_id == user_id)
                )
            ).scalar_one()

        self.assertEqual(count, 1)

    async def test_same_slot_is_booked_once_under_concurrent_creates(self) -> None:
        async with self.sessionmaker() as db:
            users = [
                User(
                    tg_user_id=2000 + i,
                    tg_username=f"racer{i}",
                    full_name=f"Racer {i}",
                    allowed=True,
                )
                for i in range(5)
            ]
            db.add_all(users)
            await db.commit()
            user_ids = [u.id for u in users]

        async def attempt(user_id: int) -> str:
            async with self.sessionmaker() as db:
                status, _ = await safe_create_booking(
                    db,
                    user_id=user_id,
                    b_date=date(2026, 3, 24),
                    b_hour=18,
                )
                return status

        with patch(
            "app.services.booking_service._weekly_limit_value",
            new=AsyncMock(return_value=5),
        ):
            statuses = await asyncio.gather(*(attempt(uid) for uid in user_ids))

        self.assertEqual(sorted(statuses), ["success"] + ["taken"] * 4)

        async with self.sessionmaker() as db:
            count = (
                await db.execute(
                    select(func.count(Booking.id)).where(
                        Booking.date == date(2026, 3, 24),
                        Booking.hour == 18,
                    )
                )
            ).scalar_one()

        self.assertEqual(count, 1)
