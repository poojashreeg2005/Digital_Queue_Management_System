from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
DATASET_PATH = ROOT / "data" / "simulated_peak_data.csv"
MODEL_PATH = ROOT / "models" / "peak_model.joblib"
METADATA_PATH = ROOT / "models" / "peak_model_metadata.json"


def load_model(model_path: str | Path = MODEL_PATH):
    model_path = Path(model_path)
    if not model_path.exists():
        raise FileNotFoundError(
            f"Trained peak-hour model not found at {model_path}"
        )
    return joblib.load(model_path)


def get_model_metrics(metadata_path: str | Path = METADATA_PATH) -> dict:
    metadata_path = Path(metadata_path)
    if not metadata_path.exists():
        return {}
    with metadata_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def demand_level(expected_bookings: float) -> str:
    if expected_bookings >= 28:
        return "high"
    if expected_bookings >= 18:
        return "medium"
    return "low"


def recommendation(
    level: str,
    expected_bookings: float,
    active_counters: int,
) -> str:
    if level == "high":
        additional = max(1, int(np.ceil(expected_bookings / 18)) - active_counters)
        if additional > 0:
            return (
                f"Prepare for high demand: open approximately "
                f"{additional} additional counter(s)."
            )
        return "Prepare for high demand and increase staff availability."
    if level == "medium":
        return "Maintain normal counter staffing and monitor queue workload."
    return "Reduce unnecessary counter allocation and retain baseline coverage."


def predict_department(
    department: str,
    forecast_days: int = 7,
    dataset_path: str | Path = DATASET_PATH,
    model_path: str | Path = MODEL_PATH,
) -> list[dict]:
    model = load_model(model_path)
    frame = pd.read_csv(dataset_path)
    department_history = frame[
        frame["department"].astype(str) == department
    ].copy()
    if department_history.empty:
        return []

    department_history["date"] = pd.to_datetime(
        department_history["date"]
    ).dt.date
    latest_date = department_history["date"].max()
    latest_rows = department_history[
        department_history["date"] == latest_date
    ]

    slot_history = {
        row["time_slot"]: float(row["previous_queue_workload"])
        for _, row in latest_rows.iterrows()
    }
    predictions = []

    for day_offset in range(forecast_days):
        forecast_date = date.today() + timedelta(days=day_offset)
        day_name = forecast_date.strftime("%A")

        for time_slot in sorted(department_history["time_slot"].unique()):
            prior_workload = slot_history.get(time_slot, 18.0)
            input_row = pd.DataFrame([{
                "day_of_week": day_name,
                "time_slot": time_slot,
                "department": department,
                "previous_queue_workload": prior_workload,
                "active_counters": (
                    1 if prior_workload < 18
                    else 2 if prior_workload < 32
                    else 3
                ),
            }])
            expected = max(
                0.0,
                float(model.predict(input_row)[0]),
            )
            level = demand_level(expected)
            active_counters = (
                1 if expected < 18
                else 2 if expected < 28
                else 3
            )
            predictions.append({
                "department": department,
                "forecast_date": forecast_date.isoformat(),
                "time_slot": time_slot,
                "expected_bookings": round(expected, 1),
                "demand_level": level,
                "recommended_counters": active_counters,
                "recommendation": recommendation(
                    level,
                    expected,
                    active_counters,
                ),
            })

    return predictions
