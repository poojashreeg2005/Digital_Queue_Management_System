import base64
import io
import re
import secrets

import mysql.connector
from flask import Flask, jsonify, request
from flask_cors import CORS
from qrcode import ERROR_CORRECT_M, QRCode
from werkzeug.security import generate_password_hash

from database import get_db_connection


app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})


def _success(data, status_code=200):
    return jsonify({"success": True, "data": data}), status_code


def _error(code, message, status_code):
    return jsonify(
        {
            "success": False,
            "error": {"code": code, "message": message},
        }
    ), status_code


def _fetch_all(query, parameters=()):
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(query, parameters)
            return cursor.fetchall()
        finally:
            cursor.close()
    finally:
        connection.close()


def _json_body():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None
    return body


def _positive_id(value):
    max_id = 18446744073709551615
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 0 < value <= max_id else None
    if isinstance(value, str) and value.isdecimal():
        parsed = int(value)
        return parsed if 0 < parsed <= max_id else None
    return None


def _make_qr_code(token_code):
    qr = QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=8,
        border=4,
    )
    qr.add_data('{"token_code":"' + token_code + '"}')
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    image_buffer = io.BytesIO()
    image.save(image_buffer, format="PNG")
    return base64.b64encode(image_buffer.getvalue()).decode("ascii")


@app.get("/api/health")
def health():
    try:
        rows = _fetch_all("SELECT 1 AS database_available")
    except mysql.connector.Error:
        app.logger.error("Health check failed because the database is unavailable.")
        return _error(
            "database_unavailable",
            "The database is currently unavailable.",
            503,
        )

    return _success({"status": "ok", "database": rows[0]["database_available"] == 1})


@app.get("/api/departments")
def get_departments():
    try:
        departments = _fetch_all(
            """
            SELECT id, name, description, is_active
            FROM departments
            ORDER BY name
            """
        )
    except mysql.connector.Error:
        app.logger.error("Could not retrieve departments because of a database error.")
        return _error(
            "database_error",
            "Departments could not be retrieved right now.",
            500,
        )

    return _success(departments)


@app.get("/api/services")
def get_services():
    department_id = request.args.get("department_id")
    if department_id is not None:
        try:
            department_id = int(department_id)
        except ValueError:
            return _error(
                "invalid_department_id",
                "department_id must be a positive integer.",
                400,
            )
        if department_id < 1:
            return _error(
                "invalid_department_id",
                "department_id must be a positive integer.",
                400,
            )

    query = """
        SELECT id, department_id, name, description,
               estimated_duration_minutes, is_active
        FROM services
        WHERE is_active = TRUE
    """
    parameters = ()
    if department_id is not None:
        query += " AND department_id = %s"
        parameters = (department_id,)
    query += " ORDER BY department_id, name"

    try:
        services = _fetch_all(query, parameters)
    except mysql.connector.Error:
        app.logger.error("Could not retrieve services because of a database error.")
        return _error(
            "database_error",
            "Services could not be retrieved right now.",
            500,
        )

    return _success(services)


@app.get("/api/counters")
@app.get("/api/admin/counters")
def get_counters():
    department_id = request.args.get("department_id")
    if department_id is not None:
        try:
            department_id = int(department_id)
        except ValueError:
            return _error(
                "invalid_department_id",
                "department_id must be a positive integer.",
                400,
            )
        if department_id < 1:
            return _error(
                "invalid_department_id",
                "department_id must be a positive integer.",
                400,
            )

    query = """
        SELECT c.id, c.department_id, c.counter_name, c.location,
               c.is_active, d.name AS department_name
        FROM counters AS c
        JOIN departments AS d ON d.id = c.department_id
        WHERE c.is_active = TRUE
    """
    parameters = ()
    if department_id is not None:
        query += " AND c.department_id = %s"
        parameters = (department_id,)
    query += " ORDER BY c.department_id, c.counter_name"

    try:
        counters = _fetch_all(query, parameters)
    except mysql.connector.Error:
        app.logger.error("Could not retrieve counters because of a database error.")
        return _error(
            "database_error",
            "Counters could not be retrieved right now.",
            500,
        )

    return _success(counters)


@app.post("/api/users")
def register_user():
    body = _json_body()
    if body is None:
        return _error("invalid_json", "A JSON object is required.", 400)

    full_name = body.get("full_name")
    email = body.get("email")
    password = body.get("password")
    if not isinstance(full_name, str) or not full_name.strip():
        return _error("invalid_full_name", "full_name is required.", 400)
    if len(full_name.strip()) > 120:
        return _error("invalid_full_name", "full_name must be at most 120 characters.", 400)
    if not isinstance(email, str):
        return _error("invalid_email", "A valid email address is required.", 400)
    email = email.strip().lower()
    if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return _error("invalid_email", "A valid email address is required.", 400)
    if not isinstance(password, str) or not 8 <= len(password) <= 128:
        return _error(
            "invalid_password",
            "password must be between 8 and 128 characters.",
            400,
        )

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO users (full_name, email, password_hash)
            VALUES (%s, %s, %s)
            """,
            (full_name.strip(), email, generate_password_hash(password)),
        )
        user_id = cursor.lastrowid
        connection.commit()
    except mysql.connector.IntegrityError as error:
        if connection is not None:
            connection.rollback()
        if error.errno == 1062:
            return _error("email_already_registered", "This email is already registered.", 409)
        app.logger.error("Student registration failed due to a database constraint.")
        return _error("database_error", "Registration could not be completed right now.", 500)
    except mysql.connector.Error:
        if connection is not None:
            connection.rollback()
        app.logger.error("Student registration failed because of a database error.")
        return _error("database_error", "Registration could not be completed right now.", 500)
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()

    return _success({"user_id": user_id}, 201)


@app.post("/api/tokens")
def create_token():
    body = _json_body()
    if body is None:
        return _error("invalid_json", "A JSON object is required.", 400)

    user_id = _positive_id(body.get("user_id"))
    if user_id is None:
        return _error("invalid_user_id", "user_id must be a positive integer.", 400)
    service_id = _positive_id(body.get("service_id"))
    if service_id is None:
        return _error("invalid_service_id", "service_id must be a positive integer.", 400)

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        connection.start_transaction()
        cursor = connection.cursor()

        cursor.execute(
            "SELECT id FROM services WHERE id = %s AND is_active = TRUE FOR UPDATE",
            (service_id,),
        )
        if cursor.fetchone() is None:
            connection.rollback()
            return _error("service_not_found", "The requested active service was not found.", 404)

        cursor.execute(
            "SELECT id FROM users WHERE id = %s AND is_active = TRUE",
            (user_id,),
        )
        if cursor.fetchone() is None:
            connection.rollback()
            return _error("user_not_found", "The requested active user was not found.", 404)

        cursor.execute("SELECT CURRENT_DATE")
        queue_date = cursor.fetchone()[0]
        cursor.execute(
            """
            SELECT COALESCE(MAX(queue_number), 0) + 1
            FROM tokens
            WHERE service_id = %s AND queue_date = %s
            """,
            (service_id, queue_date),
        )
        queue_number = cursor.fetchone()[0]
        token_code = secrets.token_hex(16).upper()

        cursor.execute(
            """
            INSERT INTO tokens (
                service_id, user_id, queue_date, queue_number, token_code, status
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (service_id, user_id, queue_date, queue_number, token_code, "Waiting"),
        )
        token_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO queue_records (token_id, event_type)
            VALUES (%s, %s)
            """,
            (token_id, "Waiting"),
        )
        cursor.execute("SELECT created_at FROM tokens WHERE id = %s", (token_id,))
        created_at = cursor.fetchone()[0]
        qr_code_base64 = _make_qr_code(token_code)
        connection.commit()
    except mysql.connector.Error:
        if connection is not None:
            connection.rollback()
        app.logger.error("Token generation failed because of a database error.")
        return _error("database_error", "A token could not be generated right now.", 500)
    except Exception:
        if connection is not None:
            connection.rollback()
        app.logger.error("Token generation failed unexpectedly.")
        return _error("token_generation_error", "A token could not be generated right now.", 500)
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()

    return _success(
        {
            "token_id": token_id,
            "service_id": service_id,
            "queue_date": queue_date.isoformat(),
            "queue_number": queue_number,
            "token_code": token_code,
            "status": "Waiting",
            "created_at": created_at.isoformat(),
            "qr_code_base64": qr_code_base64,
            "qr_code_mime_type": "image/png",
        },
        201,
    )


@app.get("/api/tokens/<token_reference>")
def get_token_tracking(token_reference):
    if token_reference.isdecimal():
        token_id = _positive_id(token_reference)
        if token_id is None:
            return _error("invalid_token_id", "Token ID must be a positive integer.", 400)
        lookup_column = "t.id"
        lookup_value = token_id
    elif re.fullmatch(r"[A-Fa-f0-9]{32}", token_reference):
        lookup_column = "t.token_code"
        lookup_value = token_reference.upper()
    else:
        return _error(
            "invalid_token_reference",
            "Provide a positive token ID or a 32-character hexadecimal token code.",
            400,
        )

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            f"""
            SELECT t.id AS token_id, t.service_id, t.queue_date,
                   t.queue_number, t.token_code, t.status, t.created_at,
                   s.name AS service_name, s.department_id,
                   s.estimated_duration_minutes,
                   d.name AS department_name
            FROM tokens AS t
            JOIN services AS s ON s.id = t.service_id
            JOIN departments AS d ON d.id = s.department_id
            WHERE {lookup_column} = %s
            """,
            (lookup_value,),
        )
        token = cursor.fetchone()
        if token is None:
            return _error("token_not_found", "The requested token was not found.", 404)

        active_statuses = ("Waiting", "Called", "Serving")
        people_ahead = 0
        queue_position = None
        estimated_wait_minutes = 0
        estimate_basis = "not_queued"

        if token["status"] in active_statuses:
            cursor.execute(
                """
                SELECT COUNT(*) AS people_ahead
                FROM tokens
                WHERE service_id = %s
                  AND queue_date = %s
                  AND status IN ('Waiting', 'Called', 'Serving')
                  AND (
                      created_at < %s
                      OR (created_at = %s AND id < %s)
                  )
                """,
                (
                    token["service_id"],
                    token["queue_date"],
                    token["created_at"],
                    token["created_at"],
                    token["token_id"],
                ),
            )
            people_ahead = cursor.fetchone()["people_ahead"]
            queue_position = people_ahead + 1

            cursor.execute(
                """
                SELECT COUNT(*) AS sample_count,
                       AVG(duration_seconds) AS average_duration_seconds
                FROM service_history
                WHERE service_id = %s AND duration_seconds > 0
                """,
                (token["service_id"],),
            )
            history = cursor.fetchone()
            if history["sample_count"] >= 3:
                service_minutes = max(
                    1,
                    int((history["average_duration_seconds"] + 30) // 60),
                )
                estimate_basis = "service_history_average"
            elif token["estimated_duration_minutes"]:
                service_minutes = token["estimated_duration_minutes"]
                estimate_basis = "configured_service_duration"
            else:
                service_minutes = 10
                estimate_basis = "fallback"

            estimated_wait_minutes = people_ahead * service_minutes

        # Fetch assigned counter details if called or assigned
        cursor.execute(
            """
            SELECT qr.counter_id, c.counter_name, c.location AS counter_location
            FROM queue_records qr
            LEFT JOIN counters c ON c.id = qr.counter_id
            WHERE qr.token_id = %s
            ORDER BY qr.id DESC
            LIMIT 1
            """,
            (token["token_id"],),
        )
        assigned_counter = cursor.fetchone()
        counter_id = assigned_counter["counter_id"] if assigned_counter else None
        counter_name = assigned_counter["counter_name"] if assigned_counter else None
        counter_location = assigned_counter["counter_location"] if assigned_counter else None

        response_data = {
            "token_id": token["token_id"],
            "token_number": token["queue_number"],
            "token_code": token["token_code"],
            "service_id": token["service_id"],
            "service_name": token["service_name"],
            "department_id": token["department_id"],
            "department_name": token["department_name"],
            "queue_date": token["queue_date"].isoformat(),
            "created_at": token["created_at"].isoformat(),
            "status": token["status"],
            "queue_position": queue_position,
            "people_ahead": people_ahead,
            "estimated_wait_minutes": estimated_wait_minutes,
            "estimate_basis": estimate_basis,
            "counter_id": counter_id,
            "counter_name": counter_name,
            "counter_location": counter_location,
            "qr_code_base64": _make_qr_code(token["token_code"]),
            "qr_code_mime_type": "image/png",
        }
    except mysql.connector.Error:
        app.logger.error("Token tracking lookup failed because of a database error.")
        return _error(
            "database_error",
            "Token details could not be retrieved right now.",
            500,
        )
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()

    return _success(response_data)


@app.get("/api/admin/queues")
@app.get("/api/queues")
def get_admin_queues():
    department_id = request.args.get("department_id")
    counter_id = request.args.get("counter_id")

    dept_param = None
    if department_id is not None:
        dept_param = _positive_id(department_id)
        if dept_param is None:
            return _error("invalid_department_id", "department_id must be a positive integer.", 400)

    counter_param = None
    if counter_id is not None:
        counter_param = _positive_id(counter_id)
        if counter_param is None:
            return _error("invalid_counter_id", "counter_id must be a positive integer.", 400)

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute("SELECT CURRENT_DATE")
            today = cursor.fetchone()["CURRENT_DATE"]

            query = """
                SELECT t.id AS token_id, t.service_id, t.queue_date,
                       t.queue_number, t.token_code, t.status, t.created_at,
                       t.called_at, t.completed_at,
                       s.name AS service_name, s.department_id,
                       d.name AS department_name,
                       u.id AS user_id, u.full_name AS student_name, u.email AS student_email,
                       (
                           SELECT qr.counter_id
                           FROM queue_records qr
                           WHERE qr.token_id = t.id
                           ORDER BY qr.id DESC
                           LIMIT 1
                       ) AS counter_id,
                       (
                           SELECT c.counter_name
                           FROM queue_records qr
                           JOIN counters c ON c.id = qr.counter_id
                           WHERE qr.token_id = t.id
                           ORDER BY qr.id DESC
                           LIMIT 1
                       ) AS counter_name
                FROM tokens t
                JOIN services s ON s.id = t.service_id
                JOIN departments d ON d.id = s.department_id
                LEFT JOIN users u ON u.id = t.user_id
                WHERE t.queue_date = %s
            """
            params = [today]
            if dept_param is not None:
                query += " AND s.department_id = %s"
                params.append(dept_param)

            query += " ORDER BY t.created_at ASC, t.id ASC"
            cursor.execute(query, tuple(params))
            tokens = cursor.fetchall()

            waiting_count = 0
            called_count = 0
            completed_count = 0
            skipped_count = 0

            for tok in tokens:
                st = tok["status"]
                if st == "Waiting":
                    waiting_count += 1
                elif st in ("Called", "Serving"):
                    called_count += 1
                elif st == "Completed":
                    completed_count += 1
                elif st == "Skipped":
                    skipped_count += 1
                if tok.get("queue_date") is not None:
                    tok["queue_date"] = tok["queue_date"].isoformat()
                if tok.get("created_at") is not None:
                    tok["created_at"] = tok["created_at"].isoformat()
                if tok.get("called_at") is not None:
                    tok["called_at"] = tok["called_at"].isoformat()
                if tok.get("completed_at") is not None:
                    tok["completed_at"] = tok["completed_at"].isoformat()

            current_token = None
            if counter_param is not None:
                for tok in tokens:
                    if tok.get("counter_id") == counter_param and tok["status"] in ("Called", "Serving"):
                        current_token = tok
                        break

            return _success(
                {
                    "queue_date": today.isoformat(),
                    "summary": {
                        "waiting_count": waiting_count,
                        "called_count": called_count,
                        "completed_count": completed_count,
                        "skipped_count": skipped_count,
                        "total_count": len(tokens),
                    },
                    "current_token": current_token,
                    "tokens": tokens,
                }
            )
        finally:
            cursor.close()
            connection.close()
    except mysql.connector.Error:
        app.logger.error("Could not retrieve admin queues because of a database error.")
        return _error(
            "database_error",
            "Queue data could not be retrieved right now.",
            500,
        )


@app.post("/api/admin/call-next")
def call_next_token():
    body = _json_body()
    if body is None:
        return _error("invalid_json", "A JSON object is required.", 400)
    counter_id = _positive_id(body.get("counter_id"))
    if counter_id is None:
        return _error("invalid_counter_id", "counter_id must be a positive integer.", 400)

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT id, department_id
            FROM counters
            WHERE id = %s AND is_active = TRUE
            FOR UPDATE
            """,
            (counter_id,),
        )
        counter = cursor.fetchone()
        if counter is None:
            connection.rollback()
            return _error("counter_not_found", "The requested active counter was not found.", 404)

        cursor.execute(
            """
            SELECT t.id AS token_id, t.service_id, t.queue_date, t.queue_number,
                   t.token_code, t.status, t.created_at, s.name AS service_name
            FROM tokens AS t
            JOIN services AS s ON s.id = t.service_id
            WHERE s.department_id = %s
              AND s.is_active = TRUE
              AND t.status = 'Waiting'
            ORDER BY t.created_at ASC, t.id ASC
            LIMIT 1
            FOR UPDATE
            """,
            (counter["department_id"],),
        )
        token = cursor.fetchone()
        if token is None:
            connection.rollback()
            return _error("queue_empty", "There are no waiting tokens for this department.", 404)

        cursor.execute(
            """
            UPDATE tokens
            SET status = 'Called', called_at = CURRENT_TIMESTAMP
            WHERE id = %s AND status = 'Waiting'
            """,
            (token["token_id"],),
        )
        if cursor.rowcount != 1:
            connection.rollback()
            return _error("token_unavailable", "The waiting token is no longer available.", 409)

        cursor.execute(
            """
            INSERT INTO queue_records (token_id, counter_id, event_type)
            VALUES (%s, %s, 'Called')
            """,
            (token["token_id"], counter_id),
        )
        cursor.execute(
            "SELECT called_at FROM tokens WHERE id = %s",
            (token["token_id"],),
        )
        called_at = cursor.fetchone()["called_at"]
        connection.commit()
    except mysql.connector.Error:
        if connection is not None:
            connection.rollback()
        app.logger.error("Calling the next token failed because of a database error.")
        return _error("database_error", "The next token could not be called right now.", 500)
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()

    return _success(
        {
            "token_id": token["token_id"],
            "service_id": token["service_id"],
            "service_name": token["service_name"],
            "queue_date": token["queue_date"].isoformat(),
            "queue_number": token["queue_number"],
            "token_code": token["token_code"],
            "status": "Called",
            "counter_id": counter_id,
            "created_at": token["created_at"].isoformat(),
            "called_at": called_at.isoformat(),
        }
    )


@app.post("/api/admin/complete")
def complete_token():
    body = _json_body()
    if body is None:
        return _error("invalid_json", "A JSON object is required.", 400)
    token_id = _positive_id(body.get("token_id"))
    if token_id is None:
        return _error("invalid_token_id", "token_id must be a positive integer.", 400)
    counter_id = _positive_id(body.get("counter_id"))
    if counter_id is None:
        return _error("invalid_counter_id", "counter_id must be a positive integer.", 400)

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT id, department_id
            FROM counters
            WHERE id = %s AND is_active = TRUE
            FOR UPDATE
            """,
            (counter_id,),
        )
        counter = cursor.fetchone()
        if counter is None:
            connection.rollback()
            return _error("counter_not_found", "The requested active counter was not found.", 404)

        cursor.execute(
            """
            SELECT t.id, t.service_id, t.status, t.called_at,
                   t.service_started_at, s.department_id
            FROM tokens AS t
            JOIN services AS s ON s.id = t.service_id
            WHERE t.id = %s
            FOR UPDATE
            """,
            (token_id,),
        )
        token = cursor.fetchone()
        if token is None:
            connection.rollback()
            return _error("token_not_found", "The requested token was not found.", 404)
        if token["department_id"] != counter["department_id"]:
            connection.rollback()
            return _error("counter_mismatch", "The token does not belong to this counter's department.", 409)
        if token["status"] not in ("Called", "Serving"):
            connection.rollback()
            return _error(
                "invalid_token_status",
                "Only a Called or Serving token can be completed.",
                409,
            )

        cursor.execute(
            """
            SELECT event_type, counter_id
            FROM queue_records
            WHERE token_id = %s
            ORDER BY id DESC
            LIMIT 1
            FOR UPDATE
            """,
            (token_id,),
        )
        assignment = cursor.fetchone()
        if (
            assignment is None
            or assignment["counter_id"] != counter_id
            or assignment["event_type"] not in ("Called", "Serving")
        ):
            connection.rollback()
            return _error("counter_mismatch", "This token is not assigned to the specified counter.", 409)

        started_at = token["service_started_at"] or token["called_at"]
        if started_at is None:
            connection.rollback()
            return _error(
                "service_start_missing",
                "The token has no recorded call or service start time.",
                409,
            )

        cursor.execute(
            """
            UPDATE tokens
            SET status = 'Completed',
                service_started_at = COALESCE(service_started_at, called_at),
                completed_at = CURRENT_TIMESTAMP
            WHERE id = %s AND status IN ('Called', 'Serving')
            """,
            (token_id,),
        )
        if cursor.rowcount != 1:
            connection.rollback()
            return _error("invalid_token_status", "The token could not be completed.", 409)

        cursor.execute(
            """
            INSERT INTO queue_records (token_id, counter_id, event_type)
            VALUES (%s, %s, 'Completed')
            """,
            (token_id, counter_id),
        )
        cursor.execute(
            """
            INSERT INTO service_history (
                token_id, service_id, counter_id, started_at,
                completed_at, duration_seconds
            )
            SELECT id, service_id, %s, COALESCE(service_started_at, called_at),
                   completed_at,
                   GREATEST(
                       0,
                       TIMESTAMPDIFF(
                           SECOND,
                           COALESCE(service_started_at, called_at),
                           completed_at
                       )
                   )
            FROM tokens
            WHERE id = %s
            """,
            (counter_id, token_id),
        )
        cursor.execute(
            """
            SELECT completed_at,
                   TIMESTAMPDIFF(
                       SECOND, service_started_at, completed_at
                   ) AS duration_seconds
            FROM tokens
            WHERE id = %s
            """,
            (token_id,),
        )
        completion = cursor.fetchone()
        connection.commit()
    except mysql.connector.IntegrityError as error:
        if connection is not None:
            connection.rollback()
        if error.errno == 1062:
            return _error("token_already_completed", "Service history already exists for this token.", 409)
        app.logger.error("Completing the token failed because of a database constraint.")
        return _error("database_error", "The token could not be completed right now.", 500)
    except mysql.connector.Error:
        if connection is not None:
            connection.rollback()
        app.logger.error("Completing the token failed because of a database error.")
        return _error("database_error", "The token could not be completed right now.", 500)
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()

    return _success(
        {
            "token_id": token_id,
            "counter_id": counter_id,
            "status": "Completed",
            "completed_at": completion["completed_at"].isoformat(),
            "duration_seconds": completion["duration_seconds"],
        }
    )


@app.post("/api/admin/skip")
def skip_token():
    body = _json_body()
    if body is None:
        return _error("invalid_json", "A JSON object is required.", 400)
    token_id = _positive_id(body.get("token_id"))
    if token_id is None:
        return _error("invalid_token_id", "token_id must be a positive integer.", 400)
    counter_id = _positive_id(body.get("counter_id"))
    if counter_id is None:
        return _error("invalid_counter_id", "counter_id must be a positive integer.", 400)

    connection = None
    cursor = None
    try:
        connection = get_db_connection()
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            "SELECT id, department_id FROM counters WHERE id = %s AND is_active = TRUE FOR UPDATE",
            (counter_id,),
        )
        counter = cursor.fetchone()
        if counter is None:
            connection.rollback()
            return _error("counter_not_found", "The requested active counter was not found.", 404)

        cursor.execute(
            """
            SELECT t.id, t.status, s.department_id
            FROM tokens AS t
            JOIN services AS s ON s.id = t.service_id
            WHERE t.id = %s
            FOR UPDATE
            """,
            (token_id,),
        )
        token = cursor.fetchone()
        if token is None:
            connection.rollback()
            return _error("token_not_found", "The requested token was not found.", 404)
        if token["department_id"] != counter["department_id"]:
            connection.rollback()
            return _error("counter_mismatch", "The token does not belong to this counter's department.", 409)
        if token["status"] not in ("Waiting", "Called"):
            connection.rollback()
            return _error(
                "invalid_token_status",
                "Only a Waiting or Called token can be skipped.",
                409,
            )

        if token["status"] == "Called":
            cursor.execute(
                """
                SELECT event_type, counter_id
                FROM queue_records
                WHERE token_id = %s
                ORDER BY id DESC
                LIMIT 1
                FOR UPDATE
                """,
                (token_id,),
            )
            assignment = cursor.fetchone()
            if (
                assignment is None
                or assignment["counter_id"] != counter_id
                or assignment["event_type"] != "Called"
            ):
                connection.rollback()
                return _error("counter_mismatch", "This token is not assigned to the specified counter.", 409)

        cursor.execute(
            """
            UPDATE tokens
            SET status = 'Skipped'
            WHERE id = %s AND status IN ('Waiting', 'Called')
            """,
            (token_id,),
        )
        if cursor.rowcount != 1:
            connection.rollback()
            return _error("invalid_token_status", "The token could not be skipped.", 409)

        cursor.execute(
            """
            INSERT INTO queue_records (token_id, counter_id, event_type)
            VALUES (%s, %s, 'Skipped')
            """,
            (token_id, counter_id),
        )
        connection.commit()
    except mysql.connector.Error:
        if connection is not None:
            connection.rollback()
        app.logger.error("Skipping the token failed because of a database error.")
        return _error("database_error", "The token could not be skipped right now.", 500)
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()

    return _success(
        {
            "token_id": token_id,
            "counter_id": counter_id,
            "status": "Skipped",
        }
    )


@app.errorhandler(404)
def not_found(exception):
    return _error("not_found", "The requested resource was not found.", 404)


if __name__ == "__main__":
    app.run(debug=False)
