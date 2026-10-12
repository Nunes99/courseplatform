import inspect
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.courseplatform.app import app
from backend.courseplatform.domains import platform


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "20261012120000_add_platform_onboarding_foundation.sql"


class M4MigrationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8").lower()

    def test_global_identity_and_sessions_are_separate_from_tenant_admin(self):
        self.assertIn("create table if not exists courseplatform.platform_operators", self.sql)
        self.assertIn("create table if not exists courseplatform.platform_sessions", self.sql)
        self.assertIn("student_id text not null unique", self.sql)
        self.assertNotIn("insert into courseplatform.platform_operators", self.sql)

    def test_onboarding_cannot_provision_an_organization_in_this_phase(self):
        self.assertIn("organization_onboarding_not_provisioned_check", self.sql)
        self.assertIn("check (provisioned_organization_id is null)", self.sql)
        self.assertNotIn("insert into courseplatform.organizations\n", self.sql)
        self.assertIn("'ready_for_provisioning'", self.sql)

    def test_client_roles_have_no_direct_access(self):
        self.assertIn("from public, anon, authenticated", self.sql)
        self.assertIn("enable row level security", self.sql)
        self.assertIn("values ('application', 20261012120000, now())", self.sql)


class M4DomainContractTests(unittest.TestCase):
    def test_onboarding_transitions_stop_before_provisioning(self):
        self.assertIn(
            "READY_FOR_PROVISIONING",
            platform.ONBOARDING_TRANSITIONS["UNDER_REVIEW"],
        )
        self.assertNotIn("ACTIVE", platform.ONBOARDING_STATUSES)
        self.assertNotIn("PROVISIONED", platform.ONBOARDING_STATUSES)

    def test_only_global_write_roles_can_review_requests(self):
        self.assertEqual(
            {"GLOBAL_OWNER", "PLATFORM_ADMIN"},
            set(platform.PLATFORM_WRITE_ROLES),
        )
        source = inspect.getsource(platform.update_onboarding_request)
        self.assertIn("PLATFORM_WRITE_ROLES", source)
        self.assertIn("for update", source.lower())
        self.assertIn("ONBOARDING_STATUS_CHANGED", source)

    def test_dashboard_does_not_query_academic_rows(self):
        source = inspect.getsource(platform.platform_dashboard).lower()
        self.assertIn("courseplatform.organizations", source)
        self.assertIn("organization_onboarding_requests", source)
        self.assertNotIn("courseplatform.attempts", source)
        self.assertNotIn("courseplatform.answers", source)
        self.assertNotIn("courseplatform.lesson_progress", source)


class M4TypedRouteTests(unittest.TestCase):
    client = TestClient(app)

    def test_openapi_exposes_global_routes_separately(self):
        paths = self.client.get("/openapi.json").json()["paths"]
        self.assertIn("/api/v1/platform/auth/sessions", paths)
        self.assertIn("/api/v1/platform/auth/sessions/current", paths)
        self.assertIn("/api/v1/platform/onboarding-requests", paths)
        self.assertIn("/api/v1/platform/dashboard", paths)
        self.assertIn("/api/v1/platform/onboarding-requests/{request_id}", paths)

    def test_platform_login_uses_dedicated_domain(self):
        result = {
            "success": True,
            "data": {
                "platformToken": "token",
                "expiresAt": "2026-10-12T12:00:00+00:00",
                "operator": {"operatorId": "POP-1"},
            },
        }
        with patch.object(platform, "create_platform_session", return_value=result) as action:
            response = self.client.post(
                "/api/v1/platform/auth/sessions",
                json={"email": "operator@example.test", "password": "password"},
            )
        self.assertEqual(200, response.status_code)
        self.assertEqual(result, response.json())
        payload = action.call_args.args[0]
        self.assertEqual("operator@example.test", payload["email"])
        self.assertNotIn("organizationId", payload)

    def test_public_onboarding_is_strict_and_idempotent(self):
        result = {"success": True, "data": {"request": {"requestId": "ONB-1"}, "replayed": False}}
        payload = {
            "idempotencyKey": "f0cb59d2-78b1-4ed4-9a95-5a9949a7fd60",
            "requestedSlug": "instituicao-teste",
            "displayName": "Instituição Teste",
            "contactName": "Responsável",
            "contactEmail": "contact@example.test",
        }
        with patch.object(platform, "submit_onboarding_request", return_value=result) as action:
            response = self.client.post("/api/v1/platform/onboarding-requests", json=payload)
        self.assertEqual(200, response.status_code)
        self.assertEqual(payload["idempotencyKey"], action.call_args.args[0]["idempotencyKey"])

        invalid = self.client.post(
            "/api/v1/platform/onboarding-requests",
            json={**payload, "unexpected": True},
        )
        self.assertEqual(422, invalid.status_code)

        invalid_url = self.client.post(
            "/api/v1/platform/onboarding-requests",
            json={**payload, "websiteUrl": "javascript:alert(1)"},
        )
        self.assertEqual(422, invalid_url.status_code)

    def test_idempotency_conflict_and_rate_limit_are_explicit_contracts(self):
        source = inspect.getsource(platform.submit_onboarding_request)
        self.assertIn("IDEMPOTENCY_KEY_CONFLICT", source)
        self.assertIn("ONBOARDING_RATE_LIMITED", source)
        self.assertIn("interval '24 hours'", source)

    def test_platform_page_is_a_separate_static_entrypoint(self):
        response = self.client.get("/platform")
        self.assertEqual(200, response.status_code)
        self.assertIn("Administração global", response.text)
        self.assertIn("platform.js", response.text)


if __name__ == "__main__":
    unittest.main()
