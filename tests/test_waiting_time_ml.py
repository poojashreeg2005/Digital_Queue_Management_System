import tempfile
import unittest
from pathlib import Path

import joblib

from ml.generate_dataset import (
    FEATURE_COLUMNS,
    RANDOM_SEED,
    TARGET_COLUMN,
    generate_dataset,
)
from ml.train_model import train_waiting_time_model
from services import waiting_time


class WaitingTimeMlTests(unittest.TestCase):
    def test_synthetic_dataset_shape_and_no_leakage(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.csv"
            _path, dataframe = generate_dataset(path, rows=300, seed=RANDOM_SEED)
            self.assertEqual(len(dataframe), 300)
            self.assertTrue(set(FEATURE_COLUMNS).issubset(dataframe.columns))
            self.assertIn(TARGET_COLUMN, dataframe.columns)
            self.assertNotIn(TARGET_COLUMN, FEATURE_COLUMNS)

    def test_training_saves_loadable_model_and_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            dataset_path = directory / "dataset.csv"
            artifact_path = directory / "waiting_time_model.joblib"
            metadata_path = directory / "model_metadata.json"
            generate_dataset(dataset_path, rows=300, seed=RANDOM_SEED)

            _model, metadata = train_waiting_time_model(
                dataset_path=dataset_path,
                artifact_path=artifact_path,
                metadata_path=metadata_path,
            )
            self.assertTrue(artifact_path.exists())
            self.assertTrue(metadata_path.exists())
            loaded = joblib.load(artifact_path)
            self.assertIsNotNone(loaded)
            self.assertIn("mae", metadata["evaluation_metrics"])
            self.assertEqual(
                metadata["dataset_type"],
                "SYNTHETIC DEMONSTRATION DATA",
            )

    def test_prediction_is_non_negative_and_compatible(self):
        prediction = waiting_time.predict_ml_waiting_time(
            department_id=1,
            counter_id=2,
            queue_position=5,
            priority="urgent",
            average_service_minutes=15,
            active_counters=2,
            estimated_workload_ahead=60,
            queue_category="student",
            service_category="Fee Payment Assistance",
            ml_enabled=False,
        )
        self.assertIn(prediction["model_source"], (
            "HEURISTIC_FALLBACK (ML disabled)",
            "HEURISTIC_FALLBACK (model unavailable)",
            "ML_MODEL",
        ))
        self.assertGreaterEqual(prediction["estimated_minutes"], 0)

    def test_missing_model_uses_heuristic_fallback(self):
        old_path = waiting_time.ML_ARTIFACT_PATH
        old_loaded = waiting_time._ML_MODEL_LOADED
        old_model = waiting_time._ML_MODEL
        old_error = waiting_time._ML_MODEL_ERROR
        try:
            waiting_time.ML_ARTIFACT_PATH = Path(tempfile.gettempdir()) / "missing-queueflow-model.joblib"
            waiting_time._ML_MODEL_LOADED = False
            waiting_time._ML_MODEL = None
            waiting_time._ML_MODEL_ERROR = None
            result = waiting_time.predict_ml_waiting_time(
                department_id=1,
                counter_id=1,
                queue_position=4,
                ml_enabled=True,
            )
            self.assertIn("HEURISTIC_FALLBACK", result["model_source"])
            self.assertGreaterEqual(result["estimated_minutes"], 0)
        finally:
            waiting_time.ML_ARTIFACT_PATH = old_path
            waiting_time._ML_MODEL_LOADED = old_loaded
            waiting_time._ML_MODEL = old_model
            waiting_time._ML_MODEL_ERROR = old_error

    def test_ml_disable_and_student_visitor_categories_are_preserved(self):
        student = waiting_time.predict_ml_waiting_time(
            1, 2, 3, queue_category="student", ml_enabled=False,
        )
        visitor = waiting_time.predict_ml_waiting_time(
            1, 2, 3, queue_category="visitor", ml_enabled=False,
        )
        self.assertIn("ML disabled", student["model_source"])
        self.assertIn("ML disabled", visitor["model_source"])
        self.assertGreaterEqual(student["estimated_minutes"], 0)
        self.assertGreaterEqual(visitor["estimated_minutes"], 0)


if __name__ == "__main__":
    unittest.main()
