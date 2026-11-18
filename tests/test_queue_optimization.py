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

    def token(
        self,
        token_id,
        counter_id,
        service_id=101,
        status="approved",
        priority="normal",
        priority_verified=True,
        created_at=None,
        called_at=None,
        visit_date=None,
    ):
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

    def test_recommends_least_workloaded_compatible_counter(self):
        existing = [
            self.token(1, 1, service_id=102),
            self.token(2, 1, service_id=102),
            self.token(3, 2, service_id=101),
            self.token(4, 4, service_id=101),
        ]

        recommendation = recommend_counter(
            self.counters,
            existing,
            department_id=10,
            service_minutes_by_id=self.minutes,
            visit_date=self.visit_date,
            now=self.now,
        )

        self.assertEqual(recommendation.id, 2)

    def test_assignment_reduces_simulated_workload_imbalance(self):
        existing = [
            self.token(1, 1, service_id=102),
            self.token(2, 1, service_id=102),
            self.token(3, 2, service_id=101),
        ]
        before = calculate_counter_workloads(
            self.counters,
            existing,
            self.minutes,
            self.visit_date,
            now=self.now,
        )
        recommendation = recommend_counter(
            self.counters,
            existing,
            department_id=10,
            service_minutes_by_id=self.minutes,
            visit_date=self.visit_date,
            now=self.now,
        )
        existing.append(self.token(4, recommendation.id, service_id=101))
        after = calculate_counter_workloads(
            self.counters,
            existing,
            self.minutes,
            self.visit_date,
            now=self.now,
        )

        before_loads = [
            item["workload_minutes"] for item in before if item["counter"].active
            and item["counter"].department_id == 10
        ]
        after_loads = [
            item["workload_minutes"] for item in after if item["counter"].active
            and item["counter"].department_id == 10
        ]
        self.assertEqual(before_loads, [40, 10])
        self.assertEqual(after_loads, [40, 20])
        self.assertEqual(max(before_loads) - min(before_loads), 30)
        self.assertEqual(max(after_loads) - min(after_loads), 20)

    def test_no_active_compatible_counter_returns_none(self):
        recommendation = recommend_counter(
            self.counters,
            [],
            department_id=30,
            service_minutes_by_id=self.minutes,
            visit_date=self.visit_date,
        )

        self.assertIsNone(recommendation)

    def test_inactive_counter_is_not_recommended(self):
        recommendation = recommend_counter(
            [self.counters[3]],
            [],
            department_id=10,
            service_minutes_by_id=self.minutes,
            visit_date=self.visit_date,
        )

        self.assertIsNone(recommendation)

    def test_workload_uses_only_active_queue_and_estimates_called_remaining(self):
        called = self.token(
            1,
            1,
            status="called",
            called_at=self.now - timedelta(minutes=4),
        )
        excluded_statuses = [
            "pending", "completed", "declined", "missed"
        ]
        ignored = [
            self.token(index + 2, 1, status=status)
            for index, status in enumerate(excluded_statuses)
        ]
        other_date = self.token(
            8,
            1,
            visit_date=self.visit_date + timedelta(days=1),
        )

        workloads = calculate_counter_workloads(
            self.counters,
            [called] + ignored + [other_date],
            self.minutes,
            self.visit_date,
            now=self.now,
        )
        by_id = {item["counter_id"]: item for item in workloads}

        self.assertEqual(by_id[1]["waiting_count"], 0)
        self.assertEqual(by_id[1]["in_service_count"], 1)
        self.assertEqual(by_id[1]["workload_minutes"], 6)

    def test_missing_or_nonpositive_service_estimate_uses_default(self):
        unknown_estimate = self.token(1, 1, service_id=999)

        workloads = calculate_counter_workloads(
            self.counters,
            [unknown_estimate],
            {999: 0},
            self.visit_date,
            now=self.now,
        )
        by_id = {item["counter_id"]: item for item in workloads}

        self.assertEqual(by_id[1]["workload_minutes"], 15)

    def test_admin_load_labels_identify_overloaded_and_underused_counters(self):
        workloads = calculate_counter_workloads(
            self.counters,
            [
                self.token(1, 1, service_id=102),
                self.token(2, 1, service_id=102),
            ],
            self.minutes,
            self.visit_date,
            now=self.now,
        )
        by_id = {item["counter_id"]: item for item in workloads}

        self.assertEqual(by_id[1]["allocation_status"], "overloaded")
        self.assertEqual(by_id[2]["allocation_status"], "underused")

    def test_reassignment_and_completion_remove_old_counter_workload(self):
        token = self.token(1, 1, service_id=102)
        before = calculate_counter_workloads(
            self.counters, [token], self.minutes, self.visit_date, self.now
        )
        token.counter_id = 2
        after_reassignment = calculate_counter_workloads(
            self.counters, [token], self.minutes, self.visit_date, self.now
        )
        token.status = "completed"
        after_completion = calculate_counter_workloads(
            self.counters, [token], self.minutes, self.visit_date, self.now
        )

        before_by_id = {item["counter_id"]: item for item in before}
        moved_by_id = {item["counter_id"]: item for item in after_reassignment}
        completed_by_id = {item["counter_id"]: item for item in after_completion}
        self.assertEqual(before_by_id[1]["workload_minutes"], 20)
        self.assertEqual(moved_by_id[1]["workload_minutes"], 0)
        self.assertEqual(moved_by_id[2]["workload_minutes"], 20)
        self.assertEqual(completed_by_id[2]["workload_minutes"], 0)

    def test_priority_and_fifo_ordering(self):
        first_normal = self.token(
            1, 1, created_at=self.now - timedelta(minutes=2)
        )
        second_normal = self.token(
            2, 1, created_at=self.now - timedelta(minutes=1)
        )
        verified_urgent = self.token(
            3,
            1,
            priority="urgent",
            priority_verified=True,
            created_at=self.now,
        )
        unverified_emergency = self.token(
            4,
            1,
            priority="emergency",
            priority_verified=False,
            created_at=self.now + timedelta(seconds=1),
        )

        ordered = schedule_tokens(
            [second_normal, unverified_emergency, first_normal, verified_urgent],
            now=self.now,
        )

        self.assertEqual([token.id for token in ordered], [3, 1, 2, 4])

    def test_waiting_time_aging_prevents_normal_token_starvation(self):
        aged_normal = self.token(
            1,
            1,
            created_at=self.now - timedelta(minutes=60),
        )
        newer_urgent = self.token(
            2,
            1,
            priority="urgent",
            priority_verified=True,
            created_at=self.now - timedelta(minutes=20),
        )

        ordered = schedule_tokens(
            [newer_urgent, aged_normal],
            now=self.now,
            aging_minutes=30,
        )

        self.assertEqual([token.id for token in ordered], [1, 2])

    def test_invalid_aging_interval_is_rejected(self):
        with self.assertRaises(ValueError):
            schedule_tokens([], now=self.now, aging_minutes=0)


if __name__ == "__main__":
    unittest.main()
