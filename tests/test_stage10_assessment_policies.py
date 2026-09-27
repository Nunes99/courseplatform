import copy
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.courseplatform import actions
from backend.courseplatform.domains import catalog


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "20260926120000_add_versioned_assessment_policies.sql"


def version_lesson():
    return {
        "lesson_id": "LESSON-1",
        "title": "Avaliação",
        "assessment_attempt_limit": 2,
        "assessment_available_from": "2026-09-26T08:00:00+00:00",
        "assessment_available_until": "2026-09-30T18:00:00+00:00",
        "submission_duration_minutes": 90,
        "assessment_randomization_mode": "QUESTION_ORDER",
        "assessment_question_limit": 1,
        "passing_score": 0,
        "feedback_release_mode": "AFTER_REVIEW",
        "show_correct_answers": True,
        "show_explanations": False,
        "questions": [
            {"question_id": "Q1", "question_order": 1, "status": "ACTIVE", "options": []},
            {"question_id": "Q2", "question_order": 2, "status": "ACTIVE", "options": []},
        ],
    }


class ReverseRandom:
    @staticmethod
    def shuffle(values):
        values.reverse()


class ExceptionConnection:
    def __init__(self, row):
        self.row = row
        self.params = None

    def execute(self, _query, params):
        self.params = params
        return self

    def fetchone(self):
        return self.row


class AssessmentPolicyTests(unittest.TestCase):
    def test_policy_normalization_preserves_zero_passing_score(self):
        policy = actions.assessment_policy(version_lesson())

        self.assertEqual(2, policy["attemptLimit"])
        self.assertEqual(90, policy["timeLimitMinutes"])
        self.assertEqual(0, policy["passingScore"])
        self.assertEqual("QUESTION_ORDER", policy["randomizationMode"])
        self.assertEqual(1, policy["questionLimit"])

    def test_randomization_limits_a_copy_without_mutating_published_snapshot(self):
        source = version_lesson()["questions"]
        original = copy.deepcopy(source)

        selected = actions.randomized_assessment_questions(
            source,
            {"randomizationMode": "QUESTION_ORDER", "questionLimit": 1},
            rng=ReverseRandom(),
        )

        self.assertEqual(["Q2"], [item["question_id"] for item in selected])
        self.assertEqual(1, selected[0]["question_order"])
        self.assertEqual(original, source)

    def test_attempt_snapshot_freezes_policy_and_questions(self):
        lesson = version_lesson()
        policy = actions.assessment_policy(lesson)
        policy["randomizationMode"] = "NONE"
        policy["questionLimit"] = None

        snapshot = actions.assessment_snapshot_from_version_lesson(lesson, policy)
        lesson["assessment_attempt_limit"] = 9
        lesson["questions"][0]["question_id"] = "CHANGED"

        self.assertEqual(2, snapshot["assessmentPolicy"]["attemptLimit"])
        self.assertEqual("Q1", snapshot["questions"][0]["question_id"])
        self.assertEqual(2, snapshot["version"])
        self.assertTrue(snapshot["digest"])

    def test_active_individual_exception_overrides_only_configured_fields(self):
        now = datetime(2026, 9, 26, 12, tzinfo=timezone.utc)
        exception = {
            "assessment_exception_id": "AEX-1",
            "attempt_limit": 4,
            "available_from": now - timedelta(hours=1),
            "available_until": now + timedelta(days=2),
            "time_limit_minutes": 150,
        }
        connection = ExceptionConnection(exception)

        policy, selected = actions.effective_assessment_policy_with_conn(
            connection,
            {"enrollment_id": "ENR-1", "lesson_id": "LESSON-1"},
            version_lesson(),
            now,
        )

        self.assertIs(exception, selected)
        self.assertEqual(4, policy["attemptLimit"])
        self.assertEqual(150, policy["timeLimitMinutes"])
        self.assertEqual("AEX-1", policy["exception"]["assessmentExceptionId"])
        self.assertEqual(("ENR-1", "LESSON-1", now), connection.params)

    def test_draft_editor_updates_complete_assessment_policy(self):
        snapshot = {"course": {}, "lessons": [{**version_lesson(), "content": []}]}
        updated = catalog.edit_course_version_draft_snapshot(snapshot, "UPDATE_LESSON", {
            "lessonId": "LESSON-1",
            "title": "Avaliação final",
            "summary": "Síntese",
            "attemptLimit": 3,
            "timeLimitMinutes": 120,
            "questionLimit": 1,
            "passingScore": 70,
            "availableFrom": "2026-10-01T08:00:00+00:00",
            "availableUntil": "2026-10-02T18:00:00+00:00",
            "randomizationMode": "QUESTIONS_AND_OPTIONS",
            "feedbackReleaseMode": "AFTER_SUBMISSION",
            "showCorrectAnswers": True,
            "showExplanations": True,
        })
        lesson = updated["lessons"][0]

        self.assertEqual(3, lesson["assessment_attempt_limit"])
        self.assertEqual(120, lesson["submission_duration_minutes"])
        self.assertEqual("QUESTIONS_AND_OPTIONS", lesson["assessment_randomization_mode"])
        self.assertEqual("AFTER_SUBMISSION", lesson["feedback_release_mode"])
        self.assertTrue(lesson["show_correct_answers"])

    def test_draft_editor_rejects_inverted_window(self):
        snapshot = {"course": {}, "lessons": [{**version_lesson(), "content": []}]}
        with self.assertRaises(catalog.ApiError) as raised:
            catalog.edit_course_version_draft_snapshot(snapshot, "UPDATE_LESSON", {
                "lessonId": "LESSON-1",
                "title": "Avaliação",
                "attemptLimit": 1,
                "timeLimitMinutes": 30,
                "passingScore": 60,
                "availableFrom": "2026-10-03T10:00:00+00:00",
                "availableUntil": "2026-10-03T09:00:00+00:00",
            })

        self.assertEqual("ASSESSMENT_WINDOW_INVALID", raised.exception.code)

    def test_publication_validation_reports_malformed_window_without_crashing(self):
        lesson = {
            **version_lesson(),
            "lesson_number": 1,
            "assessment_available_from": "not-a-date",
            "content": [{"content_id": "CONTENT-1", "status": "ACTIVE"}],
            "questions": [],
        }
        validation = catalog.validate_course_version_snapshot({
            "course": {
                "course_code": "COURSE-1",
                "course_name": "Curso de teste",
                "workload_hours": 10,
                "passing_score": 60,
            },
            "lessons": [lesson],
        })

        self.assertFalse(validation["valid"])
        self.assertIn(
            "ASSESSMENT_WINDOW_INVALID",
            {issue["code"] for issue in validation["issues"]},
        )

    def test_migration_is_private_expansive_and_versioned(self):
        sql = MIGRATION.read_text(encoding="utf-8").lower()

        self.assertIn("add column if not exists assessment_attempt_limit", sql)
        self.assertIn("create table if not exists courseplatform.assessment_policy_exceptions", sql)
        self.assertIn("enable row level security", sql)
        self.assertIn("revoke all privileges", sql)
        self.assertIn("20260926120000", sql)
        self.assertNotIn("drop table", sql)
        self.assertNotIn("truncate ", sql)


if __name__ == "__main__":
    unittest.main()
