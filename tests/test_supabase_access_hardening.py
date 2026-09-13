import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "20260913072447_stage3_harden_supabase_access.sql"
DIAGNOSTIC = ROOT / "supabase" / "diagnostics" / "stage3_access_audit.sql"
SCHEMAS = (
    ROOT / "supabase" / "schema.sql",
    ROOT / "backend" / "courseplatform" / "schema.sql",
)


class SupabaseAccessHardeningTests(unittest.TestCase):
    def test_diagnostic_is_metadata_only(self):
        sql = DIAGNOSTIC.read_text(encoding="utf-8").lower()
        self.assertNotRegex(sql, r"\b(insert|update|delete|alter|create|drop|truncate|grant|revoke)\b\s")
        self.assertIn("pg_policies", sql)
        self.assertIn("pg_default_acl", sql)
        self.assertIn("storage.buckets", sql)

    def test_migration_revokes_clients_and_uses_security_invoker(self):
        sql = MIGRATION.read_text(encoding="utf-8").lower()
        self.assertIn("security_invoker = true", sql)
        self.assertIn("from public, anon, authenticated, service_role", sql)
        self.assertIn("schema courseplatform from public, anon, authenticated", sql)
        self.assertIn("schema public", sql)
        for view in (
            "students", "admins", "sessions", "questions", "question_options",
            "answers", "audit_log", "new_credentials",
        ):
            self.assertRegex(sql, rf"['\"]{re.escape(view)}['\"]")

    def test_realtime_exception_is_narrow(self):
        migration = MIGRATION.read_text(encoding="utf-8").lower()
        chat_sql = (ROOT / "supabase" / "chat_realtime.sql").read_text(encoding="utf-8").lower()
        for sql in (migration, chat_sql):
            self.assertIn("grant execute on function courseplatform.chat_realtime_topic_allowed", sql)
            self.assertNotIn("grant execute on all functions in schema courseplatform to authenticated", sql)
        self.assertIn("revoke all on function courseplatform.broadcast_chat_message_change()", chat_sql)

    def test_fresh_install_schemas_do_not_grant_public_schema_wholesale(self):
        for path in SCHEMAS:
            sql = path.read_text(encoding="utf-8").lower()
            self.assertNotIn("grant select on all tables in schema public", sql)
            self.assertIn("security_invoker = true", sql)
            self.assertIn("revoke all privileges on schema courseplatform from public, anon, authenticated", sql)

    def test_server_secrets_are_absent_from_frontend_sources(self):
        forbidden = re.compile(
            r"supabase_service_role_key|supabase_secret_key|supabase_jwt_secret|"
            r"supabase_realtime_jwt_secret|postgres_password|database_url",
            re.IGNORECASE,
        )
        frontend_roots = (ROOT / "public", ROOT / "backend" / "courseplatform" / "static")
        violations = []
        for frontend_root in frontend_roots:
            for path in frontend_root.rglob("*"):
                if path.suffix.lower() not in {".js", ".html", ".css", ".json"}:
                    continue
                if forbidden.search(path.read_text(encoding="utf-8", errors="ignore")):
                    violations.append(str(path.relative_to(ROOT)))
        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
