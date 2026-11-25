import os

os.environ["DATABASE_URL"] = "sqlite://"

from app import app
from models import db


with app.app_context():
    test_database_url = db.engine.url
    if test_database_url.drivername != "sqlite" or test_database_url.database:
        raise RuntimeError(
            "Tests require an isolated in-memory SQLite database."
        )
