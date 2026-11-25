"""
migrate_visitor.py
Safe database migration and seed script for the Parent & Visitor Assistance Module.
Creates only the new visitor tables and seeds verified sample data for Canara Engineering College.
Does NOT modify or drop any existing tables.
"""

from datetime import date, timedelta
from app import app
from models import (
    db, Department, Counter,
    VisitorPurpose, VisitorInstruction,
    FloorPlan, CampusLocation, CampusNotice, VisitorToken
)


def run_migration():
    print("=" * 65)
    print("QUEUEFLOW AI: VISITOR MODULE DATABASE MIGRATION")
    print("=" * 65)

    with app.app_context():
        # Step 1: Create only new tables safely
        print("\n[1/3] Creating visitor module tables if not present...")
        db.create_all()
        print("✓ Database tables verified.")

        # Step 2: Seed or update visitor purposes
        print("\n[2/3] Seeding configurable campus visit purposes...")

        # Ensure departments exist
        admin_dept = Department.query.filter_by(name="Student Administration").first()
        tech_dept = Department.query.filter_by(name="Technical Support").first()
        library_dept = Department.query.filter_by(name="Library Services").first()

        purposes_data = [
            {
                "name": "Admission Enquiry",
                "code": "admission-enquiry",
                "description": "Inquire about undergraduate and postgraduate engineering admissions, eligibility criteria, management/KEA quota, and document requirements.",
                "icon": "🎓",
                "default_department_id": admin_dept.id if admin_dept else None,
                "display_order": 1,
            },
            {
                "name": "Fee Payment",
                "code": "fee-payment",
                "description": "Tuition fee, examination fee, hostel fee deposit, online receipt clearance, and accounts queries.",
                "icon": "💳",
                "default_department_id": admin_dept.id if admin_dept else None,
                "display_order": 2,
            },
            {
                "name": "Examination Queries",
                "code": "examination-queries",
                "description": "Semester marks card verification, transcript issuance, re-evaluation applications, and university exam queries.",
                "icon": "📝",
                "default_department_id": admin_dept.id if admin_dept else None,
                "display_order": 3,
            },
            {
                "name": "Library Assistance",
                "code": "library-assistance",
                "description": "Guest access to Central Library reference sections, alumni book return, digital catalog, and research journals inquiry.",
                "icon": "📚",
                "default_department_id": library_dept.id if library_dept else None,
                "display_order": 4,
            },
            {
                "name": "Meet the Principal",
                "code": "meet-principal",
                "description": "Official interaction with the Principal or Academic Deans regarding institutional matters, prior appointments, or special approvals.",
                "icon": "🏛️",
                "default_department_id": admin_dept.id if admin_dept else None,
                "display_order": 5,
            },
            {
                "name": "General Enquiry",
                "code": "general-enquiry",
                "description": "General campus inquiries, campus tour assistance, lost and found, and guidance for parents of new students.",
                "icon": "ℹ️",
                "default_department_id": tech_dept.id if tech_dept else None,
                "display_order": 6,
            },
        ]

        purpose_map = {}
        for p_data in purposes_data:
            purpose = VisitorPurpose.query.filter_by(code=p_data["code"]).first()
            if not purpose:
                purpose = VisitorPurpose(**p_data)
                db.session.add(purpose)
                db.session.flush()
                print(f"  + Added Purpose: {purpose.name}")
            else:
                purpose.name = p_data["name"]
                purpose.description = p_data["description"]
                purpose.icon = p_data["icon"]
                purpose.default_department_id = p_data["default_department_id"]
                purpose.display_order = p_data["display_order"]
                print(f"  * Updated Purpose: {purpose.name}")
            purpose_map[p_data["code"]] = purpose

        db.session.commit()

        # Step 3: Seed Visitor Instructions
        print("\n[3/3] Seeding department instructions, required documents & floor plans...")

        if admin_dept:
            instructions_data = [
                (
                    "admission-enquiry",
                    admin_dept.id,
                    "Step 1: Report to the Security Gate and collect a Visitor Entry Pass.\n"
                    "Step 2: Proceed straight along the main boulevard to the Administrative Block.\n"
                    "Step 3: Check in at the Ground Floor Reception Desk (Counter 101).\n"
                    "Step 4: Present your student details and obtain an Admissions Guidance Checklist.\n"
                    "Step 5: Attend one-on-one counseling with the Admissions Officer in Room 104.",
                    "1. Original & 2 photocopies of 10th & 12th Marks Cards / Equivalent.\n"
                    "2. KEA / COMEDK / Management Entrance Exam Rank Card & Admit Card.\n"
                    "3. Transfer Certificate (TC) & Conduct Certificate from previous institution.\n"
                    "4. Valid Government Photo ID of Candidate & Parent (Aadhaar / Passport / Voter ID).\n"
                    "5. 4 recent passport-size photographs of the candidate.",
                    "9:30 AM – 4:30 PM (Lunch Break: 1:00 PM – 2:00 PM)",
                    "Security Main Gate 1 -> Reception Desk, Administrative Block (Ground Floor)",
                    "Please arrive before 3:30 PM to ensure document verification can be completed on the same day."
                ),
                (
                    "fee-payment",
                    admin_dept.id,
                    "Step 1: Collect visitor token at Reception Desk or show your booked digital token.\n"
                    "Step 2: Proceed to Accounts Counter 2 on Ground Floor.\n"
                    "Step 3: Quote Student USN / Roll Number and verify pending fee structure.\n"
                    "Step 4: Complete transaction via UPI / Debit Card / Demand Draft / Bank Challan.\n"
                    "Step 5: Collect physical stamped receipt and digital confirmation SMS.",
                    "1. Student USN / University Registration Number or Provisional Admission Letter.\n"
                    "2. Previous Semester / Academic Year Fee Receipt copy.\n"
                    "3. Demand Draft (if paying via DD) drawn in favor of 'Canara Engineering College'.\n"
                    "4. Parent / Guardian Identity Proof for refund or concession queries.",
                    "9:30 AM – 3:30 PM (Cash Counter closes at 3:00 PM)",
                    "Accounts Section, Room 102, Ground Floor, Administrative Block",
                    "Cash transactions above Rs. 10,000 are not accepted; please use Demand Draft, Net Banking or POS Card swipe."
                ),
                (
                    "examination-queries",
                    admin_dept.id,
                    "Step 1: Enter Administrative Block and head to Exam Section (Counter 3).\n"
                    "Step 2: Fill out the Student Verification & Query Slip.\n"
                    "Step 3: Submit application for Transcript / Duplicate Grade Card / Revaluation.\n"
                    "Step 4: Pay necessary processing fees at the adjacent accounts window.\n"
                    "Step 5: Collect acknowledgment receipt with tentative dispatch / dispatch date.",
                    "1. Valid Student College ID Card or Letter of Authorization from the student.\n"
                    "2. Copy of Semester Grade Cards / Hall Ticket.\n"
                    "3. Government Photo ID of Parent/Guardian collecting documents on behalf of student.\n"
                    "4. Formal written request letter signed by parent and student.",
                    "10:00 AM – 1:00 PM & 2:00 PM – 4:00 PM",
                    "Exam Section Desk, Room 108, Ground Floor, Administrative Block",
                    "Transcripts normally require 3 to 5 working days for processing and university endorsement."
                ),
                (
                    "meet-principal",
                    admin_dept.id,
                    "Step 1: Check in at the Security Gate with photo identification.\n"
                    "Step 2: Arrive at the Principal's Secretariat on the First Floor of Administrative Block.\n"
                    "Step 3: Present your appointment confirmation or submit a Visitor Representation Slip.\n"
                    "Step 4: Wait in the Executive Visitors Lounge until called by the Secretary.\n"
                    "Step 5: Enter the Principal's Chamber for your scheduled discussion.",
                    "1. Prior Appointment Confirmation (Email / SMS / Letter) if pre-scheduled.\n"
                    "2. Valid Government Photo Identity Card.\n"
                    "3. Written representation or memorandum summarizing the subject of meeting.\n"
                    "4. Student USN / Academic file records if discussing student matters.",
                    "Visiting Hours: 2:30 PM – 4:30 PM (By Prior Appointment Preferred)",
                    "Principal's Office, First Floor, Administrative Block (Staircase A / Elevator)",
                    "Parents without prior appointments are requested to meet the respective Department HOD first."
                )
            ]

            for code, dept_id, proc, docs, hours, point, notes in instructions_data:
                purpose = purpose_map.get(code)
                if not purpose:
                    continue
                inst = VisitorInstruction.query.filter_by(
                    purpose_id=purpose.id,
                    department_id=dept_id
                ).first()
                if not inst:
                    inst = VisitorInstruction(
                        purpose_id=purpose.id,
                        department_id=dept_id,
                        procedure_steps=proc,
                        required_documents=docs,
                        visiting_hours=hours,
                        first_reporting_point=point,
                        important_notes=notes,
                        active=True
                    )
                    db.session.add(inst)
                    print(f"  + Added Instruction for Purpose: {purpose.name}")
                else:
                    inst.procedure_steps = proc
                    inst.required_documents = docs
                    inst.visiting_hours = hours
                    inst.first_reporting_point = point
                    inst.important_notes = notes
                    print(f"  * Updated Instruction for Purpose: {purpose.name}")

        if library_dept:
            purpose = purpose_map.get("library-assistance")
            if purpose:
                inst = VisitorInstruction.query.filter_by(
                    purpose_id=purpose.id,
                    department_id=library_dept.id
                ).first()
                if not inst:
                    inst = VisitorInstruction(
                        purpose_id=purpose.id,
                        department_id=library_dept.id,
                        procedure_steps="Step 1: Register at the Library Security Counter.\n"
                                        "Step 2: Deposit personal bags in the visitor lockers.\n"
                                        "Step 3: Meet the Reference Librarian at Ground Floor Counter L1.\n"
                                        "Step 4: Obtain Guest Reading Pass for designated research section.",
                        required_documents="1. Visitor ID Proof (Aadhaar / College ID / Alumni Card).\n"
                                           "2. Recommendation letter if affiliated with another educational institution.",
                        visiting_hours="9:00 AM – 5:00 PM (Monday to Saturday)",
                        first_reporting_point="Central Library Entrance Counter, Ground Floor",
                        important_notes="Borrowing privileges are reserved for registered students and faculty; visitors enjoy in-house reading access.",
                        active=True
                    )
                    db.session.add(inst)
                    print(f"  + Added Instruction for Library Assistance")

        # Seed Demo Floor Plans with embedded vector blueprint
        sample_svg_admin_ground = """<svg viewBox="0 0 800 500" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:100%;background:#f4f5fc;border-radius:12px;">
  <rect x="20" y="20" width="760" height="460" rx="10" fill="#ffffff" stroke="#333854" stroke-width="3"/>
  <text x="35" y="55" font-family="'Space Grotesk', sans-serif" font-weight="700" font-size="18" fill="#17152e">CANARA ENGINEERING COLLEGE – ADMIN BLOCK (GROUND FLOOR)</text>
  <text x="35" y="75" font-family="'DM Sans', sans-serif" font-size="11" fill="#757492">[DEMONSTRATION FLOOR PLAN / SAMPLE BLUEPRINT]</text>

  <!-- Corridors -->
  <rect x="200" y="90" width="400" height="70" fill="#eef0fb" stroke="#ccd1e6" stroke-width="1.5" stroke-dasharray="4"/>
  <text x="360" y="130" font-family="'DM Sans', sans-serif" font-size="12" font-weight="600" fill="#717a99">MAIN CORRIDOR</text>

  <!-- Rooms -->
  <!-- Entrance & Reception -->
  <g id="room-reception">
    <rect x="40" y="90" width="140" height="130" rx="6" fill="#f0edff" stroke="#7657f6" stroke-width="2"/>
    <text x="65" y="150" font-family="'Space Grotesk', sans-serif" font-weight="700" font-size="14" fill="#6242e8">RECEPTION</text>
    <text x="60" y="170" font-family="'DM Sans', sans-serif" font-size="11" fill="#6242e8">Room 101 · Helpdesk</text>
  </g>

  <!-- Accounts & Fee Counter -->
  <g id="room-accounts">
    <rect x="40" y="240" width="140" height="150" rx="6" fill="#eaf8f0" stroke="#16865a" stroke-width="2"/>
    <text x="55" y="305" font-family="'Space Grotesk', sans-serif" font-weight="700" font-size="13" fill="#16865a">ACCOUNTS &amp; FEES</text>
    <text x="65" y="325" font-family="'DM Sans', sans-serif" font-size="11" fill="#16865a">Room 102 · Counter 2</text>
  </g>

  <!-- Admissions Cell -->
  <g id="room-admissions">
    <rect x="620" y="90" width="140" height="140" rx="6" fill="#eef3ff" stroke="#365bb5" stroke-width="2"/>
    <text x="635" y="155" font-family="'Space Grotesk', sans-serif" font-weight="700" font-size="13" fill="#365bb5">ADMISSIONS CELL</text>
    <text x="645" y="175" font-family="'DM Sans', sans-serif" font-size="11" fill="#365bb5">Room 104 · Verification</text>
  </g>

  <!-- Exam Section -->
  <g id="room-exams">
    <rect x="620" y="250" width="140" height="140" rx="6" fill="#fff7e8" stroke="#d9822b" stroke-width="2"/>
    <text x="640" y="315" font-family="'Space Grotesk', sans-serif" font-weight="700" font-size="13" fill="#d9822b">EXAM SECTION</text>
    <text x="645" y="335" font-family="'DM Sans', sans-serif" font-size="11" fill="#d9822b">Room 108 · Counter 3</text>
  </g>

  <!-- Principal's Staircase / Elevator -->
  <rect x="330" y="270" width="140" height="90" rx="6" fill="#fdf0f2" stroke="#d94b61" stroke-width="2"/>
  <text x="345" y="315" font-family="'Space Grotesk', sans-serif" font-weight="700" font-size="12" fill="#d94b61">STAIRCASE &amp; LIFT</text>
  <text x="345" y="335" font-family="'DM Sans', sans-serif" font-size="10" fill="#888">To Principal's Office (1st Fl)</text>

  <!-- Security Main Entrance -->
  <path d="M 360 480 L 440 480" stroke="#7657f6" stroke-width="6"/>
  <text x="355" y="470" font-family="'DM Sans', sans-serif" font-weight="700" font-size="12" fill="#7657f6">MAIN ENTRANCE</text>
</svg>"""

        admin_ground_fp = FloorPlan.query.filter_by(building="Administrative Block", floor="Ground Floor").first()
        if not admin_ground_fp:
            admin_ground_fp = FloorPlan(
                building="Administrative Block",
                floor="Ground Floor",
                title="Admin Block – Ground Floor Layout",
                svg_blueprint=sample_svg_admin_ground,
                description="Interactive floor plan for Reception, Accounts, Admissions & Exam counters."
            )
            db.session.add(admin_ground_fp)
            db.session.flush()
            print("  + Added FloorPlan: Admin Block (Ground Floor)")

        # Seed Campus Locations (Demo Geolocation Coordinates for Canara Engineering College, Benjanapadavu)
        # Note: Clearly flagged as sample/demonstration data
        locations_data = [
            {
                "name": "Campus Security Main Gate",
                "building": "Main Entrance Gate 1",
                "floor": "Ground",
                "room": "Security Post 1",
                "latitude": 12.8797,
                "longitude": 74.9872,
                "floor_plan_id": None,
                "marker_x": 50.0,
                "marker_y": 95.0,
                "directions": "Enter Canara Engineering College from Benjanapadavu Main Road. Stop at Security Gate 1 to receive a Visitor Pass.",
                "is_demo": True
            },
            {
                "name": "Reception Desk & Helpdesk",
                "building": "Administrative Block",
                "floor": "Ground Floor",
                "room": "Room 101",
                "latitude": 12.8801,
                "longitude": 74.9870,
                "floor_plan_id": admin_ground_fp.id if admin_ground_fp else None,
                "marker_x": 13.5,
                "marker_y": 32.0,
                "directions": "Follow main driveway from Gate 1 to Administrative Block. Enter main entrance and turn immediate left to Room 101.",
                "is_demo": True
            },
            {
                "name": "Fee Payment & Accounts Counter",
                "building": "Administrative Block",
                "floor": "Ground Floor",
                "room": "Room 102",
                "latitude": 12.8801,
                "longitude": 74.9870,
                "floor_plan_id": admin_ground_fp.id if admin_ground_fp else None,
                "marker_x": 13.5,
                "marker_y": 62.0,
                "directions": "Enter Administrative Block. Proceed 15 meters left down the corridor to Accounts Window Counter 2.",
                "is_demo": True
            },
            {
                "name": "Admissions Verification Cell",
                "building": "Administrative Block",
                "floor": "Ground Floor",
                "room": "Room 104",
                "latitude": 12.8801,
                "longitude": 74.9870,
                "floor_plan_id": admin_ground_fp.id if admin_ground_fp else None,
                "marker_x": 86.5,
                "marker_y": 32.0,
                "directions": "Enter Administrative Block and turn right down the east wing corridor to Room 104.",
                "is_demo": True
            },
            {
                "name": "Examination & Records Section",
                "building": "Administrative Block",
                "floor": "Ground Floor",
                "room": "Room 108",
                "latitude": 12.8801,
                "longitude": 74.9870,
                "floor_plan_id": admin_ground_fp.id if admin_ground_fp else None,
                "marker_x": 86.5,
                "marker_y": 64.0,
                "directions": "Enter Administrative Block. Turn right down the east corridor past admissions to Counter 3.",
                "is_demo": True
            },
            {
                "name": "Principal's Secretariat",
                "building": "Administrative Block",
                "floor": "First Floor",
                "room": "Room 201",
                "latitude": 12.8801,
                "longitude": 74.9870,
                "floor_plan_id": None,
                "marker_x": 50.0,
                "marker_y": 40.0,
                "directions": "Take Staircase A or Elevator in central atrium to First Floor. The Principal's Secretariat is directly opposite the landing.",
                "is_demo": True
            },
            {
                "name": "Central Library & Information Center",
                "building": "Central Library Block",
                "floor": "Ground Floor",
                "room": "Counter L1",
                "latitude": 12.8794,
                "longitude": 74.9878,
                "floor_plan_id": None,
                "marker_x": 50.0,
                "marker_y": 50.0,
                "directions": "Located south of Administrative Block. Enter through the portico to the central issue desk.",
                "is_demo": True
            },
            {
                "name": "Visitor Vehicle Parking",
                "building": "Campus Ground Area",
                "floor": "Ground",
                "room": "Parking Bay P2",
                "latitude": 12.8796,
                "longitude": 74.9868,
                "floor_plan_id": None,
                "marker_x": 20.0,
                "marker_y": 90.0,
                "directions": "Turn right immediately after passing through Security Gate 1 into designated visitor bays.",
                "is_demo": True
            }
        ]

        for loc in locations_data:
            existing_loc = CampusLocation.query.filter_by(name=loc["name"]).first()
            if not existing_loc:
                new_loc = CampusLocation(**loc)
                db.session.add(new_loc)
                print(f"  + Added Campus Location: {loc['name']}")
            else:
                existing_loc.building = loc["building"]
                existing_loc.floor = loc["floor"]
                existing_loc.room = loc["room"]
                existing_loc.latitude = loc["latitude"]
                existing_loc.longitude = loc["longitude"]
                existing_loc.floor_plan_id = loc["floor_plan_id"]
                existing_loc.marker_x = loc["marker_x"]
                existing_loc.marker_y = loc["marker_y"]
                existing_loc.directions = loc["directions"]
                print(f"  * Updated Campus Location: {loc['name']}")

        # Seed Campus Notices (with valid and expired notices to verify auto-filtering)
        today = date.today()
        notices_data = [
            {
                "title": "Admissions Open for Academic Year 2026-27",
                "content": "Admissions counseling and campus verification desks are open for CET, COMEDK, and Management quota candidates. Parents can visit Room 104, Administrative Block.",
                "category": "Admissions",
                "is_active": True,
                "start_date": today - timedelta(days=5),
                "expiry_date": today + timedelta(days=60),
            },
            {
                "title": "Tuition Fee Payment Reminder & Counter Timings",
                "content": "Even semester tuition fee payments may be made at Accounts Counter 2 until 3:00 PM on weekdays. Net Banking & UPI preferred to reduce waiting times.",
                "category": "Fees",
                "is_active": True,
                "start_date": today - timedelta(days=2),
                "expiry_date": today + timedelta(days=30),
            },
            {
                "title": "Visitor Parking Notice",
                "content": "All visiting parents and guests are requested to park vehicles strictly in Parking Bay P2 near Gate 1. Follow security personnel directions.",
                "category": "Advisory",
                "is_active": True,
                "start_date": today - timedelta(days=10),
                "expiry_date": today + timedelta(days=90),
            },
            {
                "title": "Old Notice (Expired – For Auto-Filter Verification)",
                "content": "This notice should be automatically excluded from active visitor listings because its expiry date is in the past.",
                "category": "General",
                "is_active": True,
                "start_date": today - timedelta(days=30),
                "expiry_date": today - timedelta(days=1),
            }
        ]

        for n_data in notices_data:
            existing_notice = CampusNotice.query.filter_by(title=n_data["title"]).first()
            if not existing_notice:
                notice = CampusNotice(**n_data)
                db.session.add(notice)
                print(f"  + Added Notice: {n_data['title']}")
            else:
                existing_notice.content = n_data["content"]
                existing_notice.expiry_date = n_data["expiry_date"]
                print(f"  * Updated Notice: {n_data['title']}")

        db.session.commit()
        print("\n" + "=" * 65)
        print("MIGRATION COMPLETED SUCCESSFULLY!")
        print("All visitor tables and initial Canara Engineering College demo records ready.")
        print("=" * 65)


if __name__ == "__main__":
    run_migration()
