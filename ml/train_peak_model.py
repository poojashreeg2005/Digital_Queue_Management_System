from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = ROOT / "data" / "simulated_peak_data.csv"
DEFAULT_MODEL = ROOT / "models" / "peak_model.joblib"
DEFAULT_METADATA = ROOT / "models" / "peak_model_metadata.json"


def train_peak_model(
    dataset_path: str | Path = DEFAULT_DATASET,
    model_path: str | Path = DEFAULT_MODEL,
    metadata_path: str | Path = DEFAULT_METADATA,
) -> dict:
    dataset_path = Path(dataset_path)
    model_path = Path(model_path)
    metadata_path = Path(metadata_path)

    if not dataset_path.exists():
        raise FileNotFoundError(
            f"Simulated peak dataset not found at {dataset_path}"
        )

    frame = pd.read_csv(dataset_path)
    required = {
        "day_of_week",
        "time_slot",
        "department",
        "previous_queue_workload",
        "active_counters",
        "tokens_booked",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(
            f"Dataset is missing required columns: {sorted(missing)}"
        )

    features = [
        "day_of_week",
        "time_slot",
        "department",
        "previous_queue_workload",
        "active_counters",
    ]
    x = frame[features]
    y = frame["tokens_booked"]

    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=0.20,
        random_state=42,
    )

    preprocessing = ColumnTransformer([
        (
            "category",
            OneHotEncoder(handle_unknown="ignore"),
            ["day_of_week", "time_slot", "department"],
        ),
        ("numeric", "passthrough", [
            "previous_queue_workload",
            "active_counters",
        ]),
    ])
    model = Pipeline([
        ("preprocessing", preprocessing),
        (
            "regressor",
            RandomForestRegressor(
                n_estimators=180,
                random_state=42,
                min_samples_leaf=2,
                n_jobs=-1,
            ),
        ),
    ])
    model.fit(x_train, y_train)
    predictions = model.predict(x_test)

    metrics = {
        "mae": round(float(mean_absolute_error(y_test, predictions)), 3),
        "rmse": round(
            float(mean_squared_error(y_test, predictions) ** 0.5),
            3,
        ),
        "r2": round(float(r2_score(y_test, predictions)), 3),
        "training_rows": int(len(x_train)),
        "test_rows": int(len(x_test)),
        "is_simulated": True,
        "model": "RandomForestRegressor",
        "features": features,
    }

    model_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_path)
    metadata_path.write_text(
        json.dumps(metrics, indent=2),
        encoding="utf-8",
    )
    return metrics


def main() -> None:
    metrics = train_peak_model()
    print("Trained on SIMULATED peak-hour data.")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
