import os
import re
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).with_name(".env"), override=False)


class Config:
    MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1").strip()
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER = os.getenv("MYSQL_USER", "").strip()
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "digital_queue").strip()

    @classmethod
    def validate(cls):
        if not cls.MYSQL_HOST:
            raise ValueError("MYSQL_HOST must not be empty.")
        if not 1 <= cls.MYSQL_PORT <= 65535:
            raise ValueError("MYSQL_PORT must be between 1 and 65535.")
        if not cls.MYSQL_USER:
            raise ValueError("Set MYSQL_USER in backend/.env before connecting to MySQL.")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", cls.MYSQL_DATABASE):
            raise ValueError("MYSQL_DATABASE must contain only letters, numbers, and underscores.")

    @classmethod
    def server_connection_options(cls):
        cls.validate()
        return {
            "host": cls.MYSQL_HOST,
            "port": cls.MYSQL_PORT,
            "user": cls.MYSQL_USER,
            "password": cls.MYSQL_PASSWORD,
        }
