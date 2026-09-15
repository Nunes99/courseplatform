import asyncio
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import httpx

from backend.courseplatform import actions
from backend.courseplatform import app as app_module


ROOT = Path(__file__).resolve().parents[1]


class ThreadpoolDispatchTests(unittest.TestCase):
    def test_concurrent_requests_do_not_serialize_sync_dispatch(self):
        lock = threading.Lock()
        both_started = threading.Event()
        active = 0
        maximum_active = 0

        def slow_dispatch(_action, _payload):
            nonlocal active, maximum_active
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
                if active == 2:
                    both_started.set()
            both_started.wait(timeout=1)
            with lock:
                active -= 1
            return {"success": True, "data": {"status": "ok"}}

        async def run_requests():
            transport = httpx.ASGITransport(app=app_module.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await asyncio.gather(
                    client.get("/api?action=threadpoolProbe"),
                    client.get("/api?action=threadpoolProbe"),
                )

        with patch.object(app_module, "dispatch", side_effect=slow_dispatch):
            responses = asyncio.run(run_requests())

        self.assertEqual([200, 200], [response.status_code for response in responses])
        self.assertEqual(2, maximum_active)


class CursorPaginationTests(unittest.TestCase):
    def test_cursor_roundtrip_is_bound_to_filters(self):
        created_at = datetime(2026, 9, 14, 12, 30, tzinfo=timezone.utc)
        scope = actions.cursor_scope("admin-submissions", "ALL", "ana")
        cursor = actions.encode_list_cursor("admin-submissions", scope, created_at, "ATT-009")

        decoded_at, decoded_id = actions.decode_list_cursor(
            cursor,
            "admin-submissions",
            scope,
        )
        self.assertEqual(created_at, decoded_at)
        self.assertEqual("ATT-009", decoded_id)

        with self.assertRaises(actions.ApiError) as raised:
            actions.decode_list_cursor(
                cursor,
                "admin-submissions",
                actions.cursor_scope("admin-submissions", "APPROVED", "ana"),
            )
        self.assertEqual("CURSOR_FILTER_MISMATCH", raised.exception.code)

    def test_page_uses_limit_plus_one_without_returning_the_probe_row(self):
        base = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
        rows = [
            {"attempt_id": f"ATT-{index}", "pagination_sort_at": base - timedelta(minutes=index)}
            for index in range(3)
        ]
        visible, pagination = actions.cursor_pagination_result(
            rows,
            2,
            "admin-submissions",
            actions.cursor_scope("admin-submissions", "ALL", ""),
            "pagination_sort_at",
            "attempt_id",
        )
        self.assertEqual(["ATT-0", "ATT-1"], [row["attempt_id"] for row in visible])
        self.assertTrue(pagination["hasMore"])
        self.assertEqual(2, pagination["returned"])
        self.assertTrue(pagination["nextCursor"])

    def test_invalid_cursor_returns_a_safe_api_error(self):
        with self.assertRaises(actions.ApiError) as raised:
            actions.decode_list_cursor("not-base64", "admin-certificates", "scope")
        self.assertEqual("INVALID_CURSOR", raised.exception.code)

    def test_submission_list_returns_stable_cursor_metadata(self):
        created_at = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
        rows = [
            {
                "attempt_id": f"ATT-{index}",
                "attempt_student_id": "STU-1",
                "attempt_lesson_id": "LESSON-1",
                "pagination_sort_at": created_at - timedelta(minutes=index),
            }
            for index in range(3)
        ]
        with (
            patch.object(actions, "admin_context"),
            patch.object(actions, "expire_overdue_attempts"),
            patch.object(actions, "fetch_all", return_value=rows) as fetch_all,
        ):
            result = actions.admin_list_submissions({"limit": 2, "status": "ALL"})["data"]

        self.assertEqual(2, len(result["submissions"]))
        self.assertTrue(result["pagination"]["hasMore"])
        query, params = fetch_all.call_args.args
        self.assertIn("a.attempt_id desc", query)
        self.assertEqual(3, params[-1])


class _RowsResult:
    def __init__(self, rows=None, row=None):
        self.rows = rows or []
        self.row = row

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row


class _ListConnection:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback):
        return False

    def execute(self, query, params=()):
        self.queries.append((query, params))
        return _RowsResult(self.rows)

    def commit(self):
        return None


class _ChatSummaryConnection:
    def __init__(self, rooms):
        self.rooms = rooms
        self.query_count = 0

    def execute(self, query, params=()):
        self.query_count += 1
        normalized = " ".join(query.split()).lower()
        if "select distinct on (room_id)" in normalized:
            return _RowsResult([
                {"room_id": room["room_id"], "message_id": f"MSG-{room['room_id']}"}
                for room in self.rooms
            ])
        if "select m.*" in normalized:
            return _RowsResult([
                {
                    "message_id": f"MSG-{room['room_id']}",
                    "room_id": room["room_id"],
                    "sender_type": "ADMIN",
                    "sender_admin_id": "ADM-1",
                    "admin_name": "Admin",
                    "status": "ACTIVE",
                    "body": "Mensagem",
                }
                for room in self.rooms
            ])
        if "with read_cursors" in normalized or "from courseplatform.chat_presence" in normalized:
            return _RowsResult([])
        if "from courseplatform.students s" in normalized:
            return _RowsResult([
                {
                    "student_id": room["owner_student_id"],
                    "public_student_id": f"PUBLIC-{index}",
                    "full_name": f"Estudante {index}",
                }
                for index, room in enumerate(self.rooms)
            ])
        raise AssertionError(f"Consulta inesperada: {normalized}")


class _RecordingConnection:
    def __init__(self):
        self.queries = []

    def execute(self, query, params=()):
        self.queries.append((" ".join(query.split()).lower(), params))
        return _RowsResult()


class ChatBatchQueryTests(unittest.TestCase):
    def test_room_synchronization_is_one_set_based_statement(self):
        for actor in (
            {"type": "STUDENT", "id": "STU-1"},
            {"type": "ADMIN", "id": "ADM-1"},
        ):
            conn = _RecordingConnection()
            actions.sync_chat_rooms(conn, actor)
            self.assertEqual(1, len(conn.queries))
            self.assertIn("with desired_rooms as", conn.queries[0][0])
            self.assertIn("on conflict (room_key)", conn.queries[0][0])

    def test_room_summary_query_count_does_not_grow_with_rooms(self):
        rooms = [
            {
                "room_id": f"ROOM-{index}",
                "room_type": "SUPPORT",
                "owner_student_id": f"STU-{index}",
            }
            for index in range(40)
        ]
        conn = _ChatSummaryConnection(rooms)
        summaries = actions.chat_room_summary_context(
            conn,
            rooms,
            {"type": "ADMIN", "id": "ADM-1"},
            active_admin_count=3,
        )

        self.assertEqual(40, len(summaries))
        self.assertEqual(5, conn.query_count)
        self.assertTrue(all(item["participantCount"] == 4 for item in summaries.values()))


class AdministrativeListContractTests(unittest.TestCase):
    def test_certificate_requests_are_cursor_paginated(self):
        created_at = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
        rows = [
            {"request_id": f"REQ-{index}", "pagination_sort_at": created_at - timedelta(minutes=index)}
            for index in range(3)
        ]
        conn = _ListConnection(rows)
        with (
            patch.object(actions, "admin_context"),
            patch.object(actions, "ensure_certificate_feature_schema"),
            patch.object(actions, "connection", return_value=conn),
            patch.object(actions, "public_certificate_request", side_effect=lambda row: {"requestId": row["request_id"]}),
        ):
            result = actions.admin_list_certificate_requests({"status": "ALL", "limit": 2})["data"]

        self.assertEqual(2, len(result["requests"]))
        self.assertTrue(result["pagination"]["hasMore"])
        self.assertNotIn("{cursor_sql}", conn.queries[0][0])
        self.assertEqual(3, conn.queries[0][1][-1])

    def test_certificates_with_null_issue_dates_remain_pageable(self):
        rows = [
            {"certificate_id": f"CERT-{index}", "issue_date": None, "course_certificate_profile": {}}
            for index in range(3)
        ]
        conn = _ListConnection(rows)
        with (
            patch.object(actions, "admin_context"),
            patch.object(actions, "ensure_certificate_feature_schema"),
            patch.object(actions, "connection", return_value=conn),
            patch.object(actions, "public_certificate", side_effect=lambda row: {"certificateId": row["certificate_id"]}),
            patch.object(actions, "certificate_download_access", return_value={}),
        ):
            first_page = actions.admin_list_certificates({"status": "ALL", "limit": 2})["data"]

        cursor = first_page["pagination"]["nextCursor"]
        decoded_at, decoded_id = actions.decode_list_cursor(
            cursor,
            "admin-certificates",
            actions.cursor_scope("admin-certificates", "ALL", ""),
            allow_null_sort=True,
        )
        self.assertIsNone(decoded_at)
        self.assertEqual("CERT-1", decoded_id)


class AdministrativePaginationFrontendTests(unittest.TestCase):
    def test_packaged_admin_frontend_matches_public_source(self):
        public_source = (ROOT / "public" / "admin.js").read_text(encoding="utf-8")
        packaged_source = (
            ROOT / "backend" / "courseplatform" / "static" / "admin.js"
        ).read_text(encoding="utf-8")
        self.assertEqual(public_source, packaged_source)

    def test_admin_lists_send_and_render_cursor_metadata(self):
        source = (ROOT / "public" / "admin.js").read_text(encoding="utf-8")
        pagination_source = (ROOT / "public" / "admin" / "pagination.js").read_text(encoding="utf-8")
        self.assertIn("cursor: state.submissionPagination.cursor", source)
        self.assertIn("cursor: state.certificatePagination.requests.cursor", source)
        self.assertIn("cursor: state.certificatePagination.certificates.cursor", source)
        self.assertIn("cursorPaginationTemplate", source)
        self.assertIn("function cursorPaginationTemplate", pagination_source)
        self.assertIn("function scheduleCertificateRefresh", source)


if __name__ == "__main__":
    unittest.main()
