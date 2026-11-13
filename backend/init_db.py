"""Create the QueueFlow AI schema and insert missing sample departments/services."""

from config import Config
from database import ensure_database_exists, get_db_connection


TABLES = (
    """
    CREATE TABLE IF NOT EXISTS users (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        full_name VARCHAR(120) NOT NULL,
        email VARCHAR(254) NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        role ENUM('Admin', 'Staff', 'Student') NOT NULL DEFAULT 'Student',
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            ON UPDATE CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uq_users_email (email)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS departments (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        name VARCHAR(100) NOT NULL,
        description VARCHAR(500) NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uq_departments_name (name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS services (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        department_id BIGINT UNSIGNED NOT NULL,
        name VARCHAR(120) NOT NULL,
        description VARCHAR(500) NULL,
        estimated_duration_minutes SMALLINT UNSIGNED NOT NULL DEFAULT 10,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uq_services_department_name (department_id, name),
        KEY ix_services_active_department (is_active, department_id),
        CONSTRAINT fk_services_department
            FOREIGN KEY (department_id) REFERENCES departments (id)
            ON UPDATE CASCADE ON DELETE RESTRICT,
        CONSTRAINT chk_services_estimated_duration
            CHECK (estimated_duration_minutes > 0)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS counters (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        department_id BIGINT UNSIGNED NOT NULL,
        counter_name VARCHAR(80) NOT NULL,
        location VARCHAR(160) NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uq_counters_department_name (department_id, counter_name),
        KEY ix_counters_active_department (is_active, department_id),
        CONSTRAINT fk_counters_department
            FOREIGN KEY (department_id) REFERENCES departments (id)
            ON UPDATE CASCADE ON DELETE RESTRICT
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS tokens (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        service_id BIGINT UNSIGNED NOT NULL,
        user_id BIGINT UNSIGNED NULL,
        queue_date DATE NOT NULL,
        queue_number INT UNSIGNED NOT NULL,
        token_code VARCHAR(32) NOT NULL,
        status ENUM(
            'Waiting', 'Called', 'Serving', 'Completed', 'Skipped', 'Cancelled'
        ) NOT NULL DEFAULT 'Waiting',
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        called_at TIMESTAMP NULL,
        service_started_at TIMESTAMP NULL,
        completed_at TIMESTAMP NULL,
        PRIMARY KEY (id),
        UNIQUE KEY uq_tokens_code (token_code),
        UNIQUE KEY uq_tokens_service_queue_number
            (service_id, queue_date, queue_number),
        KEY ix_tokens_service_date_status (service_id, queue_date, status),
        KEY ix_tokens_user_created (user_id, created_at),
        CONSTRAINT fk_tokens_service
            FOREIGN KEY (service_id) REFERENCES services (id)
            ON UPDATE CASCADE ON DELETE RESTRICT,
        CONSTRAINT fk_tokens_user
            FOREIGN KEY (user_id) REFERENCES users (id)
            ON UPDATE CASCADE ON DELETE SET NULL,
        CONSTRAINT chk_tokens_queue_number CHECK (queue_number > 0)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS queue_records (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        token_id BIGINT UNSIGNED NOT NULL,
        counter_id BIGINT UNSIGNED NULL,
        changed_by_user_id BIGINT UNSIGNED NULL,
        event_type ENUM(
            'Waiting', 'Called', 'Serving', 'Completed', 'Skipped', 'Cancelled'
        ) NOT NULL,
        event_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        notes VARCHAR(500) NULL,
        PRIMARY KEY (id),
        KEY ix_queue_records_token_event (token_id, event_at),
        KEY ix_queue_records_counter_event (counter_id, event_at),
        CONSTRAINT fk_queue_records_token
            FOREIGN KEY (token_id) REFERENCES tokens (id)
            ON UPDATE CASCADE ON DELETE RESTRICT,
        CONSTRAINT fk_queue_records_counter
            FOREIGN KEY (counter_id) REFERENCES counters (id)
            ON UPDATE CASCADE ON DELETE SET NULL,
        CONSTRAINT fk_queue_records_user
            FOREIGN KEY (changed_by_user_id) REFERENCES users (id)
            ON UPDATE CASCADE ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS service_history (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        token_id BIGINT UNSIGNED NOT NULL,
        service_id BIGINT UNSIGNED NOT NULL,
        counter_id BIGINT UNSIGNED NOT NULL,
        staff_user_id BIGINT UNSIGNED NULL,
        started_at TIMESTAMP NOT NULL,
        completed_at TIMESTAMP NOT NULL,
        duration_seconds INT UNSIGNED NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (id),
        UNIQUE KEY uq_service_history_token (token_id),
        KEY ix_service_history_service_completed (service_id, completed_at),
        KEY ix_service_history_counter_completed (counter_id, completed_at),
        CONSTRAINT fk_service_history_token
            FOREIGN KEY (token_id) REFERENCES tokens (id)
            ON UPDATE CASCADE ON DELETE RESTRICT,
        CONSTRAINT fk_service_history_service
            FOREIGN KEY (service_id) REFERENCES services (id)
            ON UPDATE CASCADE ON DELETE RESTRICT,
        CONSTRAINT fk_service_history_counter
            FOREIGN KEY (counter_id) REFERENCES counters (id)
            ON UPDATE CASCADE ON DELETE RESTRICT,
        CONSTRAINT fk_service_history_staff
            FOREIGN KEY (staff_user_id) REFERENCES users (id)
            ON UPDATE CASCADE ON DELETE SET NULL,
        CONSTRAINT chk_service_history_time_order
            CHECK (completed_at >= started_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
)


DEPARTMENTS = (
    ("Examination", "Examinations, results, transcripts, and academic records."),
    ("Accounts", "Student fees, statements, and refunds."),
    ("Admission", "Applications, document verification, and enrollment."),
    ("Student Support", "Student services, identification, and general assistance."),
)


SERVICES = (
    ("Examination", "Transcript Request", "Request an official academic transcript.", 15),
    ("Examination", "Exam Registration", "Assistance with examination registration.", 10),
    ("Examination", "Results and Records", "Questions about examination results or records.", 10),
    ("Accounts", "Fee Payment", "Pay or confirm student fees.", 8),
    ("Accounts", "Fee Statement", "Request a student fee statement.", 8),
    ("Accounts", "Refund Request", "Submit or check a fee refund request.", 15),
    ("Admission", "Application Inquiry", "Get help with an admission application.", 10),
    ("Admission", "Document Verification", "Verify admission and enrollment documents.", 15),
    ("Admission", "Enrollment", "Complete admission enrollment steps.", 20),
    ("Student Support", "ID Card Request", "Request or replace a student ID card.", 10),
    ("Student Support", "General Inquiry", "Get help with a student support inquiry.", 10),
    ("Student Support", "Letter or Certificate Request", "Request an official student letter or certificate.", 12),
)


COUNTERS = (
    ("Examination", "Counter 1 - Transcripts & Records", "Building A, Room 101"),
    ("Examination", "Counter 2 - Exam Inquiries", "Building A, Room 102"),
    ("Accounts", "Counter 1 - Fee Payments", "Finance Wing, Window 1"),
    ("Accounts", "Counter 2 - Statements & Refunds", "Finance Wing, Window 2"),
    ("Admission", "Counter 1 - Verification", "Admissions Hall, Desk A"),
    ("Admission", "Counter 2 - Enrollment", "Admissions Hall, Desk B"),
    ("Student Support", "Counter 1 - General Help & ID Cards", "Student Center, Desk 1"),
    ("Student Support", "Counter 2 - Letters & Certificates", "Student Center, Desk 2"),
)


def seed_departments(cursor):
    cursor.executemany(
        """
        INSERT INTO departments (name, description)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE id = id
        """,
        DEPARTMENTS,
    )
    department_ids = {}
    for name, _ in DEPARTMENTS:
        cursor.execute("SELECT id FROM departments WHERE name = %s", (name,))
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError(f"Could not find department after seeding: {name}")
        department_ids[name] = row[0]
    return department_ids


def seed_services(cursor, department_ids):
    cursor.executemany(
        """
        INSERT INTO services (
            department_id, name, description, estimated_duration_minutes
        )
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE id = id
        """,
        [
            (department_ids[department], name, description, duration)
            for department, name, description, duration in SERVICES
        ],
    )


def seed_counters(cursor, department_ids):
    cursor.executemany(
        """
        INSERT INTO counters (
            department_id, counter_name, location
        )
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE id = id
        """,
        [
            (department_ids[department], counter_name, location)
            for department, counter_name, location in COUNTERS
        ],
    )


def initialize_database():
    ensure_database_exists()
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        try:
            for statement in TABLES:
                cursor.execute(statement)
            department_ids = seed_departments(cursor)
            seed_services(cursor, department_ids)
            seed_counters(cursor, department_ids)
            connection.commit()
        finally:
            cursor.close()
    finally:
        connection.close()


if __name__ == "__main__":
    initialize_database()
    print(
        f"Database '{Config.MYSQL_DATABASE}' is initialized. "
        f"Verified {len(DEPARTMENTS)} sample departments, {len(SERVICES)} sample services, and {len(COUNTERS)} sample counters."
    )
