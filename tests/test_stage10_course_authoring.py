import inspect
import unittest
from pathlib import Path

from backend.courseplatform.domains import catalog


ROOT = Path(__file__).resolve().parents[1]


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

    def test_publish_action_enforces_the_same_validation_as_preview(self):
        publish_source = inspect.getsource(catalog.admin_publish_course_version_action)
        preview_source = inspect.getsource(catalog.admin_preview_course_version_action)

        self.assertIn("validate_course_version_snapshot(snapshot)", publish_source)
        self.assertIn('"COURSE_VERSION_INVALID"', publish_source)
        self.assertIn("validate_course_version_snapshot(snapshot)", preview_source)


class CourseAuthoringFrontendContractTests(unittest.TestCase):
    def test_admin_exposes_preview_validation_before_publication(self):
        admin_source = (ROOT / "public" / "admin.js").read_text(encoding="utf-8")
        api_source = (ROOT / "public" / "api.js").read_text(encoding="utf-8")

        self.assertIn("data-preview-course-version", admin_source)
        self.assertIn("course-version-validation", admin_source)
        self.assertIn("adminPreviewCourseVersion", api_source)
        self.assertIn("Corrija os bloqueios antes de publicar", admin_source)


if __name__ == "__main__":
    unittest.main()
