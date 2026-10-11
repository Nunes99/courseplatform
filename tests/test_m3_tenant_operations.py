import base64
import json
import unittest
from pathlib import Path

from backend.courseplatform import actions, storage


ROOT = Path(__file__).resolve().parents[1]


def _jwt_claims(token: str) -> dict:
    segment = token.split(".")[1]
    padding = "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(segment + padding))


class M3TenantOperationTests(unittest.TestCase):
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
