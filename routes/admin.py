
from datetime import date, datetime

from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash
)
from flask_login import login_required
from sqlalchemy.orm import aliased

from models import (
    db, Token, Service, Department,
    Counter, User, Notification
)
from routes.auth import role_required
from routes.forecasting import get_forecast_payload, persist_forecasts


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# --------------------------------------------------
# NOTIFICATION HELPER
# --------------------------------------------------

def send_notification(user_id, message):
    notification = Notification(
        user_id=user_id,
        message=message
    )
    db.session.add(notification)


# --------------------------------------------------
# ADMIN DASHBOARD
# --------------------------------------------------

@admin_bp.route("/dashboard")
@login_required
@role_required("admin")
def dashboard():

    selected_date_text = request.args.get("date", "")

    try:
        selected_date = (
            date.fromisoformat(selected_date_text)
            if selected_date_text
            else date.today()
        )
    except ValueError:
        selected_date = date.today()

    token_records = (
        db.session.query(Token, Service, Department, User, Counter)
        .join(Service, Token.service_id == Service.id)
        .join(Department, Service.department_id == Department.id)
        .join(User, Token.user_id == User.id)
        .outerjoin(Counter, Token.counter_id == Counter.id)
        .filter(Token.visit_date == selected_date)
        .order_by(Token.created_at.asc())
        .all()
    )

    # --------------------------------------------------
    # RESCHEDULED TOKEN HISTORY
    # --------------------------------------------------

    OriginalToken = aliased(Token)

    rescheduled_records = (
        db.session.query(
            Token,
            OriginalToken,
            User,
            Service,
            Department
        )
        .join(
            OriginalToken,
            Token.rescheduled_from == OriginalToken.id
        )
        .join(User, Token.user_id == User.id)
        .join(Service, Token.service_id == Service.id)
        .join(Department, Service.department_id == Department.id)
        .filter(Token.visit_date == selected_date)
        .order_by(Token.created_at.desc())
        .all()
    )

    all_tokens = Token.query.filter_by(
        visit_date=selected_date
    ).all()

    total_tokens = len(all_tokens)

    pending_count = sum(
        1 for token in all_tokens
        if token.status == "pending"
    )

    approved_count = sum(
        1 for token in all_tokens
        if token.status == "approved"
    )

    called_count = sum(
        1 for token in all_tokens
        if token.status == "called"
    )

    completed_count = sum(
        1 for token in all_tokens
        if token.status == "completed"
    )

    missed_count = sum(
        1 for token in all_tokens
        if token.status == "missed"
    )

    priority_count = sum(
        1 for token in all_tokens
        if token.priority != "normal"
        and not token.priority_verified
    )

    departments = Department.query.filter_by(
        active=True
    ).order_by(Department.name).all()

    counters = Counter.query.filter_by(
        active=True
    ).order_by(Counter.name).all()

    forecast_payload = get_forecast_payload()
    forecast_warning = persist_forecasts(forecast_payload)
    if forecast_warning:
        forecast_payload["warning"] = forecast_warning

    return render_template(
        "admin_dashboard.html",
        token_records=token_records,
        selected_date=selected_date.isoformat(),
        total_tokens=total_tokens,
        pending_count=pending_count,
        approved_count=approved_count,
        called_count=called_count,
        completed_count=completed_count,
        missed_count=missed_count,
        priority_count=priority_count,
        departments=departments,
        counters=counters,
        rescheduled_records=rescheduled_records,
        rescheduled_count=len(rescheduled_records),
        forecast_departments=forecast_payload["departments"],
        forecast_predictions=forecast_payload["predictions"],
        forecast_metrics=forecast_payload["metrics"],
        forecast_warning=forecast_payload["warning"]
    )


# --------------------------------------------------
# TOKEN ACTIONS
# APPROVE / DECLINE / CALL / COMPLETE / MISSED
# --------------------------------------------------

@admin_bp.route("/token/<int:token_id>/action", methods=["POST"])
@login_required
@role_required("admin")
def token_action(token_id):

    token = db.session.get(Token, token_id)

    if not token:
        flash("Token not found.", "error")
        return redirect(url_for("admin.dashboard"))

    action = request.form.get("action", "").strip().lower()
    note = request.form.get("note", "").strip()

    allowed_actions = [
        "approve", "decline", "call", "complete", "missed"
    ]

    if action not in allowed_actions:
        flash("Invalid token action.", "error")
        return redirect(url_for("admin.dashboard"))

    if action == "approve":

        if token.status != "pending":
            flash("Only pending tokens can be approved.", "error")
            return redirect(url_for("admin.dashboard"))

        token.status = "approved"
        token.decline_reason = None

        send_notification(
            token.user_id,
            f"Your token {token.code} has been approved."
        )

        flash(f"Token {token.code} approved.", "success")

    elif action == "decline":

        if token.status not in ["pending", "approved"]:
            flash("This token cannot be declined now.", "error")
            return redirect(url_for("admin.dashboard"))

        if not note:
            flash("Please enter a reason before declining.", "error")
            return redirect(url_for("admin.dashboard"))

        token.status = "declined"
        token.decline_reason = note
        token.admin_note = note

        send_notification(
            token.user_id,
            f"Your token {token.code} was declined. Reason: {note}"
        )

        flash(f"Token {token.code} declined.", "success")

    elif action == "call":

        if token.status != "approved":
            flash("Only approved tokens can be called.", "error")
            return redirect(url_for("admin.dashboard"))

        if token.priority != "normal" and not token.priority_verified:
            flash(
                "Verify the priority request before calling this token.",
                "error"
            )
            return redirect(
                url_for("admin.dashboard", date=token.visit_date.isoformat())
            )

        if not token.counter_id:
            flash("Assign a counter before calling this token.", "error")
            return redirect(
                url_for("admin.dashboard", date=token.visit_date.isoformat())
            )

        token.status = "called"
        token.called_at = datetime.utcnow()

        counter = db.session.get(Counter, token.counter_id)
        counter_name = counter.name if counter else "your assigned counter"

        send_notification(
            token.user_id,
            f"Your token {token.code} is now being called. "
            f"Please proceed to {counter_name}."
        )

        flash(f"Token {token.code} called.", "success")

    elif action == "complete":

        if token.status != "called":
            flash("Only called tokens can be completed.", "error")
            return redirect(url_for("admin.dashboard"))

        token.status = "completed"
        token.completed_at = datetime.utcnow()

        send_notification(
            token.user_id,
            f"Your service for token {token.code} has been completed."
        )

        flash(f"Token {token.code} completed.", "success")

    elif action == "missed":

        if token.status not in ["approved", "called"]:
            flash(
                "Only approved or called tokens can be marked missed.",
                "error"
            )
            return redirect(url_for("admin.dashboard"))

        token.status = "missed"

        send_notification(
            token.user_id,
            f"You missed your turn for token {token.code}. "
            "Please contact the service desk."
        )

        flash(f"Token {token.code} marked as missed.", "success")

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Could not update the token. Please try again.", "error")

    return redirect(
        url_for("admin.dashboard", date=token.visit_date.isoformat())
    )


# --------------------------------------------------
# VERIFY PRIORITY REQUEST
# --------------------------------------------------

@admin_bp.route("/token/<int:token_id>/verify-priority", methods=["POST"])
@login_required
@role_required("admin")
def verify_priority(token_id):

    token = db.session.get(Token, token_id)

    if not token:
        flash("Token not found.", "error")
        return redirect(url_for("admin.dashboard"))

    if token.priority == "normal":
        flash("This token does not have a priority request.", "error")
        return redirect(url_for("admin.dashboard"))

    if token.priority_verified:
        flash("This priority request is already verified.", "error")
        return redirect(url_for("admin.dashboard"))

    decision = request.form.get("decision", "").strip().lower()

    if decision not in ["verify", "reject"]:
        flash("Invalid priority decision.", "error")
        return redirect(url_for("admin.dashboard"))

    if decision == "verify":

        token.priority_verified = True

        send_notification(
            token.user_id,
            f"Your {token.priority} priority request for "
            f"token {token.code} has been verified."
        )

        flash("Priority request verified.", "success")

    else:

        token.priority = "normal"
        token.priority_verified = True

        send_notification(
            token.user_id,
            f"Your priority request for token {token.code} "
            "was not approved. Your token remains in the normal queue."
        )

        flash(
            "Priority request rejected. Token remains normal priority.",
            "success"
        )

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Could not update the priority request.", "error")

    return redirect(
        url_for("admin.dashboard", date=token.visit_date.isoformat())
    )


# --------------------------------------------------
# MANAGE DEPARTMENTS AND COUNTERS
# --------------------------------------------------

@admin_bp.route("/locations", methods=["GET"])
@login_required
@role_required("admin")
def manage_locations():

    departments = Department.query.order_by(
        Department.name
    ).all()

    counters = (
        Counter.query
        .join(Department, Counter.department_id == Department.id)
        .order_by(Department.name, Counter.name)
        .all()
    )

    return render_template(
        "admin_locations.html",
        departments=departments,
        counters=counters
    )


# --------------------------------------------------
# UPDATE DEPARTMENT
# --------------------------------------------------

@admin_bp.route(
    "/department/<int:department_id>/update",
    methods=["POST"]
)
@login_required
@role_required("admin")
def update_department(department_id):

    department = db.session.get(Department, department_id)

    if not department:
        flash("Department not found.", "error")
        return redirect(url_for("admin.manage_locations"))

    try:
        daily_limit = int(request.form.get("daily_limit", "100"))

        if daily_limit < 1:
            raise ValueError

    except ValueError:
        flash("Daily token limit must be a positive number.", "error")
        return redirect(url_for("admin.manage_locations"))

    department.name = request.form.get("name", "").strip()
    department.building = request.form.get("building", "").strip()
    department.floor = request.form.get("floor", "").strip()
    department.contact_person = request.form.get(
        "contact_person", ""
    ).strip()
    department.contact_phone = request.form.get(
        "contact_phone", ""
    ).strip()
    department.contact_email = request.form.get(
        "contact_email", ""
    ).strip()
    department.daily_limit = daily_limit

    if not department.name:
        flash("Department name is required.", "error")
        return redirect(url_for("admin.manage_locations"))

    try:
        db.session.commit()
        flash("Department details updated successfully.", "success")

    except Exception:
        db.session.rollback()
        flash(
            "Could not update department details. "
            "Check whether the name already exists.",
            "error"
        )

    return redirect(url_for("admin.manage_locations"))


# --------------------------------------------------
# CREATE COUNTER
# --------------------------------------------------

@admin_bp.route("/counter/create", methods=["POST"])
@login_required
@role_required("admin")
def create_counter():

    try:
        department_id = int(request.form.get("department_id", ""))

    except (ValueError, TypeError):
        flash("Please select a valid department.", "error")
        return redirect(url_for("admin.manage_locations"))

    department = db.session.get(Department, department_id)
    name = request.form.get("name", "").strip()

    if not department or not name:
        flash("Select a department and enter a counter name.", "error")
        return redirect(url_for("admin.manage_locations"))

    counter = Counter(
        department_id=department.id,
        name=name,
        building=request.form.get("building", "").strip(),
        floor=request.form.get("floor", "").strip(),
        room=request.form.get("room", "").strip(),
        directions=request.form.get("directions", "").strip(),
        active=True
    )

    try:
        db.session.add(counter)
        db.session.commit()
        flash("New counter added successfully.", "success")

    except Exception:
        db.session.rollback()
        flash("Could not add the counter. Please try again.", "error")

    return redirect(url_for("admin.manage_locations"))


# --------------------------------------------------
# UPDATE COUNTER
# --------------------------------------------------

@admin_bp.route(
    "/counter/<int:counter_id>/update",
    methods=["POST"]
)
@login_required
@role_required("admin")
def update_counter(counter_id):

    counter = db.session.get(Counter, counter_id)

    if not counter:
        flash("Counter not found.", "error")
        return redirect(url_for("admin.manage_locations"))

    try:
        department_id = int(request.form.get("department_id", ""))

    except (ValueError, TypeError):
        flash("Please select a valid department.", "error")
        return redirect(url_for("admin.manage_locations"))

    department = db.session.get(Department, department_id)
    name = request.form.get("name", "").strip()

    if not department or not name:
        flash("Select a department and enter a counter name.", "error")
        return redirect(url_for("admin.manage_locations"))

    counter.department_id = department.id
    counter.name = name
    counter.building = request.form.get("building", "").strip()
    counter.floor = request.form.get("floor", "").strip()
    counter.room = request.form.get("room", "").strip()
    counter.directions = request.form.get("directions", "").strip()

    try:
        db.session.commit()
        flash("Counter details updated successfully.", "success")

    except Exception:
        db.session.rollback()
        flash("Could not update counter details.", "error")

    return redirect(url_for("admin.manage_locations"))


# --------------------------------------------------
# ASSIGN COUNTER TO APPROVED TOKEN
# --------------------------------------------------

@admin_bp.route(
    "/token/<int:token_id>/assign-counter",
    methods=["POST"]
)
@login_required
@role_required("admin")
def assign_counter(token_id):

    token = db.session.get(Token, token_id)

    if not token:
        flash("Token not found.", "error")
        return redirect(url_for("admin.dashboard"))

    if token.status != "approved":
        flash(
            "Only approved tokens can be assigned a counter.",
            "error"
        )
        return redirect(
            url_for("admin.dashboard", date=token.visit_date.isoformat())
        )

    try:
        counter_id = int(request.form.get("counter_id", ""))

    except (ValueError, TypeError):
        flash("Please select a valid counter.", "error")
        return redirect(
            url_for("admin.dashboard", date=token.visit_date.isoformat())
        )

    counter = db.session.get(Counter, counter_id)

    if not counter or not counter.active:
        flash("Selected counter is unavailable.", "error")
        return redirect(
            url_for("admin.dashboard", date=token.visit_date.isoformat())
        )

    service = db.session.get(Service, token.service_id)

    if not service or service.department_id != counter.department_id:
        flash(
            "This counter does not belong to the token's department.",
            "error"
        )
        return redirect(
            url_for("admin.dashboard", date=token.visit_date.isoformat())
        )

    token.counter_id = counter.id

    send_notification(
        token.user_id,
        f"Counter assigned for token {token.code}: {counter.name}. "
        f"Location: {counter.building or 'Not specified'}, "
        f"Floor: {counter.floor or 'Not specified'}, "
        f"Room: {counter.room or 'Not specified'}."
    )

    try:
        db.session.commit()
        flash(
            f"Counter {counter.name} assigned to {token.code}.",
            "success"
        )

    except Exception:
        db.session.rollback()
        flash("Could not assign the counter. Please try again.", "error")

    return redirect(
        url_for("admin.dashboard", date=token.visit_date.isoformat())
    )


# --------------------------------------------------
# CALL NEXT TOKEN FOR A COUNTER
# --------------------------------------------------

@admin_bp.route(
    "/counter/<int:counter_id>/call-next",
    methods=["POST"]
)
@login_required
@role_required("admin")
def call_next(counter_id):

    counter = db.session.get(Counter, counter_id)

    if not counter or not counter.active:
        flash("Counter not found or inactive.", "error")
        return redirect(url_for("admin.dashboard"))

    eligible_tokens = (
        Token.query
        .join(Service, Token.service_id == Service.id)
        .filter(
            Token.counter_id == counter.id,
            Token.status == "approved",
            Token.visit_date == date.today(),
            Service.department_id == counter.department_id
        )
        .all()
    )

    if not eligible_tokens:
        flash(
            "No approved tokens are waiting at this counter.",
            "info"
        )
        return redirect(url_for("admin.dashboard"))

    eligible_tokens.sort(
        key=lambda token: (
            0 if (
                token.priority != "normal"
                and token.priority_verified
            ) else 1,
            token.created_at
        )
    )

    next_token = eligible_tokens[0]

    if next_token.priority != "normal" and not next_token.priority_verified:
        flash("Priority request must be verified before calling.", "error")
        return redirect(
            url_for("admin.dashboard", date=next_token.visit_date.isoformat())
        )

    next_token.status = "called"
    next_token.called_at = datetime.utcnow()

    send_notification(
        next_token.user_id,
        f"Your token {next_token.code} is now being called. "
        f"Please proceed to {counter.name}. "
        f"Location: {counter.building or 'Not specified'}, "
        f"Floor: {counter.floor or 'Not specified'}, "
        f"Room: {counter.room or 'Not specified'}."
    )

    try:
        db.session.commit()

        flash(
            f"Next token {next_token.code} called at {counter.name}.",
            "success"
        )

    except Exception:
        db.session.rollback()
        flash("Could not call the next token. Please try again.", "error")

    return redirect(
        url_for(
            "admin.dashboard",
            date=next_token.visit_date.isoformat()
        )
    )
