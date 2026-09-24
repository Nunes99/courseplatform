import unittest
from pathlib import Path

from backend.courseplatform import actions


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260915173343_model_course_versions_and_offerings.sql"
)


class _Result:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows if rows is not None else ([] if row is None else [row])

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class _ProgressConnection:
    def __init__(self):
        self.progress = set()
        self.inserts = []

    def execute(self, query, params=()):
        normalized = " ".join(query.lower().split())
        if normalized.startswith("select content_snapshot_json from courseplatform.course_versions"):
            return _Result({
                "content_snapshot_json": {
                    "lessons": [
                        {
                            "lesson_id": "L2",
                            "lesson_number": 2,
                            "status": "ACTIVE",
                            "prerequisite_lesson_id": "L1",
                        },
                        {
                            "lesson_id": "L1",
                            "lesson_number": 1,
                            "status": "ACTIVE",
                            "prerequisite_lesson_id": None,
                        },
                        {"lesson_id": "L3", "lesson_number": 3, "status": "DELETED"},
                    ]
                }
            })
        if normalized.startswith("insert into courseplatform.lesson_progress"):
            enrollment_id, lesson_id = params[1], params[3]
            key = (enrollment_id, lesson_id)
            if key in self.progress:
                return _Result()
            self.progress.add(key)
            self.inserts.append({"lessonId": lesson_id, "accessStatus": params[4]})
            return _Result({"progress_id": params[0]})
        raise AssertionError(normalized)


class CourseVersionsAndOfferingsTests(unittest.TestCase):
    def test_new_enrollment_initializes_only_active_snapshot_lessons(self):
        conn = _ProgressConnection()
        enrollment = {
            "enrollment_id": "E1",
            "student_id": "S1",
            "course_version_id": "CV1",
        }

        self.assertEqual(2, actions.initialize_enrollment_progress_with_conn(conn, enrollment))
        self.assertEqual(0, actions.initialize_enrollment_progress_with_conn(conn, enrollment))
        self.assertEqual(
            [
                {"lessonId": "L1", "accessStatus": "AVAILABLE"},
                {"lessonId": "L2", "accessStatus": "LOCKED"},
            ],
            conn.inserts,
        )

    def test_ambiguous_course_requires_explicit_enrollment(self):
        class Connection:
            def execute(self, query, params=()):
                return _Result(rows=[{"enrollment_id": "E2"}, {"enrollment_id": "E1"}])

        with self.assertRaises(actions.ApiError) as raised:
            actions.resolve_student_enrollment_with_conn(Connection(), "S1", "C1")
        self.assertEqual("ENROLLMENT_REQUIRED", raised.exception.code)

    def test_public_version_does_not_expose_assessment_snapshot(self):
        payload = actions.public_course_version({
            "course_version_id": "CV1",
            "course_id": "C1",
            "version_number": 1,
            "status": "PUBLISHED",
            "title": "Curso",
            "content_snapshot_json": {"questions": [{"correct_answer": "SECRET"}]},
        })
        self.assertNotIn("contentSnapshot", payload)
        self.assertNotIn("content_snapshot_json", payload)

    def test_course_actions_are_registered(self):
        for action in (
            "adminCreateCourseVersion",
            "adminPublishCourseVersion",
            "adminSaveCourseOffering",
            "adminEnrollStudentsInOffering",
            "adminListCourseReconciliationIssues",
        ):
            self.assertIn(action, actions.ACTIONS)

    def test_migration_preserves_unlimited_legacy_capacity_and_certificate_context(self):
        sql = MIGRATION.read_text(encoding="utf-8").lower()
        self.assertIn("null::integer", sql)
        self.assertIn("certificates_enrollment_context_fk", sql)
        self.assertIn("certificate_requests_enrollment_context_fk", sql)
        self.assertIn("unique (student_id, offering_id)", sql)


if __name__ == "__main__":
    unittest.main()
