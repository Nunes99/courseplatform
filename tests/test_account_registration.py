import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.courseplatform import actions
from backend.courseplatform.app import app


NOW = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
SETTINGS = SimpleNamespace(
    password_reset_hash_key="test-only-registration-key-32-bytes-long",
    account_verification_ttl_minutes=60,
    registration_account_limit=3,
    registration_account_window_minutes=60,
    registration_source_limit=10,
    registration_source_window_minutes=60,
)


class _Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class _RegistrationConnection:
    def __init__(self, *, existing=None, verification=None, source_count=0, email_count=0):
        self.existing = existing
        self.verification = verification
        self.source_count = source_count
        self.email_count = email_count
        self.queries = []
        self.committed = False
        self.student = None

    def execute(self, query, params=()):
        normalized = " ".join(query.split()).lower()
        self.queries.append((normalized, params))
        if "from courseplatform.student_account_verifications" in normalized and "source_hash =" in normalized:
            return _Result({"count": self.source_count})
        if "from courseplatform.student_account_verifications" in normalized and "email_hash =" in normalized:
            return _Result({"count": self.email_count})
        if "from courseplatform.students where email" in normalized:
            return _Result(self.existing or self.student)
        if "insert into courseplatform.students" in normalized:
            self.student = {
                "student_id": params[0],
                "public_student_id": params[1],
                "full_name": params[2],
                "email": params[3],
                "status": "PENDING_VERIFICATION",
                "email_verified_at": None,
            }
            return _Result(self.student)
        if "join courseplatform.students" in normalized and "where v.token_hash" in normalized:
            return _Result(self.verification)
        if "update courseplatform.students" in normalized and "set status = 'active'" in normalized:
            self.student = {
                "student_id": params[0],
                "public_student_id": "STU-12345",
                "full_name": "Student One",
                "email": "student@example.test",
                "status": "ACTIVE",
                "email_verified_at": NOW,
            }
            return _Result(self.student)
        return _Result()

    def commit(self):
        self.committed = True


def _connection_for(conn):
    @contextmanager
    def fake_connection():
        yield conn

    return fake_connection


class AccountRegistrationTests(unittest.TestCase):
    def _register(self, conn):
        with (
            patch.object(actions, "get_settings", return_value=SETTINGS),
            patch.object(actions, "connection", _connection_for(conn)),
            patch.object(actions, "utc_now", return_value=NOW),
            patch.object(actions, "audit"),
            patch.object(actions, "generate_id", side_effect=["VFY-1", "STUDENT-1"]),
            patch.object(actions, "public_student_id", return_value="STU-12345"),
        ):
            return actions.register_student_account({
                "fullName": "Student One",
                "email": "student@example.test",
                "password": "strong-password",
                "confirmPassword": "strong-password",
                "country": "Mozambique",
                "_requestSource": "203.0.113.10",
            })

    def test_registration_creates_pending_account_and_hashes_verification_token(self):
        conn = _RegistrationConnection()
        result = self._register(conn)

        self.assertEqual(actions.REGISTRATION_GENERIC_MESSAGE, result["data"]["message"])
        self.assertIn("_accountVerificationDelivery", result)
        token = result["_accountVerificationDelivery"]["token"]
        verification_insert = next(
            item for item in conn.queries
            if "insert into courseplatform.student_account_verifications" in item[0]
        )
        self.assertNotIn(token, verification_insert[1])
        self.assertIn(actions.hash_secret(token), verification_insert[1])
        self.assertTrue(any("'pending_verification'" in query for query, _ in conn.queries))
        self.assertTrue(conn.committed)

    def test_existing_active_account_gets_generic_response_without_new_token(self):
        conn = _RegistrationConnection(existing={
            "student_id": "STUDENT-1",
            "email": "student@example.test",
            "status": "ACTIVE",
            "email_verified_at": NOW,
        })
        result = self._register(conn)

        self.assertEqual(actions.REGISTRATION_GENERIC_MESSAGE, result["data"]["message"])
        self.assertNotIn("_accountVerificationDelivery", result)

    def test_valid_verification_activates_account_once(self):
        token = "valid-verification-token"
        conn = _RegistrationConnection(verification={
            "verification_id": "VFY-1",
            "student_id": "STUDENT-1",
            "status": "DELIVERED",
            "student_status": "PENDING_VERIFICATION",
            "email_verified_at": None,
            "expires_at": NOW + timedelta(minutes=10),
            "consumed_at": None,
            "invalidated_at": None,
        })
        with (
            patch.object(actions, "connection", _connection_for(conn)),
            patch.object(actions, "utc_now", return_value=NOW),
            patch.object(actions, "audit"),
        ):
            result = actions.complete_student_account_verification({"token": token})

        self.assertTrue(result["data"]["accountActivated"])
        self.assertEqual("ACTIVE", result["data"]["student"]["status"])
        self.assertTrue(any("set status = 'consumed'" in query for query, _ in conn.queries))
        self.assertTrue(conn.committed)

    def test_http_registration_never_returns_plaintext_verification_token(self):
        captured = {}

        def fake_dispatch(action, payload):
            captured.update(payload)
            return {
                "success": True,
                "data": {"message": actions.REGISTRATION_GENERIC_MESSAGE},
                "_accountVerificationDelivery": {
                    "verificationId": "VFY-1",
                    "token": "server-secret-token",
                },
            }

        with (
            patch("backend.courseplatform.app.dispatch", side_effect=fake_dispatch),
            patch("backend.courseplatform.app.dispatch_student_account_verification") as deliver,
        ):
            response = TestClient(app).post("/api", json={
                "action": "registerStudentAccount",
                "fullName": "Student One",
                "email": "student@example.test",
                "password": "strong-password",
                "confirmPassword": "strong-password",
                "_requestSource": "attacker-controlled",
            })

        self.assertEqual(200, response.status_code)
        self.assertNotIn("server-secret-token", response.text)
        self.assertNotEqual("attacker-controlled", captured["_requestSource"])
        deliver.assert_called_once()

    def test_delivery_uses_one_time_fragment_link(self):
        row = {
            "verification_id": "VFY-1",
            "student_id": "STUDENT-1",
            "status": "PENDING",
            "student_status": "PENDING_VERIFICATION",
            "full_name": "Student One",
            "email": "student@example.test",
            "expires_at": NOW + timedelta(minutes=10),
        }
        conn = _RegistrationConnection()
        with (
            patch.object(actions, "fetch_one", return_value=row) as fetch,
            patch.object(actions, "email_runtime_configuration", return_value={
                "platformUrl": "https://learning.example.test",
                "configured": True,
            }),
            patch.object(actions, "send_email_notification", return_value="message-id") as send,
            patch.object(actions, "connection", _connection_for(conn)),
        ):
            actions.dispatch_student_account_verification("VFY-1", "plain-token")

        self.assertNotIn("plain-token", fetch.call_args.args[1])
        self.assertIn("/#/verify-account?token=plain-token", send.call_args.args[0]["action_url"])
        self.assertTrue(any("set status = 'delivered'" in query for query, _ in conn.queries))

    def test_delivery_ignores_the_request_host_for_verification_links(self):
        row = {
            "verification_id": "VFY-1",
            "student_id": "STUDENT-1",
            "status": "PENDING",
            "student_status": "PENDING_VERIFICATION",
            "full_name": "Student One",
            "email": "student@example.test",
            "expires_at": NOW + timedelta(minutes=10),
        }
        conn = _RegistrationConnection()
        with (
            patch.object(actions, "fetch_one", return_value=row),
            patch.object(actions, "email_runtime_configuration", return_value={
                "platformUrl": "https://learning.example.test",
                "configured": True,
            }),
            patch.object(actions, "send_email_notification", return_value="message-id") as send,
            patch.object(actions, "connection", _connection_for(conn)),
        ):
            actions.dispatch_student_account_verification(
                "VFY-1",
                "plain-token",
                "https://attacker.example.test",
            )

        action_url = send.call_args.args[0]["action_url"]
        self.assertTrue(action_url.startswith("https://learning.example.test/"))
        self.assertNotIn("attacker.example.test", action_url)


if __name__ == "__main__":
    unittest.main()
