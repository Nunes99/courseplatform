import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from backend.courseplatform import actions
from backend.courseplatform.domains import administration, identity


class _Result:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, handler=None):
        self.handler = handler or (lambda _query, _params: _Result())
        self.queries = []
        self.committed = False

    def execute(self, query, params=()):
        normalized = " ".join(query.split()).lower()
        self.queries.append((normalized, params))
        return self.handler(normalized, params)

    def commit(self):
        self.committed = True


def _connection_for(conn):
    @contextmanager
    def fake_connection():
        yield conn

    return fake_connection


def _identity_runtime(admin, conn, verify_password):
    def fetch_one(query, _params=()):
        if "count(*) as total" in query.lower():
            return {"total": 1}
        return admin

    return SimpleNamespace(
        require_fields=lambda *_args: None,
        fetch_one=fetch_one,
        database_api_error=lambda error: error,
        verify_password=verify_password,
        connection=_connection_for(conn),
        revoke_sessions=Mock(),
        create_session=lambda *_args: {"token": "admin-token", "expiresAt": None},
        public_admin=lambda row: identity.serialize_admin(row, as_iso=lambda value: value),
        iso=lambda value: value,
        success=lambda data: {"success": True, "data": data},
    )


class UnifiedIdentityLoginTests(unittest.TestCase):
    def test_linked_reviewer_uses_student_password_hash(self):
        admin = {
            "admin_id": "ADM-1",
            "student_id": "STU-1",
            "full_name": "Reviewer",
            "email": "old@example.test",
            "identity_email": "reviewer@example.test",
            "identity_password_hash": "student-hash",
            "identity_status": "ACTIVE",
            "password_hash": "legacy-admin-hash",
            "role": "REVIEWER",
            "status": "ACTIVE",
        }
        checked_hashes = []

        def verify(_password, password_hash):
            checked_hashes.append(password_hash)
            return password_hash == "student-hash"

        conn = _Connection()
        runtime = _identity_runtime(admin, conn, verify)
        result = identity.admin_login_action(
            {"email": "REVIEWER@example.test", "adminKey": "student-password"},
            runtime,
        )

        self.assertEqual(["student-hash"], checked_hashes)
        self.assertEqual("STUDENT", result["data"]["admin"]["identitySource"])
        self.assertEqual("STU-1", result["data"]["admin"]["studentId"])
        self.assertEqual("reviewer@example.test", result["data"]["admin"]["email"])
        runtime.revoke_sessions.assert_called_once_with(conn, "ADMIN:ADM-1")
        self.assertTrue(conn.committed)

    def test_linked_reviewer_cannot_use_dormant_legacy_hash(self):
        admin = {
            "admin_id": "ADM-1",
            "student_id": "STU-1",
            "identity_password_hash": "student-hash",
            "identity_status": "ACTIVE",
            "password_hash": "legacy-admin-hash",
            "role": "REVIEWER",
            "status": "ACTIVE",
        }
        runtime = _identity_runtime(
            admin,
            _Connection(),
            lambda _password, password_hash: password_hash == "legacy-admin-hash",
        )

        with self.assertRaises(actions.ApiError) as raised:
            identity.admin_login_action(
                {"email": "reviewer@example.test", "adminKey": "legacy-password"},
                runtime,
            )

        self.assertEqual("INVALID_ADMIN_CREDENTIALS", raised.exception.code)

    def test_inactive_student_identity_disables_administrative_access(self):
        admin = {
            "admin_id": "ADM-1",
            "student_id": "STU-1",
            "identity_password_hash": "student-hash",
            "identity_status": "INACTIVE",
            "role": "REVIEWER",
            "status": "ACTIVE",
        }
        verifier = Mock(return_value=True)
        runtime = _identity_runtime(admin, _Connection(), verifier)

        with self.assertRaises(actions.ApiError) as raised:
            identity.admin_login_action(
                {"email": "reviewer@example.test", "adminKey": "student-password"},
                runtime,
            )

        self.assertEqual("INVALID_ADMIN_CREDENTIALS", raised.exception.code)
        verifier.assert_not_called()

    def test_unlinked_owner_keeps_legacy_credential_compatibility(self):
        admin = {
            "admin_id": "ADM-OWNER",
            "student_id": None,
            "email": "owner@example.test",
            "password_hash": "owner-hash",
            "role": "OWNER",
            "status": "ACTIVE",
        }
        checked_hashes = []
        conn = _Connection()
        runtime = _identity_runtime(
            admin,
            conn,
            lambda _password, password_hash: checked_hashes.append(password_hash) or True,
        )

        result = identity.admin_login_action(
            {"email": "owner@example.test", "adminKey": "owner-password"},
            runtime,
        )

        self.assertEqual(["owner-hash"], checked_hashes)
        self.assertEqual("LEGACY_ADMIN", result["data"]["admin"]["identitySource"])


class UnifiedIdentityRecoveryTests(unittest.TestCase):
    def test_reviewer_cannot_use_owner_emergency_recovery(self):
        runtime = SimpleNamespace(
            require_fields=lambda *_args: None,
            configured_admin_recovery_hashes=lambda: {"configured"},
            verify_admin_recovery_key=lambda _key: True,
            fetch_one=lambda *_args: {
                "admin_id": "REVIEWER-1",
                "student_id": None,
                "email": "reviewer@example.test",
                "role": "REVIEWER",
                "status": "ACTIVE",
            },
            database_api_error=lambda error: error,
            connection=Mock(),
        )

        with self.assertRaises(actions.ApiError) as raised:
            identity.recover_admin_access_action(
                {"email": "reviewer@example.test", "recoveryKey": "owner-key"},
                runtime,
            )

        self.assertEqual("ADMIN_RECOVERY_OWNER_ONLY", raised.exception.code)
        runtime.connection.assert_not_called()

    def test_owner_emergency_recovery_remains_available(self):
        owner = {
            "admin_id": "OWNER-1",
            "student_id": None,
            "full_name": "Platform Owner",
            "email": "owner@example.test",
            "role": "OWNER",
            "status": "ACTIVE",
        }

        def handler(query, _params):
            if "update courseplatform.admins" in query and "returning" in query:
                return _Result(owner)
            return _Result()

        conn = _Connection(handler)
        runtime = SimpleNamespace(
            require_fields=lambda *_args: None,
            configured_admin_recovery_hashes=lambda: {"configured"},
            verify_admin_recovery_key=lambda _key: True,
            fetch_one=lambda *_args: owner,
            database_api_error=lambda error: error,
            generate_access_code=lambda _length: "temporary-owner-key",
            connection=_connection_for(conn),
            audit=Mock(),
            mask_email=lambda email: email,
            public_admin=lambda row: identity.serialize_admin(row, as_iso=lambda value: value),
            success=lambda data: {"success": True, "data": data},
        )

        result = identity.recover_admin_access_action(
            {"email": "owner@example.test", "recoveryKey": "owner-key"},
            runtime,
        )

        self.assertEqual("temporary-owner-key", result["data"]["temporaryAdminKey"])
        self.assertTrue(conn.committed)


class UnifiedIdentityStaffManagementTests(unittest.TestCase):
    def _runtime(self, conn):
        return SimpleNamespace(
            admin_context=lambda *_args: ({}, {"admin_id": "OWNER-1", "role": "OWNER"}),
            audit=Mock(),
            connection=_connection_for(conn),
            generate_access_code=Mock(return_value="temporary-password"),
            generate_id=lambda _prefix: "ADM-NEW",
            normalize_email=identity.normalize_email,
            public_admin=lambda row: identity.serialize_admin(row, as_iso=lambda value: value),
            require_fields=lambda *_args: None,
            str_value=actions.str_value,
            success=lambda data: {"success": True, "data": data},
            valid_password=identity.valid_password,
        )

    def test_new_reviewer_links_existing_student_without_second_password(self):
        student = {
            "student_id": "STU-1",
            "full_name": "Registered Reviewer",
            "email": "reviewer@example.test",
            "status": "ACTIVE",
        }

        def handler(query, params):
            if "from courseplatform.admins where admin_id" in query:
                return _Result(None)
            if "from courseplatform.students where student_id" in query:
                return _Result(student)
            if "where student_id = %s and admin_id <> %s" in query:
                return _Result(None)
            if "insert into courseplatform.admins" in query:
                return _Result({
                    "admin_id": params[0],
                    "student_id": params[1],
                    "full_name": params[2],
                    "email": params[3],
                    "role": params[-2],
                    "status": params[-1],
                })
            return _Result()

        conn = _Connection(handler)
        runtime = self._runtime(conn)
        result = administration.admin_save_staff_action(
            {
                "studentId": "STU-1",
                "role": "REVIEWER",
                "status": "ACTIVE",
            },
            runtime=runtime,
        )

        self.assertEqual("STU-1", result["data"]["admin"]["studentId"])
        self.assertEqual("Registered Reviewer", result["data"]["admin"]["fullName"])
        self.assertEqual("reviewer@example.test", result["data"]["admin"]["email"])
        self.assertTrue(result["data"]["admin"]["accessActive"])
        self.assertEqual("", result["data"]["adminPassword"])
        runtime.generate_access_code.assert_not_called()
        self.assertTrue(conn.committed)

    def test_new_reviewer_requires_an_active_student_account(self):
        def handler(query, _params):
            if "from courseplatform.admins where admin_id" in query:
                return _Result(None)
            if "from courseplatform.students where student_id" in query:
                return _Result(None)
            return _Result()

        runtime = self._runtime(_Connection(handler))
        with self.assertRaises(actions.ApiError) as raised:
            administration.admin_save_staff_action(
                {
                    "studentId": "STU-MISSING",
                    "role": "REVIEWER",
                    "status": "ACTIVE",
                },
                runtime=runtime,
            )

        self.assertEqual("STUDENT_ACCOUNT_REQUIRED", raised.exception.code)

    def test_linked_staff_identity_cannot_be_reassigned(self):
        existing = {
            "admin_id": "ADM-1",
            "student_id": "STU-1",
            "role": "REVIEWER",
            "status": "ACTIVE",
        }

        def handler(query, _params):
            if "from courseplatform.admins where admin_id" in query:
                return _Result(existing)
            return _Result()

        runtime = self._runtime(_Connection(handler))
        with self.assertRaises(actions.ApiError) as raised:
            administration.admin_save_staff_action(
                {
                    "targetAdminId": "ADM-1",
                    "studentId": "STU-2",
                    "role": "REVIEWER",
                    "status": "ACTIVE",
                },
                runtime=runtime,
            )

        self.assertEqual("STAFF_IDENTITY_CHANGE_FORBIDDEN", raised.exception.code)

    def test_owner_cannot_disable_the_current_owner_session(self):
        runtime = SimpleNamespace(
            admin_context=lambda *_args: ({}, {"admin_id": "OWNER-1", "role": "OWNER"}),
            audit=Mock(),
            connection=Mock(),
            public_admin=Mock(),
            require_fields=lambda *_args: None,
            str_value=actions.str_value,
            success=lambda data: {"success": True, "data": data},
        )

        with self.assertRaises(actions.ApiError) as raised:
            administration.admin_set_staff_status_action(
                {"targetAdminId": "OWNER-1", "status": "INACTIVE"},
                runtime=runtime,
            )

        self.assertEqual("CANNOT_DISABLE_CURRENT_OWNER", raised.exception.code)
        runtime.connection.assert_not_called()

    def test_legacy_staff_cannot_be_reactivated_without_registered_user(self):
        legacy_staff = {
            "admin_id": "ADM-LEGACY",
            "student_id": None,
            "role": "REVIEWER",
            "status": "DELETED",
        }

        def handler(query, _params):
            if "from courseplatform.admins a" in query:
                return _Result(legacy_staff)
            return _Result()

        runtime = SimpleNamespace(
            admin_context=lambda *_args: ({}, {"admin_id": "OWNER-1", "role": "OWNER"}),
            audit=Mock(),
            connection=_connection_for(_Connection(handler)),
            public_admin=Mock(),
            require_fields=lambda *_args: None,
            str_value=actions.str_value,
            success=lambda data: {"success": True, "data": data},
        )

        with self.assertRaises(actions.ApiError) as raised:
            administration.admin_set_staff_status_action(
                {"targetAdminId": "ADM-LEGACY", "status": "ACTIVE"},
                runtime=runtime,
            )

        self.assertEqual("STUDENT_ACCOUNT_REQUIRED", raised.exception.code)

    def test_disabling_student_revokes_student_and_linked_admin_sessions(self):
        student = {"student_id": "STU-1", "status": "INACTIVE"}

        def handler(query, _params):
            if "update courseplatform.students set status" in query:
                return _Result(student)
            return _Result()

        conn = _Connection(handler)
        runtime = SimpleNamespace(
            admin_context=lambda *_args: ({}, {"admin_id": "ADMIN-1", "role": "ADMIN"}),
            audit=Mock(),
            connection=_connection_for(conn),
            public_student=lambda row: row,
            require_fields=lambda *_args: None,
            str_value=actions.str_value,
            success=lambda data: {"success": True, "data": data},
        )

        administration.admin_set_student_status_action(
            {"studentId": "STU-1", "status": "INACTIVE"},
            runtime=runtime,
        )

        session_updates = [query for query, _params in conn.queries if "update courseplatform.sessions" in query]
        self.assertEqual(2, len(session_updates))
        self.assertTrue(any("'admin:' || a.admin_id" in query for query in session_updates))
        self.assertTrue(conn.committed)


class UnifiedIdentityMigrationTests(unittest.TestCase):
    def test_migration_is_additive_and_does_not_copy_password_hashes(self):
        migration = (
            Path(__file__).resolve().parents[1]
            / "supabase"
            / "migrations"
            / "20260920221040_unify_staff_student_identity.sql"
        ).read_text(encoding="utf-8").lower()

        self.assertIn("add column if not exists student_id", migration)
        self.assertIn("uq_admins_student_identity", migration)
        self.assertIn("having count(*) = 1", migration)
        self.assertNotIn("set password_hash", migration)
        self.assertIn("20260920115325", migration)


if __name__ == "__main__":
    unittest.main()
