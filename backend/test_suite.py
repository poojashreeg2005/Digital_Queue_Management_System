"""
QueueFlow AI - Comprehensive End-to-End Integration & Regression Test Suite
Tests all 13 workflows and verifies MySQL database persistence.
"""

import sys
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent))

import json
from app import app
import database


def run_tests():
    print("=" * 70)
    print("QUEUEFLOW AI - END-TO-END TEST SUITE")
    print("=" * 70)

    client = app.test_client()
    db_conn = database.get_db_connection()

    test_user_ids = []
    test_token_ids = []

    def get_query_cursor():
        # Commit to advance InnoDB snapshot view for accurate verification
        db_conn.commit()
        return db_conn.cursor(dictionary=True)

    def cleanup():
        print("\nCleaning up temporary test data...")
        try:
            db_conn.commit()
            c = db_conn.cursor()
            if test_token_ids:
                format_strings = ",".join(["%s"] * len(test_token_ids))
                c.execute(f"DELETE FROM service_history WHERE token_id IN ({format_strings})", tuple(test_token_ids))
                c.execute(f"DELETE FROM queue_records WHERE token_id IN ({format_strings})", tuple(test_token_ids))
                c.execute(f"DELETE FROM tokens WHERE id IN ({format_strings})", tuple(test_token_ids))
            if test_user_ids:
                format_strings = ",".join(["%s"] * len(test_user_ids))
                c.execute(f"DELETE FROM users WHERE id IN ({format_strings})", tuple(test_user_ids))
            db_conn.commit()
            c.close()
            print("Cleanup completed successfully.")
        except Exception as e:
            print(f"Cleanup error: {e}")

    try:
        # TEST 1: Register a student
        print("\n[TEST 1] Register a student (POST /api/users)...")
        reg_payload = {
            "full_name": "Test Student E2E",
            "email": "test_e2e_student1@example.edu",
            "password": "SecurePassword123!",
        }
        resp = client.post("/api/users", json=reg_payload)
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.data}"
        data1 = json.loads(resp.data)["data"]
        user1_id = data1["user_id"]
        test_user_ids.append(user1_id)
        print(f" PASS: Registered student user_id={user1_id}")

        # TEST 2: Select a department and service
        print("\n[TEST 2] Select a department and service (GET /api/departments, GET /api/services)...")
        resp_dept = client.get("/api/departments")
        assert resp_dept.status_code == 200, f"Expected 200, got {resp_dept.status_code}"
        departments = json.loads(resp_dept.data)["data"]
        assert len(departments) > 0, "No departments found"
        exam_dept = next((d for d in departments if d["name"] == "Examination"), departments[0])
        dept_id = exam_dept["id"]
        print(f" Department selected: {exam_dept['name']} (ID={dept_id})")

        resp_svc = client.get(f"/api/services?department_id={dept_id}")
        assert resp_svc.status_code == 200, f"Expected 200, got {resp_svc.status_code}"
        services = json.loads(resp_svc.data)["data"]
        assert len(services) > 0, "No services found for department"
        service = services[0]
        service_id = service["id"]
        print(f" Service selected: {service['name']} (ID={service_id}, Duration={service['estimated_duration_minutes']}m)")
        print(" PASS: Department and service list retrieved successfully.")

        # TEST 3: Generate a token and QR code
        print("\n[TEST 3] Generate a token and QR code (POST /api/tokens)...")
        token_payload = {"user_id": user1_id, "service_id": service_id}
        resp_tok = client.post("/api/tokens", json=token_payload)
        assert resp_tok.status_code == 201, f"Expected 201, got {resp_tok.status_code}: {resp_tok.data}"
        token1_data = json.loads(resp_tok.data)["data"]
        token1_id = token1_data["token_id"]
        token1_code = token1_data["token_code"]
        test_token_ids.append(token1_id)
        assert token1_data["status"] == "Waiting"
        assert token1_data["queue_number"] >= 1
        assert len(token1_data["qr_code_base64"]) > 50, "QR code missing or too short"
        assert token1_data["qr_code_mime_type"] == "image/png"
        print(f" PASS: Generated Token ID={token1_id}, Number=#{token1_data['queue_number']}, Code={token1_code}")

        # TEST 4: Verify the student record and token in MySQL
        print("\n[TEST 4] Verify student record and token in MySQL...")
        cur = get_query_cursor()
        cur.execute("SELECT id, full_name, email FROM users WHERE id = %s", (user1_id,))
        db_user = cur.fetchone()
        assert db_user is not None, "User not found in MySQL"
        assert db_user["email"] == "test_e2e_student1@example.edu"

        cur.execute("SELECT id, service_id, user_id, queue_number, token_code, status FROM tokens WHERE id = %s", (token1_id,))
        db_token = cur.fetchone()
        assert db_token is not None, "Token not found in MySQL"
        assert db_token["status"] == "Waiting"
        assert db_token["token_code"] == token1_code

        cur.execute("SELECT event_type FROM queue_records WHERE token_id = %s", (token1_id,))
        db_records = cur.fetchall()
        assert any(r["event_type"] == "Waiting" for r in db_records), "Waiting event not in queue_records"
        cur.close()
        print(f" PASS: Student record and token verified in MySQL.")

        # TEST 5: Track the token and verify queue position
        print("\n[TEST 5] Track the token and verify queue position (GET /api/tokens/<id>)...")
        resp_track = client.get(f"/api/tokens/{token1_id}")
        assert resp_track.status_code == 200
        track_data = json.loads(resp_track.data)["data"]
        assert track_data["token_id"] == token1_id
        assert track_data["status"] == "Waiting"
        assert track_data["queue_position"] >= 1
        assert track_data["estimated_wait_minutes"] >= 0
        assert len(track_data["qr_code_base64"]) > 50, "QR code retrievable on tracking"

        # Also test by 32-character code
        resp_track_code = client.get(f"/api/tokens/{token1_code}")
        assert resp_track_code.status_code == 200
        assert json.loads(resp_track_code.data)["data"]["token_id"] == token1_id
        print(f" PASS: Token tracking verified. Position={track_data['queue_position']}, Wait={track_data['estimated_wait_minutes']}m")

        # TEST 6: Open the admin dashboard / read APIs
        print("\n[TEST 6] Open Admin Dashboard APIs (GET /api/counters, GET /api/admin/queues)...")
        resp_cnt = client.get(f"/api/counters?department_id={dept_id}")
        assert resp_cnt.status_code == 200
        counters = json.loads(resp_cnt.data)["data"]
        assert len(counters) >= 2, f"Expected at least 2 counters for dept {dept_id}, got {len(counters)}"
        counter1 = counters[0]
        counter2 = counters[1]
        print(f" Available Counters: Counter 1 (ID={counter1['id']}, {counter1['counter_name']}), Counter 2 (ID={counter2['id']}, {counter2['counter_name']})")

        resp_admin_q = client.get(f"/api/admin/queues?department_id={dept_id}&counter_id={counter1['id']}")
        assert resp_admin_q.status_code == 200
        admin_q_data = json.loads(resp_admin_q.data)["data"]
        assert "summary" in admin_q_data
        assert admin_q_data["summary"]["waiting_count"] >= 1
        print(f" PASS: Admin dashboard APIs verified. Waiting in queue: {admin_q_data['summary']['waiting_count']}")

        # TEST 7: Call the next token
        print(f"\n[TEST 7] Call next token (POST /api/admin/call-next with counter_id={counter1['id']})...")
        resp_call = client.post("/api/admin/call-next", json={"counter_id": counter1["id"]})
        assert resp_call.status_code == 200, f"Call next failed: {resp_call.data}"
        called_data = json.loads(resp_call.data)["data"]
        assert called_data["token_id"] == token1_id
        assert called_data["status"] == "Called"
        assert called_data["counter_id"] == counter1["id"]
        print(f" PASS: Token #{called_data['queue_number']} called to Counter {counter1['id']}")

        # TEST 8: Verify student queue status changes
        print("\n[TEST 8] Verify student queue status changes on tracking...")
        resp_track2 = client.get(f"/api/tokens/{token1_id}")
        assert resp_track2.status_code == 200
        track_data2 = json.loads(resp_track2.data)["data"]
        assert track_data2["status"] == "Called"
        assert track_data2["counter_id"] == counter1["id"]
        assert track_data2["counter_name"] == counter1["counter_name"]
        print(f" PASS: Student status changed to 'Called' with counter '{track_data2['counter_name']}'")

        # TEST 9: Complete the token
        print(f"\n[TEST 9] Complete the token (POST /api/admin/complete with token_id={token1_id}, counter_id={counter1['id']})...")
        resp_comp = client.post("/api/admin/complete", json={"token_id": token1_id, "counter_id": counter1["id"]})
        assert resp_comp.status_code == 200, f"Complete token failed: {resp_comp.data}"
        comp_data = json.loads(resp_comp.data)["data"]
        assert comp_data["status"] == "Completed"
        assert "duration_seconds" in comp_data
        print(f" PASS: Token completed. Duration={comp_data['duration_seconds']}s")

        # TEST 10: Verify completed status and service history in MySQL
        print("\n[TEST 10] Verify completed status and service history in MySQL...")
        cur = get_query_cursor()
        cur.execute("SELECT status, completed_at FROM tokens WHERE id = %s", (token1_id,))
        token_completed = cur.fetchone()
        assert token_completed is not None, "Token row missing"
        assert token_completed["status"] == "Completed", f"Expected 'Completed', got '{token_completed['status']}'"
        assert token_completed["completed_at"] is not None

        cur.execute("SELECT * FROM service_history WHERE token_id = %s", (token1_id,))
        hist = cur.fetchone()
        assert hist is not None, "Service history record missing in MySQL"
        assert hist["counter_id"] == counter1["id"]
        assert hist["duration_seconds"] >= 0

        cur.execute("SELECT event_type FROM queue_records WHERE token_id = %s ORDER BY id DESC LIMIT 1", (token1_id,))
        latest_event = cur.fetchone()
        assert latest_event["event_type"] == "Completed"
        cur.close()
        print(f" PASS: MySQL persistence verified for completed token and service history (Duration: {hist['duration_seconds']}s).")

        # TEST 11: Test skipping a token
        print("\n[TEST 11] Test skipping a token (POST /api/admin/skip)...")
        # Register student 2
        resp_u2 = client.post("/api/users", json={"full_name": "Student Skip Test", "email": "test_e2e_student2@example.edu", "password": "Password123!"})
        user2_id = json.loads(resp_u2.data)["data"]["user_id"]
        test_user_ids.append(user2_id)

        # Generate token 2
        resp_t2 = client.post("/api/tokens", json={"user_id": user2_id, "service_id": service_id})
        token2_id = json.loads(resp_t2.data)["data"]["token_id"]
        test_token_ids.append(token2_id)

        # Call token 2
        resp_call2 = client.post("/api/admin/call-next", json={"counter_id": counter1["id"]})
        assert resp_call2.status_code == 200
        assert json.loads(resp_call2.data)["data"]["token_id"] == token2_id

        # Skip token 2
        resp_skip = client.post("/api/admin/skip", json={"token_id": token2_id, "counter_id": counter1["id"]})
        assert resp_skip.status_code == 200, f"Skip failed: {resp_skip.data}"
        assert json.loads(resp_skip.data)["data"]["status"] == "Skipped"

        # Verify in MySQL
        cur = get_query_cursor()
        cur.execute("SELECT status FROM tokens WHERE id = %s", (token2_id,))
        assert cur.fetchone()["status"] == "Skipped"
        cur.close()
        print(f" PASS: Token #{token2_id} called and successfully skipped.")

        # TEST 12: Test two counters operating simultaneously
        print("\n[TEST 12] Test two counters operating simultaneously...")
        # Create token A for user 1
        resp_ta = client.post("/api/tokens", json={"user_id": user1_id, "service_id": service_id})
        token_a_id = json.loads(resp_ta.data)["data"]["token_id"]
        test_token_ids.append(token_a_id)

        # Create token B for user 2
        resp_tb = client.post("/api/tokens", json={"user_id": user2_id, "service_id": service_id})
        token_b_id = json.loads(resp_tb.data)["data"]["token_id"]
        test_token_ids.append(token_b_id)

        # Counter 1 calls next -> gets Token A
        resp_c1 = client.post("/api/admin/call-next", json={"counter_id": counter1["id"]})
        assert resp_c1.status_code == 200
        assert json.loads(resp_c1.data)["data"]["token_id"] == token_a_id
        print(f" Counter 1 ({counter1['counter_name']}) called Token A (ID={token_a_id})")

        # Counter 2 calls next -> gets Token B
        resp_c2 = client.post("/api/admin/call-next", json={"counter_id": counter2["id"]})
        assert resp_c2.status_code == 200
        assert json.loads(resp_c2.data)["data"]["token_id"] == token_b_id
        print(f" Counter 2 ({counter2['counter_name']}) called Token B (ID={token_b_id})")

        # Counter 1 attempts to complete Counter 2's token (should fail with 409 counter_mismatch)
        resp_cross = client.post("/api/admin/complete", json={"token_id": token_b_id, "counter_id": counter1["id"]})
        assert resp_cross.status_code == 409, f"Expected 409 counter_mismatch, got {resp_cross.status_code}"
        assert json.loads(resp_cross.data)["error"]["code"] == "counter_mismatch"
        print(" Verified isolation: Counter 1 cannot complete Counter 2's token (409 counter_mismatch).")

        # Counter 1 completes Token A
        resp_comp_a = client.post("/api/admin/complete", json={"token_id": token_a_id, "counter_id": counter1["id"]})
        assert resp_comp_a.status_code == 200

        # Counter 2 completes Token B
        resp_comp_b = client.post("/api/admin/complete", json={"token_id": token_b_id, "counter_id": counter2["id"]})
        assert resp_comp_b.status_code == 200
        print(" PASS: Two counters operated simultaneously and independently without interference.")

        # TEST 13: Check invalid inputs and empty queues
        print("\n[TEST 13] Check invalid inputs and empty queues...")
        # Missing fields in registration
        resp_inv1 = client.post("/api/users", json={"full_name": "", "email": "bad", "password": "123"})
        assert resp_inv1.status_code == 400

        # Duplicate email
        resp_dup = client.post("/api/users", json={"full_name": "Dup", "email": "test_e2e_student1@example.edu", "password": "Password123!"})
        assert resp_dup.status_code == 409
        assert json.loads(resp_dup.data)["error"]["code"] == "email_already_registered"

        # Invalid token reference
        resp_inv_ref = client.get("/api/tokens/invalid-code-123!")
        assert resp_inv_ref.status_code == 400

        # Non-existent token
        resp_not_found = client.get("/api/tokens/999999999")
        assert resp_not_found.status_code == 404

        # Non-existent counter
        resp_bad_cnt = client.post("/api/admin/call-next", json={"counter_id": 999999})
        assert resp_bad_cnt.status_code == 404

        # Call next when queue is empty for this department
        resp_empty = client.post("/api/admin/call-next", json={"counter_id": counter1["id"]})
        assert resp_empty.status_code == 404
        assert json.loads(resp_empty.data)["error"]["code"] == "queue_empty"

        print(" PASS: All boundary, invalid input, and empty queue checks passed as expected.")

        print("\n" + "=" * 70)
        print("ALL 13 TESTS PASSED SUCCESSFULLY! (100% SUCCESS RATE)")
        print("=" * 70)

    finally:
        cleanup()
        db_conn.close()


if __name__ == "__main__":
    run_tests()
