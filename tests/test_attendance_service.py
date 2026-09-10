from datetime import date, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from app.core.config import TIMEZONE
from app.services.attendance_service import get_current_booking, record_attendance


class _Result:
    def __init__(self, rows) -> None:
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one(self):
        return self._rows[0]


class AttendanceServiceTests(IsolatedAsyncioTestCase):
    async def test_get_current_booking_prefers_latest_active_slot(self) -> None:
        now = datetime(2026, 5, 19, 10, 5, tzinfo=ZoneInfo(TIMEZONE))
        old_booking = SimpleNamespace(date=now.date(), hour=9)
        current_booking = SimpleNamespace(date=now.date(), hour=10)
        db = AsyncMock()
        db.execute.return_value = _Result([old_booking, current_booking])

        with (
            patch("app.services.attendance_service.now_tz", return_value=now),
            patch("app.services.attendance_service.get_runtime_config", new=AsyncMock(return_value=120)),
        ):
            result = await get_current_booking(db, user_id=7)

        self.assertIs(result, current_booking)

    async def test_record_attendance_can_store_prevalidated_check_in(self) -> None:
        booking = SimpleNamespace(
            id=1,
            user_id=7,
            date=date(2026, 5, 19),
            hour=10,
            attendance_verified=False,
            attendance_lat=None,
            attendance_lon=None,
            attendance_recorded_at=None,
            absence_reported=False,
            location_prompted=False,
        )
        db = AsyncMock()
        db.execute.return_value = _Result([booking])

        with patch(
            "app.services.attendance_service.get_runtime_config",
            new=AsyncMock(return_value=1),
        ):
            await record_attendance(
                db,
                booking_id=1,
                user_id=7,
                lat=51.0,
                lon=71.0,
                distance=25.0,
                verified=True,
            )

        self.assertTrue(booking.attendance_verified)
