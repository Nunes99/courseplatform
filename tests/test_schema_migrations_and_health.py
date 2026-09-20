import inspect
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.courseplatform import actions, db
from backend.courseplatform.app import app


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"


class _RowResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _SchemaConnection:
    def __init__(self, relation_row, version_row=None):
        self.relation_row = relation_row
        self.version_row = version_row
        self.queries = []

    def execute(self, query, params=()):
        self.queries.append((query, params))
        if "to_regclass" in query:
            return _RowResult(self.relation_row)
        return _RowResult(self.version_row)


class SchemaContractTests(unittest.TestCase):
    def tearDown(self):
        actions._APPLICATION_SCHEMA_READY = False

    def test_missing_version_table_is_incompatible_without_ddl(self):
        conn = _SchemaConnection(
            {"students_ready": True, "admins_ready": True, "version_table_ready": False}
        )
        status = db.schema_status_with_conn(conn)
        self.assertFalse(status["compatible"])
        self.assertEqual("VERSION_TABLE_MISSING", status["reason"])
        self.assertTrue(all(re.search(r"\bselect\b", query, re.IGNORECASE) for query, _ in conn.queries))

    def test_matching_version_is_compatible(self):
        conn = _SchemaConnection(
            {"students_ready": True, "admins_ready": True, "version_table_ready": True},
            {"version": db.EXPECTED_SCHEMA_VERSION},
        )
        status = db.schema_status_with_conn(conn)
        self.assertTrue(status["compatible"])
        self.assertEqual("READY", status["reason"])

    def test_dispatch_rejects_incompatible_schema_before_handler(self):
        called = []
        actions.ACTIONS["schemaContractProbe"] = lambda payload: called.append(payload)
        try:
            with patch.object(
                actions,
                "schema_status",
                return_value={
                    "compatible": False,
                    "installedVersion": 1,
                    "expectedVersion": db.EXPECTED_SCHEMA_VERSION,
                    "reason": "VERSION_MISMATCH",
                },
            ):
                with self.assertRaises(actions.ApiError) as raised:
                    actions.dispatch("schemaContractProbe", {})
        finally:
            actions.ACTIONS.pop("schemaContractProbe", None)
        self.assertEqual("DATABASE_MIGRATION_REQUIRED", raised.exception.code)
        self.assertEqual([], called)


class HealthEndpointTests(unittest.TestCase):
    client = TestClient(app)

    def test_liveness_does_not_access_database(self):
        with patch.object(actions, "schema_status", side_effect=AssertionError("database accessed")):
            response = self.client.get("/health/live")
        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "ok"}, response.json())

    def test_readiness_reports_unavailable_dependency_without_details(self):
        with patch.object(actions, "schema_status", side_effect=RuntimeError("secret SQL detail")):
            response = self.client.get("/health/ready")
        self.assertEqual(503, response.status_code)
        self.assertEqual({"status": "not_ready"}, response.json())
        self.assertNotIn("secret", response.text.lower())

    def test_readiness_reports_compatible_schema(self):
        with patch.object(
            actions,
            "schema_status",
            return_value={
                "compatible": True,
                "installedVersion": db.EXPECTED_SCHEMA_VERSION,
                "expectedVersion": db.EXPECTED_SCHEMA_VERSION,
                "reason": "READY",
            },
        ):
            response = self.client.get("/health/ready")
        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "ready"}, response.json())

    def test_legacy_public_health_exposes_only_status(self):
        with patch.object(actions, "schema_status", side_effect=RuntimeError("host=private password=hidden")):
            response = self.client.get("/api/index?action=health")
        self.assertEqual(200, response.status_code)
        self.assertEqual({"success": True, "data": {"status": "not_ready"}}, response.json())

    def test_diagnostics_requires_admin_header(self):
        response = self.client.get("/health/diagnostics")
        self.assertEqual(401, response.status_code)
        self.assertEqual("ADMIN_SESSION_REQUIRED", response.json()["error"]["code"])

    def test_query_string_cannot_open_diagnostics(self):
        response = self.client.get("/api/index?action=healthDiagnostics&adminToken=token")
        self.assertEqual(405, response.status_code)

    def test_protected_diagnostics_reports_password_recovery_configuration(self):
        with (
            patch.object(actions, "admin_context"),
            patch.object(actions, "configured_admin_recovery_hashes", return_value=set()),
            patch.object(actions, "get_settings", return_value=SimpleNamespace(
                password_reset_hash_key="test-only-password-reset-key-32-bytes-long",
            )),
            patch.object(actions, "schema_status", return_value={
                "compatible": True,
                "installedVersion": db.EXPECTED_SCHEMA_VERSION,
                "expectedVersion": db.EXPECTED_SCHEMA_VERSION,
                "reason": "READY",
            }),
            patch.object(actions, "fetch_one", return_value={
                "students": 1,
                "students_with_password": 1,
                "admins": 1,
                "admins_with_password": 1,
                "courses": 1,
                "lessons": 1,
            }),
        ):
            result = actions.health_diagnostics({"adminToken": "token"})

        self.assertTrue(result["data"]["authentication"]["studentPasswordRecoveryConfigured"])


class MigrationManifestTests(unittest.TestCase):
    def test_migration_versions_are_unique_and_orderable(self):
        files = sorted(MIGRATIONS.glob("*.sql"))
        versions = [path.name.split("_", 1)[0] for path in files]
        self.assertEqual(len(versions), len(set(versions)))
        self.assertTrue(all(version.isdigit() for version in versions))
        self.assertEqual("20260911000000", versions[0])

    def test_version_migration_matches_backend_contract(self):
        migrations = sorted(MIGRATIONS.glob("*.sql"))
        matching = [
            path for path in migrations
            if str(db.EXPECTED_SCHEMA_VERSION) in path.read_text(encoding="utf-8")
        ]
        self.assertTrue(matching)
        self.assertIn("courseplatform.schema_versions", matching[-1].read_text(encoding="utf-8"))

    def test_runtime_ddl_was_removed_from_python_request_modules(self):
        ddl = re.compile(r"\b(create|alter|drop|grant|revoke)\s+(table|schema|view|function|trigger|privileges)\b", re.IGNORECASE)
        for path in (ROOT / "backend" / "courseplatform").glob("*.py"):
            self.assertIsNone(ddl.search(path.read_text(encoding="utf-8")), path.name)
        self.assertNotRegex((ROOT / "backend" / "courseplatform" / "actions.py").read_text(encoding="utf-8"), r"[A-Z_]+_SQL\s*=")

    def test_all_prepare_and_ensure_functions_are_read_only_with_respect_to_schema(self):
        ddl = re.compile(r"\b(create|alter|drop|grant|revoke)\s+(table|schema|view|function|trigger|privileges)\b", re.IGNORECASE)
        functions = [
            value
            for name, value in vars(actions).items()
            if callable(value) and name.startswith(("prepare_", "ensure_"))
        ]
        self.assertTrue(functions)
        for function in functions:
            self.assertIsNone(ddl.search(inspect.getsource(function)), function.__name__)

    def test_extracted_feature_migrations_cover_runtime_capabilities(self):
        combined = "\n".join(
            path.read_text(encoding="utf-8").lower()
            for path in sorted(MIGRATIONS.glob("2026091312*_materialize_*.sql"))
        )
        for capability in (
            "courseplatform.notification_templates",
            "courseplatform.push_subscriptions",
            "courseplatform.chat_rooms",
            "courseplatform.chat_realtime_topic_allowed",
            "courseplatform.attempts add column if not exists retry_authorized",
            "courseplatform.certificate_settings",
            "courseplatform.certificate_requests",
        ):
            self.assertIn(capability, combined)


if __name__ == "__main__":
    unittest.main()
