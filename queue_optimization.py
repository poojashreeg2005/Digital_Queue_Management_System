"""Counter allocation and queue scheduling helpers for QueueFlow."""

from datetime import datetime, timezone


ACTIVE_QUEUE_STATUSES = ("approved", "called")
WAITING_STATUS = "approved"
DEFAULT_SERVICE_MINUTES = 15
DEFAULT_AGING_MINUTES = 30

PRIORITY_RANKS = {
    "emergency": 0,
    "urgent": 1,
    "accessibility": 2,
    "normal": 3,
}


def _utc_naive(value):
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _service_minutes(service_id, service_minutes_by_id):
    value = service_minutes_by_id.get(service_id)
    try:
        minutes = int(value)
        return minutes if minutes > 0 else DEFAULT_SERVICE_MINUTES
    except (TypeError, ValueError):
        return DEFAULT_SERVICE_MINUTES


def calculate_counter_workloads(
    counters,
    tokens,
    service_minutes_by_id,
    visit_date,
    now=None,
    available_counter_ids=None,
):
    """Return counter waiting/in-service counts and estimated workload."""
    now = _utc_naive(now or datetime.now(timezone.utc))
    by_counter = {counter.id: counter for counter in counters}
    workloads = {
        counter.id: {
            "counter": counter,
            "counter_id": counter.id,
            "available": (
                counter.active
                and (
                    available_counter_ids is None
                    or counter.id in available_counter_ids
                )
            ),
            "waiting_count": 0,
            "in_service_count": 0,
            "workload_minutes": 0,
            "allocation_status": "balanced",
        }
        for counter in counters
    }

    for token in tokens:
        if (
            token.counter_id not in by_counter
            or token.visit_date != visit_date
            or token.status not in ACTIVE_QUEUE_STATUSES
        ):
            continue

        service_duration = _service_minutes(
            token.service_id,
            service_minutes_by_id,
        )
        if token.status == WAITING_STATUS:
            workloads[token.counter_id]["waiting_count"] += 1
            workloads[token.counter_id]["workload_minutes"] += service_duration
        else:
            workloads[token.counter_id]["in_service_count"] += 1
            called_at = _utc_naive(token.called_at)
            remaining = service_duration
            if called_at is not None:
                elapsed = max(0, int((now - called_at).total_seconds() // 60))
                remaining = max(0, service_duration - elapsed)
            workloads[token.counter_id]["workload_minutes"] += remaining

    active_by_department = {}
    for workload in workloads.values():
        counter = workload["counter"]
        if workload["available"]:
            active_by_department.setdefault(counter.department_id, []).append(
                workload
            )

    for department_workloads in active_by_department.values():
        if len(department_workloads) < 2:
            continue
        average = sum(
            item["workload_minutes"] for item in department_workloads
        ) / len(department_workloads)
        if average <= 0:
            continue
        for workload in department_workloads:
            if workload["workload_minutes"] > average * 1.25:
                workload["allocation_status"] = "overloaded"
            elif workload["workload_minutes"] < average * 0.5:
                workload["allocation_status"] = "underused"

    return sorted(
        workloads.values(),
        key=lambda item: (
            item["counter"].department_id,
            item["counter"].name.lower(),
            item["counter_id"],
        ),
    )


def recommend_counter(
    counters,
    tokens,
    department_id,
    service_minutes_by_id,
    visit_date,
    now=None,
    exclude_token_id=None,
    priority="normal",
    priority_verified=True,
):
    """Prefer matching counters, then choose the least-loaded eligible one."""
    candidates = [
        counter for counter in counters
        if counter.active and counter.department_id == department_id
    ]
    if not candidates:
        return None

    requested_priority = (priority or "normal").strip().lower()
    if requested_priority not in PRIORITY_RANKS:
        requested_priority = "normal"
    if requested_priority != "normal" and not priority_verified:
        requested_priority = "normal"

    preferred_candidates = [
        counter for counter in candidates
        if (
            isinstance(counter.preferred_priorities, list)
            and requested_priority in counter.preferred_priorities
        )
    ]
    if preferred_candidates:
        candidates = preferred_candidates

    workload_tokens = [
        token for token in tokens
        if token.id != exclude_token_id
    ]
    workloads = calculate_counter_workloads(
        candidates,
        workload_tokens,
        service_minutes_by_id,
        visit_date,
        now=now,
    )
    by_id = {item["counter_id"]: item for item in workloads}

    return min(
        candidates,
        key=lambda counter: (
            by_id[counter.id]["workload_minutes"],
            by_id[counter.id]["waiting_count"]
            + by_id[counter.id]["in_service_count"],
            counter.id,
        ),
    )


def _effective_priority_rank(token, now, aging_minutes):
    priority = (token.priority or "normal").lower()
    if priority not in PRIORITY_RANKS:
        priority = "normal"
    if priority != "normal" and not token.priority_verified:
        priority = "normal"

    rank = PRIORITY_RANKS[priority]
    if priority == "emergency":
        return rank

    created_at = _utc_naive(token.created_at)
    if created_at is None:
        return rank

    waited_minutes = max(0, int((now - created_at).total_seconds() // 60))
    promotions = waited_minutes // aging_minutes
    return max(PRIORITY_RANKS["urgent"], rank - promotions)


def select_next_token_for_counter(tokens, now=None):
    """Select the department's next token using the shared priority queue."""
    ordered = schedule_tokens(tokens, now=now)
    return ordered[0] if ordered else None


def schedule_tokens(tokens, now=None, aging_minutes=DEFAULT_AGING_MINUTES):
    """Order waiting tokens by verified priority, aging, then FIFO."""
    if aging_minutes < 1:
        raise ValueError("aging_minutes must be a positive number.")

    now = _utc_naive(now or datetime.now(timezone.utc))
    oldest = datetime.min

    return sorted(
        tokens,
        key=lambda token: (
            _effective_priority_rank(token, now, aging_minutes),
            _utc_naive(token.created_at) or oldest,
            token.id or 0,
        ),
    )
