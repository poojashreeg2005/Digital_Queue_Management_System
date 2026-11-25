
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "development-secret-key")

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    ML_WAITING_TIME_ENABLED = os.getenv(
        "ML_WAITING_TIME_ENABLED",
        "true"
    ).lower() in ("1", "true", "yes", "on")
