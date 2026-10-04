import unittest
from contextlib import contextmanager
from types import SimpleNamespace

from backend.courseplatform import actions
from backend.courseplatform.contracts import ApiError
from backend.courseplatform.domains import assessments, learning
from backend.courseplatform.reviewer_scopes import require_attempt_scope


class _Result:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class _RecordingConnection:
    def __init__(self, *, row=None, rows=None):
        self.row = row
        self.rows = rows or []
        self.calls = []
        self.committed = False

    def execute(self, query, params=()):
        self.calls.append((" ".join(query.split()).lower(), params))
        return _Result(self.row, self.rows)

    def commit(self):
        self.committed = True


def _connection_for(conn):
    @contextmanager
    def connection():
        yield conn

    return connection


class StudentAssessmentTenantMutationTests(unittest.TestCase):
    def test_editable_attempt_rejects_attempt_from_another_organization(self):
        conn = _RecordingConnection()

        with self.assertRaises(ApiError) as raised:
            actions.editable_attempt(conn, "ATT-B", "STUDENT-1", "ORG-A")

        self.assertEqual("ATTEMPT_NOT_EDITABLE", raised.exception.code)
        self.assertTrue(all("c.organization_id" in query for query, _ in conn.calls))
        self.assertTrue(all(params[-2:] == ("ORG-A", "ORG-A") for _, params in conn.calls))
        self.assertFalse(conn.committed)

    def test_save_answer_passes_session_tenant_before_any_write(self):
        conn = _RecordingConnection()
        captured = {}

        def deny_foreign_attempt(_conn, attempt_id, student_id, organization_id):
            captured.update(
                attempt_id=attempt_id,
                student_id=student_id,
                organization_id=organization_id,
            )
            raise ApiError("ATTEMPT_NOT_EDITABLE", "Tentativa fora da organização.")

        runtime = SimpleNamespace(
            connection=_connection_for(conn),
            editable_attempt=deny_foreign_attempt,
            generate_id=lambda _prefix: "ANS-1",
            prepare_assessment_feature_schema=lambda: None,
            require_fields=lambda *_args: None,
            selected_option_ids=lambda value: [],
            selected_option_storage=lambda value, question_type: "",
            snapshot_for_attempt_with_conn=lambda *_args: {},
            str_value=lambda value: str(value or ""),
            student_answer=lambda row: row,
            student_context_with_conn=lambda _conn, _payload: (
                {"organization_id": "ORG-A"},
                {"student_id": "STUDENT-1"},
            ),
            success=lambda data: {"success": True, "data": data},
        )

        with self.assertRaises(ApiError):
            assessments.save_answer_action(
                {"attemptId": "ATT-B", "questionId": "QUESTION-1"},
                runtime,
            )

        self.assertEqual("ORG-A", captured["organization_id"])
        self.assertEqual([], conn.calls)


class AdministrativeAssessmentTenantMutationTests(unittest.TestCase):
    def test_admin_cannot_manage_attempt_from_another_organization(self):
        conn = _RecordingConnection()
        admin = {
            "admin_id": "ADMIN-A",
            "role": "ADMIN",
            "active_organization_id": "ORG-A",
        }

        with self.assertRaises(ApiError) as raised:
            require_attempt_scope(conn, admin, "ATT-B")

        self.assertEqual("ATTEMPT_NOT_FOUND", raised.exception.code)
        query, params = conn.calls[0]
        self.assertIn("c.organization_id = %s", query)
        self.assertEqual(("ATT-B", "ORG-A"), params)

    def test_batch_rejects_student_without_active_membership(self):
        conn = _RecordingConnection(rows=[{"student_id": "STUDENT-A"}])

        with self.assertRaises(ApiError) as raised:
            learning._require_active_student_memberships(
                conn,
                {"STUDENT-A", "STUDENT-B"},
                "ORG-A",
            )

        self.assertEqual("STUDENT_ORGANIZATION_MISMATCH", raised.exception.code)
        query, params = conn.calls[0]
        self.assertIn("organization_id = %s", query)
        self.assertEqual("ORG-A", params[0])
        self.assertFalse(conn.committed)


if __name__ == "__main__":
    unittest.main()
