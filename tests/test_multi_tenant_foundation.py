import unittest
from pathlib import Path

from backend.courseplatform.config import Settings
from backend.courseplatform.db import EXPECTED_SCHEMA_VERSION


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "20261004063506_add_multi_tenant_foundation.sql"


class MultiTenantFoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8").lower()

    def test_backend_and_migration_share_the_schema_contract(self):
        self.assertEqual(20261004063506, EXPECTED_SCHEMA_VERSION)
        self.assertIn("values ('application', 20261004063506, now())", self.sql)

    def test_global_identities_are_not_repurposed_as_tenants(self):
        self.assertIn("create table if not exists courseplatform.organizations", self.sql)
        self.assertIn("create table if not exists courseplatform.organization_memberships", self.sql)
        self.assertNotIn("alter table courseplatform.students\n  rename column organization", self.sql)
        self.assertIn("student_id text references courseplatform.students", self.sql)
        self.assertIn("admin_id text references courseplatform.admins", self.sql)

    def test_existing_context_is_backfilled_without_recreating_history(self):
        self.assertIn("'org-lmtwebnairs'", self.sql)
        self.assertIn("alter table courseplatform.courses", self.sql)
        self.assertIn("alter table courseplatform.sessions", self.sql)
        self.assertIn("alter table courseplatform.reviewer_scopes", self.sql)
        self.assertNotIn("delete from courseplatform.students", self.sql)
        self.assertNotIn("delete from courseplatform.courses", self.sql)

    def test_memberships_have_identity_role_and_uniqueness_guards(self):
        for contract in (
            "organization_memberships_identity_check",
            "organization_memberships_role_identity_check",
            "uq_organization_memberships_student_role",
            "uq_organization_memberships_admin_role",
        ):
            self.assertIn(contract, self.sql)

    def test_transition_keeps_new_identities_in_the_default_organization(self):
        self.assertIn("sync_default_student_membership", self.sql)
        self.assertIn("sync_default_admin_membership", self.sql)
        self.assertIn("after insert or update of status on courseplatform.students", self.sql)
        self.assertIn("after insert or update of role, status on courseplatform.admins", self.sql)

    def test_browser_roles_receive_no_direct_access(self):
        self.assertIn("from public, anon, authenticated", self.sql)
        self.assertIn("alter table courseplatform.organizations enable row level security", self.sql)
        self.assertIn("alter table courseplatform.organization_memberships enable row level security", self.sql)
        self.assertIn("grant select on table", self.sql)
        self.assertNotIn("grant insert on table\n      courseplatform.organizations", self.sql)

    def test_default_organization_is_explicit_configuration(self):
        self.assertEqual("ORG-LMTWEBNAIRS", Settings().default_organization_id)


if __name__ == "__main__":
    unittest.main()
