import copy
import json
import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from backend.courseplatform import actions


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "20260929120000_complete_stage11_certification_contract.sql"
NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


class Result:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class SnapshotDB:
    def execute(self, sql, params=()):
        normalized = " ".join(sql.split()).lower()
        self.assert_parameter_count(normalized, params)
        if "from courseplatform.courses" in normalized:
            return Result([{
                "course_id": "C1", "title": "Título atual", "description": "Descrição",
                "total_hours": 24, "passing_score": 70,
            }])
        if "from courseplatform.certificate_settings" in normalized:
            return Result([{
                "course_id": "C1",
                "congratulations_message": "Parabéns",
                "survey_questions_json": [{"id": "q1", "prompt": "Qualidade?", "options": ["Boa"]}],
                "professional_price": "1500",
                "certificate_profile_json": {
                    "issuerName": "Entidade original",
                    "certifiedContents": "Conteúdo A\nConteúdo B",
                    "participation": {"enabled": True, "maxDownloads": 2},
                },
            }])
        raise AssertionError(normalized)

    @staticmethod
    def assert_parameter_count(sql, params):
        assert sql.count("%s") == len(params), (sql, params)


class ReissueDB:
    def __init__(self):
        self.current = {
            "certificate_id": "CERT-OLD", "student_id": "S1", "course_id": "C1",
            "enrollment_id": "E1", "offering_id": "O1", "course_version_id": "V1",
            "certificate_number": "LSS-2026-OLD", "verification_code": "OLD-CODE",
            "issue_date": NOW, "final_score": 88, "status": "ISSUED",
            "certificate_type": "PROFESSIONAL", "recognition_level": "CONTENT_DETAILED",
            "content_summary": "Conteúdo antigo", "professional_request_id": "R1",
            "download_count": 2, "max_downloads": 5, "payment_status": "CONFIRMED",
            "approved_by": "A0", "approved_at": NOW,
            "template_snapshot_json": {"version": 1, "profile": {"issuerName": "Original"}},
            "document_snapshot_version": 1, "generation_revision": 1,
            "student_name": "Estudante Original", "course_title": "Curso Original",
        }
        self.original_snapshot = copy.deepcopy(self.current["template_snapshot_json"])
        self.new = None
        self.request_certificate_id = "CERT-OLD"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def commit(self):
        return None

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split()).lower()
        assert normalized.count("%s") == len(params), (normalized, params)
        if normalized.startswith("select cert.*"):
            return Result([self.current])
        if normalized.startswith("select certificate_id") and "supersedes_certificate_id" in normalized:
            return Result()
        if normalized.startswith("select * from courseplatform.course_versions"):
            return Result([{"course_version_id": "V1", "course_id": "C1", "title": "Versão publicada", "total_hours": 24}])
        if normalized.startswith("insert into courseplatform.certificates"):
            self.new = {
                "certificate_id": params[0], "student_id": params[1], "course_id": params[2],
                "enrollment_id": params[3], "offering_id": params[4], "course_version_id": params[5],
                "certificate_number": params[6], "verification_code": params[7], "issue_date": params[8],
                "final_score": params[9], "status": params[10], "certificate_type": params[11],
                "recognition_level": params[12], "content_summary": params[13],
                "professional_request_id": params[14], "max_downloads": params[15],
                "payment_status": params[16], "template_snapshot_json": json.loads(params[20]),
                "document_snapshot_version": 2, "document_snapshot_hash": params[21],
                "generation_revision": params[22], "supersedes_certificate_id": params[23],
                "reissued_by": params[24], "reissued_at": NOW,
                "student_name": self.current["student_name"], "course_title": self.current["course_title"],
            }
            return Result([self.new])
        if normalized.startswith("update courseplatform.certificates"):
            self.current["status"] = "SUPERSEDED"
            self.current["status_note"] = params[0]
            return Result([self.current])
        if normalized.startswith("update courseplatform.certificate_requests"):
            self.request_certificate_id = params[0]
            return Result()
        raise AssertionError(normalized)


class SurveyRequestDB:
    def __init__(self):
        self.response = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def commit(self):
        return None

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split()).lower()
        assert normalized.count("%s") == len(params), (normalized, params)
        if normalized.startswith("select * from courseplatform.courses"):
            return Result([{"course_id": "C1", "title": "Curso"}])
        if normalized.startswith("select * from courseplatform.certificate_settings"):
            return Result([{"course_id": "C1"}])
        if normalized.startswith("select cr.*"):
            return Result()
        if normalized.startswith("insert into courseplatform.certificate_requests"):
            return Result([{
                "request_id": params[0], "student_id": params[1], "course_id": params[2],
                "enrollment_id": params[3], "offering_id": params[4], "course_version_id": params[5],
                "request_type": "PROFESSIONAL", "status": params[6],
            }])
        if normalized.startswith("insert into courseplatform.certificate_survey_responses"):
            self.response = {
                "response_id": params[0], "request_id": params[1],
                "questions": json.loads(params[7]), "answers": json.loads(params[8]),
            }
            return Result([{"response_id": params[0]}])
        raise AssertionError(normalized)


class Stage11CertificationContractTests(unittest.TestCase):
    def test_snapshot_v2_freezes_document_and_hash(self):
        snapshot = actions.certificate_template_snapshot(
            SnapshotDB(), "C1", "PROFESSIONAL",
            {"course_version_id": "V1", "title": "Título publicado", "total_hours": 20, "passing_score": 75},
            certificate_data={
                "certificateNumber": "LSS-2026-ABC", "verificationCode": "CODEABC",
                "issueDate": NOW.isoformat(), "finalScore": 91, "maxDownloads": 5,
                "paymentStatus": "CONFIRMED",
            },
            student={"student_id": "S1", "full_name": "Nome emitido"},
            content_summary="Conteúdo versionado",
        )
        self.assertEqual(snapshot["version"], 2)
        self.assertEqual(snapshot["document"]["recipient"]["fullName"], "Nome emitido")
        self.assertEqual(snapshot["document"]["course"]["title"], "Título publicado")
        self.assertEqual(snapshot["document"]["course"]["hours"], 20.0)
        self.assertEqual(snapshot["document"]["course"]["contentSummary"], "Conteúdo versionado")
        self.assertEqual(len(actions.certificate_snapshot_hash(snapshot)), 64)

        public = actions.public_certificate({
            "certificate_id": "CERT1", "certificate_number": "LIVE", "verification_code": "LIVE",
            "issue_date": NOW, "final_score": 1, "status": "ISSUED",
            "template_snapshot_json": snapshot, "student_name": "Nome alterado", "course_title": "Curso alterado",
        })
        self.assertEqual(public["studentName"], "Nome emitido")
        self.assertEqual(public["courseTitle"], "Título publicado")
        self.assertEqual(public["certificateNumber"], "LSS-2026-ABC")
        self.assertEqual(public["finalScore"], 91.0)
        payload = actions.certificate_document_payload(
            {
                "certificate_id": "CERT1", "status": "ISSUED", "template_snapshot_json": snapshot,
                "document_snapshot_hash": actions.certificate_snapshot_hash(snapshot),
            },
            snapshot,
            "https://example.test/verify",
        )
        self.assertEqual(payload["pdfData"]["student_name"], public["studentName"])
        self.assertEqual(payload["pdfData"]["course_title"], public["courseTitle"])
        with self.assertRaises(actions.ApiError) as error:
            actions.certificate_document_payload(
                {"certificate_id": "CERT1", "document_snapshot_hash": "0" * 64},
                snapshot,
                "https://example.test/verify",
            )
        self.assertEqual(error.exception.code, "CERTIFICATE_INTEGRITY_FAILED")

    def test_financial_contract_omits_survey_answers_by_default(self):
        row = {"request_id": "R1", "survey_answers_json": {"Pergunta": "Resposta"}}
        self.assertNotIn("surveyAnswers", actions.public_certificate_request(row))
        self.assertEqual(
            actions.public_certificate_request(row, include_survey_answers=True)["surveyAnswers"],
            {"Pergunta": "Resposta"},
        )

    def test_professional_request_writes_survey_to_its_own_domain(self):
        db = SurveyRequestDB()
        stack = ExitStack()
        self.addCleanup(stack.close)
        enrollment = {
            "enrollment_id": "E1", "offering_id": "O1", "course_version_id": "V1",
            "student_id": "S1", "course_id": "C1",
        }
        for name, value in {
            "connection": db,
            "student_context": ({}, {"student_id": "S1", "full_name": "Estudante"}),
            "ensure_simple_certificate": (None, enrollment, {"course_id": "C1"}, True),
            "certificate_settings_payload": {
                "certificateProfile": {"printAccess": "paid"},
                "surveyQuestions": [{"id": "q1", "prompt": "Qualidade?", "options": ["Boa"], "required": True}],
            },
            "generate_id": "GENERATED",
            "audit": None,
        }.items():
            stack.enter_context(patch.object(actions, name, return_value=value))

        result = actions.request_professional_certificate({
            "courseId": "C1", "enrollmentId": "E1", "surveyAnswers": {"Qualidade?": "Boa"},
        })["data"]

        self.assertEqual(result["request"]["requestId"], "GENERATED")
        self.assertNotIn("surveyAnswers", result["request"])
        self.assertEqual(db.response["request_id"], "GENERATED")
        self.assertEqual(db.response["answers"], {"Qualidade?": "Boa"})

    def test_public_verification_rejects_tampered_snapshot(self):
        snapshot = {"version": 2, "document": {"recipient": {"fullName": "Nome"}}}
        row = {
            "certificate_id": "CERT1", "certificate_number": "NUMBER", "verification_code": "CODE",
            "issue_date": NOW, "status": "ISSUED", "template_snapshot_json": snapshot,
            "document_snapshot_hash": "0" * 64, "full_name": "Nome", "title": "Curso",
        }
        with patch.object(actions, "fetch_one", return_value=row):
            result = actions.verify_certificate({"code": "CODE"})["data"]
        self.assertFalse(result["valid"])
        self.assertEqual(result["certificate"]["integrityStatus"], "INVALID")

    def test_reissue_preserves_original_and_creates_audited_revision(self):
        db = ReissueDB()
        snapshot = {
            "version": 2,
            "document": {
                "recipient": {"fullName": "Estudante Original"},
                "course": {"title": "Versão publicada", "hours": 24},
                "credential": {"certificateNumber": "LSS-2026-NEW", "verificationCode": "NEW-CODE"},
            },
            "profile": {"issuerName": "Nova identidade"},
        }
        stack = ExitStack()
        self.addCleanup(stack.close)
        for name, value in {
            "connection": db,
            "admin_context": ({}, {"admin_id": "ADMIN1", "role": "OWNER"}),
            "ensure_certificate_feature_schema": None,
            "certificate_content_summary": "Conteúdo versionado",
            "certificate_template_snapshot": snapshot,
            "certificate_snapshot_hash": "a" * 64,
            "certificate_number": "LSS-2026-NEW",
            "certificate_verification_code": "NEW-CODE",
            "generate_id": "CERT-NEW",
            "utc_now": NOW,
            "audit": None,
        }.items():
            stack.enter_context(patch.object(actions, name, return_value=value))

        result = actions.admin_refresh_certificate_format({
            "certificateId": "CERT-OLD", "reason": "Correção institucional",
        })["data"]

        self.assertEqual(result["certificate"]["certificateId"], "CERT-NEW")
        self.assertEqual(db.current["status"], "SUPERSEDED")
        self.assertEqual(db.current["template_snapshot_json"], db.original_snapshot)
        self.assertEqual(db.new["supersedes_certificate_id"], "CERT-OLD")
        self.assertEqual(db.new["generation_revision"], 2)
        self.assertEqual(db.request_certificate_id, "CERT-NEW")

    def test_migration_is_additive_and_frontend_has_no_bulk_reissue(self):
        sql = MIGRATION.read_text(encoding="utf-8").lower()
        self.assertIn("document_snapshot_hash", sql)
        self.assertIn("supersedes_certificate_id", sql)
        self.assertIn("create table if not exists courseplatform.certificate_survey_responses", sql)
        self.assertIn("from courseplatform.certificate_requests cr", sql)
        self.assertIn("on conflict (request_id) do nothing", sql)
        self.assertIn("revoke all privileges on courseplatform.certificate_survey_responses", sql)
        self.assertIn("on delete restrict", sql)
        self.assertIn("20260929120000", sql)
        self.assertNotIn("drop table", sql)
        admin_js = (ROOT / "public" / "admin.js").read_text(encoding="utf-8")
        self.assertNotIn("refreshCertificateFormatAll", admin_js)
        self.assertIn("O documento atual será preservado", admin_js)


if __name__ == "__main__":
    unittest.main()
