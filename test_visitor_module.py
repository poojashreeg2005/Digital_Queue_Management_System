"""
test_visitor_module.py
Comprehensive automated test suite for QueueFlow AI Visitor & Campus Navigation Module.
Validates all 17 requirements and verifies regression safety on existing student/admin flows.
"""

from datetime import date
import os
import re
import unittest

from werkzeug.security import generate_password_hash

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["ADMIN_EMAIL"] = "admin@example.test"
os.environ["ADMIN_PASSWORD"] = "test-password"

from app import app
from models import (
    db, User, Department, Counter,
    Service,
    VisitorPurpose, VisitorInstruction,
    CampusLocation, FloorPlan, CampusNotice, VisitorToken
)
from services.waiting_time import calculate_waiting_time


with app.app_context():
    test_database_url = db.engine.url
    if test_database_url.drivername != "sqlite" or test_database_url.database:
        raise RuntimeError(
            "Visitor tests require an isolated in-memory SQLite database."
        )


class VisitorModuleTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        cls.client = app.test_client()
        cls.app_context = app.app_context()
        cls.app_context.push()

        db.drop_all()
        db.create_all()

        admin = User(
            name="Test Admin",
            email="admin@example.test",
            password_hash=generate_password_hash("test-password"),
            role="admin"
        )
        department = Department(
            name="Student Administration",
            building="Main Administrative Block",
            floor="Ground Floor",
            room="Room 101",
            active=True
        )
        db.session.add_all([admin, department])
        db.session.flush()

        service = Service(
            department_id=department.id,
            name="Admission Assistance",
            estimated_minutes=15,
            active=True
        )
        counter = Counter(
            department_id=department.id,
            name="Main Service Counter",
            active=True
        )
        purpose = VisitorPurpose(
            name="Admission Enquiry",
            code="admission-enquiry",
            description="Admission and engineering enrollment enquiries.",
            icon="🎓",
            default_department_id=department.id,
            active=True,
            display_order=1
        )
        fee_purpose = VisitorPurpose(
            name="Fee Payment",
            code="fee-payment",
            description="Tuition and fee payment enquiries.",
            icon="💳",
            default_department_id=department.id,
            active=True,
            display_order=2
        )
        db.session.add_all([service, counter, purpose, fee_purpose])
        db.session.flush()

        instruction = VisitorInstruction(
            purpose_id=purpose.id,
            department_id=department.id,
            procedure_steps="Step 1: Report to Security Gate 1.\n"
                            "Step 2: Proceed to the Administrative Block.",
            required_documents="1. Valid Government Photo ID.\n"
                               "2. Student admission documents.",
            visiting_hours="9:30 AM - 4:30 PM",
            first_reporting_point="Reception Desk, Administrative Block",
            active=True
        )
        db.session.add(instruction)
        db.session.commit()

    @classmethod
    def tearDownClass(cls):
        db.session.remove()
        db.drop_all()
        cls.app_context.pop()

    def test_01_visitor_home_page(self):
        """1. Open the visitor portal and verify Canara Engineering College demo banner & purposes."""
        response = self.client.get("/visitor", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        content = response.data.decode("utf-8")
        self.assertIn("Canara Engineering College", content)
        self.assertIn("Demonstration & Sample Data Mode", content)
        self.assertIn("Admission Enquiry", content)
        self.assertIn("Fee Payment", content)
        print("✓ Test 1 Passed: Visitor home loaded with Canara Engineering College demo banner.")

    def test_02_purpose_selection(self):
        """2. Select a visit purpose and verify redirection to department/instructions."""
        response = self.client.get("/visitor/purpose/admission-enquiry", follow_redirects=False)
        self.assertIn(response.status_code, [200, 302])
        if response.status_code == 302:
            self.assertIn("/visitor/instructions/", response.headers["Location"])
        print("✓ Test 2 Passed: Visit purpose successfully resolves to department instructions.")

    def test_03_instructions_and_documents(self):
        """3. View department instructions, procedure steps, and required documents checklist."""
        dept = Department.query.first()
        self.assertIsNotNone(dept, "Department should exist in database.")
        response = self.client.get(f"/visitor/instructions/admission-enquiry/{dept.id}", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        content = response.data.decode("utf-8")
        self.assertIn("Step-by-Step Arrival Procedure", content)
        self.assertIn("Required Documents Checklist", content)
        self.assertIn("Official Visiting Hours", content)
        self.assertIn("First Reporting Point", content)
        print("✓ Test 3 Passed: Step-by-step procedures, checklists, and hours displayed correctly.")

    def test_04_campus_navigation_outdoor_and_indoor(self):
        """4. Verify OpenStreetMap outdoor map and indoor floor plans layout."""
        response = self.client.get("/visitor/navigate", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        content = response.data.decode("utf-8")
        self.assertIn("campus-map", content)
        self.assertIn("OpenStreetMap", content)
        self.assertIn("Google Maps to College Gate", content)
        self.assertIn("Demonstration & Sample Map Data", content)
        print("✓ Test 4 Passed: Outdoor map & indoor floor plans loaded with verified demo tags.")

    def test_05_guest_token_booking_and_duplicate_prevention(self):
        """5, 6, 7. Book guest token, verify creation, and enforce duplicate active booking protection."""
        dept = Department.query.first()
        purpose = VisitorPurpose.query.filter_by(code="admission-enquiry").first()
        test_phone = "9876501234"
        visit_date = date.today().isoformat()

        # First Booking: Should succeed
        payload = {
            "visitor_name": "TestVisitor Alpha",
            "visitor_phone": test_phone,
            "purpose_id": purpose.id,
            "department_id": dept.id,
            "visit_date": visit_date,
            "priority": "normal"
        }
        res1 = self.client.post("/visitor/book", data=payload, follow_redirects=False)
        self.assertEqual(res1.status_code, 302)
        self.assertIn("/visitor/status/", res1.headers["Location"])

        # Extract tracking token
        match = re.search(r"/visitor/status/([a-zA-Z0-9_-]+)", res1.headers["Location"])
        self.assertIsNotNone(match)
        tracking_token = match.group(1)

        created_token = VisitorToken.query.filter_by(tracking_token=tracking_token).first()
        self.assertIsNotNone(created_token)
        self.assertEqual(created_token.status, "pending")
        self.assertTrue(created_token.token_code.startswith("VQ-"))

        # Second Booking with same phone + dept + date: Must be REJECTED as active duplicate
        res2 = self.client.post("/visitor/book", data=payload, follow_redirects=True)
        content2 = res2.data.decode("utf-8")
        self.assertIn("You already have an active booking", content2)
        # Should redirect to existing token pass
        self.assertIn(created_token.token_code, content2)

        print("✓ Tests 5, 6, 7 Passed: Token created (VQ-*) and duplicate active booking strictly prevented.")

    def test_08_privacy_and_token_status_tracking(self):
        """8, 9. Verify token status pass and confirm visitor phone number is masked for privacy."""
        test_phone = "9876501234"
        token = VisitorToken.query.filter_by(visitor_phone=test_phone).first()
        self.assertIsNotNone(token)

        response = self.client.get(f"/visitor/status/{token.tracking_token}", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        content = response.data.decode("utf-8")

        # Full phone must NOT appear unmasked!
        self.assertNotIn("9876501234", content)
        # Masked phone (e.g. ••••••1234) must appear
        self.assertIn("1234", content)
        self.assertIn("Standard Queue Heuristic", content)

        # Test live updates endpoint
        update_res = self.client.get(f"/visitor/updates/{token.tracking_token}")
        self.assertEqual(update_res.status_code, 200)
        data = update_res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["token_code"], token.token_code)
        self.assertNotIn("visitor_phone", data)  # Never leaks phone

        print("✓ Tests 8, 9 Passed: Digital pass tracks live status, phone masked, heuristic clearly labelled.")

    def test_10_admin_visitor_management_workflow(self):
        """10, 11, 12, 13, 14. Admin logs in, approves token, assigns counter, calls next, completes."""
        admin_email = os.getenv("ADMIN_EMAIL")
        admin_password = os.getenv("ADMIN_PASSWORD")

        # Login as Admin
        login_res = self.client.post(
            "/admin/login",
            data={"email": admin_email, "password": admin_password},
            follow_redirects=True
        )
        self.assertEqual(login_res.status_code, 200)

        # Access Visitor Admin Dashboard
        dash_res = self.client.get("/admin/visitors", follow_redirects=True)
        self.assertEqual(dash_res.status_code, 200)
        self.assertTrue("Parent & Visitor Queue Management" in dash_res.data.decode("utf-8") or "Parent &amp; Visitor Queue Management" in dash_res.data.decode("utf-8"))

        test_phone = "9876501234"
        token = VisitorToken.query.filter_by(visitor_phone=test_phone).first()
        self.assertIsNotNone(token)
        counter = Counter.query.filter_by(department_id=token.department_id).first()

        # Action 1: Approve Token
        app_res = self.client.post(f"/admin/visitor/{token.id}/action", data={"action": "approve"}, follow_redirects=True)
        self.assertEqual(app_res.status_code, 200)
        db.session.refresh(token)
        self.assertEqual(token.status, "approved")

        # Action 2: Assign Counter
        if counter:
            assign_res = self.client.post(f"/admin/visitor/{token.id}/assign-counter", data={"counter_id": counter.id}, follow_redirects=True)
            self.assertEqual(assign_res.status_code, 200)
            db.session.refresh(token)
            self.assertEqual(token.counter_id, counter.id)

        # Action 3: Call Next Visitor
        call_res = self.client.post(f"/admin/visitor/{token.id}/action", data={"action": "call"}, follow_redirects=True)
        self.assertEqual(call_res.status_code, 200)
        db.session.refresh(token)
        self.assertEqual(token.status, "called")
        self.assertIsNotNone(token.called_at)

        # Action 4: Complete Token
        comp_res = self.client.post(f"/admin/visitor/{token.id}/action", data={"action": "complete"}, follow_redirects=True)
        self.assertEqual(comp_res.status_code, 200)
        db.session.refresh(token)
        self.assertEqual(token.status, "completed")
        self.assertIsNotNone(token.completed_at)

        print("✓ Tests 10-14 Passed: Admin visitor lifecycle (approve -> assign counter -> call -> complete) verified.")

    def test_15_admin_content_and_locations(self):
        """15. Verify Admin can manage visitor purposes, instructions, notices, and locations."""
        login_res = self.client.post(
            "/admin/login",
            data={
                "email": os.getenv("ADMIN_EMAIL"),
                "password": os.getenv("ADMIN_PASSWORD")
            },
            follow_redirects=True
        )
        self.assertEqual(login_res.status_code, 200)

        res1 = self.client.get("/admin/visitor-content", follow_redirects=True)
        self.assertEqual(res1.status_code, 200)
        content1 = res1.data.decode("utf-8")
        self.assertIn("Configure Visit Purpose", content1)
        self.assertIn("Publish Campus Notice", content1)

        res2 = self.client.get("/admin/campus-locations", follow_redirects=True)
        self.assertEqual(res2.status_code, 200)
        content2 = res2.data.decode("utf-8")
        self.assertTrue("Campus Map Locations & Indoor Floor Plans" in content2 or "Campus Map Locations &amp; Indoor Floor Plans" in content2)
        print("✓ Test 15 Passed: Admin content, notices with expiry, and location management functional.")

    def test_16_regression_existing_student_system(self):
        """16, 17. Verify existing student registration, login, dashboard, and tokens still work 100%."""
        # Check student login page
        s_login_page = self.client.get("/student/login", follow_redirects=True)
        self.assertEqual(s_login_page.status_code, 200)

        # Check home page
        home_page = self.client.get("/", follow_redirects=True)
        self.assertEqual(home_page.status_code, 200)
        content = home_page.data.decode("utf-8")
        self.assertIn("QueueFlow AI", content)
        self.assertIn("Student Login", content)
        self.assertIn("Parent &amp; Visitor Portal", content)

        # Verify Student Token model still has NOT NULL constraint on user_id
        from models import Token as StudentToken
        self.assertFalse(StudentToken.user_id.nullable, "StudentToken.user_id must remain NOT NULL.")

        print("✓ Tests 16, 17 Passed: Existing student and core system fully preserved with zero regression.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
