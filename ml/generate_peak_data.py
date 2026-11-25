from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_TIME_SLOTS = [
    "08:00-09:00",
    "09:00-10:00",
    "10:00-11:00",
    "11:00-12:00",
    "12:00-13:00",
    "13:00-14:00",
    "14:00-15:00",
    "15:00-16:00",
    "16:00-17:00",
]


def generate_peak_data(
    department_names: list[str],
    output_path: str | Path,
    weeks: int = 16,
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start_date = date.today() - timedelta(weeks=weeks)
    records = []
    department_size = {
        department: rng.uniform(0.75, 1.35)
        for department in department_names
    }

    for department in department_names:
        previous_slot_values: dict[str, float] = {
            slot: 18.0 for slot in DEFAULT_TIME_SLOTS
        }
        for day_offset in range(weeks * 7):
            current_date = start_date + timedelta(days=day_offset)
            if current_date.weekday() >= 5:
                day_factor = 0.55
            else:
                day_factor = 1.0

            for slot_index, slot in enumerate(DEFAULT_TIME_SLOTS):
                hour_factor = (
                    1.25 if slot_index in (2, 3, 6)
                    else 0.75 if slot_index in (0, 8)
                    else 1.0
                )
                base = 18.0 * department_size[department] * day_factor * hour_factor
                noise = rng.normal(0, 3.2)
                bookings = max(2, int(round(base + noise)))
                completed = int(round(bookings * rng.uniform(0.72, 0.90)))
                cancelled = int(round(bookings * rng.uniform(0.03, 0.10)))
                missed = max(0, bookings - completed - cancelled)
                avg_service_minutes = round(float(rng.uniform(12, 28)), 1)
                active_counters = int(
                    1
                    if bookings < 18
                    else 2
                    if bookings < 32
                    else 3
                )
                queue_workload = int(
                    round(bookings * rng.uniform(0.65, 1.15))
                )
                previous_queue_workload = int(
                    round(previous_slot_values[slot] * rng.uniform(0.85, 1.15))
                )

                records.append({
                    "date": current_date.isoformat(),
                    "day_of_week": current_date.strftime("%A"),
                    "time_slot": slot,
                    "department": department,
                    "tokens_booked": bookings,
                    "completed_tokens": completed,
                    "cancelled_tokens": cancelled,
                    "missed_tokens": missed,
                    "average_service_duration": avg_service_minutes,
                    "active_counters": active_counters,
                    "queue_workload": queue_workload,
                    "previous_queue_workload": previous_queue_workload,
                })
                previous_slot_values[slot] = queue_workload

    frame = pd.DataFrame(records)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate clearly labeled simulated queue activity data."
    )
    parser.add_argument(
        "--departments",
        nargs="+",
        default=[
            "Student Administration",
            "Technical Support",
            "Library Services",
        ],
    )
    parser.add_argument(
        "--output",
        default=str(
            Path(__file__).resolve().parent
            / "data"
            / "simulated_peak_data.csv"
        ),
    )
    parser.add_argument("--weeks", type=int, default=16)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    frame = generate_peak_data(
        args.departments,
        args.output,
        args.weeks,
        args.seed,
    )
    print(
        f"Generated {len(frame)} SIMULATED records at "
        f"{Path(args.output).resolve()}"
    )


if __name__ == "__main__":
    main()
