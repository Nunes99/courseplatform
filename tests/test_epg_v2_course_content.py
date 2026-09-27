import json
import re
import unittest
from pathlib import Path

from backend.courseplatform.domains.catalog import validate_course_version_snapshot


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260928133000_seed_epg_v2_draft_content.sql"
)


def load_snapshot() -> tuple[str, dict]:
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    match = re.search(
        r"\$course_snapshot\$\s*(\{.*?\})\s*\$course_snapshot\$::jsonb",
        sql,
        flags=re.DOTALL,
    )
    if not match:
        raise AssertionError("Academic snapshot not found in the migration")
    return sql, json.loads(match.group(1))


class EpgV2CourseContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql, cls.snapshot = load_snapshot()
        cls.lessons = cls.snapshot["lessons"]
        cls.contents = [item for lesson in cls.lessons for item in lesson["content"]]
        cls.questions = [item for lesson in cls.lessons for item in lesson["questions"]]

    def test_snapshot_is_publishable_after_academic_review(self):
        validation = validate_course_version_snapshot(self.snapshot)

        self.assertTrue(validation["valid"], validation["issues"])
        self.assertEqual(
            validation["summary"],
            {
                "lessonCount": 2,
                "contentCount": 8,
                "questionCount": 10,
                "errorCount": 0,
                "warningCount": 0,
            },
        )

    def test_workload_and_assessment_policy_are_consistent(self):
        self.assertEqual(self.snapshot["course"]["total_hours"], 12)
        self.assertEqual(sum(item["estimated_minutes"] for item in self.contents), 720)

        for lesson in self.lessons:
            self.assertEqual(sum(item["estimated_minutes"] for item in lesson["content"]), 360)
            self.assertEqual(lesson["assessment_attempt_limit"], 2)
            self.assertEqual(lesson["submission_duration_minutes"], 60)
            self.assertEqual(lesson["assessment_question_limit"], 5)
            self.assertEqual(lesson["passing_score"], 60)
            self.assertEqual(lesson["assessment_randomization_mode"], "QUESTIONS_AND_OPTIONS")
            self.assertEqual(lesson["feedback_release_mode"], "AFTER_REVIEW")
            self.assertIsNone(lesson["assessment_available_from"])
            self.assertIsNone(lesson["assessment_available_until"])
            self.assertEqual(sum(question["points"] for question in lesson["questions"]), 100)

    def test_questions_have_stable_ids_and_valid_answer_models(self):
        self.assertEqual(len({item["question_id"] for item in self.questions}), 10)
        self.assertEqual(len({item["bank_question_id"] for item in self.questions}), 10)
        self.assertEqual(len({item["bank_question_version_id"] for item in self.questions}), 10)

        for question in self.questions:
            self.assertTrue(question["explanation"].strip())
            self.assertTrue(question["tags"])
            self.assertGreater(question["points"], 0)
            if question["question_type"] == "LONG_TEXT":
                self.assertEqual(question["options"], [])
                self.assertTrue(question["correct_answer"].startswith("Rubrica:"))
            elif question["question_type"] == "MULTIPLE_CHOICE":
                self.assertGreaterEqual(
                    sum(option["is_correct"] for option in question["options"]), 2
                )
            else:
                self.assertEqual(
                    sum(option["is_correct"] for option in question["options"]), 1
                )

    def test_primary_sources_are_attached_to_every_content_section(self):
        allowed_hosts = {"www.inp.gov.mz", "inp.gov.mz", "mireme.gov.mz"}
        for content in self.contents:
            self.assertTrue(content["sources"], content["content_id"])
            for source in content["sources"]:
                host = source["url"].split("/", 3)[2]
                self.assertIn(host, allowed_hosts)

    def test_migration_preserves_published_history_and_student_records(self):
        normalized = " ".join(self.sql.lower().split())
        self.assertIn("'crsv-epg-001-v2', 'course-epg-001', 2, 'draft'", normalized)
        self.assertIn("course-epg-001 is absent; skipping its optional academic seed", normalized)
        self.assertRegex(
            normalized,
            r"if not exists \( select 1 from courseplatform\.courses .*? then raise notice .*? return;",
        )
        self.assertNotRegex(normalized, r"update courseplatform\.course_versions\s+set")
        self.assertNotRegex(normalized, r"delete from courseplatform\.course_versions")
        for table in (
            "course_offerings",
            "enrollments",
            "student_progress",
            "attempts",
            "certificates",
        ):
            self.assertNotRegex(normalized, rf"(?:insert into|update|delete from) courseplatform\.{table}")

    def test_question_options_are_created_before_versions_become_immutable(self):
        insert_version = self.sql.index("insert into courseplatform.question_bank_versions")
        insert_options = self.sql.index("insert into courseplatform.question_bank_options")
        publish_version = self.sql.index("update courseplatform.question_bank_versions")
        self.assertLess(insert_version, insert_options)
        self.assertLess(insert_options, publish_version)
        self.assertIn("and status = 'DRAFT'", self.sql)
        self.assertIn("already has a different draft", self.sql)
        self.assertIn("differs from the reviewed academic snapshot", self.sql)


if __name__ == "__main__":
    unittest.main()
