import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from backend.courseplatform import actions


ROOT = Path(__file__).resolve().parents[1]


class CursorTypeTests(unittest.TestCase):
    def test_text_and_number_cursors_roundtrip(self):
        text_scope = actions.cursor_scope("admin-courses", "ALL", "ALL", "")
        text_cursor = actions.encode_list_cursor("admin-courses", text_scope, "curso a", "COURSE-1")
        self.assertEqual(
            ("curso a", "COURSE-1"),
            actions.decode_list_cursor(
                text_cursor, "admin-courses", text_scope, sort_type="text"
            ),
        )

        number_scope = actions.cursor_scope("admin-students", "ALL", "ALL", "progressDesc", "")
        number_cursor = actions.encode_list_cursor("admin-students", number_scope, 72.5, "STUDENT-1")
        self.assertEqual(
            (72.5, "STUDENT-1"),
            actions.decode_list_cursor(
                number_cursor, "admin-students", number_scope, sort_type="number"
            ),
        )

    def test_more_than_five_hundred_records_remain_stable_after_insert(self):
        base = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
        original = [
            {
                "attempt_id": f"ATT-{index:04d}",
                "pagination_sort_at": base - timedelta(seconds=index),
            }
            for index in range(507)
        ]
        scope = actions.cursor_scope("admin-submissions", "ALL", "")
        cursor = ""
        visited = []

        while True:
            remaining = original
            if cursor:
                cursor_at, cursor_id = actions.decode_list_cursor(
                    cursor, "admin-submissions", scope
                )
                remaining = [
                    row for row in original
                    if row["pagination_sort_at"] < cursor_at
                    or (
                        row["pagination_sort_at"] == cursor_at
                        and row["attempt_id"] < cursor_id
                    )
                ]
            page, pagination = actions.cursor_pagination_result(
                remaining[:101],
                100,
                "admin-submissions",
                scope,
                "pagination_sort_at",
                "attempt_id",
            )
            visited.extend(row["attempt_id"] for row in page)
            if not pagination["hasMore"]:
                break
            cursor = pagination["nextCursor"]
            if len(visited) == 100:
                original.insert(0, {
                    "attempt_id": "ATT-NEW",
                    "pagination_sort_at": base + timedelta(seconds=1),
                })

        self.assertEqual(507, len(visited))
        self.assertEqual(507, len(set(visited)))
        self.assertNotIn("ATT-NEW", visited)


class AdministrativeListQueryTests(unittest.TestCase):
    def test_course_filters_are_applied_before_keyset_limit(self):
        rows = [
            {
                "course_id": f"COURSE-{index}",
                "pagination_sort_text": f"curso {index}",
                "lesson_count": 1,
                "group_count": 0,
                "enrollment_count": 2,
                "total_count": 3,
                "active_count": 3,
                "inactive_count": 0,
                "total_lessons": 3,
                "total_groups": 0,
            }
            for index in range(3)
        ]
        with (
            patch.object(actions, "admin_context"),
            patch.object(actions, "fetch_all", return_value=rows) as fetch_all,
            patch.object(actions, "public_course", side_effect=lambda row: {"courseId": row["course_id"]}),
        ):
            result = actions.admin_list_courses({
                "content": "WITH_MODULES", "query": "curso", "limit": 2
            })["data"]

        query, params = fetch_all.call_args.args
        normalized = " ".join(query.split()).lower()
        self.assertIn("filtered_courses", normalized)
        self.assertIn("lesson_count > 0", normalized)
        self.assertIn("order by pagination_sort_text, course_id", normalized)
        self.assertEqual(3, params[-1])
        self.assertEqual(2, len(result["courses"]))
        self.assertTrue(result["pagination"]["hasMore"])

    def test_student_progress_filter_and_sort_are_database_side(self):
        rows = [
            {
                "student_id": f"STUDENT-{index}",
                "primary_progress": 90 - index,
                "enrollments": [],
                "memberships": [],
                "total_count": 3,
                "active_count": 3,
                "blocked_count": 0,
                "completed_count": 0,
                "average_progress": 89,
            }
            for index in range(3)
        ]
        with (
            patch.object(actions, "admin_context"),
            patch.object(actions, "prepare_notification_feature_schema"),
            patch.object(actions, "fetch_all", return_value=rows) as fetch_all,
            patch.object(actions, "public_student", side_effect=lambda row: {"studentId": row["student_id"]}),
        ):
            result = actions.admin_list_students({
                "progress": "IN_PROGRESS", "sort": "progressDesc", "limit": 2
            })["data"]

        query, params = fetch_all.call_args.args
        normalized = " ".join(query.split()).lower()
        self.assertIn("primary_progress > 0 and primary_progress < 100", normalized)
        self.assertIn("order by primary_progress desc, student_id desc", normalized)
        self.assertEqual(3, params[-1])
        self.assertEqual(2, len(result["students"]))
        self.assertEqual(3, result["total"])

    def test_remaining_admin_lists_expose_cursor_metadata(self):
        group_rows = [
            {
                "group_id": f"GROUP-{index}",
                "pagination_sort_text": f"grupo {index}",
                "member_count": 0,
                "total_count": 3,
            }
            for index in range(3)
        ]
        with patch.object(actions, "admin_context"), patch.object(
            actions, "fetch_all", return_value=group_rows
        ):
            groups = actions.admin_list_groups({"limit": 2})["data"]
        self.assertTrue(groups["pagination"]["hasMore"])

        staff_rows = [
            {
                "admin_id": f"ADMIN-{index}",
                "pagination_sort_text": f"admin {index}",
                "total_count": 3,
                "active_count": 2,
                "reviewer_count": 1,
            }
            for index in range(3)
        ]
        with (
            patch.object(actions, "admin_context", return_value=("token", {"admin_id": "ADMIN-0"})),
            patch.object(actions, "fetch_all", return_value=staff_rows),
            patch.object(actions, "public_admin", side_effect=lambda row: {"adminId": row["admin_id"]}),
        ):
            staff = actions.admin_list_staff({"limit": 2})["data"]
        self.assertTrue(staff["pagination"]["hasMore"])
        self.assertEqual(3, staff["pagination"]["total"])


class AdministrativeListFrontendTests(unittest.TestCase):
    def test_all_large_admin_views_use_cursor_state(self):
        source = (ROOT / "public" / "admin.js").read_text(encoding="utf-8")
        for state_name in (
            "studentPagination",
            "coursePagination",
            "groupPagination",
            "staffPagination",
            "surveyPagination",
            "notificationPagination",
        ):
            self.assertIn(state_name, source)
        self.assertIn("Selecionar esta página", source)
        self.assertIn("Exportar página CSV", source)
        self.assertIn("new AbortController()", source)
        self.assertIn("signal: beginListRequest", source)

        api_source = (ROOT / "public" / "api.js").read_text(encoding="utf-8")
        self.assertIn("signal: options.signal", api_source)
        self.assertIn("REQUEST_ABORTED", api_source)

    def test_public_and_packaged_frontend_match(self):
        for name in ("admin.js", "api.js"):
            self.assertEqual(
                (ROOT / "public" / name).read_text(encoding="utf-8"),
                (ROOT / "backend" / "courseplatform" / "static" / name).read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
