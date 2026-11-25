import unittest
from datetime import date
import os

from werkzeug.security import generate_password_hash

os.environ["DATABASE_URL"] = "sqlite://"

from app import app
from models import (
    Counter,
    Department,
    Service,
    Token,
    User,
    VisitorPurpose,
    VisitorToken,
    db,
)

with app.app_context():
    test_database_url = db.engine.url
    if test_database_url.drivername != "sqlite" or test_database_url.database:
        raise RuntimeError(
            "Integration tests require an isolated in-memory SQLite database."
        )


class FlaskAllocationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(
            TESTING=True,
            SECRET_KEY="queueflow-test-secret",
            SQLALCHEMY_DATABASE_URI="sqlite://",
        )

    def setUp(self):
        with app.app_context():
            db.drop_all()
            db.create_all()

            admin = User(
                name="Test Admin",
                email="admin@example.test",
                password_hash=generate_password_hash("test-password"),
                role="admin",
            )
            student = User(
                name="Test Student",
                email="student@example.test",
                password_hash=generate_password_hash("test-password"),
                role="student",
            )
            department = Department(name="Test Department", active=True)
            db.session.add_all([admin, student, department])
            db.session.flush()

            service = Service(
                department_id=department.id,
                name="Test Service",
                estimated_minutes=20,
                active=True,
            )
            counter_a = Counter(
                department_id=department.id,
                name="Counter A",
                active=True,
            )
            counter_b = Counter(
                department_id=department.id,
                name="Counter B",
                active=True,
            )
            db.session.add_all([service, counter_a, counter_b])
            db.session.flush()
            visitor_purpose = VisitorPurpose(
                name="General Enquiry",
                code="general-enquiry",
                default_department_id=department.id,
                active=True,
                display_order=1,
            )
            db.session.add(visitor_purpose)
            db.session.flush()

            existing = [
                Token(
                    code=f"QF-EXIST-{number}",
                    user_id=student.id,
                    service_id=service.id,
                    counter_id=counter_a.id,
                    visit_date=date.today(),
                    status="approved",
                    priority="normal",
                    priority_verified=True,
                )
                for number in (1, 2)
            ]
            pending = Token(
                code="QF-PENDING-1",
                user_id=student.id,
                service_id=service.id,
                visit_date=date.today(),
                status="pending",
                priority="normal",
                priority_verified=True,
            )
            db.session.add_all(existing + [pending])
            db.session.commit()

            self.student_id = student.id
            self.counter_a_id = counter_a.id
            self.counter_b_id = counter_b.id
            self.pending_token_id = pending.id
            self.service_id = service.id
            self.department_id = department.id
            self.visitor_purpose_id = visitor_purpose.id

        self.client = app.test_client()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def login(self, url):
        email = "admin@example.test" if url == "/admin/login" else "student@example.test"
        return self.client.post(
            url,
            data={"email": email, "password": "test-password"},
            follow_redirects=True,
        )

    def test_student_dashboard_and_live_recommendation(self):
        self.login("/student/login")
        dashboard = self.client.get("/student/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b"Suggested counter:", dashboard.data)

        update = self.client.get("/student/updates")
        self.assertEqual(update.status_code, 200)
        pending = next(
            item for item in update.json["tokens"]
            if item["id"] == self.pending_token_id
        )
        self.assertEqual(pending["recommended_counter_name"], "Counter B")

    def test_admin_approval_assigns_lowest_load_counter(self):
        self.login("/admin/login")
        dashboard = self.client.get("/admin/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b"Smart Counter Workload", dashboard.data)

        self.client.post(
            f"/admin/token/{self.pending_token_id}/action",
            data={"action": "approve"},
        )
        with app.app_context():
            token = db.session.get(Token, self.pending_token_id)
            self.assertEqual(token.status, "approved")
            self.assertEqual(token.counter_id, self.counter_b_id)

    def test_admin_permission_and_priority_verification(self):
        student_login = self.login("/student/login")
        self.assertIn(b"Welcome to QueueFlow!", student_login.data)
        denied = self.client.get("/admin/dashboard")
        self.assertEqual(denied.status_code, 403)

        self.client.get("/logout")
        self.login("/admin/login")
        with app.app_context():
            token = db.session.get(Token, self.pending_token_id)
            token.priority = "urgent"
            token.priority_verified = False
            db.session.commit()

        self.client.post(
            f"/admin/token/{self.pending_token_id}/action",
            data={"action": "approve"},
        )
        self.client.post(
            f"/admin/counter/{self.counter_b_id}/call-next"
        )
        with app.app_context():
            token = db.session.get(Token, self.pending_token_id)
            self.assertEqual(token.status, "approved")

    def test_student_booking_and_admin_service_management(self):
        self.login("/student/login")
        booking_page = self.client.get("/student/book")
        self.assertEqual(booking_page.status_code, 200)
        self.assertIn(b"Test Service", booking_page.data)

        response = self.client.post(
            "/student/book",
            data={
                "service_id": str(self.service_id),
                "visit_date": date.today().isoformat(),
                "priority": "normal",
            },
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            created = Token.query.filter_by(
                user_id=self.student_id,
                service_id=self.service_id,
                status="pending",
            ).order_by(Token.id.desc()).first()
            self.assertIsNotNone(created)

        self.client.get("/logout")
        self.login("/admin/login")
        for path in (
            "/admin/visitors",
            "/admin/visitor-content",
            "/admin/campus-locations",
        ):
            self.assertEqual(self.client.get(path).status_code, 200, path)

        locations = self.client.get("/admin/locations")
        self.assertEqual(locations.status_code, 200)
        self.assertIn(b"Existing Services", locations.data)

        create = self.client.post(
            "/admin/service/create",
            data={
                "department_id": str(self.department_id),
                "name": "New Demonstration Service",
                "description": "Isolated test service",
                "estimated_minutes": "12",
                "fee": "5.00",
                "active": "1",
            },
        )
        self.assertEqual(create.status_code, 302)
        with app.app_context():
            created_service = Service.query.filter_by(
                name="New Demonstration Service"
            ).first()
            self.assertIsNotNone(created_service)
            self.assertTrue(created_service.active)

    def test_visitor_booking_tracking_remains_separate(self):
        response = self.client.get("/visitor")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"General Enquiry", response.data)
        css_response = self.client.get("/static/css/visitor.css")
        self.assertEqual(css_response.status_code, 200)
        css_response.close()
        js_response = self.client.get("/static/js/visitor_queue.js")
        self.assertEqual(js_response.status_code, 200)
        js_response.close()

        response = self.client.post(
            "/visitor/book",
            data={
                "visitor_name": "Test Visitor",
                "visitor_phone": "9876501234",
                "purpose_id": str(self.visitor_purpose_id),
                "department_id": str(self.department_id),
                "visit_date": date.today().isoformat(),
                "priority": "normal",
            },
        )
        self.assertEqual(response.status_code, 302)
        tracking_path = response.headers["Location"]
        self.assertIn("/visitor/status/", tracking_path)
        status_response = self.client.get(tracking_path)
        self.assertEqual(status_response.status_code, 200)

        tracking_token = tracking_path.rsplit("/", 1)[-1]
        updates = self.client.get(f"/visitor/updates/{tracking_token}")
        self.assertEqual(updates.status_code, 200)
        self.assertTrue(updates.json["success"])
        self.assertEqual(updates.json["status"], "pending")

        with app.app_context():
            self.assertEqual(Token.query.count(), 3)
            self.assertEqual(VisitorToken.query.count(), 1)


if __name__ == "__main__":
    unittest.main()
