import asyncio
import os
from datetime import date
from unittest import IsolatedAsyncioTestCase, skipUnless
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import admin as _admin  # noqa: F401
from app.models import booking as _booking  # noqa: F401
from app.models import club as _club  # noqa: F401
from app.models import config_model as _config_model  # noqa: F401
from app.models import equipment_request as _equipment_request  # noqa: F401
from app.models import equipment_request_range as _equipment_request_range  # noqa: F401
from app.models import gift_offer as _gift_offer  # noqa: F401
from app.models import swap_offer as _swap_offer  # noqa: F401
from app.models import user as _user  # noqa: F401
from app.models import weekly_slot as _weekly_slot  # noqa: F401
from app.models.booking import Booking
from app.models.user import User
from app.services.booking_service import safe_create_booking

POSTGRES_TEST_DATABASE_URL = os.environ.get("MUSICROOM_POSTGRES_TEST_DATABASE_URL")


@skipUnless(
    POSTGRES_TEST_DATABASE_URL,
    "set MUSICROOM_POSTGRES_TEST_DATABASE_URL to run Postgres concurrency tests",
)
class BookingConcurrencyPostgresTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        assert POSTGRES_TEST_DATABASE_URL is not None
        self.schema = f"musicroom_test_{uuid4().hex}"
        self.engine = create_async_engine(
            POSTGRES_TEST_DATABASE_URL,
            connect_args={"server_settings": {"search_path": self.schema}},
        )
        async with self.engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{self.schema}"'))
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(
                    sync_conn.execution_options(
                        schema_translate_map={None: self.schema}
                    )
                )
            )

        self.sessionmaker = async_sessionmaker(
            self.engine.execution_options(
                schema_translate_map={None: self.schema},
            ),
            expire_on_commit=False,
        )

    async def asyncTearDown(self) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE'))
        await self.engine.dispose()

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
