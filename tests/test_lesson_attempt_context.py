import unittest
from contextlib import contextmanager
from types import SimpleNamespace

from backend.courseplatform.domains import learning


class _Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _Connection:
    def execute(self, query, params):
        if "from courseplatform.lessons" in query:
            return _Result({"course_id": "COURSE-1"})
        if "from courseplatform.course_versions" in query:
            return _Result({
                "course_version_id": "VERSION-1",
                "content_snapshot_json": {
                    "lessons": [{
                        "lesson_id": "LESSON-1",
                        "status": "ACTIVE",
                        "content": [],
                        "questions": [],
                    }]
                },
            })
        if "from courseplatform.lesson_progress" in query:
            return _Result({
                "progress_id": "PROGRESS-1",
                "lesson_id": "LESSON-1",
                "status": "APPROVED",
                "content_access_status": "AVAILABLE",
                "evaluation_status": "APPROVED",
            })
        if "from courseplatform.attempts" in query:
            return _Result({
                "attempt_id": "ATTEMPT-1",
                "progress_id": "PROGRESS-1",
                "status": "APPROVED",
                "score": 85,
            })
        raise AssertionError(f"Unexpected query: {query}")


class LessonAttemptContextTests(unittest.TestCase):
    def test_lesson_read_includes_latest_attempt_for_direct_navigation(self):
        @contextmanager
        def connection():
            yield _Connection()

        runtime = SimpleNamespace(
            connection=connection,
            prepare_assessment_feature_schema=lambda: None,
            progress_access_status=lambda row: row["content_access_status"],
            public_content=lambda row: row,
            public_course_version=lambda row: row,
            public_enrollment=lambda row: row,
            public_lesson=lambda row: row,
            public_progress=lambda row: row,
            require_fields=lambda payload, fields: None,
            resolve_student_enrollment_with_conn=lambda conn, student_id, course_id, enrollment_id: {
                "enrollment_id": "ENROLLMENT-1",
                "course_id": "COURSE-1",
                "course_version_id": "VERSION-1",
            },
            str_value=lambda value: str(value or ""),
            student_attempt=lambda row: {
                "attemptId": row["attempt_id"],
                "status": row["status"],
                "score": row["score"],
            },
            student_context=lambda payload: (None, {"student_id": "STUDENT-1"}),
            student_option=lambda row: row,
            student_question=lambda row: row,
            success=lambda data: {"success": True, "data": data},
        )

        result = learning.get_lesson_action(
            {
                "sessionToken": "test-session",
                "lessonId": "LESSON-1",
                "enrollmentId": "ENROLLMENT-1",
            },
            runtime=runtime,
        )

        self.assertEqual("ATTEMPT-1", result["data"]["activeAttempt"]["attemptId"])
        self.assertEqual("APPROVED", result["data"]["activeAttempt"]["status"])


if __name__ == "__main__":
    unittest.main()
