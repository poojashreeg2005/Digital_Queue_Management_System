import unittest
from datetime import date

from werkzeug.security import generate_password_hash

from app import app
from models import Counter, Department, Service, Token, User, db


class FlaskAllocationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(
            TESTING=True,
            SECRET_KEY="queueflow-test-secret",
            SQLALCHEMY_DATABASE_URI="sqlite://",
        )
        with app.app_context():
            db.create_all()

    @classmethod
    def tearDownClass(cls):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def setUp(self):
        with app.app_context():
            db.session.remove()
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

            existing_tokens = [
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
            pending_token = Token(
                code="QF-PENDING-1",
                user_id=student.id,
                service_id=service.id,
                visit_date=date.today(),
                status="pending",
                priority="normal",
                priority_verified=True,
            )
            db.session.add_all(existing_tokens + [pending_token])
            db.session.commit()

            self.admin_id = admin.id
            self.student_id = student.id
            self.service_id = service.id
            self.counter_a_id = counter_a.id
            self.counter_b_id = counter_b.id
            self.pending_token_id = pending_token.id

        self.client = app.test_client()

    def tearDown(self):
        with app.app_context():
            db.session.remove()

    def login(self, url):
        return self.client.post(
            url,
            data={
                "email": (
                    "admin@example.test"
                    if url == "/admin/login"
                    else "student@example.test"
                ),
                "password": "test-password",
            },
            follow_redirects=True,
        )

    def test_student_recommendation_admin_approval_and_call_workflow(self):
        self.login("/student/login")
        dashboard = self.client.get("/student/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b"Suggested counter:", dashboard.data)
        self.assertIn(b"Counter B", dashboard.data)

        update = self.client.get("/student/updates")
        self.assertEqual(update.status_code, 200)
        pending_update = next(
            item for item in update.json["tokens"]
            if item["id"] == self.pending_token_id
        )
        self.assertEqual(
            pending_update["recommended_counter_name"],
            "Counter B",
        )

        self.client.get("/logout")
        self.login("/admin/login")
        admin_dashboard = self.client.get("/admin/dashboard")
        self.assertEqual(admin_dashboard.status_code, 200)
        self.assertIn(b"Smart Counter Workload", admin_dashboard.data)

        self.client.post(
            f"/admin/token/{self.pending_token_id}/action",
            data={"action": "approve"},
        )
        with app.app_context():
            token = db.session.get(Token, self.pending_token_id)
            self.assertEqual(token.status, "approved")
            self.assertEqual(token.counter_id, self.counter_b_id)

        self.client.post(
            f"/admin/counter/{self.counter_b_id}/call-next"
        )
        with app.app_context():
            token = db.session.get(Token, self.pending_token_id)
            self.assertEqual(token.status, "called")

        self.client.post(
            f"/admin/token/{self.pending_token_id}/action",
            data={"action": "complete"},
        )
        with app.app_context():
            token = db.session.get(Token, self.pending_token_id)
            self.assertEqual(token.status, "completed")

    def test_admin_can_reassign_approved_token_to_compatible_active_counter(self):
        self.login("/admin/login")
        self.client.post(
            f"/admin/token/{self.pending_token_id}/action",
            data={"action": "approve"},
        )
        self.client.post(
            f"/admin/token/{self.pending_token_id}/assign-counter",
            data={"counter_id": str(self.counter_a_id)},
        )

        with app.app_context():
            token = db.session.get(Token, self.pending_token_id)
            self.assertEqual(token.status, "approved")
            self.assertEqual(token.counter_id, self.counter_a_id)

    def test_priority_request_stays_unverified_until_admin_decides(self):
        with app.app_context():
            token = db.session.get(Token, self.pending_token_id)
            token.priority = "urgent"
            token.priority_verified = False
            db.session.commit()

        self.login("/admin/login")
        self.client.post(
            f"/admin/token/{self.pending_token_id}/action",
            data={"action": "approve"},
        )
        with app.app_context():
            token = db.session.get(Token, self.pending_token_id)
            self.assertEqual(token.priority, "urgent")
            self.assertFalse(token.priority_verified)
            assigned_counter_id = token.counter_id

        self.client.post(
            f"/admin/counter/{assigned_counter_id}/call-next"
        )
        with app.app_context():
            token = db.session.get(Token, self.pending_token_id)
            self.assertEqual(token.status, "approved")

        self.client.post(
            f"/admin/token/{self.pending_token_id}/verify-priority",
            data={"decision": "verify"},
        )
        self.client.post(
            f"/admin/counter/{assigned_counter_id}/call-next"
        )
        with app.app_context():
            token = db.session.get(Token, self.pending_token_id)
            self.assertTrue(token.priority_verified)
            self.assertEqual(token.status, "called")

    def test_approval_without_eligible_counter_keeps_token_unassigned(self):
        with app.app_context():
            department = Department(name="No Counter Department", active=True)
            db.session.add(department)
            db.session.flush()
            service = Service(
                department_id=department.id,
                name="Unstaffed Service",
                estimated_minutes=15,
                active=True,
            )
            db.session.add(service)
            db.session.flush()
            token = Token(
                code="QF-NO-COUNTER",
                user_id=self.student_id,
                service_id=service.id,
                visit_date=date.today(),
                status="pending",
                priority="normal",
                priority_verified=True,
            )
            db.session.add(token)
            db.session.commit()
            token_id = token.id

        self.login("/admin/login")
        self.client.post(
            f"/admin/token/{token_id}/action",
            data={"action": "approve"},
        )

        with app.app_context():
            token = db.session.get(Token, token_id)
            self.assertEqual(token.status, "approved")
            self.assertIsNone(token.counter_id)


if __name__ == "__main__":
    unittest.main()
