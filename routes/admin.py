
import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash, current_app
)
from flask_login import login_required
from sqlalchemy import or_
from sqlalchemy.orm import aliased
from werkzeug.utils import secure_filename

from models import (
    db, Token, Service, Department,
    Counter, User, Notification,
    VisitorToken, VisitorPurpose, VisitorInstruction,
    CampusNotice, CampusLocation, FloorPlan
)
from services.queue_reentry import (
    AUTO_REENTRY_EXCEPTION_PREFIX,
    AUTO_REENTRY_NOTE_PREFIX,
    AUTO_REENTRY_USED_PREFIX,
    GRACE_PERIOD,
    process_expired_called_token,
)
from queue_optimization import (
    PRIORITY_RANKS,
    calculate_counter_workloads,
    recommend_counter,
    select_next_token_for_counter,
)
from routes.auth import role_required


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
PRIORITY_OPTIONS = tuple(PRIORITY_RANKS)


def parse_counter_priority_preferences():
    submitted = {
        priority.strip().lower()
        for priority in request.form.getlist("preferred_priorities")
        if priority.strip()
    }
    if not submitted.issubset(PRIORITY_OPTIONS):
        return None
    return [
        priority
        for priority in PRIORITY_OPTIONS
        if priority in submitted
    ]


# --------------------------------------------------
# NOTIFICATION HELPER
# --------------------------------------------------

def send_notification(user_id, message):
    notification = Notification(
        user_id=user_id,
        message=message
    )
    db.session.add(notification)


def load_allocation_snapshot(visit_date, lock_counters=False):
    """Load active counters and only student queue workload."""
    counter_query = (
        Counter.query
        .join(Department, Counter.department_id == Department.id)
        .filter(
            Counter.active.is_(True),
            Department.active.is_(True)
        )
        .order_by(Counter.name, Counter.id)
    )
    if lock_counters:
        counter_query = counter_query.with_for_update()

    counters = counter_query.all()
    active_tokens = (
        Token.query
        .filter(
            Token.visit_date == visit_date,
            Token.status.in_(("approved", "called"))
        )
        .all()
    )
    service_minutes = {
        service_id: minutes
        for service_id, minutes in db.session.query(
            Service.id,
            Service.estimated_minutes
        ).all()
    }
    return counters, active_tokens, service_minutes


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

    counters, waiting_tokens, service_minutes = load_allocation_snapshot(
        selected_date
    )
    all_counters = Counter.query.order_by(Counter.name).all()
    counter_workloads = calculate_counter_workloads(
        all_counters,
        waiting_tokens,
        service_minutes,
        selected_date,
        available_counter_ids={counter.id for counter in counters},
    )
    eligible_queue_tokens = [
        token
        for token, service, department, _student, _counter in token_records
        if (
            token.status == "approved"
            and service.active
            and department.active
            and (
                token.priority == "normal"
                or token.priority_verified
            )
        )
    ]
    service_department_by_token = {
        token.id: service.department_id
        for token, service, _department, _student, _counter in token_records
    }
    for workload in counter_workloads:
        counter = workload["counter"]
        department_tokens = [
            token
            for token in eligible_queue_tokens
            if service_department_by_token[token.id] == counter.department_id
        ]
        current_tokens = sorted(
            (
                token
                for token, _service, department, _student, assigned_counter
                in token_records
                if (
                    token.status == "called"
                    and token.counter_id == counter.id
                    and department.id == counter.department_id
                )
            ),
            key=lambda token: (token.called_at or datetime.min, token.id)
        )
        workload["current_token"] = current_tokens[0] if current_tokens else None
        workload["current_token_count"] = len(current_tokens)
        workload["busy"] = bool(current_tokens)
        workload["available"] = workload["available"] and not current_tokens
        workload["next_token"] = (
            select_next_token_for_counter(
                department_tokens,
                now=datetime.utcnow(),
            )
            if workload["available"]
            else None
        )

    counter_recommendations = {}
    for token, service, department, _student, _counter in token_records:
        if token.status not in ("pending", "approved") or not service.active:
            continue
        counter_recommendations[token.id] = recommend_counter(
            counters,
            waiting_tokens,
            department.id,
            service_minutes,
            selected_date,
            exclude_token_id=token.id,
            priority=token.priority,
            priority_verified=token.priority_verified,
        )

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
        counter_workloads=counter_workloads,
        counter_recommendations=counter_recommendations,
        rescheduled_records=rescheduled_records,
        rescheduled_count=len(rescheduled_records),
        automatic_reentry_exception_prefix=AUTO_REENTRY_EXCEPTION_PREFIX,
        automatic_reentry_ids={
            new_token.id
            for new_token, original_token, _student, _service, _department
            in rescheduled_records
            if (
                (new_token.admin_note or "").startswith(AUTO_REENTRY_NOTE_PREFIX)
                or (
                    (original_token.admin_note or "").startswith(
                        AUTO_REENTRY_USED_PREFIX
                    )
                    and f"created as {new_token.code}."
                    in original_token.admin_note
                )
            )
        }
    )


# --------------------------------------------------
# TOKEN ACTIONS
# APPROVE / DECLINE / CALL / COMPLETE / MISSED
# --------------------------------------------------

@admin_bp.route("/token/<int:token_id>/action", methods=["POST"])
@login_required
@role_required("admin")
def token_action(token_id):

    action = request.form.get("action", "").strip().lower()
    note = request.form.get("note", "").strip()

    counter = None
    if action == "call":
        token_preview = db.session.get(Token, token_id)
        if not token_preview:
            flash("Token not found.", "error")
            return redirect(url_for("admin.dashboard"))
        if token_preview.status != "approved" or not token_preview.counter_id:
            flash(
                "Only approved tokens assigned to a counter can be called.",
                "error"
            )
            return redirect(
                url_for("admin.dashboard", date=token_preview.visit_date.isoformat())
            )

        service_preview = db.session.get(Service, token_preview.service_id)
        if not service_preview:
            flash("The token's service is unavailable.", "error")
            return redirect(url_for("admin.dashboard"))

        department = (
            Department.query
            .filter_by(id=service_preview.department_id, active=True)
            .with_for_update()
            .first()
        )
        if not department:
            flash("The token's department is unavailable.", "error")
            return redirect(url_for("admin.dashboard"))

        busy_token = (
            Token.query
            .filter(
                Token.counter_id == token_preview.counter_id,
                Token.visit_date == token_preview.visit_date,
                Token.status == "called"
            )
            .with_for_update()
            .first()
        )
        if busy_token:
            flash(
                f"Counter is already serving {busy_token.code}.",
                "warning"
            )
            return redirect(
                url_for("admin.dashboard", date=token_preview.visit_date.isoformat())
            )

        counter = (
            Counter.query
            .filter_by(
                id=token_preview.counter_id,
                department_id=department.id,
                active=True
            )
            .with_for_update()
            .first()
        )
        if not counter:
            flash("The assigned counter is unavailable.", "error")
            return redirect(
                url_for("admin.dashboard", date=token_preview.visit_date.isoformat())
            )

        token = (
            Token.query
            .filter_by(id=token_id)
            .with_for_update()
            .first()
        )
        if (
            not token
            or token.status != "approved"
            or token.counter_id != counter.id
        ):
            flash("The token assignment changed. Refresh and try again.", "error")
            return redirect(url_for("admin.dashboard"))
    else:
        token = (
            Token.query
            .filter_by(id=token_id)
            .with_for_update()
            .first()
        )

    if not token:
        flash("Token not found.", "error")
        return redirect(url_for("admin.dashboard"))

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

        service = db.session.get(Service, token.service_id)
        recommendation = None
        if service and service.active:
            counters, waiting_tokens, service_minutes = (
                load_allocation_snapshot(
                    token.visit_date,
                    lock_counters=True,
                )
            )
            recommendation = recommend_counter(
                counters,
                waiting_tokens,
                service.department_id,
                service_minutes,
                token.visit_date,
                exclude_token_id=token.id,
                priority=token.priority,
                priority_verified=token.priority_verified,
            )

        token.status = "approved"
        token.counter_id = recommendation.id if recommendation else None
        token.decline_reason = None

        if recommendation:
            send_notification(
                token.user_id,
                f"Your token {token.code} has been approved and assigned "
                f"to {recommendation.name}."
            )
            approval_flash = (
                f"Token {token.code} approved and assigned to "
                f"{recommendation.name}.",
                "success",
            )
        else:
            send_notification(
                token.user_id,
                f"Your token {token.code} has been approved. "
                "No active compatible counter is available yet.",
            )
            approval_flash = (
                f"Token {token.code} approved, but no active compatible "
                "counter is available.",
                "warning",
            )

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

        if counter is None:
            flash("Assign an active counter before calling this token.", "error")
            return redirect(
                url_for("admin.dashboard", date=token.visit_date.isoformat())
            )

        eligible_tokens = (
            Token.query
            .join(Service, Token.service_id == Service.id)
            .filter(
                Token.visit_date == token.visit_date,
                Token.status == "approved",
                Service.department_id == counter.department_id,
                Service.active.is_(True),
                (Token.priority == "normal")
                | (Token.priority_verified.is_(True))
            )
            .order_by(Token.id)
            .with_for_update()
            .all()
        )
        next_token = select_next_token_for_counter(eligible_tokens)
        if not next_token or next_token.id != token.id:
            next_code = next_token.code if next_token else "none"
            flash(
                f"Queue order must be respected. The next eligible token is "
                f"{next_code}.",
                "warning"
            )
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
            f"Please proceed to {counter_name} within 2 minutes."
        )

        flash(f"Token {token.code} called.", "success")

    elif action == "complete":

        if token.status != "called":
            flash("Only called tokens can be completed.", "error")
            return redirect(url_for("admin.dashboard"))

        if (
            token.called_at
            and datetime.utcnow() >= token.called_at + GRACE_PERIOD
        ):
            flash(
                "The two-minute grace period has expired. This token cannot "
                "be completed; the queue scheduler will mark it missed.",
                "error"
            )
            return redirect(
                url_for("admin.dashboard", date=token.visit_date.isoformat())
            )

        token.status = "completed"
        token.completed_at = datetime.utcnow()

        send_notification(
            token.user_id,
            f"Your service for token {token.code} has been completed."
        )

        flash(f"Token {token.code} completed.", "success")

    elif action == "missed":

        if token.status == "called":
            if (
                not token.called_at
                or datetime.utcnow() < token.called_at + GRACE_PERIOD
            ):
                flash(
                    "The student must have the full two-minute grace period "
                    "before the called token can be marked missed.",
                    "error"
                )
                return redirect(
                    url_for("admin.dashboard", date=token.visit_date.isoformat())
                )

            db.session.rollback()
            result = process_expired_called_token(token_id)
            if result == "reentered":
                flash(
                    "The token was marked missed and automatically re-entered "
                    "at the end of the queue.",
                    "success"
                )
            elif result == "missed":
                flash(
                    "The token was marked missed. No automatic re-entry was "
                    "created; review the token note for details.",
                    "warning"
                )
            elif result == "skipped":
                flash("This token has already been updated.", "info")
            else:
                flash(
                    "The token could not be processed. Check the server log "
                    "and try again.",
                    "error"
                )
            return redirect(
                url_for("admin.dashboard", date=token.visit_date.isoformat())
            )

        if token.status != "approved":
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
        if action == "approve" and approval_flash:
            flash(approval_flash[0], approval_flash[1])
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
    services = (
        db.session.query(Service, Department)
        .join(Department, Service.department_id == Department.id)
        .order_by(Department.name, Service.name)
        .all()
    )

    return render_template(
        "admin_locations.html",
        departments=departments,
        counters=counters,
        priority_options=PRIORITY_OPTIONS,
        services=services,
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
# CREATE AND UPDATE SERVICES
# --------------------------------------------------

def parse_service_form():
    try:
        department_id = int(request.form.get("department_id", ""))
        estimated_minutes = int(request.form.get("estimated_minutes", "15"))
        fee = Decimal(request.form.get("fee", "0"))
    except (ValueError, TypeError, InvalidOperation):
        return None

    name = request.form.get("name", "").strip()
    if not name or estimated_minutes < 1 or fee < 0:
        return None

    department = db.session.get(Department, department_id)
    if not department:
        return None

    return {
        "department": department,
        "name": name,
        "description": request.form.get("description", "").strip(),
        "estimated_minutes": estimated_minutes,
        "fee": fee,
        "active": request.form.get("active") == "1",
    }


@admin_bp.route("/service/create", methods=["POST"])
@login_required
@role_required("admin")
def create_service():
    values = parse_service_form()
    if not values:
        flash(
            "Enter a service name, department, positive duration, and valid fee.",
            "error",
        )
        return redirect(url_for("admin.manage_locations"))

    existing = Service.query.filter_by(
        department_id=values["department"].id,
        name=values["name"],
    ).first()
    if existing:
        flash("That service already exists in the selected department.", "error")
        return redirect(url_for("admin.manage_locations"))

    service = Service(
        department_id=values["department"].id,
        name=values["name"],
        description=values["description"],
        estimated_minutes=values["estimated_minutes"],
        fee=values["fee"],
        active=values["active"],
    )
    try:
        db.session.add(service)
        db.session.commit()
        flash("Service added successfully.", "success")
    except Exception:
        db.session.rollback()
        flash("Could not add the service. Please try again.", "error")

    return redirect(url_for("admin.manage_locations"))


@admin_bp.route("/service/<int:service_id>/update", methods=["POST"])
@login_required
@role_required("admin")
def update_service(service_id):
    service = db.session.get(Service, service_id)
    if not service:
        flash("Service not found.", "error")
        return redirect(url_for("admin.manage_locations"))

    values = parse_service_form()
    if not values:
        flash(
            "Enter a service name, department, positive duration, and valid fee.",
            "error",
        )
        return redirect(url_for("admin.manage_locations"))

    duplicate = Service.query.filter(
        Service.department_id == values["department"].id,
        Service.name == values["name"],
        Service.id != service.id,
    ).first()
    if duplicate:
        flash("That service already exists in the selected department.", "error")
        return redirect(url_for("admin.manage_locations"))

    service.department_id = values["department"].id
    service.name = values["name"]
    service.description = values["description"]
    service.estimated_minutes = values["estimated_minutes"]
    service.fee = values["fee"]
    service.active = values["active"]

    try:
        db.session.commit()
        flash("Service updated successfully.", "success")
    except Exception:
        db.session.rollback()
        flash("Could not update the service. Please try again.", "error")

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

    preferred_priorities = parse_counter_priority_preferences()
    if preferred_priorities is None:
        flash("Select only supported priority categories.", "error")
        return redirect(url_for("admin.manage_locations"))

    counter = Counter(
        department_id=department.id,
        name=name,
        building=request.form.get("building", "").strip(),
        floor=request.form.get("floor", "").strip(),
        room=request.form.get("room", "").strip(),
        directions=request.form.get("directions", "").strip(),
        preferred_priorities=preferred_priorities,
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

    preferred_priorities = counter.preferred_priorities or []
    if "preferred_priorities" in request.form:
        preferred_priorities = parse_counter_priority_preferences()
        if preferred_priorities is None:
            flash("Select only supported priority categories.", "error")
            return redirect(url_for("admin.manage_locations"))

    counter.department_id = department.id
    counter.name = name
    counter.building = request.form.get("building", "").strip()
    counter.floor = request.form.get("floor", "").strip()
    counter.room = request.form.get("room", "").strip()
    counter.directions = request.form.get("directions", "").strip()
    counter.preferred_priorities = preferred_priorities

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

    token_preview = db.session.get(Token, token_id)

    if not token_preview:
        flash("Token not found.", "error")
        return redirect(url_for("admin.dashboard"))

    if token_preview.status != "approved":
        flash(
            "Only approved tokens can be assigned a counter.",
            "error"
        )
        return redirect(
            url_for("admin.dashboard", date=token_preview.visit_date.isoformat())
        )

    try:
        counter_id = int(request.form.get("counter_id", ""))

    except (ValueError, TypeError):
        flash("Please select a valid counter.", "error")
        return redirect(
            url_for(
                "admin.dashboard",
                date=token_preview.visit_date.isoformat()
            )
        )

    service = db.session.get(Service, token_preview.service_id)
    if not service:
        flash("The token's service is unavailable.", "error")
        return redirect(
            url_for("admin.dashboard", date=token_preview.visit_date.isoformat())
        )

    department = (
        Department.query
        .filter_by(id=service.department_id, active=True)
        .with_for_update()
        .first()
    )
    counter = (
        Counter.query
        .filter_by(
            id=counter_id,
            department_id=service.department_id,
            active=True
        )
        .with_for_update()
        .first()
    )

    if not counter or not department:
        flash("Selected counter is unavailable.", "error")
        return redirect(
            url_for("admin.dashboard", date=token_preview.visit_date.isoformat())
        )

    token = (
        Token.query
        .filter_by(id=token_id)
        .with_for_update()
        .first()
    )
    if not token or token.status != "approved":
        flash(
            "The token is no longer available for counter assignment.",
            "error"
        )
        return redirect(
            url_for("admin.dashboard", date=token_preview.visit_date.isoformat())
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

    counter_preview = db.session.get(Counter, counter_id)
    if not counter_preview:
        flash("Counter not found or inactive.", "error")
        return redirect(url_for("admin.dashboard"))

    department = (
        Department.query
        .filter_by(id=counter_preview.department_id, active=True)
        .with_for_update()
        .first()
    )
    if not department:
        flash("The counter's department is inactive.", "error")
        return redirect(url_for("admin.dashboard"))

    busy_token = (
        Token.query
        .filter(
            Token.counter_id == counter_id,
            Token.visit_date == date.today(),
            Token.status == "called"
        )
        .with_for_update()
        .first()
    )
    if busy_token:
        flash(
            f"Counter is already serving {busy_token.code}.",
            "warning"
        )
        return redirect(
            url_for("admin.dashboard", date=busy_token.visit_date.isoformat())
        )

    counter = (
        Counter.query
        .filter_by(
            id=counter_id,
            department_id=department.id,
            active=True
        )
        .with_for_update()
        .first()
    )
    if not counter:
        flash("Counter not found or inactive.", "error")
        return redirect(url_for("admin.dashboard"))

    eligible_tokens = (
        Token.query
        .join(Service, Token.service_id == Service.id)
        .filter(
            Token.status == "approved",
            Token.visit_date == date.today(),
            Service.department_id == counter.department_id,
            Service.active.is_(True),
            (Token.priority == "normal")
            | (Token.priority_verified.is_(True))
        )
        .order_by(Token.id)
        .with_for_update()
        .all()
    )

    if not eligible_tokens:
        flash(
            "No eligible approved tokens are waiting in this department.",
            "info"
        )
        return redirect(url_for("admin.dashboard"))

    next_token = select_next_token_for_counter(
        eligible_tokens,
        now=datetime.utcnow(),
    )
    if not next_token:
        flash("No eligible tokens are waiting in this department.", "info")
        return redirect(url_for("admin.dashboard"))

    next_token.counter_id = counter.id
    next_token.status = "called"
    next_token.called_at = datetime.utcnow()

    send_notification(
        next_token.user_id,
        f"Your token {next_token.code} is now being called. "
        f"Please proceed to {counter.name} within 2 minutes. "
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


# =====================================================================
# PARENT & VISITOR ASSISTANCE – ADMIN MANAGEMENT ROUTES
# =====================================================================

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "svg"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@admin_bp.route("/visitors")
@login_required
@role_required("admin")
def manage_visitors():
    """
    Central visitor queue management console.
    Filter by visit date, department, purpose, and status.
    """
    selected_date_text = request.args.get("date", "")
    try:
        selected_date = date.fromisoformat(selected_date_text) if selected_date_text else date.today()
    except ValueError:
        selected_date = date.today()

    status_filter = request.args.get("status", "").strip()
    dept_filter = request.args.get("department_id", type=int)
    purpose_filter = request.args.get("purpose_id", type=int)
    search_q = request.args.get("q", "").strip()

    # Query tokens for the date
    query = (
        db.session.query(VisitorToken, VisitorPurpose, Department, Counter)
        .join(VisitorPurpose, VisitorToken.purpose_id == VisitorPurpose.id)
        .join(Department, VisitorToken.department_id == Department.id)
        .outerjoin(Counter, VisitorToken.counter_id == Counter.id)
        .filter(VisitorToken.visit_date == selected_date)
    )

    if status_filter:
        query = query.filter(VisitorToken.status == status_filter)
    if dept_filter:
        query = query.filter(VisitorToken.department_id == dept_filter)
    if purpose_filter:
        query = query.filter(VisitorToken.purpose_id == purpose_filter)
    if search_q:
        query = query.filter(
            VisitorToken.token_code.ilike(f"%{search_q}%") |
            VisitorToken.visitor_name.ilike(f"%{search_q}%") |
            VisitorToken.visitor_phone.ilike(f"%{search_q}%")
        )

    visitor_records = query.order_by(VisitorToken.created_at.asc()).all()

    # Metrics for the selected date
    all_tokens_today = VisitorToken.query.filter_by(visit_date=selected_date).all()
    stats = {
        "total": len(all_tokens_today),
        "pending": sum(1 for t in all_tokens_today if t.status == "pending"),
        "approved": sum(1 for t in all_tokens_today if t.status == "approved"),
        "called": sum(1 for t in all_tokens_today if t.status == "called"),
        "completed": sum(1 for t in all_tokens_today if t.status == "completed"),
        "declined": sum(1 for t in all_tokens_today if t.status == "declined"),
        "missed": sum(1 for t in all_tokens_today if t.status == "missed"),
        "priority_pending": sum(1 for t in all_tokens_today if t.priority != "normal" and not t.priority_verified)
    }

    departments = Department.query.filter_by(active=True).order_by(Department.name).all()
    purposes = VisitorPurpose.query.filter_by(active=True).order_by(VisitorPurpose.display_order).all()
    counters = Counter.query.filter_by(active=True).order_by(Counter.name).all()

    return render_template(
        "admin/visitor_management.html",
        visitor_records=visitor_records,
        stats=stats,
        selected_date=selected_date.isoformat(),
        status_filter=status_filter,
        dept_filter=dept_filter,
        purpose_filter=purpose_filter,
        search_q=search_q,
        departments=departments,
        purposes=purposes,
        counters=counters
    )


@admin_bp.route("/visitor/<int:token_id>/action", methods=["POST"])
@login_required
@role_required("admin")
def visitor_token_action(token_id):
    """Handles admin actions on visitor tokens: approve, decline, call, complete, missed."""
    token = db.session.get(VisitorToken, token_id)
    if not token:
        flash("Visitor token not found.", "error")
        return redirect(url_for("admin.manage_visitors"))

    action = request.form.get("action", "").strip().lower()
    note = request.form.get("note", "").strip()

    allowed = ["approve", "decline", "call", "complete", "missed"]
    if action not in allowed:
        flash("Invalid action requested.", "error")
        return redirect(url_for("admin.manage_visitors", date=token.visit_date.isoformat()))

    if action == "approve":
        if token.status != "pending":
            flash("Only pending tokens can be approved.", "error")
            return redirect(url_for("admin.manage_visitors", date=token.visit_date.isoformat()))
        token.status = "approved"
        token.decline_reason = None
        flash(f"Visitor token {token.token_code} approved.", "success")

    elif action == "decline":
        if token.status not in ["pending", "approved"]:
            flash("This token cannot be declined now.", "error")
            return redirect(url_for("admin.manage_visitors", date=token.visit_date.isoformat()))
        if not note:
            flash("Please provide a reason when declining a visitor request.", "error")
            return redirect(url_for("admin.manage_visitors", date=token.visit_date.isoformat()))
        token.status = "declined"
        token.decline_reason = note
        token.admin_note = note
        flash(f"Visitor token {token.token_code} declined.", "success")

    elif action == "call":
        if token.status != "approved":
            flash("Only approved tokens can be called.", "error")
            return redirect(url_for("admin.manage_visitors", date=token.visit_date.isoformat()))
        if token.priority != "normal" and not token.priority_verified:
            flash("Special priority must be verified before calling this token.", "error")
            return redirect(url_for("admin.manage_visitors", date=token.visit_date.isoformat()))
        if not token.counter_id:
            flash("Please assign a counter before calling this visitor.", "error")
            return redirect(url_for("admin.manage_visitors", date=token.visit_date.isoformat()))

        token.status = "called"
        token.called_at = datetime.utcnow()
        flash(f"Visitor token {token.token_code} is now being called.", "success")

    elif action == "complete":
        if token.status != "called":
            flash("Only called tokens can be marked completed.", "error")
            return redirect(url_for("admin.manage_visitors", date=token.visit_date.isoformat()))
        token.status = "completed"
        token.completed_at = datetime.utcnow()
        flash(f"Visitor token {token.token_code} marked completed.", "success")

    elif action == "missed":
        if token.status not in ["approved", "called"]:
            flash("Only approved or called tokens can be marked missed.", "error")
            return redirect(url_for("admin.manage_visitors", date=token.visit_date.isoformat()))
        token.status = "missed"
        flash(f"Visitor token {token.token_code} marked as missed.", "warning")

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash("Could not update visitor token status.", "error")

    return redirect(url_for("admin.manage_visitors", date=token.visit_date.isoformat()))


@admin_bp.route("/visitor/<int:token_id>/assign-counter", methods=["POST"])
@login_required
@role_required("admin")
def assign_visitor_counter(token_id):
    """Assigns an approved visitor token to an active counter."""
    token = db.session.get(VisitorToken, token_id)
    if not token:
        flash("Visitor token not found.", "error")
        return redirect(url_for("admin.manage_visitors"))

    if token.status != "approved":
        flash("Only approved tokens can be assigned a counter.", "error")
        return redirect(url_for("admin.manage_visitors", date=token.visit_date.isoformat()))

    try:
        counter_id = int(request.form.get("counter_id", ""))
    except (ValueError, TypeError):
        flash("Please select a valid counter.", "error")
        return redirect(url_for("admin.manage_visitors", date=token.visit_date.isoformat()))

    counter = db.session.get(Counter, counter_id)
    if not counter or not counter.active:
        flash("Selected counter is unavailable.", "error")
        return redirect(url_for("admin.manage_visitors", date=token.visit_date.isoformat()))

    if counter.department_id != token.department_id:
        flash("Counter does not belong to this visitor's department.", "error")
        return redirect(url_for("admin.manage_visitors", date=token.visit_date.isoformat()))

    token.counter_id = counter.id
    try:
        db.session.commit()
        flash(f"Assigned {counter.name} to visitor token {token.token_code}.", "success")
    except Exception:
        db.session.rollback()
        flash("Could not assign counter.", "error")

    return redirect(url_for("admin.manage_visitors", date=token.visit_date.isoformat()))


@admin_bp.route("/visitor/<int:token_id>/verify-priority", methods=["POST"])
@login_required
@role_required("admin")
def verify_visitor_priority(token_id):
    """Verifies or rejects senior citizen / accessibility priority for a visitor."""
    token = db.session.get(VisitorToken, token_id)
    if not token:
        flash("Visitor token not found.", "error")
        return redirect(url_for("admin.manage_visitors"))

    decision = request.form.get("decision", "").strip().lower()
    if decision == "verify":
        token.priority_verified = True
        flash(f"Priority verified for {token.token_code}.", "success")
    else:
        token.priority = "normal"
        token.priority_verified = True
        flash(f"Priority rejected. {token.token_code} set to normal queue.", "warning")

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Could not update priority verification.", "error")

    return redirect(url_for("admin.manage_visitors", date=token.visit_date.isoformat()))


@admin_bp.route("/visitor/call-next", methods=["POST"])
@login_required
@role_required("admin")
def call_next_visitor():
    """Calls the next eligible visitor ticket for a designated counter."""
    try:
        counter_id = int(request.form.get("counter_id", ""))
    except (ValueError, TypeError):
        flash("Invalid counter selected.", "error")
        return redirect(url_for("admin.manage_visitors"))

    counter = db.session.get(Counter, counter_id)
    if not counter or not counter.active:
        flash("Counter is inactive or unavailable.", "error")
        return redirect(url_for("admin.manage_visitors"))

    # Eligible approved tokens for today at this counter
    today = date.today()
    eligible = (
        VisitorToken.query
        .filter(
            VisitorToken.counter_id == counter.id,
            VisitorToken.visit_date == today,
            VisitorToken.status == "approved"
        )
        .all()
    )

    if not eligible:
        flash(f"No approved visitor tokens waiting at {counter.name}.", "info")
        return redirect(url_for("admin.manage_visitors", date=today.isoformat()))

    # Sort matching queue priority & FIFO ordering
    eligible.sort(
        key=lambda tok: (
            0 if (tok.priority != "normal" and tok.priority_verified) else 1,
            tok.created_at or datetime.min,
            tok.id
        )
    )

    next_tok = eligible[0]

    # Verify priority requirement
    if next_tok.priority != "normal" and not next_tok.priority_verified:
        flash(f"Please verify special priority for token {next_tok.token_code} first.", "error")
        return redirect(url_for("admin.manage_visitors", date=today.isoformat()))

    next_tok.status = "called"
    next_tok.called_at = datetime.utcnow()

    try:
        db.session.commit()
        flash(f"Next visitor {next_tok.token_code} called at {counter.name}.", "success")
    except Exception:
        db.session.rollback()
        flash("Could not call next visitor.", "error")

    return redirect(url_for("admin.manage_visitors", date=today.isoformat()))


# ---------------------------------------------------------------------
# VISITOR CONTENT & NOTICE MANAGEMENT
# ---------------------------------------------------------------------

@admin_bp.route("/visitor-content")
@login_required
@role_required("admin")
def manage_visitor_content():
    """Admin interface for managing visit purposes, instructions, and notices."""
    purposes = VisitorPurpose.query.order_by(VisitorPurpose.display_order.asc()).all()
    departments = Department.query.filter_by(active=True).order_by(Department.name).all()
    instructions = (
        db.session.query(VisitorInstruction, VisitorPurpose, Department)
        .join(VisitorPurpose, VisitorInstruction.purpose_id == VisitorPurpose.id)
        .join(Department, VisitorInstruction.department_id == Department.id)
        .order_by(VisitorPurpose.name.asc(), Department.name.asc())
        .all()
    )
    notices = CampusNotice.query.order_by(CampusNotice.created_at.desc()).all()

    return render_template(
        "admin/visitor_content.html",
        purposes=purposes,
        departments=departments,
        instructions=instructions,
        notices=notices,
        today=date.today()
    )


@admin_bp.route("/visitor-purpose/save", methods=["POST"])
@login_required
@role_required("admin")
def save_visitor_purpose():
    """Creates or updates a configurable visit purpose."""
    purpose_id = request.form.get("purpose_id", type=int)
    name = request.form.get("name", "").strip()
    code = request.form.get("code", "").strip().lower()
    description = request.form.get("description", "").strip()
    icon = request.form.get("icon", "📋").strip()
    dept_id = request.form.get("default_department_id", type=int)
    order = request.form.get("display_order", 0, type=int)

    if not name or not code:
        flash("Purpose name and code slug are required.", "error")
        return redirect(url_for("admin.manage_visitor_content"))

    # Sanitize code
    clean_code = "".join(c if c.isalnum() or c == "-" else "-" for c in code).strip("-")

    if purpose_id:
        purpose = db.session.get(VisitorPurpose, purpose_id)
        if not purpose:
            flash("Purpose not found.", "error")
            return redirect(url_for("admin.manage_visitor_content"))
        purpose.name = name
        purpose.code = clean_code
        purpose.description = description
        purpose.icon = icon
        purpose.default_department_id = dept_id
        purpose.display_order = order
        flash("Purpose updated successfully.", "success")
    else:
        existing = VisitorPurpose.query.filter(
            (VisitorPurpose.name == name) | (VisitorPurpose.code == clean_code)
        ).first()
        if existing:
            flash("A purpose with that name or code already exists.", "error")
            return redirect(url_for("admin.manage_visitor_content"))

        purpose = VisitorPurpose(
            name=name,
            code=clean_code,
            description=description,
            icon=icon,
            default_department_id=dept_id,
            display_order=order,
            active=True
        )
        db.session.add(purpose)
        flash("New visit purpose added.", "success")

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Could not save visit purpose.", "error")

    return redirect(url_for("admin.manage_visitor_content"))


@admin_bp.route("/visitor-instruction/save", methods=["POST"])
@login_required
@role_required("admin")
def save_visitor_instruction():
    """
    Creates or updates department instructions for a specific purpose.
    Supports multiple purposes mapped to the same department.
    """
    purpose_id = request.form.get("purpose_id", type=int)
    department_id = request.form.get("department_id", type=int)
    procedure_steps = request.form.get("procedure_steps", "").strip()
    required_documents = request.form.get("required_documents", "").strip()
    visiting_hours = request.form.get("visiting_hours", "").strip()
    first_reporting_point = request.form.get("first_reporting_point", "").strip()
    important_notes = request.form.get("important_notes", "").strip()

    if not purpose_id or not department_id:
        flash("Please select both a purpose and department.", "error")
        return redirect(url_for("admin.manage_visitor_content"))

    instruction = VisitorInstruction.query.filter_by(
        purpose_id=purpose_id,
        department_id=department_id
    ).first()

    if not instruction:
        instruction = VisitorInstruction(
            purpose_id=purpose_id,
            department_id=department_id,
            procedure_steps=procedure_steps or "Report to Security Gate 1 for a visitor pass.",
            required_documents=required_documents or "Valid Government Photo ID Card.",
            visiting_hours=visiting_hours or "9:30 AM – 4:30 PM (Mon–Fri)",
            first_reporting_point=first_reporting_point or "Campus Reception Desk, Ground Floor",
            important_notes=important_notes,
            active=True
        )
        db.session.add(instruction)
        flash("New department visitor instructions added.", "success")
    else:
        instruction.procedure_steps = procedure_steps
        instruction.required_documents = required_documents
        instruction.visiting_hours = visiting_hours
        instruction.first_reporting_point = first_reporting_point
        instruction.important_notes = important_notes
        flash("Department visitor instructions updated.", "success")

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Could not save instructions.", "error")

    return redirect(url_for("admin.manage_visitor_content"))


@admin_bp.route("/notice/save", methods=["POST"])
@login_required
@role_required("admin")
def save_notice():
    """Publishes or updates a campus announcement notice with expiry date."""
    notice_id = request.form.get("notice_id", type=int)
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    category = request.form.get("category", "General").strip()
    dept_id = request.form.get("department_id", type=int)
    expiry_date_str = request.form.get("expiry_date", "").strip()

    if not title or not content:
        flash("Title and notice content are required.", "error")
        return redirect(url_for("admin.manage_visitor_content"))

    expiry_date = None
    if expiry_date_str:
        try:
            expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    if notice_id:
        notice = db.session.get(CampusNotice, notice_id)
        if not notice:
            flash("Notice not found.", "error")
            return redirect(url_for("admin.manage_visitor_content"))
        notice.title = title
        notice.content = content
        notice.category = category
        notice.department_id = dept_id
        notice.expiry_date = expiry_date
        flash("Notice updated successfully.", "success")
    else:
        notice = CampusNotice(
            title=title,
            content=content,
            category=category,
            department_id=dept_id,
            expiry_date=expiry_date,
            is_active=True
        )
        db.session.add(notice)
        flash("New announcement notice published.", "success")

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Could not save notice.", "error")

    return redirect(url_for("admin.manage_visitor_content"))


@admin_bp.route("/notice/<int:notice_id>/toggle", methods=["POST"])
@login_required
@role_required("admin")
def toggle_notice(notice_id):
    """Activates or deactivates an announcement notice."""
    notice = db.session.get(CampusNotice, notice_id)
    if not notice:
        flash("Notice not found.", "error")
    else:
        notice.is_active = not notice.is_active
        db.session.commit()
        state = "activated" if notice.is_active else "deactivated"
        flash(f"Notice '{notice.title}' {state}.", "success")
    return redirect(url_for("admin.manage_visitor_content"))


# ---------------------------------------------------------------------
# CAMPUS LOCATIONS & FLOOR PLANS MANAGEMENT
# ---------------------------------------------------------------------

@admin_bp.route("/campus-locations")
@login_required
@role_required("admin")
def manage_campus_locations():
    """Admin interface for managing GPS map locations and floor plan markers."""
    locations = CampusLocation.query.order_by(CampusLocation.building, CampusLocation.name).all()
    floor_plans = FloorPlan.query.order_by(FloorPlan.building, FloorPlan.floor).all()
    departments = Department.query.filter_by(active=True).order_by(Department.name).all()
    counters = Counter.query.filter_by(active=True).order_by(Counter.name).all()

    return render_template(
        "admin/visitor_locations.html",
        locations=locations,
        floor_plans=floor_plans,
        departments=departments,
        counters=counters
    )


@admin_bp.route("/campus-location/save", methods=["POST"])
@login_required
@role_required("admin")
def save_campus_location():
    """Creates or updates a campus location marker for outdoor/indoor maps."""
    loc_id = request.form.get("location_id", type=int)
    name = request.form.get("name", "").strip()
    building = request.form.get("building", "").strip()
    floor = request.form.get("floor", "").strip()
    room = request.form.get("room", "").strip()
    dept_id = request.form.get("department_id", type=int)
    counter_id = request.form.get("counter_id", type=int)
    lat_str = request.form.get("latitude", "").strip()
    lng_str = request.form.get("longitude", "").strip()
    floor_plan_id = request.form.get("floor_plan_id", type=int)
    marker_x_str = request.form.get("marker_x", "").strip()
    marker_y_str = request.form.get("marker_y", "").strip()
    directions = request.form.get("directions", "").strip()

    if not name or not building or not floor:
        flash("Location name, building, and floor level are required.", "error")
        return redirect(url_for("admin.manage_campus_locations"))

    lat = float(lat_str) if lat_str else None
    lng = float(lng_str) if lng_str else None
    marker_x = float(marker_x_str) if marker_x_str else None
    marker_y = float(marker_y_str) if marker_y_str else None

    if loc_id:
        loc = db.session.get(CampusLocation, loc_id)
        if not loc:
            flash("Location not found.", "error")
            return redirect(url_for("admin.manage_campus_locations"))
        loc.name = name
        loc.building = building
        loc.floor = floor
        loc.room = room
        loc.department_id = dept_id
        loc.counter_id = counter_id
        loc.latitude = lat
        loc.longitude = lng
        loc.floor_plan_id = floor_plan_id
        loc.marker_x = marker_x
        loc.marker_y = marker_y
        loc.directions = directions
        flash("Location updated successfully.", "success")
    else:
        loc = CampusLocation(
            name=name,
            building=building,
            floor=floor,
            room=room,
            department_id=dept_id,
            counter_id=counter_id,
            latitude=lat,
            longitude=lng,
            floor_plan_id=floor_plan_id,
            marker_x=marker_x,
            marker_y=marker_y,
            directions=directions,
            is_demo=True,
            active=True
        )
        db.session.add(loc)
        flash("New campus location marker added.", "success")

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Could not save campus location.", "error")

    return redirect(url_for("admin.manage_campus_locations"))


@admin_bp.route("/floor-plan/save", methods=["POST"])
@login_required
@role_required("admin")
def save_floor_plan():
    """Uploads a floor plan image or saves vector SVG blueprint."""
    plan_id = request.form.get("floor_plan_id", type=int)
    building = request.form.get("building", "").strip()
    floor = request.form.get("floor", "").strip()
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()

    if not building or not floor or not title:
        flash("Building, floor, and title are required for floor plans.", "error")
        return redirect(url_for("admin.manage_campus_locations"))

    image_filename = None
    if "image_file" in request.files:
        file = request.files["image_file"]
        if file and file.filename and allowed_file(file.filename):
            base_fname = secure_filename(file.filename)
            unique_fname = f"{int(datetime.utcnow().timestamp())}_{base_fname}"
            upload_path = os.path.join(current_app.config["UPLOAD_FOLDER"], unique_fname)
            try:
                file.save(upload_path)
                image_filename = unique_fname
            except Exception as e:
                flash(f"Error saving uploaded image: {e}", "error")

    if plan_id:
        plan = db.session.get(FloorPlan, plan_id)
        if not plan:
            flash("Floor plan not found.", "error")
            return redirect(url_for("admin.manage_campus_locations"))
        plan.building = building
        plan.floor = floor
        plan.title = title
        plan.description = description
        if image_filename:
            plan.image_filename = image_filename
        flash("Floor plan updated.", "success")
    else:
        plan = FloorPlan(
            building=building,
            floor=floor,
            title=title,
            image_filename=image_filename,
            description=description
        )
        db.session.add(plan)
        flash("New floor plan registered.", "success")

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Could not save floor plan.", "error")

    return redirect(url_for("admin.manage_campus_locations"))
