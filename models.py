
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

    preferred_priorities = db.Column(db.JSON, nullable=True, default=list)
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


# =====================================================================
# PARENT & VISITOR ASSISTANCE WITH SMART CAMPUS NAVIGATION MODELS
# =====================================================================

class VisitorPurpose(db.Model):
    """Configurable campus visit purposes (e.g. Admission Enquiry, Fee Payment)."""
    __tablename__ = "visitor_purposes"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    code = db.Column(db.String(60), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    icon = db.Column(db.String(50), default="📋")
    default_department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.id"),
        nullable=True
    )
    active = db.Column(db.Boolean, default=True)
    display_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class VisitorInstruction(db.Model):
    """
    Department-specific guidelines and document checklists.
    Supports multiple purposes mapped to the same department.
    """
    __tablename__ = "visitor_instructions"
    __table_args__ = (
        UniqueConstraint("purpose_id", "department_id", name="uq_visitor_purpose_department"),
    )

    id = db.Column(db.Integer, primary_key=True)
    purpose_id = db.Column(
        db.Integer,
        db.ForeignKey("visitor_purposes.id"),
        nullable=False
    )
    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.id"),
        nullable=False
    )

    procedure_steps = db.Column(db.Text, nullable=False)
    # Stored as JSON or newline-separated instructions

    required_documents = db.Column(db.Text, nullable=False)
    # Checklist of documents required for this purpose

    visiting_hours = db.Column(db.String(120), default="9:30 AM – 4:30 PM (Mon–Fri)")
    first_reporting_point = db.Column(
        db.String(255),
        default="Campus Reception Desk, Ground Floor, Administrative Block"
    )
    important_notes = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FloorPlan(db.Model):
    """Uploadable or vector-rendered floor plans for indoor navigation."""
    __tablename__ = "floor_plans"

    id = db.Column(db.Integer, primary_key=True)
    building = db.Column(db.String(120), nullable=False)
    floor = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    image_filename = db.Column(db.String(255), nullable=True)
    svg_blueprint = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CampusLocation(db.Model):
    """Outdoor GIS map coordinates and indoor floor plan markers."""
    __tablename__ = "campus_locations"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    building = db.Column(db.String(120), nullable=False)
    floor = db.Column(db.String(50), nullable=False)
    room = db.Column(db.String(50))

    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.id"),
        nullable=True
    )
    counter_id = db.Column(
        db.Integer,
        db.ForeignKey("counters.id"),
        nullable=True
    )

    # Outdoor GPS coordinates (Leaflet / OpenStreetMap)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)

    # Indoor Floor Plan coordinates (percentage: 0.0 - 100.0)
    floor_plan_id = db.Column(
        db.Integer,
        db.ForeignKey("floor_plans.id"),
        nullable=True
    )
    marker_x = db.Column(db.Float, nullable=True)
    marker_y = db.Column(db.Float, nullable=True)

    directions = db.Column(db.Text)
    is_demo = db.Column(db.Boolean, default=True)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CampusNotice(db.Model):
    """Visitor notices and campus announcements with automatic expiration."""
    __tablename__ = "campus_notices"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), default="General")
    # General, Admissions, Accounts, Exams, Timings, Advisory

    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.id"),
        nullable=True
    )
    purpose_id = db.Column(
        db.Integer,
        db.ForeignKey("visitor_purposes.id"),
        nullable=True
    )

    is_active = db.Column(db.Boolean, default=True)
    start_date = db.Column(db.Date, default=date.today, nullable=False)
    expiry_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class VisitorToken(db.Model):
    """
    Guest / Visitor token bookings without student account requirement.
    Separate from student tokens to preserve user_id NOT NULL integrity.
    """
    __tablename__ = "visitor_tokens"

    id = db.Column(db.Integer, primary_key=True)
    token_code = db.Column(db.String(30), unique=True, nullable=False, index=True)
    tracking_token = db.Column(db.String(64), unique=True, nullable=False, index=True)

    visitor_name = db.Column(db.String(100), nullable=False)
    visitor_phone = db.Column(db.String(20), nullable=False, index=True)

    purpose_id = db.Column(
        db.Integer,
        db.ForeignKey("visitor_purposes.id"),
        nullable=False
    )
    department_id = db.Column(
        db.Integer,
        db.ForeignKey("departments.id"),
        nullable=False
    )
    counter_id = db.Column(
        db.Integer,
        db.ForeignKey("counters.id"),
        nullable=True
    )

    visit_date = db.Column(db.Date, default=date.today, nullable=False, index=True)

    status = db.Column(
        db.String(30),
        default="pending",
        nullable=False,
        index=True
    )
    # pending, approved, called, completed, declined, missed

    priority = db.Column(
        db.String(30),
        default="normal",
        nullable=False
    )
    # normal, senior_citizen, accessibility, urgent

    priority_verified = db.Column(db.Boolean, default=False)
    decline_reason = db.Column(db.Text)
    admin_note = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    called_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
