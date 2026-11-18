# QueueFlow AI Stage 2: Smart Counter Allocation and Queue Optimization

## Problem and current behavior

The existing application stores departments, services, counters, and tokens.
Each counter belongs to one department; services also belong to one department.
Counters and departments have an `active` flag, services have an
`estimated_minutes` value, and each token has an optional `counter_id`.

Before Stage 2, the student booking flow correctly left new tokens in `pending`
for administrator approval. Approved tokens needed manual counter assignment.
Queue positions and "call next" put verified priority requests before normal
tokens, then used booking time. There was no workload-based counter
recommendation or waiting-time aging.

## Counter allocation

The allocation and scheduling functions are in `queue_optimization.py` and do
not require a new package or database column.

1. A counter is eligible only when it is active and belongs to the selected
   service's department. Flask additionally filters out counters whose
   department is inactive.
2. Allocation workload is computed for the token's visit date from `approved`
   (waiting) and `called` (in-service) tokens already assigned to each
   candidate counter. Pending, completed, declined, and missed tokens do not
   occupy a queue slot.
3. An approved waiting token adds its service's estimated minutes (15 minutes
   when that estimate is missing or invalid). A called token adds the estimated
   remaining minutes: its service estimate less elapsed time since `called_at`,
   with a floor of zero. If `called_at` is missing, its full estimate is used.
4. The compatible counter with the lowest estimated minutes wins. Ties are
   resolved by fewer active tokens, then counter ID. Recalculating after each
   approval naturally spreads new assignments across less-loaded counters.
5. On approval, the admin route assigns the recommendation in the same
   transaction. The token remains pending until an administrator approves it.
   If there is no eligible counter, it remains approved but unassigned, and
   both the admin and student see that no counter is currently available.
6. Admins can still manually assign or reassign an approved token. Existing
   status, active-counter, and department-compatibility checks remain in force.

The admin dashboard lists waiting/in-service counts and estimated minutes for
all configured counters, including unavailable ones. Relative load is labeled
overloaded above 1.25 times the mean workload or underused below 0.5 times the
mean, within a department with at least two available counters and positive
mean workload. These labels are informational; allocation still selects the
lowest workload.

## Queue scheduling, priority, and fairness

Counter allocation is separate from queue ordering. `schedule_tokens` is used
for both student queue positions and the admin "call next" action.

- A non-normal priority request has expedited rank only after the existing
  admin verification (`priority_verified`) is true. Unverified requests are
  ordered as normal and are excluded from the "call next" candidate set.
- Starting from the verified priority rank (emergency, urgent, accessibility,
  normal), a waiting token improves by one rank for every 30 minutes of
  waiting, down to rank zero. Aging never changes the token's stored priority
  or verification state. It lets long-waiting normal tokens eventually
  compete with older priority classes.
- Tokens with the same effective rank are FIFO by `created_at`, then token ID.
- Positions are computed from current approved tokens, grouped by counter and
  visit date. Completion, decline, missed status, or reassignment changes the
  next calculation; queue positions are not stored in the database.

The current schema does not define a separate `cancelled` status; a declined
token is excluded from active workload and queue ordering. Admin approval,
priority verification/rejection, and service completion continue to be
administrator decisions.

## Files changed

- `queue_optimization.py` — dependency-free workload and scheduling functions.
- `routes/admin.py` — workload/recommendation data, assignment on approval,
  compatible manual reassignment checks, and shared scheduling for call-next.
- `routes/student.py` — dynamic recommendations for pending/unassigned tokens
  and shared queue positions.
- `templates/admin_dashboard.html` — counter workload table and per-token
  recommendation.
- `templates/student_dashboard.html` — recommended-counter display and live
  dashboard updates.
- `tests/test_queue_optimization.py` — focused algorithm tests using simulated
  records.
- `tests/test_flask_integration.py` — Flask route tests against isolated
  in-memory SQLite.
- `STAGE2_QUEUE_OPTIMIZATION.md` — this guide.

No schema migration, `.env` change, or dependency change is required.

## Tests and workload comparison

Run the independent tests with:

```powershell
python -m unittest discover -s tests -v
```

The tests cover lowest-workload selection, service/department compatibility,
inactive and unavailable counters, estimated and remaining service time,
completion and decline removal, reassignment, priority verification, FIFO,
aging, invalid aging configuration, and the Flask student/admin workflow.
Flask integration tests use an isolated in-memory SQLite database.

**Simulated before/after scenario (not production data):** Counter A has two
waiting 20-minute services (40 minutes total); Counter B has one waiting
10-minute service (10 minutes total). A new 10-minute service is assigned to
Counter B. The estimated loads change from `A=40, B=10` (30-minute spread) to
`A=40, B=20` (20-minute spread). The focused test asserts these values.

**Actual test result:** 15 tests pass with the repository virtual environment
(11 algorithm tests and 4 Flask integration tests). The integration tests use
simulated records and an in-memory SQLite database; they do not connect to the
configured MySQL database or claim production performance.

## Install, initialize, and run

From the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe init_db.py
.\.venv\Scripts\python.exe seed_data.py
.\.venv\Scripts\python.exe app.py
```

`init_db.py` creates any missing tables using the existing models. `seed_data.py`
adds sample departments, counters, and services only when absent. Running
`app.py` also invokes the existing admin-account setup, which requires the
project's existing `ADMIN_EMAIL` and `ADMIN_PASSWORD` configuration. Keep
credentials in the existing environment configuration and do not commit them.

## Limitations and future work

- Compatibility currently means the service and counter share a department;
  the schema has no per-counter service capability mapping.
- There is no counter capacity, shift schedule, live availability, or observed
  service-duration history. The `active` flags and estimates are the available
  inputs.
- Remaining time for a called token is approximated from `called_at` and the
  configured service estimate; it is not a measured duration.
- If adding per-counter capabilities, working hours, measured durations, or
  persisted allocation history becomes necessary, design and review a
  migration separately before changing the schema.
