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

    def test_existing_active_account_is_reported_in_registration_form(self):
        conn = _RegistrationConnection(existing={
            "student_id": "STUDENT-1",
            "email": "student@example.test",
            "status": "ACTIVE",
            "email_verified_at": NOW,
        })

        with self.assertRaises(actions.ApiError) as raised:
            self._register(conn)

        self.assertEqual("EMAIL_ALREADY_REGISTERED", raised.exception.code)
        self.assertIn("já está cadastrado", raised.exception.message)

    def test_http_registration_returns_conflict_for_existing_account(self):
        with patch(
            "backend.courseplatform.actions.dispatch",
            side_effect=actions.ApiError(
                "EMAIL_ALREADY_REGISTERED",
                "Este email já está cadastrado. Inicie sessão ou recupere a palavra-passe.",
            ),
        ):
            response = TestClient(app).post("/api/v1/auth/registrations", json={
                "fullName": "Student One",
                "email": "student@example.test",
                "password": "strong-password",
                "confirmPassword": "strong-password",
            })

        self.assertEqual(409, response.status_code)
        self.assertEqual("EMAIL_ALREADY_REGISTERED", response.json()["error"]["code"])

    def test_rate_limiter_keeps_existing_account_response_generic(self):
        conn = _RegistrationConnection(
            existing={
                "student_id": "STUDENT-1",
                "email": "student@example.test",
                "status": "ACTIVE",
                "email_verified_at": NOW,
            },
            email_count=SETTINGS.registration_account_limit,
        )

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
        self.assertTrue(any("update courseplatform.admins" in query for query, _ in conn.queries))
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
            patch(
                "backend.courseplatform.app.dispatch_student_account_verification",
                return_value=True,
            ) as deliver,
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

    def test_typed_registration_reports_verification_delivery_failure(self):
        def fake_dispatch(action, payload):
            return {
                "success": True,
                "data": {"message": actions.REGISTRATION_GENERIC_MESSAGE},
                "_accountVerificationDelivery": {
                    "verificationId": "VFY-1",
                    "token": "server-secret-token",
                },
            }

        with (
            patch("backend.courseplatform.actions.dispatch", side_effect=fake_dispatch),
            patch(
                "backend.courseplatform.api.identity.dispatch_student_account_verification",
                return_value=False,
            ) as deliver,
        ):
            response = TestClient(app).post("/api/v1/auth/registrations", json={
                "fullName": "Student One",
                "email": "student@example.test",
                "password": "strong-password",
                "confirmPassword": "strong-password",
            })

        self.assertEqual(503, response.status_code)
        self.assertEqual(
            "ACCOUNT_VERIFICATION_DELIVERY_FAILED",
            response.json()["error"]["code"],
        )
        self.assertNotIn("server-secret-token", response.text)
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
            delivered = actions.dispatch_student_account_verification("VFY-1", "plain-token")

        self.assertTrue(delivered)
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

    def test_verification_delivery_failure_is_persisted_without_leaking_token(self):
        token = "one-time-verification-token"
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
            patch.object(actions, "send_email_notification", side_effect=RuntimeError("smtp unavailable")),
            patch.object(actions, "connection", _connection_for(conn)),
            self.assertLogs("backend.courseplatform.domains.communication", level="ERROR") as captured,
        ):
            delivered = actions.dispatch_student_account_verification("VFY-1", token)

        self.assertFalse(delivered)
        self.assertTrue(any("set status = 'delivery_failed'" in query for query, _ in conn.queries))
        log_output = " ".join(captured.output)
        self.assertNotIn(token, log_output)
        self.assertNotIn("student@example.test", log_output)


if __name__ == "__main__":
    unittest.main()
