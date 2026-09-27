from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260928120000_repair_epg_course_metadata.sql"
)


class EpgCourseMetadataRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8").lower()

    def test_preserves_historical_identifiers_and_records_backup(self):
        self.assertIn("course-epg-001", self.sql)
        self.assertIn("lesson-eapi-004", self.sql)
        self.assertIn("lesson-eapi-005", self.sql)
        self.assertIn("migration_reconciliation_issues", self.sql)
        self.assertIn("content_snapshot_json", self.sql)
        self.assertNotIn("update courseplatform.enrollments", self.sql)
        self.assertNotIn("update courseplatform.lesson_progress", self.sql)
        self.assertNotIn("delete from", self.sql)

    def test_is_guarded_and_keeps_the_published_version_number(self):
        self.assertIn("and version_number = 1", self.sql)
        self.assertIn("and status = 'published'", self.sql)
        self.assertIn("coalesce(lesson_number, 0) = 0", self.sql)
        self.assertIn("coalesce(btrim(title), '') = ''", self.sql)
        self.assertIn("disable trigger protect_published_course_version", self.sql)
        self.assertIn("enable trigger protect_published_course_version", self.sql)
        self.assertNotIn("insert into courseplatform.course_versions", self.sql)


if __name__ == "__main__":
    unittest.main()

