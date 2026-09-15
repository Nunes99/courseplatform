import inspect
import re
import unittest
from pathlib import Path

from backend.courseplatform import actions


ROOT = Path(__file__).resolve().parents[1]
APPLICATION_SOURCE = (ROOT / "backend" / "courseplatform" / "actions.py")
MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260913131500_create_courseplatform_runtime_role.sql"
)
COURSE_MODEL_MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260915101047_model_course_versions_and_offerings.sql"
)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _SchemaConnection:
    def __init__(self, relation_rows=None, column_rows=None):
        self.relation_rows = relation_rows or []
        self.column_rows = column_rows or []
        self.queries = []

    def execute(self, query, params=()):
        self.queries.append((query, params))
        if "to_regclass" in query:
            return _Rows(self.relation_rows)
        return _Rows(self.column_rows)


class RuntimeDatabaseRoleTests(unittest.TestCase):
    @staticmethod
    def _granted_tables(sql: str, privilege: str) -> set[str]:
        matches = re.finditer(
            rf"grant\s+{privilege}\s+on\s+table\s+(.*?)\s+to\s+courseplatform_runtime\s*;",
            sql,
            re.IGNORECASE | re.DOTALL,
        )
        return {
            table
            for match in matches
            for table in re.findall(r"courseplatform\.([a-z_][a-z0-9_]*)", match.group(1))
        }

    def test_runtime_role_has_no_admin_attributes_or_password_in_migration(self):
        sql = MIGRATION.read_text(encoding="utf-8").lower()
        self.assertIn("create role courseplatform_runtime", sql)
        self.assertIn("create role courseplatform_api", sql)
        self.assertIn("password null", sql)
        for attribute in (
            "nosuperuser",
            "nocreatedb",
            "nocreaterole",
            "noreplication",
            "nobypassrls",
        ):
            self.assertGreaterEqual(sql.count(attribute), 2)
        self.assertNotRegex(sql, r"password\s+['\"][^'\"]+['\"]")

    def test_runtime_role_is_limited_to_application_dml(self):
        sql = MIGRATION.read_text(encoding="utf-8").lower()
        self.assertIn("grant usage on schema courseplatform", sql)
        self.assertIn("grant select on table", sql)
        self.assertIn("grant insert on table", sql)
        self.assertIn("grant update on table", sql)
        self.assertIn("grant delete on table", sql)
        self.assertNotIn("grant all privileges on all tables", sql)
        self.assertNotIn("grant create on schema", sql)
        self.assertNotIn("grant truncate", sql)
        self.assertNotIn("grant usage, select on sequences", sql)
        self.assertNotIn("alter default privileges", sql)
        self.assertIn("for all to courseplatform_runtime using (true) with check (true)", sql)

    def test_runtime_role_has_explicit_required_pgcrypto_contract(self):
        sql = MIGRATION.read_text(encoding="utf-8").lower()
        for signature in (
            "crypt(text,text)",
            "gen_salt(text,integer)",
            "pgp_sym_encrypt(text,text,text)",
            "pgp_sym_decrypt(bytea,text)",
        ):
            self.assertIn(signature, sql)
        self.assertIn(
            "revoke all privileges on all functions in schema courseplatform",
            sql,
        )

    def test_runtime_grants_cover_every_static_application_query(self):
        source = APPLICATION_SOURCE.read_text(encoding="utf-8")
        sql = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (MIGRATION, COURSE_MODEL_MIGRATION)
        )
        expected = {
            "select": set(
                re.findall(
                    r"\b(?:from|join)\s+courseplatform\.([a-z_][a-z0-9_]*)",
                    source,
                    re.IGNORECASE,
                )
            ),
            "insert": set(
                re.findall(
                    r"\binsert\s+into\s+courseplatform\.([a-z_][a-z0-9_]*)",
                    source,
                    re.IGNORECASE,
                )
            ),
            "update": set(
                re.findall(
                    r"\bupdate\s+courseplatform\.([a-z_][a-z0-9_]*)",
                    source,
                    re.IGNORECASE,
                )
            ),
            "delete": set(
                re.findall(
                    r"\bdelete\s+from\s+courseplatform\.([a-z_][a-z0-9_]*)",
                    source,
                    re.IGNORECASE,
                )
            ),
        }
        for privilege, used_tables in expected.items():
            granted_tables = self._granted_tables(sql, privilege)
            self.assertFalse(
                used_tables - granted_tables,
                f"Missing {privilege} grants: {sorted(used_tables - granted_tables)}",
            )

    def test_unused_legacy_tables_receive_no_runtime_grant(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        all_grants = set().union(
            *(self._granted_tables(sql, privilege) for privilege in ("select", "insert", "update", "delete"))
        )
        self.assertTrue(
            {
                "lists",
                "media_content",
                "new_credentials",
                "schema_guide",
                "student_import",
                "student_import_results",
            }.isdisjoint(all_grants)
        )
        self.assertEqual(
            {"certificate_requests", "chat_presence", "notification_templates"},
            self._granted_tables(sql, "delete"),
        )

    def test_request_time_schema_checks_do_not_execute_ddl(self):
        for function in (
            actions.health,
            actions.ensure_notification_feature_schema,
            actions.ensure_chat_feature_schema,
            actions.ensure_chat_realtime_schema,
            actions.ensure_assessment_feature_schema,
            actions.ensure_certificate_feature_schema,
        ):
            source = inspect.getsource(function).lower()
            self.assertNotRegex(
                source,
                r"conn\.execute\([^\n]*(create|alter|drop|grant|revoke)",
                function.__name__,
            )
        self.assertNotIn("ensure_schema", inspect.getsource(actions.health))

    def test_schema_validation_reports_missing_objects_without_writes(self):
        conn = _SchemaConnection(
            relation_rows=[{"object_name": "courseplatform.missing_table"}],
            column_rows=[{"object_name": "courseplatform.students.missing_column"}],
        )
        with self.assertRaises(actions.ApiError) as raised:
            actions.require_schema_capabilities(
                conn,
                "teste",
                ("courseplatform.missing_table",),
                ("courseplatform.students.missing_column",),
            )
        self.assertEqual("DATABASE_MIGRATION_REQUIRED", raised.exception.code)
        self.assertEqual(
            ["courseplatform.missing_table", "courseplatform.students.missing_column"],
            raised.exception.details["missingObjects"],
        )
        self.assertTrue(all(re.search(r"\bselect\b", query, re.IGNORECASE) for query, _ in conn.queries))


if __name__ == "__main__":
    unittest.main()
