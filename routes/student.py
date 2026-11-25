
from datetime import date, datetime, timedelta
import secrets

from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash, jsonify
)

from flask_login import login_required, current_user

from models import (
    db, Service, Department, Token,
    Counter, Notification
)
from services.queue_reentry import (
    AUTO_REENTRY_NOTE_PREFIX,
    AUTO_REENTRY_USED_PREFIX,
)
from queue_optimization import recommend_counter, schedule_tokens
from services.waiting_time import predict_ml_waiting_time

from routes.auth import role_required


student_bp = Blueprint("student", __name__, url_prefix="/student")


# --------------------------------------------------
# QUEUE POSITION CALCULATION
# --------------------------------------------------

def get_queue_positions():

    approved_tokens = (
        Token.query
        .filter(
            Token.status == "approved",
            Token.counter_id.isnot(None)
        )
        .all()
    )

    queue_groups = {}

    for token in approved_tokens:
        group_key = (token.counter_id, token.visit_date)
        queue_groups.setdefault(group_key, []).append(token)

    queue_positions = {}

    for tokens in queue_groups.values():

        tokens = schedule_tokens(tokens)

        for position, token in enumerate(tokens, start=1):
            queue_positions[token.id] = position

    return queue_positions


def get_counter_recommendations(token_records):
    """Recommend a counter only for pending or unassigned student tokens."""
    candidates = [
        (token, service, department)
        for token, service, department, _counter in token_records
        if (
            token.status in ("pending", "approved")
            and token.counter_id is None
            and service.active
            and department.active
        )
    ]
    if not candidates:
        return {}

    visit_dates = {token.visit_date for token, _, _ in candidates}
    counters = (
        Counter.query
        .join(Department, Counter.department_id == Department.id)
        .filter(Counter.active.is_(True), Department.active.is_(True))
        .order_by(Counter.id)
        .all()
    )
    waiting_tokens = (
        Token.query
        .filter(
            Token.visit_date.in_(visit_dates),
            Token.status.in_(("approved", "called"))
        )
        .all()
    )
    service_minutes = {
        service.id: service.estimated_minutes
        for service in Service.query.all()
    }

    recommendations = {}
    for token, service, department in candidates:
        recommendations[token.id] = recommend_counter(
            counters,
            waiting_tokens,
            department.id,
            service_minutes,
            token.visit_date,
            exclude_token_id=token.id,
            priority=token.priority,
            priority_verified=token.priority_verified,
        )
    return recommendations


def get_waiting_estimates(token_records, queue_positions):
    """Build student-only waiting estimates without querying visitor queues."""
    estimates = {}
    for token, service, department, counter in token_records:
        if token.status not in ("approved", "called"):
            continue

        active_counters = (
            Counter.query
            .filter(
                Counter.department_id == department.id,
                Counter.active.is_(True),
            )
            .count()
        )
        queue_position = queue_positions.get(token.id)
        people_ahead = (
            max(0, queue_position - 1)
            if queue_position
            else 0
        )
        estimates[token.id] = predict_ml_waiting_time(
            department_id=department.id,
            counter_id=counter.id if counter else None,
            queue_position=queue_position,
            priority=token.priority,
            average_service_minutes=service.estimated_minutes or 15,
            active_counters=active_counters,
            estimated_workload_ahead=(
                people_ahead * max(5, service.estimated_minutes or 15)
            ),
            arrival_datetime=datetime.now(),
            queue_category="student",
            service_category=service.name,
        )
    return estimates


# --------------------------------------------------
# STUDENT DASHBOARD
# --------------------------------------------------

@student_bp.route("/dashboard")
@login_required
@role_required("student")
def dashboard():

    services = (
        db.session.query(Service, Department)
        .join(Department, Service.department_id == Department.id)
        .filter(
            Service.active.is_(True),
            Department.active.is_(True)
        )
        .order_by(Department.name, Service.name)
        .all()
    )

    token_records = (
        db.session.query(Token, Service, Department, Counter)
        .join(Service, Token.service_id == Service.id)
        .join(Department, Service.department_id == Department.id)
        .outerjoin(Counter, Token.counter_id == Counter.id)
        .filter(Token.user_id == current_user.id)
        .order_by(Token.created_at.desc())
        .all()
    )

    active_statuses = ["pending", "approved", "called"]

    active_count = sum(
        1 for record in token_records
        if record[0].status in active_statuses
    )

    completed_count = sum(
        1 for record in token_records
        if record[0].status == "completed"
    )

    queue_positions = get_queue_positions()
    counter_recommendations = get_counter_recommendations(token_records)
    waiting_estimates = get_waiting_estimates(
        token_records,
        queue_positions,
    )

    notifications = (
        Notification.query
        .filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(10)
        .all()
    )

    unread_notification_count = (
        Notification.query
        .filter_by(
            user_id=current_user.id,
            is_read=False
        )
        .count()
    )
    tokens_by_id = {record[0].id: record[0] for record in token_records}
    automatic_reentry_ids = set()
    for token, _service, _department, _counter in token_records:
        parent = tokens_by_id.get(token.rescheduled_from)
        parent_note = parent.admin_note if parent else ""
        if (
            (token.admin_note or "").startswith(AUTO_REENTRY_NOTE_PREFIX)
            or (
                (parent_note or "").startswith(AUTO_REENTRY_USED_PREFIX)
                and f"created as {token.code}." in parent_note
            )
        ):
            automatic_reentry_ids.add(token.id)

    return render_template(
        "student_dashboard.html",
        services=services,
        token_records=token_records,
        active_count=active_count,
        completed_count=completed_count,
        queue_positions=queue_positions,
        counter_recommendations=counter_recommendations,
        waiting_estimates=waiting_estimates,
        automatic_reentry_ids=automatic_reentry_ids,
        notifications=notifications,
        unread_notification_count=unread_notification_count,
        today_date=date.today().isoformat(),
        max_visit_date=(
            date.today() + timedelta(days=30)
        ).isoformat()
    )


# --------------------------------------------------
# LIVE DASHBOARD UPDATES
# --------------------------------------------------

@student_bp.route("/updates")
@login_required
@role_required("student")
def dashboard_updates():

    token_records = (
        db.session.query(Token, Service, Department, Counter)
        .join(Service, Token.service_id == Service.id)
        .join(Department, Service.department_id == Department.id)
        .outerjoin(Counter, Token.counter_id == Counter.id)
        .filter(Token.user_id == current_user.id)
        .order_by(Token.created_at.desc())
        .all()
    )

    queue_positions = get_queue_positions()
    counter_recommendations = get_counter_recommendations(token_records)
    waiting_estimates = get_waiting_estimates(
        token_records,
        queue_positions,
    )

    active_statuses = ["pending", "approved", "called"]

    active_count = sum(
        1 for record in token_records
        if record[0].status in active_statuses
    )

    completed_count = sum(
        1 for record in token_records
        if record[0].status == "completed"
    )

    tokens = []

    for token, service, department, counter in token_records:
        recommendation = counter_recommendations.get(token.id)
        waiting_estimate = waiting_estimates.get(token.id)

        tokens.append({
            "id": token.id,
            "status": token.status,
            "queue_position": queue_positions.get(token.id),
            "has_counter": counter is not None,
            "counter_name": counter.name if counter else None,
            "building": counter.building if counter else None,
            "floor": counter.floor if counter else None,
            "room": counter.room if counter else None,
            "directions": counter.directions if counter else None,
            "decline_reason": token.decline_reason,
            "recommended_counter_name": (
                recommendation.name if recommendation else None
            ),
            "waiting_estimate": waiting_estimate,
        })

    notifications = (
        Notification.query
        .filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(10)
        .all()
    )

    unread_count = (
        Notification.query
        .filter_by(
            user_id=current_user.id,
            is_read=False
        )
        .count()
    )

    notification_data = []

    for notification in notifications:

        notification_data.append({
            "id": notification.id,
            "message": notification.message,
            "is_read": notification.is_read,
            "created_at": (
                notification.created_at.strftime(
                    "%d %b %Y, %I:%M %p"
                )
                if notification.created_at else ""
            )
        })

    return jsonify({
        "tokens": tokens,
        "active_count": active_count,
        "completed_count": completed_count,
        "unread_count": unread_count,
        "notifications": notification_data
    })


# --------------------------------------------------
# MARK NOTIFICATION AS READ
# --------------------------------------------------

@student_bp.route(
    "/notification/<int:notification_id>/read",
    methods=["POST"]
)
@login_required
@role_required("student")
def mark_notification_read(notification_id):

    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=current_user.id
    ).first_or_404()

    notification.is_read = True

    db.session.commit()

    flash("Notification marked as read.", "success")

    return redirect(url_for("student.dashboard"))


# --------------------------------------------------
# BOOK A NEW TOKEN
# --------------------------------------------------

@student_bp.route("/book", methods=["GET", "POST"])
@login_required
@role_required("student")
def book_token():

    today = date.today()
    last_date = today + timedelta(days=30)

    if request.method == "POST":

        try:
            service_id = int(
                request.form.get("service_id", "")
            )

            visit_date = datetime.strptime(
                request.form.get("visit_date", ""),
                "%Y-%m-%d"
            ).date()

        except (ValueError, TypeError):

            flash(
                "Please select a valid service and date.",
                "error"
            )

            return redirect(
                url_for("student.book_token")
            )

        priority = request.form.get(
            "priority",
            "normal"
        )

        allowed_priorities = [
            "normal",
            "accessibility",
            "urgent",
            "emergency"
        ]

        if priority not in allowed_priorities:

            flash(
                "Invalid priority selection.",
                "error"
            )

            return redirect(
                url_for("student.book_token")
            )

        if visit_date < today or visit_date > last_date:

            flash(
                "Please select a date within the next 30 days.",
                "error"
            )

            return redirect(
                url_for("student.book_token")
            )

        service = Service.query.filter_by(
            id=service_id,
            active=True
        ).first()

        if not service:

            flash(
                "The selected service is unavailable.",
                "error"
            )

            return redirect(
                url_for("student.book_token")
            )

        department = (
            Department.query
            .filter_by(
                id=service.department_id,
                active=True
            )
            .with_for_update()
            .first()
        )

        if not department:

            flash(
                "The selected department is unavailable.",
                "error"
            )

            return redirect(
                url_for("student.book_token")
            )

        current_bookings = (
            db.session.query(Token)
            .join(Service, Token.service_id == Service.id)
            .filter(
                Service.department_id == department.id,
                Token.visit_date == visit_date,
                Token.status != "declined"
            )
            .count()
        )

        daily_limit = department.daily_limit or 100

        if current_bookings >= daily_limit:

            flash(
                "Sorry, this department has reached its daily "
                "token limit for the selected date. "
                "Please choose another date.",
                "error"
            )

            return redirect(
                url_for("student.book_token")
            )

        token_code = (
            f"QF-{visit_date.strftime('%Y%m%d')}-"
            f"{secrets.token_hex(3).upper()}"
        )

        new_token = Token(
            code=token_code,
            user_id=current_user.id,
            service_id=service.id,
            visit_date=visit_date,
            status="pending",
            priority=priority,
            priority_verified=(priority == "normal")
        )

        try:

            db.session.add(new_token)
            db.session.flush()

            notification = Notification(
                user_id=current_user.id,
                message=(
                    f"Your token {token_code} has been booked. "
                    "It is awaiting administrator approval."
                )
            )

            db.session.add(notification)
            db.session.commit()

        except Exception:

            db.session.rollback()

            flash(
                "We could not complete your booking. Please try again.",
                "error"
            )

            return redirect(
                url_for("student.book_token")
            )

        if priority == "normal":

            flash(
                f"Token {token_code} booked successfully!",
                "success"
            )

        else:

            flash(
                f"Token {token_code} booked. Your priority request "
                "is awaiting administrator verification.",
                "success"
            )

        return redirect(
            url_for("student.dashboard")
        )


    services = (
        db.session.query(Service, Department)
        .join(Department, Service.department_id == Department.id)
        .filter(
            Service.active.is_(True),
            Department.active.is_(True)
        )
        .order_by(Department.name, Service.name)
        .all()
    )

    return render_template(
        "book_token.html",
        services=services,
        today=today.isoformat(),
        last_date=last_date.isoformat()
    )


# --------------------------------------------------
# RESCHEDULE A MISSED TOKEN
# --------------------------------------------------

@student_bp.route(
    "/token/<int:token_id>/reschedule",
    methods=["POST"]
)
@login_required
@role_required("student")
def reschedule_token(token_id):

    # Get only the logged-in student's token.
    original_token = Token.query.filter_by(
        id=token_id,
        user_id=current_user.id
    ).first_or_404()

    # Only missed tokens can be rescheduled.
    if original_token.status != "missed":

        flash(
            "Only missed tokens can be rescheduled.",
            "error"
        )

        return redirect(
            url_for("student.dashboard")
        )

    # Prevent duplicate rescheduling.
    existing_reschedule = Token.query.filter_by(
        rescheduled_from=original_token.id
    ).first()

    if existing_reschedule:

        flash(
            f"This token has already been rescheduled as "
            f"{existing_reschedule.code}.",
            "error"
        )

        return redirect(
            url_for("student.dashboard")
        )

    # Validate selected date.
    try:

        new_visit_date = datetime.strptime(
            request.form.get("visit_date", ""),
            "%Y-%m-%d"
        ).date()

    except (ValueError, TypeError):

        flash(
            "Please select a valid rescheduling date.",
            "error"
        )

        return redirect(
            url_for("student.dashboard")
        )

    today = date.today()
    last_date = today + timedelta(days=30)

    if new_visit_date < today or new_visit_date > last_date:

        flash(
            "Choose a new date within the next 30 days.",
            "error"
        )

        return redirect(
            url_for("student.dashboard")
        )

    # Check original service.
    service = Service.query.filter_by(
        id=original_token.service_id,
        active=True
    ).first()

    if not service:

        flash(
            "The original service is no longer available.",
            "error"
        )

        return redirect(
            url_for("student.dashboard")
        )

    # Check department.
    department = (
        Department.query
        .filter_by(
            id=service.department_id,
            active=True
        )
        .with_for_update()
        .first()
    )

    if not department:

        flash(
            "The department is currently unavailable.",
            "error"
        )

        return redirect(
            url_for("student.dashboard")
        )

    # Check daily booking limit.
    current_bookings = (
        db.session.query(Token)
        .join(Service, Token.service_id == Service.id)
        .filter(
            Service.department_id == department.id,
            Token.visit_date == new_visit_date,
            Token.status != "declined"
        )
        .count()
    )

    daily_limit = department.daily_limit or 100

    if current_bookings >= daily_limit:

        flash(
            "The department has reached its daily token limit "
            "for that date. Please choose another date.",
            "error"
        )

        return redirect(
            url_for("student.dashboard")
        )

    # Generate a fresh token number.
    token_code = (
        f"QF-{new_visit_date.strftime('%Y%m%d')}-"
        f"{secrets.token_hex(3).upper()}"
    )

    # Preserve priority, but re-verify non-normal requests.
    new_priority = original_token.priority or "normal"

    new_token = Token(
        code=token_code,
        user_id=current_user.id,
        service_id=service.id,
        visit_date=new_visit_date,
        status="pending",
        priority=new_priority,
        priority_verified=(new_priority == "normal"),
        rescheduled_from=original_token.id
    )

    try:

        db.session.add(new_token)
        db.session.flush()

        notification = Notification(
            user_id=current_user.id,
            message=(
                f"Your missed token {original_token.code} has been "
                f"rescheduled as {token_code} for "
                f"{new_visit_date.strftime('%d %b %Y')}. "
                "The new token is awaiting administrator approval."
            )
        )

        db.session.add(notification)
        db.session.commit()

    except Exception:

        db.session.rollback()

        flash(
            "We could not reschedule your token. Please try again.",
            "error"
        )

        return redirect(
            url_for("student.dashboard")
        )

    flash(
        f"Your new token {token_code} has been created. "
        "It is awaiting administrator approval.",
        "success"
    )

    return redirect(
        url_for("student.dashboard")
    )


@student_bp.route(
    "/token/<int:token_id>/reschedule-date",
    methods=["POST"]
)
@login_required
@role_required("student")
def reschedule_active_token(token_id):

    token_preview = Token.query.filter_by(
        id=token_id,
        user_id=current_user.id
    ).first_or_404()

    if token_preview.status not in ("pending", "approved"):
        flash(
            "Only Pending or Approved tokens can be rescheduled.",
            "error"
        )
        return redirect(url_for("student.dashboard"))

    try:
        new_visit_date = datetime.strptime(
            request.form.get("visit_date", ""),
            "%Y-%m-%d"
        ).date()
    except (ValueError, TypeError):
        flash("Please select a valid new visit date.", "error")
        return redirect(url_for("student.dashboard"))

    today = date.today()
    last_date = today + timedelta(days=30)
    if new_visit_date < today or new_visit_date > last_date:
        flash(
            "Choose a new date from today through the next 30 days.",
            "error"
        )
        return redirect(url_for("student.dashboard"))

    if new_visit_date == token_preview.visit_date:
        flash("Choose a date different from the current visit date.", "error")
        return redirect(url_for("student.dashboard"))

    service = Service.query.filter_by(
        id=token_preview.service_id,
        active=True
    ).first()
    if not service:
        flash("The token's service is no longer available.", "error")
        return redirect(url_for("student.dashboard"))

    department = (
        Department.query
        .filter_by(id=service.department_id, active=True)
        .with_for_update()
        .first()
    )
    if not department:
        flash("The token's department is no longer available.", "error")
        return redirect(url_for("student.dashboard"))

    token = (
        Token.query
        .filter_by(id=token_id, user_id=current_user.id)
        .populate_existing()
        .with_for_update()
        .first()
    )
    if (
        not token
        or token.status not in ("pending", "approved")
        or token.service_id != service.id
    ):
        flash(
            "This token can no longer be rescheduled. Refresh your dashboard.",
            "error"
        )
        return redirect(url_for("student.dashboard"))

    if new_visit_date == token.visit_date:
        flash("Choose a date different from the current visit date.", "error")
        return redirect(url_for("student.dashboard"))

    current_bookings = (
        db.session.query(Token)
        .join(Service, Token.service_id == Service.id)
        .filter(
            Service.department_id == department.id,
            Token.visit_date == new_visit_date,
            Token.status != "declined"
        )
        .count()
    )
    daily_limit = department.daily_limit or 100
    if current_bookings >= daily_limit:
        flash(
            "The department has reached its daily token limit for that date. "
            "Please choose another date.",
            "error"
        )
        return redirect(url_for("student.dashboard"))

    old_visit_date = token.visit_date
    token.visit_date = new_visit_date
    db.session.add(Notification(
        user_id=current_user.id,
        message=(
            f"Your token {token.code} was rescheduled from "
            f"{old_visit_date.strftime('%d %b %Y')} to "
            f"{new_visit_date.strftime('%d %b %Y')}. "
            "Your token status and priority are unchanged."
        )
    ))

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("We could not reschedule your token. Please try again.", "error")
        return redirect(url_for("student.dashboard"))

    flash(
        f"Token {token.code} rescheduled to "
        f"{new_visit_date.strftime('%d %b %Y')}.",
        "success"
    )
    return redirect(url_for("student.dashboard"))
