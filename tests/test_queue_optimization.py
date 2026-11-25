import unittest
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from queue_optimization import (
    calculate_counter_workloads,
    recommend_counter,
    schedule_tokens,
)


class QueueOptimizationTests(unittest.TestCase):
    def setUp(self):
        self.visit_date = date(2026, 11, 18)
        self.now = datetime(2026, 11, 18, 12, 0)
        self.counters = [
            SimpleNamespace(id=1, department_id=10, name="Counter A", active=True),
            SimpleNamespace(id=2, department_id=10, name="Counter B", active=True),
            SimpleNamespace(id=3, department_id=20, name="Other Dept", active=True),
            SimpleNamespace(id=4, department_id=10, name="Inactive", active=False),
        ]
        self.minutes = {101: 10, 102: 20}

    def token(self, token_id, counter_id=None, service_id=101, status="approved",
              priority="normal", priority_verified=True, created_at=None,
              called_at=None, visit_date=None):
        return SimpleNamespace(
            id=token_id,
            counter_id=counter_id,
            service_id=service_id,
            status=status,
            priority=priority,
            priority_verified=priority_verified,
            created_at=created_at or self.now,
            called_at=called_at,
            visit_date=visit_date or self.visit_date,
        )

    def test_recommend_least_workloaded_counter(self):
        tokens = [
            self.token(1, 1, 102),
            self.token(2, 1, 102),
            self.token(3, 2, 101),
        ]
        result = recommend_counter(
            self.counters, tokens, 10, self.minutes,
            self.visit_date, now=self.now,
        )
        self.assertEqual(result.id, 2)

    def test_no_inactive_or_other_department_recommendation(self):
        self.assertIsNone(recommend_counter(
            [self.counters[3]], [], 10, self.minutes,
            self.visit_date,
        ))
        self.assertIsNone(recommend_counter(
            self.counters, [], 30, self.minutes,
            self.visit_date,
        ))

    def test_called_remaining_and_excluded_statuses(self):
        called = self.token(
            1, 1, status="called",
            called_at=self.now - timedelta(minutes=4),
        )
        ignored = [
            self.token(i, 1, status=status)
            for i, status in enumerate(
                ("pending", "completed", "declined", "missed"), start=2
            )
        ]
        workloads = calculate_counter_workloads(
            self.counters, [called] + ignored, self.minutes,
            self.visit_date, now=self.now,
        )
        by_id = {item["counter_id"]: item for item in workloads}
        self.assertEqual(by_id[1]["workload_minutes"], 6)
        self.assertEqual(by_id[1]["in_service_count"], 1)

    def test_priority_fifo_and_aging(self):
        urgent = self.token(
            1, 1, priority="urgent", priority_verified=True,
            created_at=self.now,
        )
        aged_normal = self.token(
            2, 1, created_at=self.now - timedelta(minutes=60),
        )
        unverified = self.token(
            3, 1, priority="emergency", priority_verified=False,
            created_at=self.now,
        )
        ordered = schedule_tokens(
            [urgent, aged_normal, unverified],
            now=self.now,
            aging_minutes=30,
        )
        self.assertEqual([item.id for item in ordered], [2, 1, 3])

    def test_invalid_aging_interval(self):
        with self.assertRaises(ValueError):
            schedule_tokens([], now=self.now, aging_minutes=0)


if __name__ == "__main__":
    unittest.main()
