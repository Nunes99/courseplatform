import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.courseplatform import actions
from backend.courseplatform.api.contracts import AdminLoginRequest, StudentLoginRequest
from backend.courseplatform.contracts import ApiError
from backend.courseplatform.domains import identity


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "20261004103000_add_tenant_session_guards.sql"
)


class _Result:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, organizations):
        self.organizations = organizations
        self.queries = []
        self.committed = False

    def execute(self, query, params=()):
        normalized = " ".join(query.split()).lower()
        self.queries.append((normalized, params))
        if "from courseplatform.organization_memberships m" in normalized:
            return _Result(rows=self.organizations)
        if "update courseplatform.sessions" in normalized and "returning subject_id" in normalized:
            return _Result(row={"subject_id": "STU-1"})
        return _Result()

    def commit(self):
        self.committed = True


def _connection_for(conn):
    @contextmanager
    def fake_connection():
        yield conn

    return fake_connection


def _organization(identifier, name):
    return {
        "organization_id": identifier,
        "slug": identifier.lower(),
        "display_name": name,
        "membership_role": "STUDENT",
    }


class TenantLoginSelectionTests(unittest.TestCase):
    def _runtime(self, conn):
        student = {
            "student_id": "STU-1",
            "email": "student@example.test",
            "status": "ACTIVE",
            "password_hash": "hash",
        }
        return SimpleNamespace(
            require_fields=lambda *_args: None,
            fetch_one=lambda *_args: student,
            database_api_error=lambda error: error,
            verify_password=lambda *_args: True,
            connection=_connection_for(conn),
            revoke_sessions=Mock(),
            create_session=Mock(return_value={"token": "token", "expiresAt": None}),
            public_student=lambda row: {"studentId": row["student_id"]},
            iso=lambda value: value,
            success=lambda data: {"success": True, "data": data},
        )

    def test_single_membership_keeps_login_backwards_compatible(self):
        conn = _Connection([_organization("ORG-A", "Institution A")])
        runtime = self._runtime(conn)

        result = identity.login_action(
            {"email": "student@example.test", "accessCode": "password"},
            runtime,
        )["data"]

        self.assertFalse(result["organizationSelectionRequired"])
        self.assertEqual("ORG-A", result["organization"]["organizationId"])
        runtime.revoke_sessions.assert_called_once_with(conn, "STU-1", "ORG-A")
        runtime.create_session.assert_called_once_with(conn, "STU-1", "", "", "ORG-A")
        self.assertTrue(conn.committed)

    def test_multiple_memberships_require_explicit_selection(self):
        conn = _Connection([
            _organization("ORG-A", "Institution A"),
            _organization("ORG-B", "Institution B"),
        ])
        runtime = self._runtime(conn)

        result = identity.login_action(
            {"email": "student@example.test", "accessCode": "password"},
            runtime,
        )["data"]

        self.assertTrue(result["organizationSelectionRequired"])
        self.assertEqual(["ORG-A", "ORG-B"], [row["organizationId"] for row in result["organizations"]])
        runtime.create_session.assert_not_called()
        runtime.revoke_sessions.assert_not_called()

    def test_tampered_organization_is_rejected_after_credentials(self):
        conn = _Connection([_organization("ORG-A", "Institution A")])
        runtime = self._runtime(conn)

        with self.assertRaises(ApiError) as raised:
            identity.login_action(
                {
                    "email": "student@example.test",
                    "accessCode": "password",
                    "organizationId": "ORG-OTHER",
                },
                runtime,
            )

        self.assertEqual("ORGANIZATION_ACCESS_DENIED", raised.exception.code)
        runtime.create_session.assert_not_called()

    def test_typed_login_contracts_accept_optional_organization(self):
        student = StudentLoginRequest.model_validate({
            "email": "student@example.test",
            "accessCode": "password",
            "organizationId": "ORG-A",
        })
        admin = AdminLoginRequest.model_validate({
            "email": "admin@example.test",
            "adminKey": "password",
            "organizationId": "ORG-A",
        })

        self.assertEqual("ORG-A", student.action_payload()["organizationId"])
        self.assertEqual("ORG-A", admin.action_payload()["organizationId"])


class TenantSessionContextTests(unittest.TestCase):
    def test_current_session_returns_the_server_validated_organization(self):
        runtime = SimpleNamespace(
            student_context=Mock(return_value=(
                {
                    "organization_id": "ORG-A",
                    "expires_at": "2026-10-05T10:00:00+00:00",
                },
                {
                    "active_organization_slug": "institution-a",
                    "active_organization_name": "Institution A",
                    "active_membership_role": "STUDENT",
                },
            )),
            iso=lambda value: value,
            success=lambda data: {"success": True, "data": data},
        )

        result = identity.current_student_session_action(
            {"sessionToken": "student-token"},
            runtime,
        )["data"]

        self.assertTrue(result["sessionActive"])
        self.assertEqual("2026-10-05T10:00:00+00:00", result["expiresAt"])
        self.assertEqual("ORG-A", result["organization"]["organizationId"])
        runtime.student_context.assert_called_once_with(
            {"sessionToken": "student-token"}
        )

    def test_payload_cannot_override_session_organization(self):
        conn = _Connection([])
        with patch.object(
            actions,
            "validate_session_with_conn",
            return_value={"subject_id": "STU-1", "organization_id": "ORG-A"},
        ):
            with self.assertRaises(ApiError) as raised:
                actions.student_context_with_conn(
                    conn,
                    {"sessionToken": "token", "organizationId": "ORG-B"},
                )

        self.assertEqual("SESSION_ORGANIZATION_MISMATCH", raised.exception.code)
        self.assertEqual([], conn.queries)

    def test_switch_rotates_token_only_after_target_membership_is_validated(self):
        organizations = [
            _organization("ORG-A", "Institution A"),
            _organization("ORG-B", "Institution B"),
        ]
        conn = _Connection(organizations)
        create_session = Mock(return_value={"token": "new-token", "expiresAt": None})
        runtime = SimpleNamespace(
            require_fields=lambda *_args: None,
            connection=_connection_for(conn),
            student_context_with_conn=lambda *_args: (
                {"organization_id": "ORG-A"},
                {"student_id": "STU-1"},
            ),
            hash_secret=lambda _token: "hashed-current-token",
            create_session=create_session,
            public_student=lambda row: {"studentId": row["student_id"]},
            iso=lambda value: value,
            success=lambda data: {"success": True, "data": data},
            database_api_error=lambda error: error,
        )

        result = identity.switch_student_organization_action(
            {
                "sessionToken": "current-token",
                "organizationId": "ORG-B",
                "userAgent": "test-agent",
            },
            runtime,
        )["data"]

        self.assertEqual("new-token", result["sessionToken"])
        self.assertEqual("ORG-B", result["organization"]["organizationId"])
        create_session.assert_called_once_with(
            conn, "STU-1", "test-agent", "", "ORG-B"
        )
        self.assertTrue(conn.committed)

    def test_revoked_membership_invalidates_only_the_current_session(self):
        class RevokedConnection(_Connection):
            def execute(self, query, params=()):
                normalized = " ".join(query.split()).lower()
                self.queries.append((normalized, params))
                if "from courseplatform.students s" in normalized:
                    return _Result(row={
                        "student_id": "STU-1",
                        "status": "ACTIVE",
                        "active_membership_status": "SUSPENDED",
                        "active_organization_status": "ACTIVE",
                    })
                return _Result()

        conn = RevokedConnection([])
        with patch.object(
            actions,
            "validate_session_with_conn",
            return_value={
                "session_token": "hashed-token",
                "subject_id": "STU-1",
                "organization_id": "ORG-A",
            },
        ):
            with self.assertRaises(ApiError) as raised:
                actions.student_context_with_conn(conn, {"sessionToken": "token"})

        self.assertEqual("ORGANIZATION_ACCESS_REVOKED", raised.exception.code)
        update_query, update_params = next(
            (query, params)
            for query, params in conn.queries
            if "update courseplatform.sessions" in query
        )
        self.assertIn("where session_token = %s", update_query)
        self.assertEqual(("hashed-token",), update_params)
        self.assertTrue(conn.committed)


class TenantSessionMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8").lower()

    def test_session_tenant_is_immutable(self):
        self.assertIn("prevent_session_organization_change", self.sql)
        self.assertIn("before update of organization_id", self.sql)

    def test_membership_and_organization_changes_revoke_scoped_sessions(self):
        self.assertIn("revoke_sessions_for_membership_change", self.sql)
        self.assertIn("organization_id = old.organization_id", self.sql)
        self.assertIn("revoke_sessions_for_organization_status", self.sql)

    def test_migration_advances_application_contract(self):
        self.assertIn("values ('application', 20261004103000, now())", self.sql)
        self.assertGreaterEqual(actions.EXPECTED_SCHEMA_VERSION, 20261004180000)


class TenantFrontendContractTests(unittest.TestCase):
    def test_login_clients_and_selectors_support_multiple_organizations(self):
        api = (ROOT / "public" / "api.js").read_text(encoding="utf-8")
        student = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
        admin = (ROOT / "public" / "admin.js").read_text(encoding="utf-8")

        self.assertIn("switchStudentOrganization", api)
        self.assertIn("switchAdminOrganization", api)
        self.assertIn("organizationSelectionRequired", student)
        self.assertIn("organizationSelectionRequired", admin)

    def test_student_client_validates_and_expires_sessions_before_loading(self):
        api = (ROOT / "public" / "api.js").read_text(encoding="utf-8")
        student = (ROOT / "public" / "app.js").read_text(encoding="utf-8")

        self.assertIn("/api/v1/auth/students/sessions/current", api)
        self.assertIn("courseSessionExpiresAt", api)
        self.assertIn("expiresAt <= Date.now()", api)
        self.assertIn("await api.currentStudentSession();", student)
        self.assertIn("ORGANIZATION_ACCESS_REVOKED", student)


if __name__ == "__main__":
    unittest.main()
