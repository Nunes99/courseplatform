import copy
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.courseplatform import actions
from backend.courseplatform.app import app


NOW = datetime(2026, 9, 13, 9, tzinfo=timezone.utc)


def lesson_row():
    return {
        "lesson_id": "L1",
        "course_id": "C1",
        "lesson_number": 1,
        "title": "Avaliação segura",
        "submission_duration_minutes": 60,
        "passing_score": 60,
        "feedback_release_mode": "AFTER_REVIEW",
        "show_correct_answers": True,
        "show_explanations": True,
        "status": "ACTIVE",
    }


def question_row():
    return {
        "question_id": "Q1",
        "lesson_id": "L1",
        "question_order": 1,
        "question_type": "SINGLE_CHOICE",
        "prompt": "Qual é a opção correta?",
        "points": 10,
        "correct_answer": "O1",
        "explanation": "O1 satisfaz o critério.",
        "is_required": True,
        "status": "ACTIVE",
    }


def option_rows():
    return [
        {"option_id": "O1", "question_id": "Q1", "option_order": 1, "option_label": "A", "option_text": "Primeira", "is_correct": True},
        {"option_id": "O2", "question_id": "Q1", "option_order": 2, "option_label": "B", "option_text": "Segunda", "is_correct": False},
    ]


def snapshot(release_mode="AFTER_REVIEW", show_answers=True, show_explanations=True):
    question = {**question_row(), "options": option_rows()}
    return {
        "version": 1,
        "capturedAt": NOW.isoformat(),
        "feedbackPolicy": {
            "releaseMode": release_mode,
            "showCorrectAnswers": show_answers,
            "showExplanations": show_explanations,
        },
        "questions": [question],
    }


def forbidden_fields(value):
    forbidden = {"correctAnswer", "explanation", "isCorrect", "awardedPoints", "points", "reviewerId"}
    found = set()
    if isinstance(value, dict):
        found.update(forbidden.intersection(value))
        for item in value.values():
            found.update(forbidden_fields(item))
    elif isinstance(value, list):
        for item in value:
            found.update(forbidden_fields(item))
    return found


class QueryResult:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows if rows is not None else ([] if row is None else [row])

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class GradingConnection:
    def __init__(self, attempt, answers):
        self.attempt = attempt
        self.answers = answers
        self.committed = False

    def execute(self, query, params=()):
        normalized = " ".join(query.lower().split())
        if normalized.startswith("select * from courseplatform.answers"):
            return QueryResult(rows=self.answers)
        if normalized.startswith("update courseplatform.answers set submitted_at"):
            for answer in self.answers:
                answer["submitted_at"] = params[0]
            return QueryResult()
        if normalized.startswith("update courseplatform.answers set is_correct"):
            answer = next(item for item in self.answers if item["answer_id"] == params[3])
            answer.update(is_correct=params[0], awarded_points=params[1], submitted_at=params[2])
            return QueryResult()
        if normalized.startswith("update courseplatform.attempts"):
            self.attempt.update(
                status=params[0],
                submitted_at=params[1],
                objective_score=params[2],
                updated_at=params[3],
            )
            return QueryResult(row=self.attempt)
        if normalized.startswith("update courseplatform.lesson_progress"):
            return QueryResult()
        raise AssertionError(normalized)

    def commit(self):
        self.committed = True


class AttemptStatusConnection:
    def execute(self, query, params=()):
        normalized = " ".join(query.lower().split())
        if "from courseplatform.answers" in normalized:
            return QueryResult(rows=[{
                "answer_id": "ANS1",
                "attempt_id": "ATT1",
                "question_id": "Q1",
                "selected_option_id": "O1",
                "is_correct": True,
                "awarded_points": 10,
            }])
        if "from courseplatform.files" in normalized:
            return QueryResult(rows=[])
        if "from courseplatform.reviews" in normalized:
            return QueryResult(row={
                "review_id": "REV1",
                "attempt_id": "ATT1",
                "reviewer_id": "R1",
                "decision": "CORRECTION_REQUIRED",
                "score": 50,
                "comments": "Revisão anterior",
                "reviewed_at": NOW - timedelta(days=1),
            })
        raise AssertionError(normalized)


class AssessmentAnswerProtectionTests(unittest.TestCase):
    def test_http_student_lesson_never_contains_answer_key_or_internal_score(self):
        class LessonConnection:
            def execute(self, query, params=()):
                normalized = " ".join(query.lower().split())
                if normalized.startswith("select course_id from courseplatform.lessons"):
                    return QueryResult(row={"course_id": "C1"})
                if normalized.startswith("select * from courseplatform.enrollments"):
                    return QueryResult(row={
                        "enrollment_id": "E1",
                        "student_id": "S1",
                        "course_id": "C1",
                        "course_version_id": "CV1",
                        "offering_id": "O1",
                        "status": "ACTIVE",
                    })
                if normalized.startswith("select * from courseplatform.course_versions"):
                    return QueryResult(row={
                        "course_version_id": "CV1",
                        "course_id": "C1",
                        "version_number": 1,
                        "status": "PUBLISHED",
                        "title": "Curso",
                        "content_snapshot_json": {
                            "lessons": [{
                                **lesson_row(),
                                "content": [],
                                "questions": [{**question_row(), "options": option_rows()}],
                            }],
                        },
                    })
                if normalized.startswith("select * from courseplatform.lesson_progress"):
                    return QueryResult(row={
                        "progress_id": "P1",
                        "enrollment_id": "E1",
                        "lesson_id": "L1",
                        "status": "AVAILABLE",
                        "content_access_status": "AVAILABLE",
                        "evaluation_status": "NOT_STARTED",
                        "attempt_count": 0,
                    })
                raise AssertionError(normalized)

        @contextmanager
        def connect():
            yield LessonConnection()

        with (
            patch.object(actions, "require_application_schema"),
            patch.object(actions, "student_context", return_value=({}, {"student_id": "S1"})),
            patch.object(actions, "prepare_assessment_feature_schema"),
            patch.object(actions, "connection", connect),
        ):
            response = TestClient(app).post("/api", json={
                "action": "getLesson",
                "sessionToken": "synthetic-session",
                "lessonId": "L1",
            })

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(forbidden_fields(body["data"]["questions"]), set())

    def test_authorized_reviewer_contract_contains_answer_key(self):
        def fetch_one(query, params):
            return {"course_id": "C1", "title": "Curso", "status": "ACTIVE"}

        def fetch_all(query, params):
            if "from courseplatform.course_versions" in query:
                return []
            if "from courseplatform.course_offerings" in query:
                return []
            if "from courseplatform.lessons" in query:
                return [lesson_row()]
            if "lesson_content" in query:
                return []
            if "question_options" in query:
                return option_rows()
            if "courseplatform.questions" in query:
                return [question_row()]
            raise AssertionError(query)

        with (
            patch.object(actions, "admin_context", return_value=({}, {"admin_id": "R1", "role": "REVIEWER"})) as authorize,
            patch.object(actions, "fetch_one", side_effect=fetch_one),
            patch.object(actions, "fetch_all", side_effect=fetch_all),
        ):
            data = actions.admin_course_structure({"courseId": "C1"})["data"]

        authorize.assert_called_once_with({"courseId": "C1"}, {"OWNER", "ADMIN", "REVIEWER"})
        question = data["lessons"][0]["questions"][0]
        self.assertEqual(question["question"]["correctAnswer"], "O1")
        self.assertTrue(question["options"][0]["isCorrect"])

    def test_student_cannot_read_another_students_attempt(self):
        captured = {}

        def fetch_one(query, params):
            captured["params"] = params
            return None

        with (
            patch.object(actions, "student_context", return_value=({}, {"student_id": "S1"})),
            patch.object(actions, "prepare_assessment_feature_schema"),
            patch.object(actions, "fetch_one", side_effect=fetch_one),
        ):
            with self.assertRaises(actions.ApiError) as raised:
                actions.attempt_status({"attemptId": "ATT-OTHER"})

        self.assertEqual(raised.exception.code, "ATTEMPT_NOT_FOUND")
        self.assertEqual(captured["params"], ("ATT-OTHER", "S1"))

    def test_http_in_progress_attempt_hides_grading_and_old_review(self):
        attempt = {
            "attempt_id": "ATT1",
            "progress_id": "P1",
            "student_id": "S1",
            "lesson_id": "L1",
            "attempt_number": 2,
            "status": "IN_PROGRESS",
            "deadline_at": NOW + timedelta(hours=1),
            "submitted_at": None,
            "reviewed_at": None,
            "assessment_snapshot_json": snapshot(),
        }
        database = AttemptStatusConnection()

        @contextmanager
        def connect():
            yield database

        with (
            patch.object(actions, "require_application_schema"),
            patch.object(actions, "student_context", return_value=({}, {"student_id": "S1"})),
            patch.object(actions, "prepare_assessment_feature_schema"),
            patch.object(actions, "fetch_one", return_value=attempt),
            patch.object(actions, "connection", connect),
            patch.object(actions, "utc_now", return_value=NOW),
        ):
            response = TestClient(app).post("/api", json={
                "action": "getAttemptStatus",
                "sessionToken": "synthetic-session",
                "attemptId": "ATT1",
            })

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(forbidden_fields(data), set())
        self.assertIsNone(data["latestReview"])

    def test_feedback_release_respects_submission_review_and_policy(self):
        base = {"submitted_at": None, "reviewed_at": None, "status": "IN_PROGRESS"}
        self.assertEqual(actions.feedback_visibility(base, snapshot("AFTER_SUBMISSION")), (False, False))
        self.assertEqual(
            actions.feedback_visibility({**base, "submitted_at": NOW}, snapshot("AFTER_SUBMISSION")),
            (True, True),
        )
        self.assertEqual(
            actions.feedback_visibility({**base, "submitted_at": NOW}, snapshot("AFTER_REVIEW")),
            (False, False),
        )
        self.assertEqual(
            actions.feedback_visibility({**base, "submitted_at": NOW, "reviewed_at": NOW, "status": "APPROVED"}, snapshot("AFTER_REVIEW")),
            (True, True),
        )
        self.assertEqual(
            actions.feedback_visibility({**base, "submitted_at": NOW, "reviewed_at": NOW, "status": "APPROVED"}, snapshot("NEVER")),
            (False, False),
        )

    def test_snapshot_result_is_not_changed_by_later_question_edit(self):
        frozen = snapshot()
        answers = [{"answer_id": "A1", "question_id": "Q1", "selected_option_id": "O1"}]
        initial_score, initial_rows = actions.grade_objective_answers(frozen, answers)

        current_question = copy.deepcopy(question_row())
        current_question["correct_answer"] = "O2"
        current_options = option_rows()
        current_options[0]["is_correct"] = False
        current_options[1]["is_correct"] = True

        score_after_edit, rows_after_edit = actions.grade_objective_answers(frozen, answers)
        self.assertEqual((initial_score, initial_rows), (100.0, [(True, 10.0, "A1")]))
        self.assertEqual((score_after_edit, rows_after_edit), (initial_score, initial_rows))
        self.assertEqual(current_question["correct_answer"], "O2")

    def test_submit_grades_objective_answer_on_server_from_frozen_snapshot(self):
        attempt = {
            "attempt_id": "ATT1",
            "progress_id": "P1",
            "student_id": "S1",
            "lesson_id": "L1",
            "attempt_number": 1,
            "status": "IN_PROGRESS",
            "deadline_at": NOW + timedelta(hours=1),
            "assessment_snapshot_json": snapshot(),
        }
        answers = [{
            "answer_id": "ANS1",
            "attempt_id": "ATT1",
            "question_id": "Q1",
            "selected_option_id": "O1",
        }]
        database = GradingConnection(attempt, answers)

        @contextmanager
        def connect():
            yield database

        with (
            patch.object(actions, "student_context", return_value=({}, {"student_id": "S1"})),
            patch.object(actions, "prepare_assessment_feature_schema"),
            patch.object(actions, "editable_attempt", return_value=attempt),
            patch.object(actions, "connection", connect),
            patch.object(actions, "utc_now", return_value=NOW),
            patch.object(actions, "audit"),
        ):
            result = actions.submit_attempt({"attemptId": "ATT1"})["data"]["attempt"]

        self.assertEqual(result["status"], "UNDER_REVIEW")
        self.assertEqual(attempt["objective_score"], 100.0)
        self.assertTrue(answers[0]["is_correct"])
        self.assertEqual(answers[0]["awarded_points"], 10.0)
        self.assertTrue(database.committed)

    def test_student_contract_reveals_only_configured_feedback(self):
        attempt = {"submitted_at": NOW, "reviewed_at": NOW, "status": "APPROVED"}
        questions = actions.student_snapshot_questions(attempt, snapshot(show_answers=False, show_explanations=True))
        self.assertNotIn("correctAnswer", questions[0])
        self.assertNotIn("isCorrect", questions[0]["options"][0])
        self.assertEqual(questions[0]["explanation"], "O1 satisfaz o critério.")

    def test_student_attempt_omits_review_metadata_before_review(self):
        result = actions.student_attempt({
            "attempt_id": "A1",
            "attempt_number": 1,
            "status": "IN_PROGRESS",
            "deadline_at": NOW + timedelta(hours=1),
            "score": 100,
            "reviewer_id": "R1",
            "review_comments": "Interno",
        })
        self.assertNotIn("score", result)
        self.assertNotIn("reviewerId", result)
        self.assertNotIn("reviewComments", result)

    def test_admin_rejects_unknown_feedback_policy(self):
        with (
            patch.object(actions, "admin_context", return_value=({}, {"admin_id": "A1"})),
            patch.object(actions, "prepare_assessment_feature_schema"),
        ):
            with self.assertRaises(actions.ApiError) as raised:
                actions.admin_save_lesson({
                    "courseId": "C1",
                    "title": "Módulo",
                    "feedbackReleaseMode": "WHENEVER",
                })
        self.assertEqual(raised.exception.code, "INVALID_FEEDBACK_POLICY")


if __name__ == "__main__":
    unittest.main()
