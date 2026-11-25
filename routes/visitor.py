"""
routes/visitor.py
Parent & Visitor Assistance Module Blueprint.
Provides public-facing, unauthenticated routes for purpose selection,
instructions, smart campus navigation, guest token booking, and live tracking.
"""

from datetime import date, datetime, timedelta
import re
import secrets

from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash, jsonify
)

from models import (
    db, Department, Counter,
    VisitorPurpose, VisitorInstruction,
    CampusLocation, CampusNotice, VisitorToken
)
from services.waiting_time import calculate_waiting_time


visitor_bp = Blueprint("visitor", __name__, url_prefix="/visitor")

VISITOR_PURPOSE_CATALOG = (
    {
        "code": "general-enquiry",
        "name": "General Enquiry",
        "description": "General campus and visitor enquiries.",
        "icon": "ℹ️",
        "department_names": (),
        "display_order": 1,
    },
    {
        "code": "admission-enquiry",
        "name": "Admission Enquiry",
        "description": "Questions about admissions and application documents.",
        "icon": "🎓",
        "department_names": ("Student Administration",),
        "display_order": 2,
    },
    {
        "code": "fee-payment",
        "name": "Fee Payment",
        "description": "Fee payment and account enquiries.",
        "icon": "💳",
        "department_names": ("Student Administration",),
        "display_order": 3,
    },
    {
        "code": "student-administration",
        "name": "Student Administration",
        "description": "Student records, certificates, and administration enquiries.",
        "icon": "📋",
        "department_names": ("Student Administration",),
        "display_order": 4,
    },
    {
        "code": "technical-support",
        "name": "Technical Support",
        "description": "Computer, laboratory, and technical support enquiries.",
        "icon": "🛠️",
        "department_names": ("Technical Support",),
        "display_order": 5,
    },
    {
        "code": "library-visit",
        "name": "Library Visit",
        "description": "Library access and library service enquiries.",
        "icon": "📚",
        "department_names": ("Library Services",),
        "display_order": 6,
    },
    {
        "code": "meeting-faculty",
        "name": "Meeting with Faculty",
        "description": "A visit to meet a faculty member.",
        "icon": "👥",
        "department_names": (),
        "display_order": 7,
    },
    {
        "code": "other",
        "name": "Other",
        "description": "A visit purpose not listed above.",
        "icon": "✏️",
        "department_names": (),
        "display_order": 8,
    },
)
OTHER_PURPOSE_NOTE_PREFIX = "[visitor-purpose-detail] "


def get_booking_department_ids(purpose_code, purpose, departments):
    """Return active departments configured for a purpose, or all if unrestricted."""
    active_department_ids = {department.id for department in departments}
    if purpose_code == "other":
        return sorted(active_department_ids)

    configured_ids = set()
    if purpose:
        instructions = VisitorInstruction.query.filter_by(
            purpose_id=purpose.id,
            active=True
        ).all()
        configured_ids.update(item.department_id for item in instructions)
        if purpose.default_department_id:
            configured_ids.add(purpose.default_department_id)

    configured_ids.intersection_update(active_department_ids)
    if configured_ids:
        return sorted(configured_ids)

    catalog_item = next(
        (item for item in VISITOR_PURPOSE_CATALOG if item["code"] == purpose_code),
        None
    )
    if catalog_item and catalog_item["department_names"]:
        matching_ids = [
            department.id for department in departments
            if department.name in catalog_item["department_names"]
        ]
        if matching_ids:
            return sorted(matching_ids)

    return sorted(active_department_ids)


# ---------------------------------------------------------------------
# HELPER: CALCULATE VISITOR QUEUE POSITION & CURRENTLY SERVING
# ---------------------------------------------------------------------

def get_visitor_queue_metrics(visitor_token):
    """
    Computes real-time queue position and waiting metrics for an approved visitor token.
    Follows priority-first and FIFO principles matching the campus queue specification.
    """
    if visitor_token.status != "approved" or not visitor_token.counter_id:
        return {
            "queue_position": None,
            "people_ahead": 0,
            "currently_serving": None
        }

    # Find the token currently being served at this counter today
    active_called = (
        VisitorToken.query
        .filter(
            VisitorToken.counter_id == visitor_token.counter_id,
            VisitorToken.visit_date == visitor_token.visit_date,
            VisitorToken.status == "called"
        )
        .order_by(VisitorToken.called_at.desc())
        .first()
    )
    currently_serving_code = active_called.token_code if active_called else "None currently active"

    # Query all approved tokens at this counter today
    approved_tokens = (
        VisitorToken.query
        .filter(
            VisitorToken.counter_id == visitor_token.counter_id,
            VisitorToken.visit_date == visitor_token.visit_date,
            VisitorToken.status == "approved"
        )
        .all()
    )

    # Sort matching the student queue ordering:
    # 1. Verified priority (non-normal and verified) comes first (rank 0), normal rank 1
    # 2. Created at timestamp ascending (FIFO)
    # 3. ID ascending
    approved_tokens.sort(
        key=lambda tok: (
            0 if (tok.priority != "normal" and tok.priority_verified) else 1,
            tok.created_at or datetime.min,
            tok.id
        )
    )

    position = None
    people_ahead = 0

    for idx, tok in enumerate(approved_tokens, start=1):
        if tok.id == visitor_token.id:
            position = idx
            people_ahead = idx - 1
            break

    return {
        "queue_position": position,
        "people_ahead": people_ahead,
        "currently_serving": currently_serving_code
    }


def mask_phone_number(phone):
    """Masks visitor phone number for public display privacy (e.g. ******4567)."""
    if not phone or len(phone) < 4:
        return "******"
    return "•" * (len(phone) - 4) + phone[-4:]


# ---------------------------------------------------------------------
# 1. VISITOR PORTAL HOME & PURPOSE SELECTION
# ---------------------------------------------------------------------

@visitor_bp.route("")
@visitor_bp.route("/")
def home():
    """Main visitor portal landing page with purpose selection & notices."""
    search_query = request.args.get("q", "").strip()

    purposes_query = VisitorPurpose.query.filter_by(active=True).order_by(
        VisitorPurpose.display_order.asc(),
        VisitorPurpose.name.asc()
    )

    if search_query:
        purposes_query = purposes_query.filter(
            VisitorPurpose.name.ilike(f"%{search_query}%") |
            VisitorPurpose.description.ilike(f"%{search_query}%")
        )

    purposes = purposes_query.all()

    # Fetch active notices (strictly exclude expired ones)
    today = date.today()
    active_notices = (
        CampusNotice.query
        .filter(
            CampusNotice.is_active == True,
            CampusNotice.start_date <= today,
            (CampusNotice.expiry_date.is_(None) | (CampusNotice.expiry_date >= today))
        )
        .order_by(CampusNotice.created_at.desc())
        .limit(5)
        .all()
    )

    departments = Department.query.filter_by(active=True).order_by(Department.name).all()

    return render_template(
        "visitor/home.html",
        purposes=purposes,
        notices=active_notices,
        departments=departments,
        search_query=search_query
    )


# ---------------------------------------------------------------------
# 2. SELECT DEPARTMENT FOR A PURPOSE
# ---------------------------------------------------------------------

@visitor_bp.route("/purpose/<string:purpose_code>")
def purpose_select(purpose_code):
    """
    Shows department options handling this visit purpose.
    Supports multiple departments per purpose or redirects if only one.
    """
    purpose = VisitorPurpose.query.filter_by(code=purpose_code, active=True).first_or_404()

    # Find configured instructions for this purpose
    instructions = (
        VisitorInstruction.query
        .filter_by(purpose_id=purpose.id, active=True)
        .all()
    )

    if len(instructions) == 1:
        # Single department configured: proceed directly to instructions
        return redirect(
            url_for(
                "visitor.instructions",
                purpose_code=purpose.code,
                department_id=instructions[0].department_id
            )
        )

    # If multiple departments or none explicitly configured, resolve choices
    dept_ids = [inst.department_id for inst in instructions]
    if purpose.default_department_id and purpose.default_department_id not in dept_ids:
        dept_ids.append(purpose.default_department_id)

    departments = (
        Department.query
        .filter(Department.id.in_(dept_ids), Department.active == True)
        .all()
        if dept_ids else Department.query.filter_by(active=True).all()
    )

    return render_template(
        "visitor/purpose_departments.html",
        purpose=purpose,
        departments=departments
    )


# ---------------------------------------------------------------------
# 3. DETAILED INSTRUCTIONS & REQUIRED DOCUMENTS
# ---------------------------------------------------------------------

@visitor_bp.route("/instructions/<string:purpose_code>/<int:department_id>")
def instructions(purpose_code, department_id):
    """
    Displays step-by-step procedure, required documents checklist,
    visiting hours, and first reporting point.
    """
    purpose = VisitorPurpose.query.filter_by(code=purpose_code, active=True).first_or_404()
    department = Department.query.filter_by(id=department_id, active=True).first_or_404()

    instruction = (
        VisitorInstruction.query
        .filter_by(purpose_id=purpose.id, department_id=department.id, active=True)
        .first()
    )

    # Split steps and documents into structured lists for display
    steps = [s.strip() for s in instruction.procedure_steps.split("\n") if s.strip()] if instruction else [
        "Report to Security Gate 1 for a visitor pass.",
        f"Proceed to the {department.building or 'Administrative Block'}.",
        f"Approach {department.name} helpdesk."
    ]

    documents = [d.strip() for d in instruction.required_documents.split("\n") if d.strip()] if instruction else [
        "Valid Government Photo ID Card (Aadhaar / Driving License / Passport).",
        "Student Registration Number or reference letter (if applicable)."
    ]

    # Department location & counter info
    counters = Counter.query.filter_by(department_id=department.id, active=True).all()

    # Active notices for this purpose / department
    today = date.today()
    relevant_notices = (
        CampusNotice.query
        .filter(
            CampusNotice.is_active == True,
            CampusNotice.start_date <= today,
            (CampusNotice.expiry_date.is_(None) | (CampusNotice.expiry_date >= today)),
            (
                (CampusNotice.department_id == department.id) |
                (CampusNotice.purpose_id == purpose.id) |
                (CampusNotice.department_id.is_(None) & CampusNotice.purpose_id.is_(None))
            )
        )
        .order_by(CampusNotice.created_at.desc())
        .all()
    )

    # Campus location reference for map button
    primary_loc = CampusLocation.query.filter(
        (CampusLocation.department_id == department.id) |
        (CampusLocation.building == department.building)
    ).first()

    return render_template(
        "visitor/instructions.html",
        purpose=purpose,
        department=department,
        instruction=instruction,
        steps=steps,
        documents=documents,
        counters=counters,
        notices=relevant_notices,
        primary_location=primary_loc
    )


# ---------------------------------------------------------------------
# 4. SMART CAMPUS NAVIGATION (OUTDOOR & INDOOR)
# ---------------------------------------------------------------------

@visitor_bp.route("/navigate")
@visitor_bp.route("/navigate/<int:location_id>")
def navigate(location_id=None):
    """
    Displays a fictional demonstration map without mixing it with database locations.
    Existing location links retain their requested location as context only.
    """
    target_location = None
    if location_id:
        target_location = CampusLocation.query.filter_by(id=location_id, active=True).first()

    return render_template(
        "visitor/navigation.html",
        target_location=target_location
    )


# ---------------------------------------------------------------------
# 5. GUEST VISITOR TOKEN BOOKING
# ---------------------------------------------------------------------

@visitor_bp.route("/book", methods=["GET", "POST"])
def book_token():
    """
    Guest token booking without account creation.
    Collects visitor name, phone, purpose, department, and date.
    Enforces transaction-safe duplicate active booking prevention.
    """
    today = date.today()
    max_date = today + timedelta(days=14)

    if request.method == "POST":
        visitor_name = request.form.get("visitor_name", "").strip()
        visitor_phone = request.form.get("visitor_phone", "").strip()
        purpose_code = request.form.get("purpose_code", "").strip()
        if not purpose_code:
            legacy_purpose_id = request.form.get("purpose_id", "").strip()
            if legacy_purpose_id:
                purpose_code = f"db:{legacy_purpose_id}"
        other_purpose_text = request.form.get("other_purpose", "").strip()
        department_id_raw = request.form.get("department_id", "")
        visit_date_raw = request.form.get("visit_date", "")
        priority = request.form.get("priority", "normal")

        # 1. Validate Visitor Name
        if not visitor_name or len(visitor_name) < 2:
            flash("Please enter your full name (at least 2 characters).", "error")
            return redirect(url_for("visitor.book_token"))

        # 2. Validate Mobile Phone (Indian 10-digit mobile number)
        clean_phone = re.sub(r"[^\d]", "", visitor_phone)
        if len(clean_phone) == 12 and clean_phone.startswith("91"):
            clean_phone = clean_phone[2:]
        if not re.match(r"^[6-9]\d{9}$", clean_phone):
            flash("Please enter a valid 10-digit Indian mobile number (e.g. 9876543210).", "error")
            return redirect(url_for("visitor.book_token"))

        # 3. Validate purpose and department selection
        catalog_item = next(
            (item for item in VISITOR_PURPOSE_CATALOG if item["code"] == purpose_code),
            None
        )
        purpose = None
        try:
            department_id = int(department_id_raw)
        except (ValueError, TypeError):
            flash("Please select a valid visit purpose and department.", "error")
            return redirect(url_for("visitor.book_token"))

        if purpose_code.startswith("db:"):
            try:
                configured_purpose_id = int(purpose_code[3:])
            except ValueError:
                flash("Please select a valid visit purpose.", "error")
                return redirect(url_for("visitor.book_token"))
            purpose = db.session.get(VisitorPurpose, configured_purpose_id)
        elif catalog_item:
            purpose = VisitorPurpose.query.filter_by(code=purpose_code).first()
            if not purpose:
                purpose = next(
                    (
                        item for item in VisitorPurpose.query.all()
                        if item.name.casefold() == catalog_item["name"].casefold()
                    ),
                    None
                )
        else:
            flash("Please select a valid visit purpose.", "error")
            return redirect(url_for("visitor.book_token"))

        department = Department.query.filter_by(id=department_id, active=True).first()

        if purpose and not purpose.active:
            flash("That visit purpose is currently unavailable. Please choose another.", "error")
            return redirect(url_for("visitor.book_token"))

        if purpose_code == "other":
            if not other_purpose_text:
                flash("Please describe your visit purpose when selecting Other.", "error")
                return redirect(url_for("visitor.book_token"))
            if len(other_purpose_text) > 120:
                flash("The Other purpose description must be 120 characters or fewer.", "error")
                return redirect(url_for("visitor.book_token"))

        if not department:
            flash("The selected department is currently unavailable. Please choose another.", "error")
            return redirect(url_for("visitor.book_token"))

        allowed_department_ids = get_booking_department_ids(
            purpose_code,
            purpose,
            Department.query.filter_by(active=True).order_by(Department.name).all()
        )
        if department.id not in allowed_department_ids:
            flash("Please select a department associated with your visit purpose.", "error")
            return redirect(url_for("visitor.book_token"))

        # 4. Validate Visit Date
        try:
            visit_date = datetime.strptime(visit_date_raw, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            flash("Please choose a valid visit date.", "error")
            return redirect(url_for("visitor.book_token"))

        if visit_date < today or visit_date > max_date:
            flash("Please select a date between today and the next 14 days.", "error")
            return redirect(url_for("visitor.book_token"))

        # 5. Validate Priority
        allowed_priorities = ["normal", "senior_citizen", "accessibility", "urgent"]
        if priority not in allowed_priorities:
            priority = "normal"

        # 6. TRANSACTION-SAFE DUPLICATE ACTIVE BOOKING CHECK
        # Lock existing active rows for this phone + department + date
        active_statuses = ["pending", "approved", "called"]
        try:
            existing_active = (
                VisitorToken.query
                .filter(
                    VisitorToken.visitor_phone == clean_phone,
                    VisitorToken.department_id == department.id,
                    VisitorToken.visit_date == visit_date,
                    VisitorToken.status.in_(active_statuses)
                )
                .with_for_update()
                .first()
            )

            if existing_active:
                flash(
                    f"You already have an active booking ({existing_active.token_code}) for "
                    f"{department.name} on {visit_date.strftime('%d %b %Y')}. "
                    "Redirecting to your existing token pass.",
                    "warning"
                )
                return redirect(
                    url_for("visitor.token_status", tracking_token=existing_active.tracking_token)
                )

            # 7. Check Department Daily Limit
            daily_limit = department.daily_limit or 100
            current_count = (
                VisitorToken.query
                .filter(
                    VisitorToken.department_id == department.id,
                    VisitorToken.visit_date == visit_date,
                    VisitorToken.status != "declined"
                )
                .count()
            )

            if current_count >= daily_limit:
                flash(
                    "Sorry, this department has reached its maximum visitor token capacity "
                    "for the chosen date. Please select another date.",
                    "error"
                )
                return redirect(url_for("visitor.book_token"))

            if not purpose:
                catalog_item_department = next(
                    (
                        item.id for item in Department.query.filter_by(active=True).all()
                        if item.name in catalog_item["department_names"]
                    ),
                    None
                )
                purpose = VisitorPurpose(
                    name=catalog_item["name"],
                    code=catalog_item["code"],
                    description=catalog_item["description"],
                    icon=catalog_item["icon"],
                    default_department_id=catalog_item_department,
                    active=True,
                    display_order=catalog_item["display_order"]
                )
                db.session.add(purpose)
                db.session.flush()

            # 8. Generate Unique Token Code & Tracking Token
            token_code = f"VQ-{visit_date.strftime('%Y%m%d')}-{secrets.token_hex(2).upper()}"
            tracking_token = secrets.token_urlsafe(32)

            new_token = VisitorToken(
                token_code=token_code,
                tracking_token=tracking_token,
                visitor_name=visitor_name,
                visitor_phone=clean_phone,
                purpose_id=purpose.id,
                department_id=department.id,
                visit_date=visit_date,
                status="pending",
                priority=priority,
                priority_verified=(priority == "normal"),
                admin_note=(
                    OTHER_PURPOSE_NOTE_PREFIX + other_purpose_text
                    if purpose_code == "other" else None
                )
            )

            db.session.add(new_token)
            db.session.commit()

            flash(
                f"Token {token_code} booked successfully! Please save your tracking pass.",
                "success"
            )
            return redirect(
                url_for("visitor.token_status", tracking_token=tracking_token)
            )

        except Exception as e:
            db.session.rollback()
            flash("Could not complete booking due to a server error. Please try again.", "error")
            return redirect(url_for("visitor.book_token"))

    # GET Request: Prepare form options
    pre_purpose_code = request.args.get("purpose", "")
    pre_dept_id = request.args.get("dept", type=int)

    all_purposes = VisitorPurpose.query.order_by(
        VisitorPurpose.display_order.asc(),
        VisitorPurpose.name.asc()
    ).all()
    active_purposes = [purpose for purpose in all_purposes if purpose.active]
    departments = Department.query.filter_by(active=True).order_by(Department.name).all()
    used_purpose_ids = set()
    purpose_options = []
    purpose_department_map = {}
    pre_purpose_value = ""

    for catalog_item in VISITOR_PURPOSE_CATALOG:
        purpose = next(
            (item for item in all_purposes if item.code == catalog_item["code"]),
            None
        )
        if not purpose:
            purpose = next(
                (
                    item for item in all_purposes
                    if item.name.casefold() == catalog_item["name"].casefold()
                ),
                None
            )

        if purpose:
            used_purpose_ids.add(purpose.id)
            purpose_value = catalog_item["code"]
            purpose_active = purpose.active
            if purpose.code == pre_purpose_code or catalog_item["code"] == pre_purpose_code:
                pre_purpose_value = purpose_value
        else:
            purpose_value = catalog_item["code"]
            purpose_active = True
            if catalog_item["code"] == pre_purpose_code:
                pre_purpose_value = purpose_value

        purpose_options.append({
            "value": purpose_value,
            "name": catalog_item["name"],
            "icon": catalog_item["icon"],
            "active": purpose_active,
            "is_other": catalog_item["code"] == "other"
        })

        if purpose_active:
            purpose_department_map[purpose_value] = get_booking_department_ids(
                catalog_item["code"],
                purpose if purpose and purpose.active else None,
                departments
            )

    for purpose in active_purposes:
        if purpose.id in used_purpose_ids:
            continue

        purpose_value = f"db:{purpose.id}"
        purpose_options.append({
            "value": purpose_value,
            "name": purpose.name,
            "icon": purpose.icon or "📋",
            "active": True,
            "is_other": False
        })
        if purpose.code == pre_purpose_code:
            pre_purpose_value = purpose_value
        purpose_department_map[purpose_value] = get_booking_department_ids(
            purpose.code,
            purpose,
            departments
        )

    return render_template(
        "visitor/book_token.html",
        purpose_options=purpose_options,
        purpose_department_map=purpose_department_map,
        departments=departments,
        pre_purpose_value=pre_purpose_value,
        pre_dept_id=pre_dept_id,
        today=today.isoformat(),
        max_date=max_date.isoformat()
    )


# ---------------------------------------------------------------------
# 6. DIGITAL VISITOR TOKEN PASS & TRACKING
# ---------------------------------------------------------------------

@visitor_bp.route("/status/<string:tracking_token>")
def token_status(tracking_token):
    """
    Renders digital pass for the visitor. Accessible through unguessable tracking token.
    Masks personal phone number to preserve privacy.
    """
    token = VisitorToken.query.filter_by(tracking_token=tracking_token).first_or_404()
    purpose = db.session.get(VisitorPurpose, token.purpose_id)
    department = db.session.get(Department, token.department_id)
    counter = db.session.get(Counter, token.counter_id) if token.counter_id else None
    other_purpose_detail = None
    if token.admin_note and token.admin_note.startswith(OTHER_PURPOSE_NOTE_PREFIX):
        other_purpose_detail = token.admin_note[len(OTHER_PURPOSE_NOTE_PREFIX):]

    # Queue Metrics
    metrics = get_visitor_queue_metrics(token)
    queue_pos = metrics["queue_position"]

    # Calculate Waiting Time using our adapter service
    wait_info = calculate_waiting_time(
        queue_position=queue_pos,
        average_service_minutes=15,
        is_serving=(token.status == "called")
    )

    masked_phone = mask_phone_number(token.visitor_phone)

    # Campus location for directions
    location = CampusLocation.query.filter(
        (CampusLocation.department_id == department.id) |
        (CampusLocation.building == department.building)
    ).first()

    return render_template(
        "visitor/token_status.html",
        token=token,
        purpose=purpose,
        other_purpose_detail=other_purpose_detail,
        department=department,
        counter=counter,
        metrics=metrics,
        wait_info=wait_info,
        masked_phone=masked_phone,
        location=location
    )


# ---------------------------------------------------------------------
# 7. AJAX LIVE POLLING ENDPOINT (EVERY 15 SECONDS)
# ---------------------------------------------------------------------

@visitor_bp.route("/updates/<string:tracking_token>")
def token_updates(tracking_token):
    """
    Polled asynchronously by JavaScript to dynamically update status,
    queue position, and counter info without refreshing the page.
    """
    token = VisitorToken.query.filter_by(tracking_token=tracking_token).first()
    if not token:
        return jsonify({"success": False, "error": "Token not found"}), 404

    metrics = get_visitor_queue_metrics(token)
    counter = db.session.get(Counter, token.counter_id) if token.counter_id else None
    department = db.session.get(Department, token.department_id)

    wait_info = calculate_waiting_time(
        queue_position=metrics["queue_position"],
        average_service_minutes=15,
        is_serving=(token.status == "called")
    )

    counter_location_text = ""
    if counter:
        parts = [p for p in [counter.building, counter.floor, counter.room] if p]
        counter_location_text = ", ".join(parts)
    elif department:
        parts = [p for p in [department.building, department.floor, department.room] if p]
        counter_location_text = ", ".join(parts)

    return jsonify({
        "success": True,
        "token_code": token.token_code,
        "status": token.status,
        "queue_position": metrics["queue_position"],
        "people_ahead": metrics["people_ahead"],
        "currently_serving": metrics["currently_serving"],
        "counter_name": counter.name if counter else "Awaiting Counter",
        "counter_location": counter_location_text,
        "estimated_wait_text": wait_info["label"],
        "decline_reason": token.decline_reason or "",
        "priority": token.priority,
        "priority_verified": token.priority_verified
    })
