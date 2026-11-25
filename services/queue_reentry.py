"""Server-side handling for same-day student queue re-entry."""

import logging
import secrets
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import or_

from models import (
    db, Token, User, Service, Department, Counter, Notification
)
from queue_optimization import recommend_counter, schedule_tokens


logger = logging.getLogger(__name__)

GRACE_PERIOD = timedelta(minutes=2)
AUTO_REENTRY_NOTE_PREFIX = "[AUTO_REENTRY]"
AUTO_REENTRY_USED_PREFIX = "[AUTO_REENTRY_USED]"
AUTO_REENTRY_EXCEPTION_PREFIX = "[AUTO_REENTRY_EXCEPTION]"


def _utc_naive(value):
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _append_marker(existing_note, marker, message):
    note = f"{marker} {message}"
    if existing_note:
        note += f"\nPrevious note: {existing_note}"
    return note


def _notify(user_id, message):
    db.session.add(Notification(user_id=user_id, message=message))


def _record_missed(token, message, marker=AUTO_REENTRY_EXCEPTION_PREFIX):
    token.status = "missed"
    token.admin_note = _append_marker(token.admin_note, marker, message)
    _notify(
        token.user_id,
        f"Your turn for token {token.code} was missed. {message}"
    )


def _automatic_reentry_exists(user_id, visit_date):
    return (
        Token.query
        .filter(
            Token.user_id == user_id,
            Token.visit_date == visit_date,
            or_(
                Token.admin_note.like(f"{AUTO_REENTRY_USED_PREFIX}%"),
                Token.admin_note.like(f"{AUTO_REENTRY_NOTE_PREFIX}%"),
            )
        )
        .first()
        is not None
    )


def _find_reentry_counter(token, department, now):
    counters = (
        Counter.query
        .filter_by(department_id=department.id, active=True)
        .order_by(Counter.id)
        .with_for_update()
        .all()
    )
    if not counters:
        return None

    service_minutes = {
        service_id: minutes
        for service_id, minutes in db.session.query(
            Service.id,
            Service.estimated_minutes
        ).filter(Service.department_id == department.id).all()
    }
    active_queue = (
        Token.query
        .filter(
            Token.visit_date == token.visit_date,
            Token.status.in_(("approved", "called")),
            Token.counter_id.in_([counter.id for counter in counters])
        )
        .all()
    )
    return recommend_counter(
        counters,
        active_queue,
        department.id,
        service_minutes,
        token.visit_date,
        now=now,
        exclude_token_id=token.id,
        priority=token.priority,
        priority_verified=token.priority_verified,
    )


def _process_expired_token(token_id, now):
    token = (
        Token.query
        .filter_by(id=token_id)
        .with_for_update()
        .first()
    )
    if (
        not token
        or token.status != "called"
        or not token.called_at
        or _utc_naive(token.called_at) > now - GRACE_PERIOD
    ):
        db.session.rollback()
        return "skipped"

    token.status = "missed"

    student = (
        User.query
        .filter_by(id=token.user_id)
        .with_for_update()
        .first()
    )
    if not student:
        _record_missed(
            token,
            "Automatic re-entry was not created because the student record "
            "is unavailable."
        )
        db.session.commit()
        return "missed"

    if token.visit_date != date.today():
        _record_missed(
            token,
            "Automatic re-entry was not created because this is not the "
            "token's visit date."
        )
        db.session.commit()
        return "missed"

    if _automatic_reentry_exists(token.user_id, token.visit_date):
        _record_missed(
            token,
            "No second automatic re-entry was created because one has "
            "already been used today."
        )
        db.session.commit()
        return "missed"

    service = db.session.get(Service, token.service_id)
    department = None
    if service:
        department = (
            Department.query
            .filter_by(id=service.department_id)
            .with_for_update()
            .first()
        )

    if not service or not service.active or not department or not department.active:
        _record_missed(
            token,
            "Automatic re-entry was not created because the original "
            "service or department is unavailable."
        )
        db.session.commit()
        return "missed"

    original_counter = db.session.get(Counter, token.counter_id)
    if (
        original_counter
        and original_counter.department_id != department.id
    ):
        _record_missed(
            token,
            "Automatic re-entry was not created because the original "
            "counter no longer matches the service department."
        )
        db.session.commit()
        return "missed"

    daily_limit = department.daily_limit or 100
    current_bookings = (
        db.session.query(Token)
        .join(Service, Token.service_id == Service.id)
        .filter(
            Service.department_id == department.id,
            Token.visit_date == token.visit_date,
            Token.status != "declined"
        )
        .count()
    )
    if current_bookings >= daily_limit:
        _record_missed(
            token,
            "Automatic re-entry could not be created because the "
            "department's daily token limit has been reached."
        )
        db.session.commit()
        return "missed"

    counter = _find_reentry_counter(token, department, now)
    if not counter:
        _record_missed(
            token,
            "Automatic re-entry could not be created because no active "
            "counter is available for this department."
        )
        db.session.commit()
        return "missed"

    token_code = (
        f"QF-{token.visit_date.strftime('%Y%m%d')}-"
        f"{secrets.token_hex(3).upper()}"
    )
    new_token = Token(
        code=token_code,
        user_id=token.user_id,
        service_id=token.service_id,
        counter_id=counter.id,
        visit_date=token.visit_date,
        status="approved",
        priority=token.priority,
        priority_verified=token.priority_verified,
        rescheduled_from=token.id,
        admin_note=(
            f"{AUTO_REENTRY_NOTE_PREFIX} Automatically re-entered after "
            f"missed token {token.code}."
        )
    )

    try:
        with db.session.begin_nested():
            db.session.add(new_token)
            db.session.flush()
    except Exception:
        logger.exception(
            "Could not insert automatic re-entry for missed token %s",
            token_id
        )
        _record_missed(
            token,
            "Automatic re-entry could not be created because token "
            "creation failed. An administrator should review this token."
        )
        db.session.commit()
        return "missed"

    try:
        token.admin_note = _append_marker(
            token.admin_note,
            AUTO_REENTRY_USED_PREFIX,
            f"Automatic re-entry created as {new_token.code}."
        )

        waiting_tokens = (
            Token.query
            .filter(
                Token.counter_id == counter.id,
                Token.visit_date == token.visit_date,
                Token.status == "approved"
            )
            .all()
        )
        ordered_tokens = schedule_tokens(waiting_tokens, now=now)
        queue_position = next(
            position
            for position, queued_token in enumerate(ordered_tokens, start=1)
            if queued_token.id == new_token.id
        )

        _notify(
            token.user_id,
            f"Your missed token {token.code} was automatically re-entered "
            f"as {new_token.code}. You are now #{queue_position} at "
            f"{counter.name}; your original priority is preserved."
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception(
            "Could not create automatic re-entry for missed token %s",
            token_id
        )
        return "error"

    return "reentered"


def process_expired_called_tokens(now=None):
    """Mark expired calls missed and create eligible same-day re-entries."""
    now = _utc_naive(now or datetime.now(timezone.utc))
    cutoff = now - GRACE_PERIOD
    due_ids = [
        token_id
        for (token_id,) in (
            db.session.query(Token.id)
            .filter(
                Token.status == "called",
                Token.called_at.isnot(None),
                Token.called_at <= cutoff
            )
            .order_by(Token.called_at, Token.id)
            .all()
        )
    ]
    db.session.rollback()

    results = {"reentered": 0, "missed": 0, "skipped": 0, "error": 0}
    for token_id in due_ids:
        try:
            result = _process_expired_token(token_id, now)
            results[result] += 1
        except Exception:
            db.session.rollback()
            logger.exception(
                "Could not process expired called token %s",
                token_id
            )
            results["error"] += 1
    return results


def process_expired_called_token(token_id, now=None):
    """Process one expired call, for the scheduler or an admin override."""
    now = _utc_naive(now or datetime.now(timezone.utc))
    try:
        return _process_expired_token(token_id, now)
    except Exception:
        db.session.rollback()
        logger.exception(
            "Could not process expired called token %s",
            token_id
        )
        return "error"
