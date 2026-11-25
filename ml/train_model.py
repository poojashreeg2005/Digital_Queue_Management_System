"""Train and evaluate the QueueFlow synthetic waiting-time model."""

from datetime import datetime, timezone
from pathlib import Path
import json

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.model_selection import train_test_split

from ml.evaluate_model import evaluate_regression
from ml.generate_dataset import (
    FEATURE_COLUMNS,
    RANDOM_SEED,
    TARGET_COLUMN,
    generate_dataset,
)


ML_DIR = Path(__file__).resolve().parent
DATASET_PATH = ML_DIR / "dataset" / "sample_queue_data.csv"
ARTIFACT_PATH = ML_DIR / "artifacts" / "waiting_time_model.joblib"
METADATA_PATH = ML_DIR / "artifacts" / "model_metadata.json"


def train_waiting_time_model(
    dataset_path=None,
    artifact_path=None,
    metadata_path=None,
    seed=RANDOM_SEED,
):
    dataset_path = Path(dataset_path) if dataset_path else DATASET_PATH
    artifact_path = Path(artifact_path) if artifact_path else ARTIFACT_PATH
    metadata_path = Path(metadata_path) if metadata_path else METADATA_PATH

    if not dataset_path.exists():
        generate_dataset(output_path=dataset_path, seed=seed)

    dataframe = pd.read_csv(dataset_path)
    missing = set(FEATURE_COLUMNS + [TARGET_COLUMN]) - set(dataframe.columns)
    if missing:
        raise ValueError(f"Dataset is missing required columns: {sorted(missing)}")
    if TARGET_COLUMN in FEATURE_COLUMNS:
        raise ValueError("Target leakage detected: target appears in feature names.")

    x = dataframe[FEATURE_COLUMNS]
    y = dataframe[TARGET_COLUMN]
    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=0.20,
        random_state=seed,
    )

    categorical_features = [
        "token_priority",
        "department_category",
        "service_category",
        "queue_category",
    ]
    numeric_features = [
        name for name in FEATURE_COLUMNS
        if name not in categorical_features
    ]

    preprocessing = ColumnTransformer(
        transformers=[
            ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical_features),
            ("numeric", "passthrough", numeric_features),
        ]
    )

    model = Pipeline(
        steps=[
            ("preprocessing", preprocessing),
            ("regression", RandomForestRegressor(
                n_estimators=200,
                max_depth=16,
                min_samples_leaf=3,
                random_state=seed,
                n_jobs=-1,
            )),
        ]
    )
    model.fit(x_train, y_train)
    predictions = model.predict(x_test)

    baseline = DummyRegressor(strategy="mean")
    baseline.fit(x_train, y_train)
    baseline_predictions = baseline.predict(x_test)

    model_metrics = evaluate_regression(y_test, predictions)
    baseline_metrics = evaluate_regression(y_test, baseline_predictions)

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, artifact_path)

    metadata = {
        "model_type": "RandomForestRegressor",
        "training_date": datetime.now(timezone.utc).isoformat(),
        "dataset_size": len(dataframe),
        "feature_names": FEATURE_COLUMNS,
        "numeric_features": numeric_features,
        "categorical_features": categorical_features,
        "target_column": TARGET_COLUMN,
        "evaluation_metrics": model_metrics,
        "baseline_metrics": baseline_metrics,
        "dataset_type": "SYNTHETIC DEMONSTRATION DATA",
        "random_seed": seed,
        "artifact_format": "joblib",
        "limitations": (
            "Prototype trained only on transparent synthetic demonstration data. "
            "Metrics are not evidence of real-world QueueFlow accuracy."
        ),
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    print("Prototype QueueFlow Waiting-Time Model")
    print("Dataset type: SYNTHETIC DEMONSTRATION DATA")
    print(f"Dataset size: {len(dataframe)}")
    print(f"Training samples: {len(x_train)}")
    print(f"Test samples: {len(x_test)}")
    print(f"Random Forest MAE: {model_metrics['mae']}")
    print(f"Random Forest RMSE: {model_metrics['rmse']}")
    print(f"Random Forest R-squared: {model_metrics['r2']}")
    print(f"Baseline (mean) MAE: {baseline_metrics['mae']}")
    print(f"Baseline (mean) RMSE: {baseline_metrics['rmse']}")
    print(f"Baseline (mean) R-squared: {baseline_metrics['r2']}")
    print(f"Model artifact: {artifact_path}")
    print(f"Metadata: {metadata_path}")

    return model, metadata


if __name__ == "__main__":
    train_waiting_time_model()
