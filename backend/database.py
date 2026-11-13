import mysql.connector

from config import Config


def ensure_database_exists():
    """Create the configured database if needed, using server-level credentials."""
    server = mysql.connector.connect(**Config.server_connection_options())
    try:
        cursor = server.cursor()
        try:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{Config.MYSQL_DATABASE}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        finally:
            cursor.close()
    finally:
        server.close()


def get_db_connection():
    """Open a connection to the configured application database."""
    return mysql.connector.connect(
        **Config.server_connection_options(),
        database=Config.MYSQL_DATABASE,
    )
