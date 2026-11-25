"""Generate a reproducible synthetic queue waiting-time dataset."""

from pathlib import Path
import argparse
import random

import numpy as np
import pandas as pd


RANDOM_SEED = 2026
DEFAULT_ROWS = 5000
TARGET_COLUMN = "waiting_time_minutes"

FEATURE_COLUMNS = [
    "queue_length_ahead",
    "active_counters",
    "estimated_workload_ahead",
    "token_priority",
    "department_category",
    "service_category",
    "hour_of_arrival",
    "day_of_week",
    "queue_category",
]


def generate_synthetic_dataset(rows=DEFAULT_ROWS, seed=RANDOM_SEED):
    rng = np.random.default_rng(seed)
    python_rng = random.Random(seed)

    priorities = ["normal", "accessibility", "urgent", "emergency"]
    departments = [
        "student_administration",
        "technical_support",
        "library_services",
    ]
    service_types = [
        "certificate_or_id",
        "fee_assistance",
        "network_support",
        "computer_lab",
        "book_issue",
        "account_assistance",
    ]

    records = []
    for _ in range(rows):
        queue_category = python_rng.choice(["student", "visitor"])
        queue_length = int(rng.integers(0, 31))
        active_counters = int(rng.integers(1, 5))
        department = python_rng.choice(departments)
        service_category = python_rng.choice(service_types)
        priority = python_rng.choices(
            priorities,
            weights=[0.70, 0.12, 0.13, 0.05],
            k=1,
        )[0]
        hour = int(rng.integers(8, 18))
        day_of_week = int(rng.integers(0, 7))

        service_base = {
            "certificate_or_id": 16,
            "fee_assistance": 14,
            "network_support": 20,
            "computer_lab": 28,
            "book_issue": 10,
            "account_assistance": 15,
        }[service_category]
        counter_speed_factor = 1.0 + (5 - active_counters) * 0.10
        estimated_workload = int(
            queue_length * service_base * counter_speed_factor
        )

        priority_factor = {
            "normal": 1.0,
            "accessibility": 0.72,
            "urgent": 0.58,
            "emergency": 0.42,
        }[priority]

        peak_hour_factor = 1.20 if hour in (10, 11, 12, 13) else 1.0
        weekend_factor = 1.12 if day_of_week >= 5 else 1.0
        visitor_factor = 1.08 if queue_category == "visitor" else 1.0

        waiting = (
            queue_length
            * service_base
            / max(active_counters, 1)
            * priority_factor
            * peak_hour_factor
            * weekend_factor
            * visitor_factor
        )
        waiting += float(rng.normal(0, 4.0))
        waiting = max(0.0, waiting)

        records.append(
            {
                "queue_length_ahead": queue_length,
                "active_counters": active_counters,
                "estimated_workload_ahead": estimated_workload,
                "token_priority": priority,
                "department_category": department,
                "service_category": service_category,
                "hour_of_arrival": hour,
                "day_of_week": day_of_week,
                "queue_category": queue_category,
                TARGET_COLUMN: round(waiting, 2),
            }
        )

    return pd.DataFrame(records)


def generate_dataset(output_path=None, rows=DEFAULT_ROWS, seed=RANDOM_SEED):
    output_path = Path(output_path) if output_path else (
        Path(__file__).resolve().parent / "dataset" / "sample_queue_data.csv"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe = generate_synthetic_dataset(rows=rows, seed=seed)
    dataframe.to_csv(output_path, index=False)
    return output_path, dataframe


def main():
    parser = argparse.ArgumentParser(
        description="Generate reproducible synthetic QueueFlow training data."
    )
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS)
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    output_path, dataframe = generate_dataset(args.output, args.rows, args.seed)
    print(f"Generated {len(dataframe)} synthetic demonstration records.")
    print(f"Dataset saved to: {output_path}")
    print("Dataset type: SYNTHETIC DEMONSTRATION DATA")


if __name__ == "__main__":
    main()
