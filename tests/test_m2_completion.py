import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.courseplatform import actions
from backend.courseplatform.contracts import ApiError
from backend.courseplatform.domains import catalog


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "20261004213604_complete_m2_tenant_isolation.sql"


class RecordingConnection:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))
        return self


class M2CompletionTests(unittest.TestCase):
    def test_migration_scopes_audit_public_catalog_and_removes_defaults(self):
        source = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("add column if not exists organization_id text", source)
        self.assertIn("audit_log_scope_organization_check", source)
        self.assertIn("public_listing_status", source)
        self.assertIn("catalog_visibility", source)
        for table in (
            "notifications",
            "push_subscriptions",
            "telegram_link_tokens",
            "chat_rooms",
            "chat_presence",
        ):
            self.assertIn(
                f"alter table courseplatform.{table}\n  alter column organization_id drop default",
                source,
            )
        self.assertIn("20261004213604", source)

    def test_audit_uses_active_organization_and_platform_fallback(self):
        conn = RecordingConnection()
        token = actions._AUDIT_ORGANIZATION_ID.set("ORG-A")
        try:
            actions.audit(conn, "ADMIN", "ADM-1", "UPDATE", "COURSE", "COURSE-1")
        finally:
            actions._AUDIT_ORGANIZATION_ID.reset(token)
        params = conn.calls[-1][1]
        self.assertEqual("ORG-A", params[1])
        self.assertEqual("ORGANIZATION", params[2])

        actions.audit(conn, "SYSTEM", "WORKER", "RUN", "JOB", "JOB-1")
        params = conn.calls[-1][1]
        self.assertIsNone(params[1])
        self.assertEqual("PLATFORM", params[2])

    def test_dispatch_does_not_leak_tenant_context(self):
        observed = []

        def first(_payload):
            actions._AUDIT_ORGANIZATION_ID.set("ORG-A")
            observed.append(actions._AUDIT_ORGANIZATION_ID.get())
            return {"success": True, "data": {}}

        def second(_payload):
            observed.append(actions._AUDIT_ORGANIZATION_ID.get())
            return {"success": True, "data": {}}

        with patch.object(actions, "require_application_schema"), patch.dict(
            actions.ACTIONS, {"m2First": first, "m2Second": second}
        ):
            actions.dispatch("m2First", {})
            actions.dispatch("m2Second", {})
        self.assertEqual(["ORG-A", ""], observed)

    @staticmethod
    def _runtime(*, organization=None, courses=None):
        return SimpleNamespace(
            fetch_one=lambda _query, _params: organization,
            fetch_all=lambda _query, _params: courses or [],
            str_value=lambda value: str(value or "").strip(),
            success=lambda data: {"success": True, "data": data},
        )

    def test_public_institution_projection_is_minimal(self):
        organization = {
            "organization_id": "ORG-A",
            "slug": "institution-a",
            "display_name": "Institution A",
            "legal_name": "Private Legal Name",
            "settings_json": {"secret": "never expose"},
            "public_profile_json": {
                "headline": "Aprender com rigor",
                "description": "Catálogo institucional",
                "logoUrl": "https://cdn.example.test/logo.png",
                "websiteUrl": "https://example.test",
                "privateField": "never expose",
            },
        }
        result = catalog.public_institution_profile_action(
            {"organizationSlug": "institution-a"},
            runtime=self._runtime(organization=organization),
        )
        public = result["data"]["institution"]
        self.assertEqual(
            {"slug", "displayName", "headline", "description", "logoUrl", "websiteUrl"},
            set(public),
        )
        self.assertNotIn("organizationId", public)
        self.assertNotIn("settings", public)

    def test_public_catalog_returns_only_explicit_projection(self):
        organization = {
            "organization_id": "ORG-A",
            "slug": "institution-a",
            "display_name": "Institution A",
            "public_profile_json": {},
        }
        courses = [
            {
                "course_id": "COURSE-1",
                "course_code": "C-1",
                "title": "Curso publicado",
                "description": None,
                "total_hours": 12,
                "version_number": 2,
                "internal_field": "never expose",
            }
        ]
        result = catalog.public_institution_catalog_action(
            {"organizationSlug": "institution-a"},
            runtime=self._runtime(organization=organization, courses=courses),
        )
        public_course = result["data"]["courses"][0]
        self.assertEqual(
            {"courseId", "courseCode", "title", "description", "totalHours", "versionNumber"},
            set(public_course),
        )

    def test_hidden_institution_is_not_exposed(self):
        with self.assertRaises(ApiError) as raised:
            catalog.public_institution_profile_action(
                {"organizationSlug": "hidden"},
                runtime=self._runtime(organization=None),
            )
        self.assertEqual("ORGANIZATION_NOT_FOUND", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
