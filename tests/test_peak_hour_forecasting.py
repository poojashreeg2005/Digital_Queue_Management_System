from __future__ import annotations

import csv
from pathlib import Path

from ml.generate_peak_data import generate_peak_data
from ml.peak_hour_forecasting import demand_level, predict_department
from ml.train_peak_model import train_peak_model


def test_simulated_dataset_generation(tmp_path: Path):
    output = tmp_path / "peak.csv"
    frame = generate_peak_data(
        ["Student Administration", "Library Services"],
        output,
        weeks=4,
        seed=7,
    )

    assert len(frame) == 4 * 7 * 9 * 2
    assert set(frame["department"]) == {
        "Student Administration",
        "Library Services",
    }
    assert set(frame["time_slot"]).issubset({
        "08:00-09:00",
        "09:00-10:00",
        "10:00-11:00",
        "11:00-12:00",
        "12:00-13:00",
        "13:00-14:00",
        "14:00-15:00",
        "15:00-16:00",
        "16:00-17:00",
    })
    assert (frame["tokens_booked"] >= 0).all()
    assert output.exists()


def test_model_training_and_prediction(tmp_path: Path):
    dataset = tmp_path / "peak.csv"
    generate_peak_data(
        ["Student Administration", "Technical Support"],
        dataset,
        weeks=8,
        seed=11,
    )
    model = tmp_path / "peak.joblib"
    metadata = tmp_path / "peak_metadata.json"

    metrics = train_peak_model(dataset, model, metadata)

    assert metrics["training_rows"] > 0
    assert metrics["test_rows"] > 0
    assert metrics["training_rows"] + metrics["test_rows"] == 8 * 7 * 9 * 2
    assert all(
        metrics[name] == metrics[name]
        for name in ("mae", "rmse", "r2")
    )

    predictions = predict_department(
        "Student Administration",
        forecast_days=2,
        dataset_path=dataset,
        model_path=model,
    )
    assert len(predictions) == 18
    assert {item["demand_level"] for item in predictions}.issubset(
        {"low", "medium", "high"}
    )
    assert all(item["expected_bookings"] >= 0 for item in predictions)
    assert all(
        item["recommended_counters"] >= 1
        for item in predictions
    )


def test_demand_levels():
    assert demand_level(10) == "low"
    assert demand_level(20) == "medium"
    assert demand_level(35) == "high"
