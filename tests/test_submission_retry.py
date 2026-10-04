import copy
import unittest
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from backend.courseplatform import actions


NOW = datetime(2026, 9, 11, 12, tzinfo=timezone.utc)


class Result:
    def __init__(self, row=None, rows=None):
        self.row = copy.deepcopy(row)
        self.rows = copy.deepcopy(rows if rows is not None else ([] if row is None else [row]))

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class SubmissionDatabase:
    def __init__(self):
        snapshot = {
            "version": 1,
            "feedbackPolicy": {
                "releaseMode": "AFTER_REVIEW",
                "showCorrectAnswers": False,
                "showExplanations": False,
            },
            "questions": [{
                "question_id": "Q1",
                "lesson_id": "L1",
                "question_order": 1,
                "question_type": "LONG_TEXT",
                "prompt": "Descreva a solução.",
                "points": 10,
                "correct_answer": "",
                "explanation": "",
                "is_required": True,
                "status": "ACTIVE",
                "options": [],
            }],
        }
        self.snapshot = snapshot
        self.progress = dict(progress_id="P1", student_id="S1", lesson_id="L1", status="TIME_EXCEEDED",
                             enrollment_id="E1",
                             evaluation_status="TIME_EXCEEDED", content_access_status="AVAILABLE", attempt_count=1,
                             submission_duration_minutes=180, feedback_release_mode="AFTER_REVIEW",
                             show_correct_answers=False, show_explanations=False)
        self.attempts = {"A1": dict(attempt_id="A1", progress_id="P1", student_id="S1", lesson_id="L1",
                                   attempt_number=1, status="TIME_EXCEEDED", retry_authorized=False,
                                   deadline_at=NOW - timedelta(days=1), score=None,
                                   assessment_snapshot_json=snapshot)}
        self.reviews = []
        self.grade_changes = []
        self.answers = {"A1": [dict(question_id="Q1", answer_text="Resposta anterior", selected_option_id="")]}
        self.files = {"F1": dict(file_id="F1", attempt_id="A1", student_id="S1", status="ACTIVE", file_name="errado.pdf")}
        self.queries = []

    def execute(self, query, params=()):
        q = " ".join(query.lower().split())
        assert q.count("%s") == len(params), (q, params)
        self.queries.append((q, params))
        latest = max(self.attempts.values(), key=lambda a: a["attempt_number"], default=None)
        if q.startswith("select p.*") or q.startswith("select progress_id from courseplatform.lesson_progress"):
            return Result(self.progress)
        if q.startswith("select 1 from courseplatform.attempts"):
            return Result({"allowed": 1})
        if q.startswith("select p.progress_id"):
            return Result(self.progress)
        if q.startswith("select a.*"):
            row = self.attempts.get(params[0])
            if not row or row["student_id"] != params[1]:
                return Result()
            return Result({**row, "content_access_status": self.progress["content_access_status"]})
        if q.startswith("select * from courseplatform.attempts"):
            return Result(latest if "order by" in q else self.attempts.get(params[0]))
        if q.startswith("select attempt_id from courseplatform.attempts"):
            return Result(latest if latest and latest["attempt_number"] > params[1] else None)
        if q.startswith("select correction_deadline"):
            rows = [r for r in self.reviews if r["attempt_id"] == params[0]]
            return Result(rows[-1] if rows else None)
        if q.startswith("select * from courseplatform.reviews"):
            rows = [r for r in self.reviews if r["attempt_id"] == params[0]]
            return Result(rows[-1] if rows else None)
        if q.startswith("select * from courseplatform.assessment_policy_exceptions"):
            return Result()
        if q.startswith("select title from"):
            return Result({"title": "Trabalho prático"})
        if q.startswith("select question_id, lesson_id"):
            return Result(rows=self.snapshot["questions"])
        if q.startswith("select option_id, question_id"):
            return Result(rows=[])
        if q.startswith("select cv.content_snapshot_json"):
            return Result({"content_snapshot_json": {"lessons": [{
                "lesson_id": "L1",
                "submission_duration_minutes": 180,
                "feedback_release_mode": "AFTER_REVIEW",
                "show_correct_answers": False,
                "show_explanations": False,
                "questions": self.snapshot["questions"],
            }]}})
        if q.startswith("select * from courseplatform.answers"):
            return Result(rows=self.answers.get(params[0], []))
        if q.startswith("select attempt_id from courseplatform.files") or q.startswith("select f.attempt_id"):
            file = self.files.get(params[0])
            return Result(file if file and file["student_id"] == params[1] else None)
        if q.startswith("insert into courseplatform.reviews"):
            row = dict(zip(("review_id", "attempt_id", "reviewer_id", "decision", "score", "comments",
                            "correction_deadline", "unlock_next_lesson", "reviewed_at",
                            "rubric_snapshot_json", "rubric_scores_json", "previous_score",
                            "revision_number", "grade_reason"), params))
            row["rubric_snapshot_json"] = actions.parse_assessment_snapshot(row["rubric_snapshot_json"])
            row["rubric_scores_json"] = actions.parse_assessment_snapshot(row["rubric_scores_json"])
            self.reviews.append(row)
            return Result(row)
        if q.startswith("insert into courseplatform.grade_change_log"):
            row = {
                "grade_change_id": params[0],
                "attempt_id": params[1],
                "progress_id": params[2],
                "review_id": params[4],
                "actor_admin_id": params[5],
                "previous_score": params[6],
                "new_score": params[7],
                "previous_decision": params[8],
                "new_decision": params[9],
                "reason": params[10],
                "rubric_snapshot_json": actions.parse_assessment_snapshot(params[11]),
                "rubric_scores_json": actions.parse_assessment_snapshot(params[12]),
                "created_at": params[13],
            }
            self.grade_changes.append(row)
            return Result()
        if q.startswith("insert into courseplatform.attempts"):
            row = dict(zip(("attempt_id", "progress_id", "student_id", "lesson_id", "attempt_number", "started_at",
                            "deadline_at", "assessment_snapshot_json", "assessment_exception_id", "created_at", "updated_at"), params))
            row["assessment_snapshot_json"] = actions.parse_assessment_snapshot(row["assessment_snapshot_json"])
            row.update(status="IN_PROGRESS", retry_authorized=False)
            self.attempts[row["attempt_id"]] = row
            return Result(row)
        if q.startswith("update courseplatform.attempts"):
            row = self.attempts[params[-1]]
            if "objective_score = %s" in q:
                row.update(status=params[0], submitted_at=params[1], objective_score=params[2])
            elif "score = %s" in q:
                row.update(status=params[0], score=params[1], review_comments=params[4], retry_authorized=params[5])
            else:
                row["retry_authorized"] = False
            return Result(row)
        if q.startswith("update courseplatform.answers set submitted_at"):
            for answer in self.answers.get(params[1], []):
                answer["submitted_at"] = params[0]
            return Result()
        if q.startswith("update courseplatform.answers set is_correct"):
            for answer in self.answers.get(params[-1], []):
                if answer.get("answer_id") == params[3]:
                    answer.update(is_correct=params[0], awarded_points=params[1], submitted_at=params[2])
            return Result()
        if q.startswith("update courseplatform.lesson_progress"):
            if "status = 'in_progress'" in q:
                self.progress.update(status="IN_PROGRESS", evaluation_status="IN_PROGRESS", attempt_count=params[1])
            else:
                self.progress.update(status=params[0], evaluation_status=params[1])
                if "case when %s then 'available'" in q and params[2]:
                    self.progress["content_access_status"] = "AVAILABLE"
            return Result(self.progress)
        if q.startswith("insert into courseplatform.answers"):
            if "select 'ans-'" in q:
                self.answers[params[1]] = copy.deepcopy(self.answers.get(params[3], []))
                return Result()
            row = dict(zip(("answer_id", "attempt_id", "question_id", "answer_text", "selected_option_id"), params))
            self.answers[row["attempt_id"]] = [row]
            return Result(row)
        if q.startswith("insert into courseplatform.files"):
            row = dict(zip(("file_id", "attempt_id", "student_id", "lesson_id", "file_name", "mime_type",
                            "size_bytes", "storage_bucket", "storage_path", "storage_checksum_sha256",
                            "storage_upload_key"), params))
            row.update(drive_file_id="", drive_url="", storage_status="READY")
            row["status"] = "ACTIVE"
            self.files[row["file_id"]] = row
            return Result(row)
        if q.startswith("update courseplatform.files"):
            row = self.files[params[0]]
            row["status"] = "DELETED"
            return Result(row)
        raise AssertionError(f"Unexpected SQL: {q}")

    def commit(self):
        pass


class SubmissionRetryTests(unittest.TestCase):
    def setUp(self):
        self.db = SubmissionDatabase()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)

        @contextmanager
        def connect():
            yield self.db

        replacements = {
            "student_context": lambda p: ({}, {"student_id": "S1"}),
            "student_context_with_conn": lambda conn, p: (
                {"organization_id": "ORG-A"},
                {"student_id": "S1"},
            ),
            "admin_context": lambda p, roles: (
                {"organization_id": "ORG-A"},
                {
                    "admin_id": "ADM1",
                    "role": "ADMIN",
                    "active_organization_id": "ORG-A",
                },
            ),
            "connection": connect,
            "fetch_one": lambda q, p: self.db.execute(q, p).fetchone(),
            "utc_now": lambda: NOW,
            "prepare_assessment_feature_schema": lambda: None,
            "prepare_notification_feature_schema": lambda: None,
            "refresh_enrollment_progress": lambda *a: None,
            "create_student_notification": lambda *a, **k: "N1",
            "dispatch_notification_deliveries": lambda *a: None,
            "audit": lambda *a: None,
            "upload_private_object": lambda *a: None,
        }
        for name, value in replacements.items():
            self.stack.enter_context(patch.object(actions, name, value))

    def authorize(self):
        return actions.admin_authorize_retry({"attemptId": "A1", "correctionDeadline": (NOW + timedelta(days=2)).isoformat(),
                                              "comments": "Envie o documento correto."})

    def assert_error(self, code, fn, payload):
        with self.assertRaises(actions.ApiError) as error:
            fn(payload)
        self.assertEqual(error.exception.code, code)

    def test_return_expired_work_reupload_and_submit_preserves_history(self):
        original = copy.deepcopy(self.db.files["F1"])
        self.db.progress["content_access_status"] = "LOCKED"
        result = self.authorize()["data"]
        self.assertTrue(result["attempt"]["retryAuthorized"])
        self.assertEqual(self.db.progress["content_access_status"], "AVAILABLE")
        started = actions.start_attempt({"lessonId": "L1"})["data"]["attempt"]
        attempt_id = started["attemptId"]
        self.assertEqual(started["attemptNumber"], 2)
        self.assertEqual(started["deadlineAt"], (NOW + timedelta(days=2)).isoformat())
        self.assertFalse(self.db.attempts["A1"]["retry_authorized"])
        self.assertEqual(self.db.answers[attempt_id], self.db.answers["A1"])
        actions.upload_file({"attemptId": attempt_id, "fileName": "correto.pdf", "base64Data": "JVBERi0="})
        actions.save_answer({"attemptId": attempt_id, "questionId": "Q1", "answerText": "Resposta corrigida"})
        submitted = actions.submit_attempt({"attemptId": attempt_id})["data"]["attempt"]
        self.assertEqual(submitted["status"], "UNDER_REVIEW")
        self.assertEqual(self.db.files["F1"], original)
        self.assertEqual(self.db.answers["A1"][0]["answer_text"], "Resposta anterior")
        self.assert_error("ATTEMPT_NOT_EDITABLE", actions.delete_uploaded_file, {"fileId": "F1"})

    def test_correction_decision_authorizes_retry_automatically(self):
        result = actions.admin_review_submission({"attemptId": "A1", "decision": "CORRECTION_REQUIRED",
                    "comments": "Corrigir anexo", "correctionDeadline": (NOW + timedelta(hours=1)).isoformat()})
        self.assertTrue(result["data"]["attempt"]["retryAuthorized"])
        self.assertIsNone(result["data"]["attempt"]["score"])

    def test_return_without_authorization_does_not_open_uploads(self):
        actions.admin_review_submission({"attemptId": "A1", "decision": "CORRECTION_REQUIRED", "authorizeRetry": False})
        self.assert_error("RETRY_NOT_AUTHORIZED", actions.start_attempt, {"lessonId": "L1"})

    def test_no_retry_without_admin_permission(self):
        for status in ("FAILED", "TIME_EXCEEDED", "CORRECTION_REQUIRED"):
            self.db.progress.update(status=status, evaluation_status=status)
            self.assert_error("RETRY_NOT_AUTHORIZED", actions.start_attempt, {"lessonId": "L1"})

    def test_invalid_or_expired_deadline_is_rejected_without_writes(self):
        for deadline in ("", "invalid", (NOW - timedelta(seconds=1)).isoformat(), NOW.isoformat()):
            self.assert_error("INVALID_CORRECTION_DEADLINE", actions.admin_authorize_retry,
                              {"attemptId": "A1", "correctionDeadline": deadline})
        self.assertFalse(self.db.reviews)

    def test_expired_retry_permission_cannot_start(self):
        self.authorize()
        with patch.object(actions, "utc_now", return_value=NOW + timedelta(days=3)):
            self.assert_error("RETRY_DEADLINE_EXPIRED", actions.start_attempt, {"lessonId": "L1"})

    def test_revoked_permission_cannot_start(self):
        self.authorize()
        actions.admin_authorize_retry({"attemptId": "A1", "authorized": False})
        self.assert_error("RETRY_NOT_AUTHORIZED", actions.start_attempt, {"lessonId": "L1"})

    def test_consumed_permission_cannot_be_revoked_on_old_attempt(self):
        self.authorize()
        actions.start_attempt({"lessonId": "L1"})
        self.assert_error("ATTEMPT_SUPERSEDED", actions.admin_authorize_retry, {"attemptId": "A1", "authorized": False})

    def test_retry_management_requires_staff_authorization(self):
        with patch.object(actions, "admin_context", side_effect=actions.ApiError("FORBIDDEN", "Sem permissão")) as auth:
            self.assert_error("FORBIDDEN", actions.admin_authorize_retry,
                              {"attemptId": "A1", "correctionDeadline": (NOW + timedelta(days=1)).isoformat()})
        self.assertEqual(auth.call_args.args[1], {"OWNER", "ADMIN", "REVIEWER"})
        self.assertFalse(self.db.reviews)

    def test_duplicate_start_reuses_active_attempt(self):
        self.authorize()
        first = actions.start_attempt({"lessonId": "L1"})["data"]["attempt"]
        second = actions.start_attempt({"lessonId": "L1"})["data"]["attempt"]
        self.assertEqual(first["attemptId"], second["attemptId"])
        self.assertEqual(len(self.db.attempts), 2)

    def test_old_attempt_cannot_be_returned_after_new_start(self):
        self.authorize()
        actions.start_attempt({"lessonId": "L1"})
        self.assert_error("ATTEMPT_SUPERSEDED", actions.admin_authorize_retry,
                          {"attemptId": "A1", "correctionDeadline": (NOW + timedelta(days=4)).isoformat()})

    def test_expired_attempt_cannot_upload_save_delete_or_submit(self):
        self.db.attempts["A1"]["status"] = "IN_PROGRESS"
        for fn, payload in ((actions.upload_file, {"attemptId": "A1", "fileName": "late.pdf"}),
                            (actions.save_answer, {"attemptId": "A1", "questionId": "Q1"}),
                            (actions.delete_uploaded_file, {"fileId": "F1"}),
                            (actions.submit_attempt, {"attemptId": "A1"})):
            self.assert_error("ATTEMPT_TIME_EXCEEDED", fn, payload)

    def test_foreign_attempt_cannot_upload(self):
        self.db.attempts["A1"].update(status="IN_PROGRESS", student_id="OTHER", deadline_at=NOW + timedelta(days=1))
        self.assert_error("ATTEMPT_NOT_EDITABLE", actions.upload_file, {"attemptId": "A1", "fileName": "other.pdf"})

    def test_first_attempt_does_not_need_retry_permission(self):
        self.db.attempts.clear()
        self.db.progress.update(status="NOT_STARTED", evaluation_status="NOT_STARTED", attempt_count=0)
        result = actions.start_attempt({"lessonId": "L1"})["data"]["attempt"]
        self.assertEqual(result["attemptNumber"], 1)

    def test_controlled_rubric_review_calculates_score_and_freezes_history(self):
        frozen_rubric = {"criteria": [
            {"criterionId": "analysis", "title": "Análise", "maxPoints": 40},
            {"criterionId": "evidence", "title": "Evidências", "maxPoints": 60},
        ]}
        self.db.attempts["A1"]["assessment_snapshot_json"] = {
            **copy.deepcopy(self.db.snapshot),
            "rubric": copy.deepcopy(frozen_rubric),
        }
        result = actions.admin_review_submission({
            "attemptId": "A1",
            "decision": "APPROVED",
            "score": 80,
            "comments": "Revisão controlada da rubrica versionada.",
            "rubricScores": [
                {"criterionId": "analysis", "awardedPoints": 30, "comments": "Boa análise."},
                {"criterionId": "evidence", "awardedPoints": 50, "comments": "Evidências adequadas."},
            ],
        })["data"]

        self.assertEqual(80, result["attempt"]["score"])
        self.assertEqual(80, self.db.grade_changes[0]["new_score"])
        review_rubric = self.db.reviews[0]["rubric_snapshot_json"]
        self.assertEqual(100, review_rubric["totalPoints"])
        self.assertEqual(["analysis", "evidence"], [item["criterionId"] for item in review_rubric["criteria"]])
        self.assertEqual(review_rubric, self.db.grade_changes[0]["rubric_snapshot_json"])

        self.db.snapshot["rubric"] = {
            "criteria": [{"criterionId": "new", "title": "Rubrica futura", "maxPoints": 100}],
        }
        self.assertEqual("Análise", review_rubric["criteria"][0]["title"])
        self.assertEqual("Análise", self.db.grade_changes[0]["rubric_snapshot_json"]["criteria"][0]["title"])


if __name__ == "__main__":
    unittest.main()
