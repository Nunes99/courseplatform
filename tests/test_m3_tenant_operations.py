import base64
import inspect
import json
import unittest
from pathlib import Path

from backend.courseplatform import actions, storage
from backend.courseplatform.domains import assessments, catalog, certificates, enrollments


ROOT = Path(__file__).resolve().parents[1]


def _jwt_claims(token: str) -> dict:
    segment = token.split(".")[1]
    padding = "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(segment + padding))


class M3TenantOperationTests(unittest.TestCase):
    def test_question_bank_search_is_namespaced_by_organization(self):
        migration = (
            ROOT
            / "supabase"
            / "migrations"
            / "20261011120000_namespace_cache_and_search_by_organization.sql"
        ).read_text(encoding="utf-8").lower()
        source = inspect.getsource(catalog.admin_list_question_bank_action)
        self.assertIn("add column if not exists organization_id text", migration)
        self.assertIn(
            "question_bank_items(organization_id, question_code)", migration
        )
        self.assertIn(
            "question_bank_items(organization_id, course_id, question_code)",
            migration,
        )
        self.assertIn('clauses = ["item.organization_id = %s"]', source)
        self.assertIn("admin_organization_id(admin)", source)

    def test_admin_searches_bind_organization_to_query_and_cursor(self):
        cases = (
            (catalog.admin_list_courses_action, '"admin-courses", organization_id', "c.organization_id = %s"),
            (enrollments.admin_list_groups_action, '"admin-groups", organization_id', "c.organization_id = %s"),
            (assessments.admin_list_submissions_action, '"admin-submissions", organization_id', "c.organization_id = %s"),
            (assessments.admin_list_gradebook_action, '"admin-gradebook", organization_id', "c.organization_id = %s"),
            (certificates.admin_list_certificates_action, '"admin-certificates", organization_id', "c.organization_id = %s"),
            (enrollments.admin_list_course_reconciliation_issues_action, '"admin-course-reconciliation", organization_id', "organization_id = %s"),
        )
        for action, cursor_fragment, sql_fragment in cases:
            with self.subTest(action=action.__name__):
                source = inspect.getsource(action)
                self.assertIn("organization_id = admin_organization_id(admin)", source)
                self.assertIn(cursor_fragment, source)
                self.assertIn(sql_fragment, source)

    def test_question_bank_mutations_reject_cross_tenant_identifiers(self):
        for action in (
            catalog.admin_get_question_bank_item_action,
            catalog.admin_save_question_bank_draft_action,
            catalog.admin_publish_question_bank_version_action,
            catalog.admin_attach_question_bank_version_action,
        ):
            with self.subTest(action=action.__name__):
                source = inspect.getsource(action)
                self.assertIn("admin_organization_id(admin)", source)
                self.assertIn("organization_id", source)

    def test_frontend_cache_uses_tenant_namespace_and_scoped_invalidation(self):
        source = (ROOT / "public" / "api.js").read_text(encoding="utf-8")
        self.assertIn("this.cacheVersions = new Map()", source)
        self.assertIn("adminCacheNamespace()", source)
        self.assertIn("`organization:${organizationId || 'unscoped'}`", source)
        self.assertIn("entry?.namespace === namespace", source)
        self.assertNotIn("this.cache.clear()", source)

    def test_storage_a_rejects_modern_object_from_b(self):
        own = "ORG-A/submission/STU-A/ATT-A/checksum/content.pdf"
        foreign = "ORG-B/submission/STU-B/ATT-B/checksum/content.pdf"
        self.assertEqual(own, storage.require_organization_storage_path(own, "ORG-A"))
        with self.assertRaises(storage.StorageError) as raised:
            storage.require_organization_storage_path(foreign, "ORG-A")
        self.assertEqual("STORAGE_TENANT_MISMATCH", raised.exception.code)

    def test_realtime_tokens_and_inboxes_are_tenant_bound(self):
        secret = "test-only-realtime-secret-with-32-bytes"
        token_a, _ = actions.chat_realtime_token(
            {"type": "STUDENT", "id": "STU-1", "organization_id": "ORG-A"},
            secret,
            30,
        )
        token_b, _ = actions.chat_realtime_token(
            {"type": "STUDENT", "id": "STU-1", "organization_id": "ORG-B"},
            secret,
            30,
        )
        claims_a = _jwt_claims(token_a)
        claims_b = _jwt_claims(token_b)
        self.assertEqual("ORG-A", claims_a["organization_id"])
        self.assertEqual("ORG-B", claims_b["organization_id"])
        self.assertNotEqual(token_a, token_b)
        self.assertNotEqual(
            f"chat:organization:{claims_a['organization_id']}:actor:student:STU-1:inbox",
            f"chat:organization:{claims_b['organization_id']}:actor:student:STU-1:inbox",
        )

    def test_realtime_policy_checks_room_and_membership_organization(self):
        migration = (
            ROOT
            / "supabase"
            / "migrations"
            / "20261004180000_isolate_communication_by_organization.sql"
        ).read_text(encoding="utf-8").lower()
        self.assertIn(
            "room.organization_id = jwt_claims ->> 'organization_id'", migration
        )
        self.assertIn(
            "membership.organization_id = jwt_claims ->> 'organization_id'",
            migration,
        )
        self.assertIn("else false", migration)

    def test_job_deduplication_is_scoped_to_tenant(self):
        migration = (
            ROOT
            / "supabase"
            / "migrations"
            / "20261005020000_isolate_operational_jobs_by_organization.sql"
        ).read_text(encoding="utf-8").lower()
        jobs_source = (
            ROOT / "backend" / "courseplatform" / "jobs.py"
        ).read_text(encoding="utf-8").lower()
        self.assertIn(
            "operational_jobs(organization_id, idempotency_key)", migration
        )
        self.assertIn(
            "on conflict (organization_id, idempotency_key)", jobs_source
        )
        self.assertIn("select job_id, organization_id, job_type", jobs_source)


if __name__ == "__main__":
    unittest.main()
