import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.courseplatform.contracts import ApiError
from backend.courseplatform.domains import enrollments


ROOT = Path(__file__).resolve().parents[1]


class _Result:
    def __init__(self, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _EnrollmentConnection:
    def __init__(self):
        self.query = ""
        self.params = ()

    def execute(self, query, params):
        self.query = query
        self.params = params
        return _Result(None)


class StudentSessionIsolationTests(unittest.TestCase):
    def test_explicit_enrollment_is_scoped_to_authenticated_student(self):
        connection = _EnrollmentConnection()

        with self.assertRaises(ApiError) as raised:
            enrollments.resolve_student_enrollment_with_conn_action(
                connection,
                "STUDENT-A",
                "COURSE-1",
                "ENROLLMENT-B",
                "ORG-A",
                runtime=SimpleNamespace(),
            )

        self.assertEqual("ENROLLMENT_NOT_FOUND", raised.exception.code)
        self.assertIn("student_id = %s", connection.query)
        self.assertIn("c.organization_id = %s", connection.query)
        self.assertEqual(
            (
                "ENROLLMENT-B",
                "STUDENT-A",
                "COURSE-1",
                "COURSE-1",
                "ORG-A",
                "ORG-A",
            ),
            connection.params,
        )

    def test_course_list_is_scoped_to_active_organization(self):
        connection = _EnrollmentConnection()

        rows = enrollments.student_courses_rows_action(
            connection,
            "STUDENT-A",
            "ORG-A",
            runtime=SimpleNamespace(),
        )

        self.assertEqual([], rows)
        self.assertIn("c.organization_id = %s", connection.query)
        self.assertIn("cv.course_id = e.course_id", connection.query)
        self.assertIn("o.course_id = e.course_id", connection.query)
        self.assertEqual(("STUDENT-A", "ORG-A"), connection.params)

    def test_frontend_discards_account_scoped_state_on_session_change(self):
        source = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
        api_source = (ROOT / "public" / "api.js").read_text(encoding="utf-8")

        self.assertIn("resetStudentAccountState({ clearSelection: true });", source)
        self.assertIn("event.key === 'courseSessionToken'", source)
        self.assertIn("window.location.reload();", source)
        self.assertIn("await api.currentStudentSession();", source)
        self.assertIn("courseSessionExpiresAt", api_source)
        self.assertIn("this.clearStudentSession();", api_source)
        self.assertLess(
            source.index("let activeAttempt = lessonData.activeAttempt"),
            source.index("state.dashboard?.lessons?.find", source.index("async function openLesson")),
        )


if __name__ == "__main__":
    unittest.main()
