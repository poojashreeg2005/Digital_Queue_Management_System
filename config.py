
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "development-secret-key")

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    PEAK_FORECAST_DAYS = int(os.getenv("PEAK_FORECAST_DAYS", "7"))
    PEAK_MODEL_PATH = os.getenv(
        "PEAK_MODEL_PATH",
        os.path.join(os.path.dirname(__file__), "ml", "models", "peak_model.joblib")
    )
    PEAK_DATASET_PATH = os.getenv(
        "PEAK_DATASET_PATH",
        os.path.join(os.path.dirname(__file__), "ml", "data", "simulated_peak_data.csv")
    )
