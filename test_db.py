
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


def check_database_connection():
    # Load settings from .env
    load_dotenv()

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL not found in .env")

    try:
        engine = create_engine(database_url)

        with engine.connect() as connection:
            result = connection.execute(
                text("SELECT DATABASE(), VERSION()")
            )

            database, version = result.fetchone()

            print("MySQL connected successfully!")
            print("Database name:", database)
            print("MySQL version:", version)

    except Exception as error:
        print("Database connection failed!")
        print(error)


if __name__ == "__main__":
    if os.getenv("QUEUEFLOW_ALLOW_MYSQL_DIAGNOSTIC") != "1":
        raise SystemExit(
            "MySQL diagnostic is disabled by default. Set "
            "QUEUEFLOW_ALLOW_MYSQL_DIAGNOSTIC=1 to run it explicitly."
        )
    check_database_connection()
