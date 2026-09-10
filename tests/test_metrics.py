from unittest import TestCase

from app.core import metrics


class MetricsTests(TestCase):
    def tearDown(self) -> None:
        metrics.reset()

    def test_counter_snapshot_includes_labels(self) -> None:
        metrics.increment(
            "booking_create_total",
            labels={"source": "manual", "status": "success"},
        )
        metrics.increment(
            "booking_create_total",
            labels={"source": "manual", "status": "success"},
        )

        snapshot = metrics.snapshot()

        self.assertEqual(len(snapshot["counters"]), 1)
        sample = snapshot["counters"][0]
        self.assertEqual(sample.name, "booking_create_total")
        self.assertEqual(sample.value, 2)
        self.assertEqual(sample.labels, {"source": "manual", "status": "success"})

    def test_timing_snapshot_records_count_total_and_max(self) -> None:
        metrics.observe_seconds("scheduler_job_seconds", 0.5, labels={"job": "geo"})
        metrics.observe_seconds("scheduler_job_seconds", 0.25, labels={"job": "geo"})

        snapshot = metrics.snapshot()

        self.assertEqual(len(snapshot["timings"]), 1)
        sample = snapshot["timings"][0]
        self.assertEqual(sample.name, "scheduler_job_seconds")
        self.assertEqual(sample.count, 2)
        self.assertEqual(sample.total_seconds, 0.75)
        self.assertEqual(sample.max_seconds, 0.5)
        self.assertEqual(sample.labels, {"job": "geo"})
