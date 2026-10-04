import inspect
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from backend.courseplatform.contracts import ApiError
from backend.courseplatform.domains import administration, certificates, communication


class _Result:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, handler):
        self.handler = handler
        self.queries = []

    def execute(self, query, params=()):
        normalized = " ".join(query.split()).lower()
        self.queries.append((normalized, params))
        return self.handler(normalized, params)

    def commit(self):
        pass


def _connection_for(conn):
    @contextmanager
    def connection():
        yield conn

    return connection


class MultiTenantSurveyTests(unittest.TestCase):
    def test_admin_from_a_cannot_edit_survey_for_course_b(self):
        conn = _Connection(lambda _query, _params: _Result(None))
        runtime = SimpleNamespace(
            admin_context_with_conn=lambda *_args: (
                {"organization_id": "ORG-A"},
                {"admin_id": "ADMIN-A", "active_organization_id": "ORG-A"},
            ),
            audit=lambda *_args: None,
            certificate_settings_payload=lambda *_args: {},
            connection=_connection_for(conn),
            ensure_certificate_feature_schema=lambda _conn: None,
            get_settings=lambda: SimpleNamespace(default_course_id="COURSE-A"),
            normalize_certificate_profile=lambda *_args: {},
            normalize_survey_questions=lambda value: value,
            public_course=lambda row: row,
            str_value=lambda value: str(value or "").strip(),
            success=lambda data: {"success": True, "data": data},
        )

        with self.assertRaises(ApiError) as raised:
            certificates.admin_save_certificate_survey_action(
                {"courseId": "COURSE-B", "surveyQuestions": []}, runtime
            )

        self.assertEqual("COURSE_NOT_FOUND", raised.exception.code)
        self.assertIn("organization_id = %s", conn.queries[0][0])
        self.assertEqual(("COURSE-B", "ORG-A"), conn.queries[0][1])


class MultiTenantCommunicationTests(unittest.TestCase):
    def test_actor_from_a_cannot_open_room_b(self):
        conn = _Connection(lambda _query, _params: _Result(None))
        runtime = SimpleNamespace(student_can_access_chat_room=lambda *_args: True)

        with self.assertRaises(ApiError) as raised:
            communication.accessible_chat_room_action(
                conn,
                "ROOM-B",
                {"type": "STUDENT", "id": "STUDENT-A", "organization_id": "ORG-A"},
                runtime=runtime,
            )

        self.assertEqual("CHAT_ROOM_NOT_FOUND", raised.exception.code)
        self.assertEqual(("ROOM-B", "ORG-A"), conn.queries[0][1])

    def test_realtime_and_storage_rows_are_tenant_bound(self):
        migration = (
            Path(__file__).resolve().parents[1]
            / "supabase"
            / "migrations"
            / "20261004180000_isolate_communication_by_organization.sql"
        ).read_text(encoding="utf-8").lower()
        self.assertIn("add column if not exists organization_id", migration)
        self.assertIn("alter column organization_id set default 'org-lmtwebnairs'", migration)
        self.assertIn("on conflict (organization_id, room_key)", inspect.getsource(communication.sync_chat_rooms_action).lower())
        self.assertIn("jwt_claims ->> 'organization_id'", migration)
        self.assertIn("organization_id, endpoint_hash", migration)

    def test_delivery_claim_from_a_excludes_notifications_from_b(self):
        conn = _Connection(lambda _query, _params: _Result(rows=[]))
        runtime = SimpleNamespace(
            connection=_connection_for(conn),
            str_value=lambda value: str(value or "").strip(),
        )

        rows = communication.claim_notification_deliveries_action(
            "EMAIL",
            None,
            10,
            "ORG-A",
            runtime=runtime,
        )

        self.assertEqual([], rows)
        query, params = conn.queries[0]
        self.assertIn("scoped_notification.organization_id = %s", query)
        self.assertEqual("ORG-A", params[1])
        self.assertIn("n.organization_id", query)

    def test_push_delivery_requires_and_forwards_notification_tenant(self):
        calls = []
        runtime = SimpleNamespace(
            push_subscriptions_for_student=lambda *args: calls.append(args) or [],
            redact_notification_error=lambda value, *_args: str(value),
            resolved_notification_action_url=lambda *_args: "",
            str_value=lambda value: str(value or "").strip(),
            student_unread_badge_count=lambda *_args: 0,
            update_push_subscription_delivery=lambda *_args: None,
            web_push_runtime_configuration=lambda: {},
            webpush=object(),
        )
        configuration = {
            "configured": True,
            "encryptionKey": "key",
            "privateKey": "private",
            "subject": "mailto:test@example.org",
            "ttlSeconds": 60,
            "timeoutSeconds": 3,
        }

        with self.assertRaisesRegex(RuntimeError, "Nenhum dispositivo"):
            communication.send_web_push_notification_action(
                {
                    "notification_id": "NTF-A",
                    "organization_id": "ORG-A",
                    "student_id": "STUDENT-A",
                },
                configuration,
                runtime=runtime,
            )

        self.assertEqual([("STUDENT-A", "key", "ORG-A")], calls)


class MultiTenantAdministrationTests(unittest.TestCase):
    def test_platform_statistics_scopes_certificates_through_course(self):
        source = inspect.getsource(administration.admin_platform_statistics_action)

        self.assertIn(
            "join courseplatform.courses course on course.course_id = certificate.course_id",
            source,
        )
        self.assertIn("where course.organization_id = %s", source)
        self.assertNotIn(
            "from courseplatform.certificates where organization_id = %s",
            source,
        )

    def test_student_list_distinguishes_membership_status(self):
        source = inspect.getsource(administration.admin_list_students_action)

        self.assertIn("organization_membership.status as membership_status", source)
        self.assertIn("where membership_status = 'ACTIVE'", source)
        self.assertIn('"status": row.get("membership_status")', source)
        self.assertNotIn("organization_membership.status as status", source)

    def test_staff_list_distinguishes_membership_role_and_status(self):
        source = inspect.getsource(administration.admin_list_staff_action)

        self.assertIn("organization_membership.membership_role as membership_role", source)
        self.assertIn("organization_membership.status as membership_status", source)
        self.assertIn("where membership_status = 'ACTIVE'", source)
        self.assertIn('"role": row.get("membership_role")', source)
        self.assertIn('"status": row.get("membership_status")', source)

    def test_admin_from_a_cannot_load_student_b(self):
        def handler(_query, params):
            if params == ("ORG-B", "STUDENT-B"):
                return _Result({"student_id": "STUDENT-B"})
            return _Result(None)

        conn = _Connection(handler)
        with self.assertRaises(ApiError) as raised:
            administration.require_organization_student_action(conn, "ORG-A", "STUDENT-B")

        self.assertEqual("STUDENT_NOT_FOUND", raised.exception.code)
        self.assertEqual(("ORG-A", "STUDENT-B"), conn.queries[0][1])

    def test_administration_queries_include_active_tenant(self):
        source = inspect.getsource(administration)
        self.assertIn("organization_memberships", source)
        self.assertIn("cert.organization_id = %s", source)
        self.assertIn("ses.organization_id = %s", source)

    def test_inactive_tenant_student_can_be_loaded_for_reactivation(self):
        conn = _Connection(lambda _query, _params: _Result({"student_id": "STUDENT-A"}))

        row = administration.require_organization_student_action(
            conn,
            "ORG-A",
            "STUDENT-A",
            active_only=False,
        )

        self.assertEqual("STUDENT-A", row["student_id"])
        self.assertNotIn("membership.status = 'active'", conn.queries[0][0])


if __name__ == "__main__":
    unittest.main()
