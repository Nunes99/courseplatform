import os
import unittest
from pathlib import Path
from urllib.parse import urlsplit

import psycopg


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"
TEST_DATABASE_URL = os.getenv("COURSEPLATFORM_TEST_DATABASE_URL", "")
UPGRADE_PREFIXES = {
    "20260913120000",
    "20260913121000",
    "20260913122000",
    "20260913123000",
    "20260913124000",
    "20260913185739",
    "20260914103215",
    "20260915101047",
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
        self.assertEqual(20260915101047, version)

    def test_previous_schema_upgrade_preserves_related_learning_records(self):
        files = migration_files()
        previous = [path for path in files if path.name.split("_", 1)[0] not in UPGRADE_PREFIXES]
        if self._runtime_roles_exist():
            previous = [path for path in previous if not path.name.startswith(RUNTIME_ROLE_VERSION)]
        upgrade = [path for path in files if path.name.split("_", 1)[0] in UPGRADE_PREFIXES]
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
        self._apply(upgrade)
        row = self.conn.execute(
            """
            select s.student_id, e.progress_percent
            from courseplatform.students s
            join courseplatform.enrollments e on e.student_id = s.student_id
            where s.student_id = 'STU-HISTORY'
            """
        ).fetchone()
        self.assertEqual(("STU-HISTORY", 75), row)

        enrollment = self.conn.execute(
            """
            select offering_id, course_version_id
            from courseplatform.enrollments
            where enrollment_id = 'ENR-HISTORY'
            """
        ).fetchone()
        self.assertTrue(enrollment[0])
        self.assertTrue(enrollment[1])

    def test_same_student_can_join_two_offerings_without_changing_first_certificate(self):
        files = migration_files()
        self._apply(files)
        self.conn.execute(
            """
            insert into courseplatform.students (student_id, full_name, email)
            values ('STU-EDITION', 'Edition Student', 'edition@example.test');
            insert into courseplatform.courses (course_id, course_code, title, total_hours)
            values ('COURSE-EDITION', 'EDITION', 'Edition Course', 12);
            """
        )
        initial_version = self.conn.execute(
            """
            insert into courseplatform.course_versions
              (course_version_id, course_id, version_number, status, title, total_hours,
               passing_score, content_snapshot_json, published_at)
            values ('CRSV-EDITION-1', 'COURSE-EDITION', 1, 'PUBLISHED', 'Edition Course',
                    12, 60, '{"lessons": []}'::jsonb, now())
            returning course_version_id
            """
        ).fetchone()[0]
        self.conn.execute(
            """
            insert into courseplatform.course_offerings
              (offering_id, course_id, course_version_id, offering_code, name, status)
            values ('COFF-EDITION-1', 'COURSE-EDITION', %s, 'EDITION-001', 'Primeira edição', 'ACTIVE');
            insert into courseplatform.enrollments
              (enrollment_id, student_id, course_id, course_version_id, offering_id,
               status, progress_percent, final_score)
            values ('ENR-EDITION-1', 'STU-EDITION', 'COURSE-EDITION', %s,
                    'COFF-EDITION-1', 'COMPLETED', 100, 88);
            insert into courseplatform.certificates
              (certificate_id, student_id, course_id, enrollment_id, offering_id,
               course_version_id, certificate_number, verification_code, final_score)
            values ('CERT-EDITION-1', 'STU-EDITION', 'COURSE-EDITION', 'ENR-EDITION-1',
                    'COFF-EDITION-1', %s, 'LSS-TEST-1', 'LSSVERIFY1', 88);
            """,
            (initial_version, initial_version, initial_version),
        )
        self.conn.execute(
            """
            insert into courseplatform.course_versions
              (course_version_id, course_id, version_number, status, title, total_hours,
               passing_score, content_snapshot_json, published_at)
            values ('CRSV-EDITION-2', 'COURSE-EDITION', 2, 'PUBLISHED', 'Edition Course v2',
                    20, 70, '{"lessons": []}'::jsonb, now());
            insert into courseplatform.course_offerings
              (offering_id, course_id, course_version_id, offering_code, name, status)
            values ('COFF-EDITION-2', 'COURSE-EDITION', 'CRSV-EDITION-2',
                    'EDITION-002', 'Segunda edição', 'OPEN');
            insert into courseplatform.enrollments
              (enrollment_id, student_id, course_id, course_version_id, offering_id,
               status, progress_percent)
            values ('ENR-EDITION-2', 'STU-EDITION', 'COURSE-EDITION', 'CRSV-EDITION-2',
                    'COFF-EDITION-2', 'ACTIVE', 0);
            """
        )
        rows = self.conn.execute(
            "select enrollment_id from courseplatform.enrollments where student_id = 'STU-EDITION' order by enrollment_id"
        ).fetchall()
        certificate = self.conn.execute(
            "select enrollment_id, course_version_id, final_score from courseplatform.certificates where certificate_id = 'CERT-EDITION-1'"
        ).fetchone()
        self.assertEqual([("ENR-EDITION-1",), ("ENR-EDITION-2",)], rows)
        self.assertEqual(("ENR-EDITION-1", "CRSV-EDITION-1", 88), certificate)

    def test_published_version_and_enrolled_offering_are_immutable(self):
        self._apply(migration_files())
        self.conn.execute(
            """
            insert into courseplatform.students (student_id, full_name, email)
            values ('STU-LOCK', 'Lock Student', 'lock@example.test');
            insert into courseplatform.courses (course_id, course_code, title)
            values ('COURSE-LOCK', 'LOCK', 'Locked Course');
            insert into courseplatform.course_versions
              (course_version_id, course_id, version_number, status, title,
               content_snapshot_json, published_at)
            values ('CRSV-LOCK-1', 'COURSE-LOCK', 1, 'PUBLISHED', 'Locked Course',
                    '{"lessons": []}'::jsonb, now());
            insert into courseplatform.course_offerings
              (offering_id, course_id, course_version_id, offering_code, name, status)
            values ('COFF-LOCK-1', 'COURSE-LOCK', 'CRSV-LOCK-1', 'LOCK-001',
                    'Locked Offering', 'ACTIVE');
            insert into courseplatform.enrollments
              (enrollment_id, student_id, course_id, course_version_id, offering_id)
            values ('ENR-LOCK-1', 'STU-LOCK', 'COURSE-LOCK', 'CRSV-LOCK-1', 'COFF-LOCK-1');
            """
        )
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.conn.execute(
                "update courseplatform.course_versions set title = 'Alterado' where course_version_id = %s",
                ("CRSV-LOCK-1",),
            )
        self.conn.rollback()
        self.conn.execute(
            """
            insert into courseplatform.course_versions
              (course_version_id, course_id, version_number, status, title,
               content_snapshot_json, published_at)
            values ('CRSV-LOCK-2', 'COURSE-LOCK', 2, 'PUBLISHED', 'Locked Course v2',
                    '{"lessons": []}'::jsonb, now())
            """
        )
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.conn.execute(
                """
                update courseplatform.course_offerings
                set course_version_id = 'CRSV-LOCK-2'
                where offering_id = 'COFF-LOCK-1'
                """
            )


if __name__ == "__main__":
    unittest.main()
