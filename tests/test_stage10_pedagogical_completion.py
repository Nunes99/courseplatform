import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from backend.courseplatform import actions
from backend.courseplatform.domains import assessments, catalog, enrollments, learning


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "20260928190000_complete_stage10_pedagogical_core.sql"


class Result:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows if rows is not None else ([] if row is None else [row])

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class CompletionDatabase:
    def __init__(self, scores):
        self.scores = scores
        self.updated = None

    def execute(self, query, params=()):
        normalized = " ".join(query.lower().split())
        if normalized.startswith("select enrollment_id from courseplatform.lesson_progress"):
            return Result({"enrollment_id": "ENR-1"})
        if normalized.startswith("select e.*, v.content_snapshot_json"):
            return Result({
                "enrollment_id": "ENR-1",
                "course_version_id": "CRSV-2",
                "version_number": 2,
                "version_passing_score": 60,
                "content_snapshot_json": {
                    "completionPolicy": {"minimumScore": 70, "requireAllLessons": True},
                    "lessons": [
                        {"lesson_id": "L1", "status": "ACTIVE", "completion_required": True},
                        {"lesson_id": "L2", "status": "ACTIVE", "completion_required": True},
                        {"lesson_id": "L3", "status": "ACTIVE", "completion_required": False},
                    ],
                },
            })
        if normalized.startswith("select lesson_id, evaluation_status"):
            return Result(rows=[
                {"lesson_id": lesson_id, "evaluation_status": "APPROVED", "status": "APPROVED", "score": score}
                for lesson_id, score in zip(("L1", "L2"), self.scores)
            ])
        if normalized.startswith("update courseplatform.enrollments"):
            self.updated = params
            return Result({
                "enrollment_id": "ENR-1",
                "progress_percent": params[0],
                "final_score": params[1],
                "status": "COMPLETED" if params[2] else "ACTIVE",
                "completion_snapshot_json": json.loads(params[4]),
                "completion_reason": params[5],
            })
        raise AssertionError(normalized)


class Stage10PedagogicalCompletionTests(unittest.TestCase):
    def test_rubric_score_is_normalized_and_complete(self):
        rubric = assessments.normalize_rubric_definition({"criteria": [
            {"criterionId": "analysis", "title": "Análise", "maxPoints": 40},
            {"criterionId": "evidence", "title": "Evidências", "maxPoints": 60},
        ]})
        scores, final_score = assessments.score_rubric(rubric, [
            {"criterionId": "analysis", "awardedPoints": 32, "comments": "Boa estrutura"},
            {"criterionId": "evidence", "awardedPoints": 45},
        ])
        self.assertEqual(77.0, final_score)
        self.assertEqual(["analysis", "evidence"], [item["criterionId"] for item in scores])

    def test_rubric_rejects_missing_or_excessive_score(self):
        rubric = assessments.normalize_rubric_definition({"criteria": [
            {"criterionId": "quality", "title": "Qualidade", "maxPoints": 10},
        ]})
        for value, code in (([], "RUBRIC_SCORES_REQUIRED"), ([{"criterionId": "quality", "awardedPoints": 11}], "RUBRIC_SCORE_INVALID")):
            with self.subTest(value=value), self.assertRaises(actions.ApiError) as raised:
                assessments.score_rubric(rubric, value)
            self.assertEqual(code, raised.exception.code)

    def test_rubric_rejects_unknown_or_duplicate_criteria(self):
        rubric = assessments.normalize_rubric_definition({"criteria": [
            {"criterionId": "quality", "title": "Qualidade", "maxPoints": 10},
        ]})
        invalid_values = (
            [{"criterionId": "other", "awardedPoints": 5}],
            [
                {"criterionId": "quality", "awardedPoints": 5},
                {"criterionId": "quality", "awardedPoints": 6},
            ],
        )
        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(actions.ApiError) as raised:
                assessments.score_rubric(rubric, value)
            self.assertEqual("RUBRIC_SCORE_INVALID", raised.exception.code)

    def test_legacy_assessment_snapshot_selects_rubric(self):
        source = actions.assessment_snapshot_with_conn.__code__
        self.assertIn("rubric_json", " ".join(str(value) for value in source.co_consts))

    def test_draft_freezes_completion_policy_and_rubric(self):
        source = {
            "course": {"course_code": "C-1", "title": "Curso", "description": "", "total_hours": 4, "passing_score": 60},
            "lessons": [{
                "lesson_id": "L1", "lesson_number": 1, "title": "Módulo", "summary": "",
                "status": "ACTIVE", "content": [], "questions": [],
            }],
        }
        course_edited = catalog.edit_course_version_draft_snapshot(source, "UPDATE_COURSE", {
            "courseCode": "C-1", "title": "Curso", "description": "", "totalHours": 4,
            "passingScore": 60, "completionMinimumScore": 75, "completionRequireAllLessons": True,
        })
        edited = catalog.edit_course_version_draft_snapshot(course_edited, "UPDATE_LESSON", {
            "lessonId": "L1", "title": "Módulo", "summary": "", "attemptLimit": 1,
            "timeLimitMinutes": 60, "passingScore": 60, "completionRequired": True,
            "rubric": {"criteria": [{"criterionId": "c1", "title": "Domínio", "maxPoints": 100}]},
        })
        self.assertEqual(75, edited["completionPolicy"]["minimumScore"])
        self.assertEqual("Domínio", edited["lessons"][0]["rubric_json"]["criteria"][0]["title"])

    def test_completion_uses_enrolled_version_snapshot(self):
        database = CompletionDatabase((80, 60))
        result = learning.refresh_enrollment_progress_action(database, "P1", runtime=SimpleNamespace())
        self.assertEqual("COMPLETED", result["status"])
        self.assertEqual(70, result["final_score"])
        self.assertEqual(["L1", "L2"], result["completion_snapshot_json"]["requiredLessonIds"])

        database = CompletionDatabase((60, 60))
        result = learning.refresh_enrollment_progress_action(database, "P1", runtime=SimpleNamespace())
        self.assertEqual("ACTIVE", result["status"])
        self.assertEqual("MINIMUM_SCORE_NOT_REACHED", result["completion_reason"])

    def test_calendar_is_normalized_and_ordered(self):
        values = enrollments.normalize_academic_calendar([
            {"eventId": "E2", "title": "Avaliação", "eventType": "ASSESSMENT", "startAt": "2026-10-12T10:00:00+00:00"},
            {"eventId": "E1", "title": "Abertura", "eventType": "SESSION", "startAt": "2026-10-10T08:00:00+00:00"},
        ], parse_datetime=actions.parse_datetime, iso=actions.iso, generate_id=lambda prefix: f"{prefix}-1")
        self.assertEqual(["E1", "E2"], [item["eventId"] for item in values])

    def test_migration_is_additive_private_and_versioned(self):
        sql = MIGRATION.read_text(encoding="utf-8").lower()
        self.assertIn("create table if not exists courseplatform.grade_change_log", sql)
        self.assertIn("rubric_snapshot_json", sql)
        self.assertIn("completion_snapshot_json", sql)
        self.assertIn("enable row level security", sql)
        self.assertIn("revoke all privileges", sql)
        self.assertIn("20260928190000", sql)
        self.assertNotIn("drop table", sql)
        self.assertNotIn("truncate ", sql)

    def test_frontend_exposes_separate_gradebook_calendar_and_rubric(self):
        source = (ROOT / "public" / "admin.js").read_text(encoding="utf-8")
        for contract in ("data-admin-view=\"gradebook\"", "data-admin-view=\"calendar\"", "data-rubric-score", "gradeHistory"):
            self.assertIn(contract, source)
        self.assertIn("formatGradebookScore(item.finalScore)", source)
        self.assertIn("maximumFractionDigits: 2", source)
        student_source = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
        self.assertIn("student-calendar-panel", student_source)
        self.assertIn("dashboard.offering.calendar", student_source)


if __name__ == "__main__":
    unittest.main()
