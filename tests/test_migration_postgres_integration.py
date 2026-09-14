import os
import unittest
from pathlib import Path
from urllib.parse import urlsplit

import psycopg


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"
TEST_DATABASE_URL = os.getenv("COURSEPLATFORM_TEST_DATABASE_URL", "")
STAGE4_PREFIXES = {
    "20260913120000",
    "20260913121000",
    "20260913122000",
    "20260913123000",
    "20260913124000",
    "20260913185739",
    "20260914100000",
}
RUNTIME_ROLE_VERSION = "20260913131500"


def migration_files():
    return sorted(MIGRATIONS.glob("*.sql"))


@unittest.skipUnless(TEST_DATABASE_URL, "COURSEPLATFORM_TEST_DATABASE_URL não configurada")
class PostgresMigrationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parsed = urlsplit(TEST_DATABASE_URL)
        if parsed.hostname not in {"127.0.0.1", "localhost"} or "test" not in parsed.path.lower():
            raise unittest.SkipTest("O teste destrutivo só aceita uma base local cujo nome contenha 'test'.")
        with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
            conn.execute("drop schema if exists courseplatform cascade")
            conn.execute("drop schema if exists realtime cascade")
            conn.execute("drop schema if exists storage cascade")
            conn.execute("drop schema if exists extensions cascade")
            conn.execute("drop schema if exists public cascade")
            conn.execute("create schema public")
            conn.execute(
                """
                do $$
                begin
                  if exists (select 1 from pg_roles where rolname = 'courseplatform_api') then
                    if exists (select 1 from pg_roles where rolname = 'courseplatform_runtime') then
                      revoke courseplatform_runtime from courseplatform_api;
                    end if;
                    drop role courseplatform_api;
                  end if;
                  if exists (select 1 from pg_roles where rolname = 'courseplatform_runtime') then
                    revoke connect on database postgres from courseplatform_runtime;
                    drop role courseplatform_runtime;
                  end if;
                end
                $$;
                """
            )

    def setUp(self):
        self.conn = psycopg.connect(TEST_DATABASE_URL, autocommit=True)
        self.conn.execute("drop schema if exists courseplatform cascade")
        self.conn.execute("drop schema if exists realtime cascade")
        self.conn.execute("drop schema if exists storage cascade")
        self.conn.execute("drop schema if exists extensions cascade")
        self.conn.execute("drop schema if exists public cascade")
        self.conn.execute("create schema public")
        self._bootstrap_supabase_contracts()

    def tearDown(self):
        self.conn.close()

    def _bootstrap_supabase_contracts(self):
        self.conn.execute(
            """
            do $$
            begin
              if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon nologin; end if;
              if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated nologin; end if;
              if not exists (select 1 from pg_roles where rolname = 'service_role') then create role service_role nologin bypassrls; end if;
            end
            $$;
            create schema extensions;
            create schema realtime;
            create schema storage;
            create table storage.buckets (
              id text primary key,
              name text not null,
              public boolean not null default false
            );
            create table realtime.messages (
              id bigint generated always as identity primary key,
              extension text not null default 'broadcast',
              private boolean not null default true
            );
            alter table realtime.messages enable row level security;
            create function realtime.topic() returns text language sql stable as $$ select ''::text $$;
            create function realtime.send(jsonb, text, text, boolean) returns void language plpgsql as $$ begin return; end $$;
            """
        )

    def _apply(self, paths):
        for path in paths:
            with self.conn.transaction():
                self.conn.execute(path.read_text(encoding="utf-8"))

    def _runtime_roles_exist(self):
        return bool(
            self.conn.execute(
                "select 1 from pg_roles where rolname = 'courseplatform_runtime'"
            ).fetchone()
        )

    def test_empty_database_receives_full_chain_and_repeat_preserves_data(self):
        files = migration_files()
        self._apply(files)
        self.conn.execute(
            "insert into courseplatform.students (student_id, full_name, email) values ('STU-TEST', 'Test Student', 'student@example.test')"
        )
        runtime_role_migration = next(
            path for path in files if path.name.startswith(RUNTIME_ROLE_VERSION)
        )
        with self.assertRaises(psycopg.errors.RaiseException):
            self._apply([runtime_role_migration])
        self._apply(
            [path for path in files if not path.name.startswith(RUNTIME_ROLE_VERSION)]
        )
        count = self.conn.execute(
            "select count(*) from courseplatform.students where student_id = 'STU-TEST'"
        ).fetchone()[0]
        version = self.conn.execute(
            "select version from courseplatform.schema_versions where component = 'application'"
        ).fetchone()[0]
        self.assertEqual(1, count)
        self.assertEqual(20260914100000, version)

    def test_previous_schema_upgrade_preserves_related_learning_records(self):
        files = migration_files()
        previous = [path for path in files if path.name.split("_", 1)[0] not in STAGE4_PREFIXES]
        if self._runtime_roles_exist():
            previous = [path for path in previous if not path.name.startswith(RUNTIME_ROLE_VERSION)]
        stage4 = [path for path in files if path.name.split("_", 1)[0] in STAGE4_PREFIXES]
        self._apply(previous)
        self.conn.execute(
            """
            insert into courseplatform.students (student_id, full_name, email)
            values ('STU-HISTORY', 'History Student', 'history@example.test');
            insert into courseplatform.courses (course_id, course_code, title)
            values ('COURSE-HISTORY', 'HISTORY', 'History Course');
            insert into courseplatform.enrollments (enrollment_id, student_id, course_id, progress_percent)
            values ('ENR-HISTORY', 'STU-HISTORY', 'COURSE-HISTORY', 75);
            """
        )
        self._apply(stage4)
        row = self.conn.execute(
            """
            select s.student_id, e.progress_percent
            from courseplatform.students s
            join courseplatform.enrollments e on e.student_id = s.student_id
            where s.student_id = 'STU-HISTORY'
            """
        ).fetchone()
        self.assertEqual(("STU-HISTORY", 75), row)


if __name__ == "__main__":
    unittest.main()
