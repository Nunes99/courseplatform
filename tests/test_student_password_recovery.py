import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.courseplatform import actions
from backend.courseplatform.app import app


NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
SETTINGS = SimpleNamespace(
    password_reset_hash_key="test-only-password-reset-key-32-bytes-long",
    password_reset_ttl_minutes=30,
    password_reset_account_limit=3,
    password_reset_account_window_minutes=30,
    password_reset_source_limit=10,
    password_reset_source_window_minutes=60,
    password_reset_completion_limit=20,
    password_reset_completion_window_minutes=15,
)


class _Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class _RecoveryConnection:
    def __init__(self, *, student=None, reset=None, legacy_admin=None, linked_admin_id=None, source_count=0, email_count=0, attempt_count=0):
        self.student = student
        self.reset = reset
        self.legacy_admin = legacy_admin
        self.linked_admin_id = linked_admin_id
        self.source_count = source_count
        self.email_count = email_count
        self.attempt_count = attempt_count
        self.queries = []
        self.committed = False

    def execute(self, query, params=()):
        normalized = " ".join(query.split()).lower()
        self.queries.append((normalized, params))
        if "from courseplatform.student_password_resets" in normalized and "source_hash =" in normalized:
            return _Result({"count": self.source_count})
        if "from courseplatform.student_password_resets" in normalized and "email_hash =" in normalized:
            return _Result({"count": self.email_count})
        if "from courseplatform.student_password_reset_attempts" in normalized and "count(*)" in normalized:
            return _Result({"count": self.attempt_count})
        if "from courseplatform.students" in normalized and "where email" in normalized:
            return _Result(self.student)
        if "insert into courseplatform.students" in normalized:
            self.student = {
                "student_id": params[0],
                "full_name": params[2],
                "email": params[3],
                "status": "PENDING_VERIFICATION",
            }
            return _Result(self.student)
        if "update courseplatform.admins" in normalized and "returning a.admin_id" in normalized:
            return _Result({"admin_id": self.linked_admin_id} if self.linked_admin_id else None)
        if "from courseplatform.admins" in normalized and "student_id is null" in normalized:
            return _Result(self.legacy_admin)
        if "join courseplatform.students" in normalized and "where r.token_hash" in normalized:
            return _Result(self.reset)
        return _Result()

    def commit(self):
        self.committed = True


def _connection_for(conn):
    @contextmanager
    def fake_connection():
        yield conn

    return fake_connection


class StudentPasswordRecoveryTests(unittest.TestCase):
    def _request(self, conn, email="student@example.test"):
        with (
            patch.object(actions, "get_settings", return_value=SETTINGS),
            patch.object(actions, "connection", _connection_for(conn)),
            patch.object(actions, "utc_now", return_value=NOW),
            patch.object(actions, "audit"),
        ):
            return actions.recover_student_access({"email": email, "_requestSource": "203.0.113.10"})

    def test_request_has_same_public_response_for_known_and_unknown_account(self):
        student = {
            "student_id": "STUDENT-1",
            "full_name": "Student One",
            "email": "student@example.test",
            "status": "ACTIVE",
        }
        known = self._request(_RecoveryConnection(student=student))
        unknown = self._request(_RecoveryConnection(student=None), "missing@example.test")

        self.assertEqual(known["data"], unknown["data"])
        self.assertNotIn("temporaryPassword", known["data"])
        self.assertNotIn("publicStudentId", known["data"])
        self.assertIn("_passwordResetDelivery", known)
        self.assertNotIn("_passwordResetDelivery", unknown)

    def test_request_persists_only_the_token_hash(self):
        student = {
            "student_id": "STUDENT-1",
            "full_name": "Student One",
            "email": "student@example.test",
            "status": "ACTIVE",
        }
        conn = _RecoveryConnection(student=student)
        result = self._request(conn)
        token = result["_passwordResetDelivery"]["token"]
        insert = next(item for item in conn.queries if "insert into courseplatform.student_password_resets" in item[0])

        self.assertNotIn(token, insert[1])
        self.assertIn(actions.hash_secret(token), insert[1])
        self.assertEqual(
            sum("pg_advisory_xact_lock" in query for query, _ in conn.queries),
            2,
        )
        self.assertTrue(conn.committed)

    def test_legacy_staff_recovery_creates_pending_identity_and_issues_token(self):
        conn = _RecoveryConnection(legacy_admin={
            "admin_id": "ADMIN-1",
            "full_name": "Legacy Reviewer",
            "email": "reviewer@example.test",
        })
        result = self._request(conn, "reviewer@example.test")

        self.assertIn("_passwordResetDelivery", result)
        self.assertTrue(any("insert into courseplatform.students" in query for query, _ in conn.queries))
        reset_insert = next(
            item for item in conn.queries
            if "insert into courseplatform.student_password_resets" in item[0]
        )
        self.assertEqual("PENDING", reset_insert[1][5])
        self.assertTrue(conn.committed)

    def test_throttled_request_remains_generic_and_does_not_issue_token(self):
        conn = _RecoveryConnection(source_count=SETTINGS.password_reset_source_limit)
        result = self._request(conn)

        self.assertEqual(result, actions.password_reset_public_result())
        self.assertFalse(any("insert into courseplatform.student_password_resets" in query for query, _ in conn.queries))

    def test_missing_hash_key_is_logged_without_exposing_account_data(self):
        settings = SimpleNamespace(**{**SETTINGS.__dict__, "password_reset_hash_key": "too-short"})
        with (
            patch.object(actions, "get_settings", return_value=settings),
            self.assertLogs("backend.courseplatform.domains.identity", level="ERROR") as captured,
        ):
            result = actions.recover_student_access({
                "email": "student@example.test",
                "_requestSource": "203.0.113.10",
            })

        self.assertEqual(result, actions.password_reset_public_result())
        log_output = " ".join(captured.output)
        self.assertIn("PASSWORD_RESET_HASH_KEY", log_output)
        self.assertNotIn("student@example.test", log_output)
        self.assertNotIn("203.0.113.10", log_output)

    def test_valid_token_changes_password_revokes_sessions_and_consumes_token(self):
        token = "valid-one-time-token"
        reset = {
            "reset_id": "PWR-1",
            "student_id": "STUDENT-1",
            "status": "DELIVERED",
            "student_status": "ACTIVE",
            "expires_at": NOW + timedelta(minutes=10),
            "consumed_at": None,
            "invalidated_at": None,
        }
        conn = _RecoveryConnection(reset=reset)
        with (
            patch.object(actions, "get_settings", return_value=SETTINGS),
            patch.object(actions, "connection", _connection_for(conn)),
            patch.object(actions, "utc_now", return_value=NOW),
            patch.object(actions, "revoke_sessions") as revoke,
            patch.object(actions, "create_student_notification") as notify,
            patch.object(actions, "audit") as audit_log,
        ):
            result = actions.complete_student_password_reset({
                "token": token,
                "newPassword": "new-password-123",
                "confirmPassword": "new-password-123",
                "_requestSource": "203.0.113.10",
            })

        self.assertTrue(result["data"]["passwordChanged"])
        revoke.assert_called_once_with(conn, "STUDENT-1")
        notify.assert_called_once()
        audit_log.assert_called_once()
        self.assertTrue(any("set status = 'consumed'" in query for query, _ in conn.queries))
        self.assertTrue(conn.committed)

    def test_pending_legacy_identity_is_activated_and_linked_after_reset(self):
        reset = {
            "reset_id": "PWR-1",
            "student_id": "STUDENT-1",
            "student_email": "reviewer@example.test",
            "status": "DELIVERED",
            "student_status": "PENDING_VERIFICATION",
            "expires_at": NOW + timedelta(minutes=10),
            "consumed_at": None,
            "invalidated_at": None,
        }
        conn = _RecoveryConnection(reset=reset, linked_admin_id="ADMIN-1")
        with (
            patch.object(actions, "get_settings", return_value=SETTINGS),
            patch.object(actions, "connection", _connection_for(conn)),
            patch.object(actions, "utc_now", return_value=NOW),
            patch.object(actions, "revoke_sessions"),
            patch.object(actions, "create_student_notification"),
            patch.object(actions, "audit") as audit_log,
        ):
            result = actions.complete_student_password_reset({
                "token": "valid-token",
                "newPassword": "new-password-123",
                "confirmPassword": "new-password-123",
                "_requestSource": "203.0.113.10",
            })

        self.assertTrue(result["data"]["passwordChanged"])
        self.assertTrue(any(
            "status = 'active'" in query and "email_verified_at" in query
            for query, _ in conn.queries
        ))
        self.assertTrue(any(
            "update courseplatform.admins" in query and "set student_id" in query
            for query, _ in conn.queries
        ))
        self.assertTrue(any(
            call.args[3] == "STAFF_IDENTITY_LINKED"
            for call in audit_log.call_args_list
        ))

    def test_delivery_accepts_pending_identity_created_for_legacy_staff(self):
        row = {
            "reset_id": "PWR-1",
            "student_id": "STUDENT-1",
            "status": "PENDING",
            "student_status": "PENDING_VERIFICATION",
            "full_name": "Legacy Reviewer",
            "email": "reviewer@example.test",
            "expires_at": NOW + timedelta(minutes=10),
        }
        conn = _RecoveryConnection()
        with (
            patch.object(actions, "fetch_one", return_value=row),
            patch.object(actions, "email_runtime_configuration", return_value={
                "platformUrl": "https://learning.example.test",
                "configured": True,
            }),
            patch.object(actions, "send_email_notification", return_value="message-id") as send,
            patch.object(actions, "connection", _connection_for(conn)),
        ):
            actions.dispatch_student_password_reset("PWR-1", "one-time-token")

        send.assert_called_once()
        self.assertTrue(any("set status = 'delivered'" in query for query, _ in conn.queries))

    def test_expired_or_consumed_token_is_rejected(self):
        for status, expires_at in (("CONSUMED", NOW + timedelta(minutes=5)), ("DELIVERED", NOW - timedelta(seconds=1))):
            conn = _RecoveryConnection(reset={
                "reset_id": "PWR-1",
                "student_id": "STUDENT-1",
                "status": status,
                "student_status": "ACTIVE",
                "expires_at": expires_at,
                "consumed_at": NOW if status == "CONSUMED" else None,
                "invalidated_at": None,
            })
            with (
                patch.object(actions, "get_settings", return_value=SETTINGS),
                patch.object(actions, "connection", _connection_for(conn)),
                patch.object(actions, "utc_now", return_value=NOW),
            ):
                with self.assertRaises(actions.ApiError) as raised:
                    actions.complete_student_password_reset({
                        "token": "invalid-token",
                        "newPassword": "new-password-123",
                        "confirmPassword": "new-password-123",
                        "_requestSource": "203.0.113.10",
                    })
            self.assertEqual(raised.exception.code, "PASSWORD_RESET_TOKEN_INVALID")

    def test_http_response_strips_internal_token_and_overwrites_client_source(self):
        captured = {}

        def fake_dispatch(action, payload):
            captured.update(payload)
            return {
                "success": True,
                "data": {"message": actions.PASSWORD_RESET_GENERIC_MESSAGE},
                "_passwordResetDelivery": {"resetId": "PWR-1", "token": "server-secret-token"},
            }

        with (
            patch("backend.courseplatform.app.dispatch", side_effect=fake_dispatch),
            patch("backend.courseplatform.app.dispatch_student_password_reset") as deliver,
        ):
            response = TestClient(app).post("/api", json={
                "action": "recoverStudentAccess",
                "email": "student@example.test",
                "_requestSource": "attacker-controlled",
            })

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("server-secret-token", response.text)
        self.assertNotEqual(captured["_requestSource"], "attacker-controlled")
        deliver.assert_called_once()

    def test_delivery_uses_fragment_link_and_never_queries_with_plain_token(self):
        token = "one-time-token"
        row = {
            "reset_id": "PWR-1",
            "student_id": "STUDENT-1",
            "status": "PENDING",
            "student_status": "ACTIVE",
            "full_name": "Student One",
            "email": "student@example.test",
            "expires_at": NOW + timedelta(minutes=10),
        }
        conn = _RecoveryConnection()
        configuration = {"platformUrl": "https://learning.example.test", "configured": True}
        with (
            patch.object(actions, "fetch_one", return_value=row) as fetch,
            patch.object(actions, "email_runtime_configuration", return_value=configuration),
            patch.object(actions, "send_email_notification", return_value="message-id") as send,
            patch.object(actions, "connection", _connection_for(conn)),
        ):
            actions.dispatch_student_password_reset("PWR-1", token)

        self.assertNotIn(token, fetch.call_args.args[1])
        delivery = send.call_args.args[0]
        self.assertIn("/#/reset-access?token=", delivery["action_url"])
        self.assertIn(token, delivery["action_url"])
        self.assertTrue(any("set status = 'delivered'" in query for query, _ in conn.queries))

    def test_delivery_ignores_the_request_host_for_reset_links(self):
        token = "one-time-token"
        row = {
            "reset_id": "PWR-1",
            "student_id": "STUDENT-1",
            "status": "PENDING",
            "student_status": "ACTIVE",
            "full_name": "Student One",
            "email": "student@example.test",
            "expires_at": NOW + timedelta(minutes=10),
        }
        conn = _RecoveryConnection()
        with (
            patch.object(actions, "fetch_one", return_value=row),
            patch.object(actions, "email_runtime_configuration", return_value={
                "platformUrl": "https://learning.example.test",
                "configured": True,
            }),
            patch.object(actions, "send_email_notification", return_value="message-id") as send,
            patch.object(actions, "connection", _connection_for(conn)),
        ):
            actions.dispatch_student_password_reset(
                "PWR-1",
                token,
                "https://attacker.example.test",
            )

        action_url = send.call_args.args[0]["action_url"]
        self.assertTrue(action_url.startswith("https://learning.example.test/"))
        self.assertNotIn("attacker.example.test", action_url)

    def test_delivery_failure_is_persisted_and_logged_without_token(self):
        token = "one-time-token"
        row = {
            "reset_id": "PWR-1",
            "student_id": "STUDENT-1",
            "status": "PENDING",
            "student_status": "ACTIVE",
            "full_name": "Student One",
            "email": "student@example.test",
            "expires_at": NOW + timedelta(minutes=10),
        }
        conn = _RecoveryConnection()
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
            actions.dispatch_student_password_reset("PWR-1", token)

        self.assertTrue(any("set status = 'delivery_failed'" in query for query, _ in conn.queries))
        log_output = " ".join(captured.output)
        self.assertIn("delivery failed", log_output.lower())
        self.assertNotIn(token, log_output)
        self.assertNotIn("student@example.test", log_output)

    def test_frontend_no_longer_displays_temporary_password(self):
        root = Path(__file__).resolve().parents[1]
        public_app = (root / "public" / "app.js").read_text(encoding="utf-8")
        static_app = (root / "backend" / "courseplatform" / "static" / "app.js").read_text(encoding="utf-8")
        public_api = (root / "public" / "api.js").read_text(encoding="utf-8")

        self.assertEqual(public_app, static_app)
        self.assertNotIn("result.temporaryPassword", public_app)
        self.assertNotIn("publicStudentId", public_app[public_app.index("function showStudentRecoveryDialog"):public_app.index("async function copyText")])
        self.assertIn("completeStudentPasswordReset", public_api)
        self.assertIn("#/reset-access?", public_app)

    def test_migration_does_not_expose_recovery_tables_as_public_views(self):
        root = Path(__file__).resolve().parents[1]
        migration = (root / "supabase" / "migrations" / "202609120001_student_password_recovery.sql").read_text(encoding="utf-8").lower()

        self.assertIn("enable row level security", migration)
        self.assertNotIn("create or replace view public.student_password", migration)
        self.assertNotIn("alter table courseplatform.students", migration)


if __name__ == "__main__":
    unittest.main()
