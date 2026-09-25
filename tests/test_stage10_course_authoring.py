import inspect
import json
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from backend.courseplatform.domains import catalog


ROOT = Path(__file__).resolve().parents[1]


class _Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class _DraftConnection:
    def __init__(self, status="DRAFT"):
        self.version = {
            "course_version_id": "VERSION-2",
            "course_id": "COURSE-1",
            "version_number": 2,
            "status": status,
            "content_snapshot_json": {"course": {}, "lessons": []},
        }
        self.updated_snapshot = None
        self.committed = False

    def execute(self, query, params=()):
        normalized = " ".join(query.lower().split())
        if normalized.startswith("select * from courseplatform.course_versions"):
            return _Result(self.version)
        if normalized.startswith("update courseplatform.course_versions"):
            self.updated_snapshot = json.loads(params[4])
            self.version = {
                **self.version,
                "title": params[0],
                "description": params[1],
                "total_hours": params[2],
                "passing_score": params[3],
                "content_snapshot_json": self.updated_snapshot,
            }
            return _Result(self.version)
        raise AssertionError(normalized)

    def commit(self):
        self.committed = True


def valid_snapshot():
    return {
        "schemaVersion": 1,
        "course": {
            "course_id": "COURSE-1",
            "course_code": "CP-101",
            "title": "Curso de validação",
            "description": "Conteúdo académico.",
            "total_hours": 12,
            "passing_score": 60,
        },
        "lessons": [
            {
                "lesson_id": "LESSON-1",
                "lesson_number": 1,
                "title": "Fundamentos",
                "status": "ACTIVE",
                "prerequisite_lesson_id": None,
                "content": [{"content_id": "CONTENT-1", "status": "ACTIVE"}],
                "questions": [],
            },
            {
                "lesson_id": "LESSON-2",
                "lesson_number": 2,
                "title": "Aplicação",
                "status": "ACTIVE",
                "prerequisite_lesson_id": "LESSON-1",
                "content": [{"content_id": "CONTENT-2", "status": "ACTIVE"}],
                "questions": [
                    {
                        "question_id": "QUESTION-1",
                        "question_type": "SINGLE_CHOICE",
                        "prompt": "Qual é a opção correta?",
                        "points": 10,
                        "status": "ACTIVE",
                        "options": [
                            {"option_id": "OPTION-1", "option_text": "A", "is_correct": True},
                            {"option_id": "OPTION-2", "option_text": "B", "is_correct": False},
                        ],
                    }
                ],
            },
        ],
    }


class CoursePublicationValidationTests(unittest.TestCase):
    def test_complete_snapshot_is_ready_for_publication(self):
        result = catalog.validate_course_version_snapshot(valid_snapshot())

        self.assertTrue(result["valid"])
        self.assertEqual(0, result["summary"]["errorCount"])
        self.assertEqual(2, result["summary"]["lessonCount"])
        self.assertEqual(2, result["summary"]["contentCount"])
        self.assertEqual(1, result["summary"]["questionCount"])

    def test_invalid_structure_reports_actionable_publication_blocks(self):
        snapshot = valid_snapshot()
        snapshot["course"]["total_hours"] = 0
        snapshot["lessons"][1]["lesson_number"] = 1
        snapshot["lessons"][1]["prerequisite_lesson_id"] = "LESSON-2"
        snapshot["lessons"][1]["questions"][0]["points"] = 0
        snapshot["lessons"][1]["questions"][0]["options"] = []

        result = catalog.validate_course_version_snapshot(snapshot)
        codes = {issue["code"] for issue in result["issues"]}

        self.assertFalse(result["valid"])
        self.assertIn("COURSE_HOURS_REQUIRED", codes)
        self.assertIn("LESSON_ORDER_DUPLICATED", codes)
        self.assertIn("PREREQUISITE_SELF_REFERENCE", codes)
        self.assertIn("QUESTION_POINTS_INVALID", codes)
        self.assertIn("QUESTION_OPTIONS_REQUIRED", codes)
        self.assertIn("QUESTION_CORRECT_ANSWER_REQUIRED", codes)

    def test_prerequisite_cycles_are_rejected(self):
        snapshot = valid_snapshot()
        snapshot["lessons"][0]["prerequisite_lesson_id"] = "LESSON-2"

        result = catalog.validate_course_version_snapshot(snapshot)

        self.assertFalse(result["valid"])
        self.assertIn("PREREQUISITE_CYCLE", {issue["code"] for issue in result["issues"]})

    def test_preview_contains_structure_without_answer_keys(self):
        preview = catalog.course_version_preview(valid_snapshot())

        self.assertEqual("Curso de validação", preview["course"]["title"])
        self.assertEqual(2, len(preview["lessons"]))
        self.assertEqual(1, preview["lessons"][1]["questionCount"])
        self.assertNotIn("questions", preview["lessons"][1])
        self.assertNotIn("correct_answer", str(preview).lower())

    def test_draft_editor_exposes_editable_content_without_answer_keys(self):
        editor = catalog.course_version_draft_editor(valid_snapshot())

        self.assertEqual("Curso de validação", editor["course"]["title"])
        self.assertEqual("CONTENT-1", editor["lessons"][0]["content"][0]["contentId"])
        self.assertEqual(1, editor["lessons"][1]["questionCount"])
        self.assertNotIn("questions", editor["lessons"][1])
        self.assertNotIn("is_correct", str(editor).lower())

    def test_draft_reordering_is_complete_and_does_not_mutate_source(self):
        snapshot = valid_snapshot()

        edited = catalog.edit_course_version_draft_snapshot(
            snapshot,
            "REORDER_LESSONS",
            {"lessonIds": ["LESSON-2", "LESSON-1"]},
        )

        self.assertEqual(["LESSON-2", "LESSON-1"], [item["lesson_id"] for item in edited["lessons"]])
        self.assertEqual([1, 2], [item["lesson_number"] for item in edited["lessons"]])
        self.assertEqual(["LESSON-1", "LESSON-2"], [item["lesson_id"] for item in snapshot["lessons"]])

    def test_draft_content_can_be_edited_and_reordered(self):
        snapshot = valid_snapshot()
        snapshot["lessons"][0]["content"].append({
            "content_id": "CONTENT-3",
            "section_order": 2,
            "title": "Segundo conteúdo",
            "status": "ACTIVE",
        })
        edited = catalog.edit_course_version_draft_snapshot(
            snapshot,
            "REORDER_CONTENT",
            {"lessonId": "LESSON-1", "contentIds": ["CONTENT-3", "CONTENT-1"]},
        )
        edited = catalog.edit_course_version_draft_snapshot(
            edited,
            "UPDATE_CONTENT",
            {
                "lessonId": "LESSON-1",
                "contentId": "CONTENT-3",
                "title": "Conteúdo revisto",
                "bodyHtml": "Texto do rascunho",
                "estimatedMinutes": 25,
                "isRequired": True,
            },
        )

        content = edited["lessons"][0]["content"]
        self.assertEqual(["CONTENT-3", "CONTENT-1"], [item["content_id"] for item in content])
        self.assertEqual([1, 2], [item["section_order"] for item in content])
        self.assertEqual("Conteúdo revisto", content[0]["title"])

    def test_incomplete_draft_order_is_rejected(self):
        with self.assertRaises(catalog.ApiError) as raised:
            catalog.edit_course_version_draft_snapshot(
                valid_snapshot(),
                "REORDER_LESSONS",
                {"lessonIds": ["LESSON-1"]},
            )

        self.assertEqual("COURSE_VERSION_ORDER_INCOMPLETE", raised.exception.code)

    def test_stored_draft_snapshot_is_parsed_without_reading_live_content(self):
        snapshot = valid_snapshot()
        parsed = catalog.stored_course_version_snapshot({
            "content_snapshot_json": json.dumps(snapshot),
        })

        self.assertEqual(snapshot, parsed)

    def test_invalid_stored_snapshot_is_rejected_explicitly(self):
        with self.assertRaises(catalog.ApiError) as raised:
            catalog.stored_course_version_snapshot({"content_snapshot_json": "not-json"})

        self.assertEqual("COURSE_VERSION_SNAPSHOT_INVALID", raised.exception.code)

    def test_publish_action_enforces_the_same_validation_as_preview(self):
        publish_source = inspect.getsource(catalog.admin_publish_course_version_action)
        preview_source = inspect.getsource(catalog.admin_preview_course_version_action)

        self.assertIn("validate_course_version_snapshot(snapshot)", publish_source)
        self.assertIn('"COURSE_VERSION_INVALID"', publish_source)
        self.assertIn("validate_course_version_snapshot(snapshot)", preview_source)
        self.assertIn("stored_course_version_snapshot(version)", publish_source)
        self.assertIn("stored_course_version_snapshot(version)", preview_source)
        self.assertNotIn("course_structure_snapshot_with_conn", publish_source)
        self.assertNotIn("course_structure_snapshot_with_conn", preview_source)

    def test_only_explicit_refresh_replaces_the_draft_snapshot(self):
        refresh_source = inspect.getsource(catalog.admin_refresh_course_version_draft_action)

        self.assertIn("course_structure_snapshot_with_conn", refresh_source)
        self.assertIn("where course_version_id = %s and status = 'DRAFT'", refresh_source)
        self.assertIn("COURSE_VERSION_DRAFT_REFRESHED", refresh_source)

    def test_explicit_refresh_replaces_only_a_draft_and_is_audited(self):
        connection = _DraftConnection()
        audits = []

        @contextmanager
        def connect():
            yield connection

        runtime = SimpleNamespace(
            admin_context=lambda payload, roles: ({}, {"admin_id": "ADMIN-1", "role": "ADMIN"}),
            audit=lambda *args: audits.append(args),
            connection=connect,
            course_structure_snapshot_with_conn=lambda conn, course_id: valid_snapshot(),
            float_value=lambda value, fallback=0: float(value if value not in (None, "") else fallback),
            public_course_version=lambda row: row,
            require_fields=lambda payload, fields: None,
            success=lambda data: data,
        )

        result = catalog.admin_refresh_course_version_draft_action(
            {"courseVersionId": "VERSION-2"},
            runtime=runtime,
        )

        self.assertEqual(valid_snapshot(), connection.updated_snapshot)
        self.assertTrue(connection.committed)
        self.assertEqual("COURSE_VERSION_DRAFT_REFRESHED", audits[0][3])
        self.assertTrue(result["validation"]["valid"])

    def test_published_version_cannot_be_refreshed_from_the_editor(self):
        connection = _DraftConnection(status="PUBLISHED")

        @contextmanager
        def connect():
            yield connection

        runtime = SimpleNamespace(
            admin_context=lambda payload, roles: ({}, {"admin_id": "ADMIN-1", "role": "ADMIN"}),
            audit=lambda *args: None,
            connection=connect,
            course_structure_snapshot_with_conn=lambda conn, course_id: valid_snapshot(),
            float_value=float,
            public_course_version=lambda row: row,
            require_fields=lambda payload, fields: None,
            success=lambda data: data,
        )

        with self.assertRaises(catalog.ApiError) as raised:
            catalog.admin_refresh_course_version_draft_action(
                {"courseVersionId": "VERSION-2"},
                runtime=runtime,
            )

        self.assertEqual("COURSE_VERSION_NOT_DRAFT", raised.exception.code)
        self.assertIsNone(connection.updated_snapshot)

    def test_draft_edit_is_transactional_and_audited(self):
        connection = _DraftConnection()
        connection.version["content_snapshot_json"] = valid_snapshot()
        audits = []

        @contextmanager
        def connect():
            yield connection

        runtime = SimpleNamespace(
            admin_context=lambda payload, roles: ({}, {"admin_id": "ADMIN-1", "role": "ADMIN"}),
            audit=lambda *args: audits.append(args),
            connection=connect,
            float_value=lambda value, fallback=0: float(value if value not in (None, "") else fallback),
            iso=lambda value: value.isoformat() if value else None,
            public_course_version=lambda row: row,
            require_fields=lambda payload, fields: None,
            success=lambda data: data,
        )

        result = catalog.admin_edit_course_version_draft_action(
            {
                "courseVersionId": "VERSION-2",
                "operation": "REORDER_LESSONS",
                "changes": {"lessonIds": ["LESSON-2", "LESSON-1"]},
            },
            runtime=runtime,
        )

        self.assertTrue(connection.committed)
        self.assertEqual("LESSON-2", connection.updated_snapshot["lessons"][0]["lesson_id"])
        self.assertEqual("COURSE_VERSION_DRAFT_EDITED", audits[0][3])
        self.assertEqual("REORDER_LESSONS", audits[0][6]["operation"])
        self.assertEqual("LESSON-2", result["draftEditor"]["lessons"][0]["lessonId"])

    def test_published_version_cannot_be_edited(self):
        connection = _DraftConnection(status="PUBLISHED")

        @contextmanager
        def connect():
            yield connection

        runtime = SimpleNamespace(
            admin_context=lambda payload, roles: ({}, {"admin_id": "ADMIN-1", "role": "ADMIN"}),
            connection=connect,
            require_fields=lambda payload, fields: None,
        )

        with self.assertRaises(catalog.ApiError) as raised:
            catalog.admin_edit_course_version_draft_action(
                {
                    "courseVersionId": "VERSION-2",
                    "operation": "UPDATE_COURSE",
                    "changes": {},
                },
                runtime=runtime,
            )

        self.assertEqual("COURSE_VERSION_NOT_DRAFT", raised.exception.code)

    def test_stale_draft_edit_is_rejected_before_writing(self):
        connection = _DraftConnection()
        connection.version["content_snapshot_json"] = valid_snapshot()
        connection.version["updated_at"] = datetime(2026, 9, 25, 8, 0, tzinfo=timezone.utc)

        @contextmanager
        def connect():
            yield connection

        runtime = SimpleNamespace(
            admin_context=lambda payload, roles: ({}, {"admin_id": "ADMIN-1", "role": "ADMIN"}),
            connection=connect,
            iso=lambda value: value.isoformat(),
            require_fields=lambda payload, fields: None,
        )

        with self.assertRaises(catalog.ApiError) as raised:
            catalog.admin_edit_course_version_draft_action(
                {
                    "courseVersionId": "VERSION-2",
                    "operation": "REORDER_LESSONS",
                    "changes": {"lessonIds": ["LESSON-2", "LESSON-1"]},
                    "expectedUpdatedAt": "2026-09-25T07:00:00+00:00",
                },
                runtime=runtime,
            )

        self.assertEqual("COURSE_VERSION_CONFLICT", raised.exception.code)
        self.assertIsNone(connection.updated_snapshot)


class CourseAuthoringFrontendContractTests(unittest.TestCase):
    def test_admin_exposes_preview_validation_before_publication(self):
        admin_source = (ROOT / "public" / "admin.js").read_text(encoding="utf-8")
        api_source = (ROOT / "public" / "api.js").read_text(encoding="utf-8")

        self.assertIn("data-preview-course-version", admin_source)
        self.assertIn("course-version-validation", admin_source)
        self.assertIn("adminPreviewCourseVersion", api_source)
        self.assertIn("adminRefreshCourseVersionDraft", api_source)
        self.assertIn("adminEditCourseVersionDraft", api_source)
        self.assertIn("data-edit-course-version", admin_source)
        self.assertIn("REORDER_LESSONS", admin_source)
        self.assertIn("REORDER_CONTENT", admin_source)
        self.assertIn("Atualizar do editor", admin_source)
        self.assertIn("Corrija os bloqueios antes de publicar", admin_source)


if __name__ == "__main__":
    unittest.main()
