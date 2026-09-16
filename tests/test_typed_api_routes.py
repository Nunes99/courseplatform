import unittest
from unittest.mock import call, patch

from fastapi.testclient import TestClient

from backend.courseplatform.api import executor
from backend.courseplatform import app as application
from backend.courseplatform.app import app
from backend.courseplatform.contracts import ApiError


class TypedApiRouteTests(unittest.TestCase):
    client = TestClient(app)

    def test_openapi_exposes_versioned_routes_without_removing_legacy_api(self):
        schema = self.client.get("/openapi.json").json()
        paths = schema["paths"]
        self.assertIn("/api/v1/auth/students/sessions", paths)
        self.assertIn("/api/v1/auth/administrators/sessions", paths)
        self.assertIn("/api/v1/students/me/courses", paths)
        self.assertIn("/api/v1/admin/students", paths)
        self.assertIn("/api/v1/admin/staff", paths)
        self.assertIn("/api", paths)

    def test_student_login_uses_typed_contract_and_legacy_action(self):
        result = {
            "success": True,
            "data": {
                "sessionToken": "session-token",
                "expiresAt": "2026-09-17T10:00:00+00:00",
                "student": {"studentId": "S1", "fullName": "Estudante"},
            },
        }
        with patch.object(executor.actions, "dispatch", return_value=result) as dispatch:
            response = self.client.post(
                "/api/v1/auth/students/sessions",
                headers={"user-agent": "courseplatform-test"},
                json={"email": "student@example.test", "accessCode": "secret-code"},
            )
        self.assertEqual(200, response.status_code)
        self.assertEqual(result, response.json())
        dispatch.assert_called_once_with(
            "login",
            {
                "email": "student@example.test",
                "accessCode": "secret-code",
                "userAgent": "courseplatform-test",
            },
        )

    def test_typed_login_rejects_unknown_or_missing_fields_before_dispatch(self):
        with patch.object(executor.actions, "dispatch") as dispatch:
            response = self.client.post(
                "/api/v1/auth/students/sessions",
                json={"email": "student@example.test", "unexpected": "value"},
            )
        self.assertEqual(422, response.status_code)
        dispatch.assert_not_called()

    def test_admin_login_and_logout_use_admin_contract(self):
        login_result = {
            "success": True,
            "data": {
                "adminToken": "admin-token",
                "expiresAt": "2026-09-17T10:00:00+00:00",
                "admin": {"adminId": "A1", "role": "OWNER"},
            },
        }
        logout_result = {"success": True, "data": {"loggedOut": True}}
        with patch.object(
            executor.actions,
            "dispatch",
            side_effect=[login_result, logout_result],
        ) as dispatch:
            login_response = self.client.post(
                "/api/v1/auth/administrators/sessions",
                headers={"user-agent": "admin-test"},
                json={"email": "admin@example.test", "adminKey": "admin-secret"},
            )
            logout_response = self.client.delete(
                "/api/v1/auth/administrators/sessions/current",
                headers={"x-admin-token": "admin-token"},
            )
        self.assertEqual(200, login_response.status_code)
        self.assertEqual(200, logout_response.status_code)
        self.assertEqual(
            [
                call(
                    "adminLogin",
                    {
                        "email": "admin@example.test",
                        "adminKey": "admin-secret",
                        "userAgent": "admin-test",
                    },
                ),
                call("adminLogout", {"adminToken": "admin-token"}),
            ],
            dispatch.call_args_list,
        )

    def test_student_courses_reads_session_from_header(self):
        result = {
            "success": True,
            "data": {
                "student": {"studentId": "S1"},
                "courses": [],
                "notificationChannelInfo": {},
            },
        }
        with patch.object(executor.actions, "dispatch", return_value=result) as dispatch:
            response = self.client.get(
                "/api/v1/students/me/courses",
                headers={"x-session-token": "student-session"},
            )
        self.assertEqual(200, response.status_code)
        self.assertEqual(result, response.json())
        dispatch.assert_called_once_with("getMyCourses", {"sessionToken": "student-session"})

    def test_admin_students_maps_typed_filters_to_existing_action(self):
        result = {
            "success": True,
            "data": {
                "students": [],
                "total": 0,
                "limit": 25,
                "pagination": {
                    "limit": 25,
                    "returned": 0,
                    "hasMore": False,
                    "nextCursor": "",
                    "total": 0,
                },
                "summary": {},
            },
        }
        with patch.object(executor.actions, "dispatch", return_value=result) as dispatch:
            response = self.client.get(
                "/api/v1/admin/students",
                headers={"x-admin-token": "admin-session"},
                params={
                    "query": "ana",
                    "status": "ACTIVE",
                    "progress": "IN_PROGRESS",
                    "sort": "progressDesc",
                    "limit": 25,
                    "cursor": "next-page",
                },
            )
        self.assertEqual(200, response.status_code)
        self.assertEqual(result, response.json())
        dispatch.assert_called_once_with(
            "adminListStudents",
            {
                "adminToken": "admin-session",
                "query": "ana",
                "status": "ACTIVE",
                "progress": "IN_PROGRESS",
                "sort": "progressDesc",
                "limit": 25,
                "cursor": "next-page",
            },
        )

    def test_admin_staff_maps_typed_filters_to_existing_action(self):
        result = {
            "success": True,
            "data": {
                "staff": [],
                "currentAdmin": {"adminId": "A1"},
                "pagination": {
                    "limit": 10,
                    "returned": 0,
                    "hasMore": False,
                    "nextCursor": "",
                    "total": 0,
                },
                "summary": {},
            },
        }
        with patch.object(executor.actions, "dispatch", return_value=result) as dispatch:
            response = self.client.get(
                "/api/v1/admin/staff",
                headers={"x-admin-token": "admin-session"},
                params={"query": "rev", "status": "ACTIVE", "role": "REVIEWER", "limit": 10},
            )
        self.assertEqual(200, response.status_code)
        self.assertEqual(result, response.json())
        dispatch.assert_called_once_with(
            "adminListStaff",
            {
                "adminToken": "admin-session",
                "query": "rev",
                "status": "ACTIVE",
                "role": "REVIEWER",
                "limit": 10,
                "cursor": "",
            },
        )

    def test_legacy_action_endpoint_remains_available(self):
        result = {"success": True, "data": {"status": "legacy-ok"}}
        with patch.object(application, "dispatch", return_value=result) as dispatch:
            response = self.client.post("/api", json={"action": "legacyProbe", "value": 7})
        self.assertEqual(200, response.status_code)
        self.assertEqual(result, response.json())
        dispatch.assert_called_once_with("legacyProbe", {"action": "legacyProbe", "value": 7})

    def test_domain_error_is_returned_with_semantic_http_status(self):
        with patch.object(
            executor.actions,
            "dispatch",
            side_effect=ApiError("INVALID_SESSION", "Sessão inválida."),
        ):
            response = self.client.get(
                "/api/v1/students/me/courses",
                headers={"x-session-token": "invalid-session"},
            )
        self.assertEqual(401, response.status_code)
        self.assertEqual(
            {
                "success": False,
                "error": {
                    "code": "INVALID_SESSION",
                    "message": "Sessão inválida.",
                    "details": None,
                },
            },
            response.json(),
        )


if __name__ == "__main__":
    unittest.main()
