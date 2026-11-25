
from datetime import datetime, date

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint

db = SQLAlchemy()


from flask_login import UserMixin

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    # student or admin
    role = db.Column(db.String(20), nullable=False, default="student")

    phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Department(db.Model):
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)

    building = db.Column(db.String(120))
    floor = db.Column(db.String(50))
    room = db.Column(db.String(50))

    directions = db.Column(db.Text)
    contact_person = db.Column(db.String(120))
    contact_phone = db.Column(db.String(20))
    contact_email = db.Column(db.String(120))

    daily_limit = db.Column(db.Integer, default=100)
    active = db.Column(db.Boolean, default=True)


class Service(db.Model):
    __tablename__ = "services"

    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.id"),
        nullable=False
    )

    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)

    estimated_minutes = db.Column(db.Integer, default=15)
    fee = db.Column(db.Numeric(10, 2), default=0)

    active = db.Column(db.Boolean, default=True)


class Counter(db.Model):
    __tablename__ = "counters"

    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.id"),
        nullable=False
    )

    name = db.Column(db.String(100), nullable=False)
    building = db.Column(db.String(120))
    floor = db.Column(db.String(50))
    room = db.Column(db.String(50))
    directions = db.Column(db.Text)

    active = db.Column(db.Boolean, default=True)


class Token(db.Model):
    __tablename__ = "tokens"

    id = db.Column(db.Integer, primary_key=True)

    code = db.Column(db.String(30), unique=True, nullable=False)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    service_id = db.Column(
        db.Integer,
        db.ForeignKey("services.id"),
        nullable=False
    )

    counter_id = db.Column(
        db.Integer,
        db.ForeignKey("counters.id")
    )

    visit_date = db.Column(db.Date, default=date.today, nullable=False)

    status = db.Column(
        db.String(30),
        default="pending",
        nullable=False
    )
    # pending, approved, called, completed, declined, missed

    priority = db.Column(
        db.String(30),
        default="normal",
        nullable=False
    )
    # normal, accessibility, urgent, emergency

    priority_verified = db.Column(db.Boolean, default=False)

    decline_reason = db.Column(db.Text)
    admin_note = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    called_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)

    rescheduled_from = db.Column(
        db.Integer,
        db.ForeignKey("tokens.id")
    )


class ServiceRequest(db.Model):
    __tablename__ = "service_requests"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    service_id = db.Column(
        db.Integer,
        db.ForeignKey("services.id"),
        nullable=False
    )

    description = db.Column(db.Text, nullable=False)

    status = db.Column(db.String(30), default="submitted")
    # submitted, in_progress, completed, declined

    staff_note = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    message = db.Column(db.Text, nullable=False)

    is_read = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)

    token_id = db.Column(
        db.Integer,
        db.ForeignKey("tokens.id"),
        nullable=False
    )

    amount = db.Column(db.Numeric(10, 2), nullable=False)

    status = db.Column(db.String(30), default="pending")
    # pending, successful, failed

    payment_reference = db.Column(db.String(100))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ForecastModelRun(db.Model):
    __tablename__ = "forecast_model_runs"

    id = db.Column(db.Integer, primary_key=True)
    model_path = db.Column(db.String(255), nullable=False)
    dataset_path = db.Column(db.String(255), nullable=False)
    trained_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    training_rows = db.Column(db.Integer, nullable=False)
    test_rows = db.Column(db.Integer, nullable=False)
    mae = db.Column(db.Float, nullable=False)
    rmse = db.Column(db.Float, nullable=False)
    r2 = db.Column(db.Float, nullable=False)
    is_simulated = db.Column(db.Boolean, default=True, nullable=False)


class PeakForecast(db.Model):
    __tablename__ = "peak_forecasts"

    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.id"),
        nullable=False
    )
    forecast_date = db.Column(db.Date, nullable=False)
    time_slot = db.Column(db.String(30), nullable=False)
    expected_bookings = db.Column(db.Float, nullable=False)
    demand_level = db.Column(db.String(10), nullable=False)
    active_counters = db.Column(db.Integer, nullable=False)
    recommendation = db.Column(db.Text, nullable=False)
    model_run_id = db.Column(
        db.Integer,
        db.ForeignKey("forecast_model_runs.id"),
        nullable=False
    )
    generated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "department_id",
            "forecast_date",
            "time_slot",
            name="uq_peak_forecast_department_date_slot"
        ),
    )
