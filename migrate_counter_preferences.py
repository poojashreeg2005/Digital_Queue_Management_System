"""Add configurable priority preferences to existing counters."""

from sqlalchemy import inspect, text

from app import app
from models import db


def run_migration():
    with app.app_context():
        inspector = inspect(db.engine)
        if "counters" not in inspector.get_table_names():
            raise RuntimeError(
                "The counters table does not exist; initialize the database first."
            )

        column_names = {
            column["name"]
            for column in inspector.get_columns("counters")
        }
        if "preferred_priorities" in column_names:
            print("Counter priority preferences column already exists.")
            return

        with db.engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE counters "
                "ADD COLUMN preferred_priorities JSON NULL"
            ))
        print("Added counters.preferred_priorities.")


if __name__ == "__main__":
    run_migration()
