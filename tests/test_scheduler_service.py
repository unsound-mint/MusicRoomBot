from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core import metrics
from app.services import scheduler_service


class _ScalarResult:
    def __init__(self, value: bool) -> None:
        self.value = value

    def scalar(self) -> bool:
        return self.value


class _AsyncSessionContext:
    def __init__(self, session: AsyncMock) -> None:
        self.session = session

    async def __aenter__(self) -> AsyncMock:
        return self.session

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class SchedulerServiceTests(IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        scheduler_service.shutdown_scheduler(wait=False)
        metrics.reset()

    async def test_setup_scheduler_called_twice_keeps_single_job_per_id(self) -> None:
        test_scheduler = AsyncIOScheduler(timezone=scheduler_service.scheduler.timezone)
        original_start = test_scheduler.start

        def start_once(*args, **kwargs):
            if not test_scheduler.running:
                return original_start(*args, **kwargs)
            return None

        with patch.object(scheduler_service, "scheduler", test_scheduler):
            with patch.object(test_scheduler, "start", Mock(side_effect=start_once)) as start:
                scheduler_service.setup_scheduler(bot=object())
                scheduler_service.setup_scheduler(bot=object())

            jobs = scheduler_service.get_scheduler_jobs()
            scheduler_service.shutdown_scheduler(wait=False)

        job_ids = [job["id"] for job in jobs]
        self.assertCountEqual(
            job_ids,
            ["weekly_reset", "reminders", "geo_checks", "expired_bans"],
        )
        self.assertEqual(len(job_ids), len(set(job_ids)))
        self.assertEqual(start.call_count, 1)

    async def test_reminder_job_runs_when_advisory_lock_acquired(self) -> None:
        session = AsyncMock()
        session.execute.side_effect = [_ScalarResult(True), _ScalarResult(True)]
        bot = object()

        with (
            patch.object(
                scheduler_service,
                "AsyncSessionLocal",
                Mock(return_value=_AsyncSessionContext(session)),
            ),
            patch.object(
                scheduler_service,
                "process_reminders",
                new=AsyncMock(),
            ) as process_reminders,
        ):
            await scheduler_service.reminder_job(bot)

        process_reminders.assert_awaited_once_with(bot)
        self.assertEqual(session.execute.await_count, 2)
        self.assertIn("pg_try_advisory_lock", str(session.execute.await_args_list[0].args[0]))
        self.assertIn("pg_advisory_unlock", str(session.execute.await_args_list[1].args[0]))
        counters = metrics.snapshot()["counters"]
        self.assertTrue(
            any(
                sample.name == "scheduler_job_total"
                and sample.labels == {"job": "reminders", "status": "success"}
                for sample in counters
            ),
            counters,
        )

    async def test_reminder_job_skips_when_advisory_lock_not_acquired(self) -> None:
        session = AsyncMock()
        session.execute.return_value = _ScalarResult(False)
        bot = object()

        with (
            patch.object(
                scheduler_service,
                "AsyncSessionLocal",
                Mock(return_value=_AsyncSessionContext(session)),
            ),
            patch.object(
                scheduler_service,
                "process_reminders",
                new=AsyncMock(),
            ) as process_reminders,
        ):
            await scheduler_service.reminder_job(bot)

        process_reminders.assert_not_awaited()
        session.execute.assert_awaited_once()
        counters = metrics.snapshot()["counters"]
        self.assertTrue(
            any(
                sample.name == "scheduler_job_total"
                and sample.labels == {"job": "reminders", "status": "skipped_lock"}
                for sample in counters
            ),
            counters,
        )

    async def test_reminder_job_releases_advisory_lock_on_failure(self) -> None:
        session = AsyncMock()
        session.execute.side_effect = [_ScalarResult(True), _ScalarResult(True)]
        bot = object()

        with (
            patch.object(
                scheduler_service,
                "AsyncSessionLocal",
                Mock(return_value=_AsyncSessionContext(session)),
            ),
            patch.object(
                scheduler_service,
                "process_reminders",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ),
            self.assertLogs(scheduler_service.log, level="ERROR") as logs,
            self.assertRaises(RuntimeError),
        ):
            await scheduler_service.reminder_job(bot)

        self.assertEqual(session.execute.await_count, 2)
        self.assertIn("pg_advisory_unlock", str(session.execute.await_args_list[1].args[0]))
        self.assertTrue(
            any("Reminder job failed" in message for message in logs.output),
            logs.output,
        )
