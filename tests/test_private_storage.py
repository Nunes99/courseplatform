import base64
import hashlib
import importlib
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from backend.courseplatform import actions, storage


ROOT = Path(__file__).resolve().parents[1]
PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF"
PDF_BASE64 = base64.b64encode(PDF_BYTES).decode("ascii")
SETTINGS = SimpleNamespace(
    submission_file_max_bytes=10 * 1024 * 1024,
    payment_receipt_max_bytes=5 * 1024 * 1024,
    storage_legacy_read_max_bytes=25 * 1024 * 1024,
    supabase_submission_bucket="courseplatform-submissions",
    supabase_payment_receipt_bucket="courseplatform-payment-receipts",
)


class Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class UploadConnection:
    def __init__(self):
        self.queries = []

    def execute(self, query, params=()):
        normalized = " ".join(query.lower().split())
        self.queries.append((normalized, params))
        if normalized.startswith("insert into courseplatform.files"):
            row = {
                "file_id": params[0],
                "attempt_id": params[1],
                "student_id": params[2],
                "lesson_id": params[3],
                "file_name": params[4],
                "mime_type": params[5],
                "size_bytes": params[6],
                "drive_file_id": "",
                "drive_url": "",
                "storage_bucket": params[7],
                "storage_path": params[8],
                "storage_checksum_sha256": params[9],
                "storage_status": "READY",
                "storage_upload_key": params[10],
                "status": "ACTIVE",
            }
            return Result(row)
        raise AssertionError(normalized)

    def commit(self):
        return None


class ReceiptConnection:
    def __init__(self):
        self.queries = []

    def execute(self, query, params=()):
        normalized = " ".join(query.lower().split())
        self.queries.append((normalized, params))
        if normalized.startswith("update courseplatform.certificate_requests"):
            return Result({
                "request_id": params[6],
                "student_id": params[7],
                "request_type": "PROFESSIONAL",
                "status": "PAYMENT_SUBMITTED",
                "payment_receipt_name": params[0],
                "payment_receipt_url": "",
                "payment_receipt_mime_type": params[1],
                "payment_receipt_bucket": params[2],
                "payment_receipt_path": params[3],
                "payment_receipt_checksum_sha256": params[4],
                "payment_receipt_size_bytes": params[5],
                "payment_receipt_storage_status": "READY",
            })
        raise AssertionError(normalized)

    def commit(self):
        return None


class StorageValidationTests(unittest.TestCase):
    def test_pdf_signature_and_decoded_size_are_used(self):
        with patch.object(storage, "get_settings", return_value=SETTINGS):
            upload = storage.validate_upload(PDF_BASE64, "trabalho.pdf", "application/pdf", purpose="SUBMISSION")
        self.assertEqual(PDF_BYTES, upload.content)
        self.assertEqual(len(PDF_BYTES), upload.size_bytes)
        self.assertEqual(hashlib.sha256(PDF_BYTES).hexdigest(), upload.checksum_sha256)

    def test_claimed_mime_cannot_disguise_content(self):
        disguised = base64.b64encode(b"not a pdf").decode("ascii")
        with patch.object(storage, "get_settings", return_value=SETTINGS):
            with self.assertRaises(storage.StorageError) as raised:
                storage.validate_upload(disguised, "trabalho.pdf", "application/pdf", purpose="SUBMISSION")
        self.assertEqual("UNSUPPORTED_FILE_TYPE", raised.exception.code)

    def test_receipts_reject_office_documents(self):
        legacy_word = base64.b64encode(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1payload").decode("ascii")
        with patch.object(storage, "get_settings", return_value=SETTINGS):
            with self.assertRaises(storage.StorageError) as raised:
                storage.validate_upload(legacy_word, "receipt.doc", "application/msword", purpose="PAYMENT_RECEIPT")
        self.assertEqual("UNSUPPORTED_FILE_TYPE", raised.exception.code)

    def test_storage_upload_requires_server_configuration(self):
        missing = SimpleNamespace(
            supabase_url="", supabase_service_role_key="", storage_timeout_seconds=1
        )
        with patch.object(storage, "get_settings", return_value=missing):
            with self.assertRaises(storage.StorageError) as raised:
                storage.upload_private_object(
                    "private", "path/content.pdf",
                    storage.ValidatedUpload(PDF_BYTES, "a.pdf", "application/pdf", len(PDF_BYTES), "0" * 64),
                )
        self.assertEqual("PRIVATE_STORAGE_NOT_CONFIGURED", raised.exception.code)

    def test_new_secret_key_is_sent_only_as_api_key(self):
        headers = storage.storage_service_headers(SimpleNamespace(
            supabase_secret_key="sb_secret_server_test",
            supabase_service_role_key="legacy-service-key",
        ))
        self.assertEqual("sb_secret_server_test", headers["apikey"])
        self.assertNotIn("Authorization", headers)

    def test_legacy_service_role_key_remains_supported(self):
        headers = storage.storage_service_headers(SimpleNamespace(
            supabase_secret_key="",
            supabase_service_role_key="legacy-service-key",
        ))
        self.assertEqual("legacy-service-key", headers["apikey"])
        self.assertEqual("Bearer legacy-service-key", headers["Authorization"])

    def test_object_path_contains_no_original_filename_or_traversal(self):
        with patch.object(storage, "get_settings", return_value=SETTINGS):
            upload = storage.validate_upload(PDF_BASE64, "../../private.pdf", "application/pdf", purpose="SUBMISSION")
        path = storage.storage_object_path("submission", "S/1", "A../1", upload)
        self.assertNotIn("..", path)
        self.assertNotIn("private", path)
        self.assertTrue(path.endswith("/content.pdf"))


class PrivateStorageActionTests(unittest.TestCase):
    def test_new_submission_stores_only_private_metadata(self):
        database = UploadConnection()

        @contextmanager
        def connect():
            yield database

        with (
            patch.object(actions, "student_context", return_value=({}, {"student_id": "S1"})),
            patch.object(actions, "prepare_assessment_feature_schema"),
            patch.object(actions, "editable_attempt", return_value={"attempt_id": "A1", "lesson_id": "L1"}),
            patch.object(actions, "connection", connect),
            patch.object(actions, "get_settings", return_value=SETTINGS),
            patch.object(storage, "get_settings", return_value=SETTINGS),
            patch.object(actions, "upload_private_object") as upload_object,
            patch.object(actions, "audit"),
        ):
            result = actions.upload_file({
                "attemptId": "A1",
                "fileName": "trabalho.pdf",
                "mimeType": "application/pdf",
                "base64Data": PDF_BASE64,
            })["data"]["file"]

        upload_object.assert_called_once()
        self.assertEqual(len(PDF_BYTES), result["sizeBytes"])
        self.assertEqual("", result["driveUrl"])
        self.assertEqual("READY", result["storageStatus"])
        self.assertEqual(f"/api/files/{result['fileId']}/content", result["contentUrl"])
        insert_query = next(query for query, _ in database.queries if query.startswith("insert into courseplatform.files"))
        self.assertIn("on conflict (storage_upload_key)", insert_query)

    def test_payment_receipt_stores_private_metadata_without_data_url(self):
        database = ReceiptConnection()
        request = {
            "request_id": "R1", "student_id": "S1", "request_type": "PROFESSIONAL",
            "status": "REQUESTED", "certificate_id": None,
        }

        @contextmanager
        def connect():
            yield database

        with (
            patch.object(actions, "student_context", return_value=({}, {"student_id": "S1"})),
            patch.object(actions, "fetch_one", return_value=request),
            patch.object(actions, "connection", connect),
            patch.object(actions, "ensure_certificate_feature_schema"),
            patch.object(actions, "get_settings", return_value=SETTINGS),
            patch.object(storage, "get_settings", return_value=SETTINGS),
            patch.object(actions, "upload_private_object") as upload_object,
            patch.object(actions, "audit"),
        ):
            result = actions.submit_professional_certificate_payment({
                "requestId": "R1",
                "receiptFileName": "comprovativo.pdf",
                "receiptMimeType": "application/pdf",
                "receiptBase64": PDF_BASE64,
            })["data"]["request"]

        upload_object.assert_called_once()
        self.assertEqual("/api/certificate-requests/R1/receipt", result["paymentReceiptUrl"])
        self.assertEqual(len(PDF_BYTES), result["paymentReceiptSizeBytes"])
        self.assertNotIn("base64", str(result).lower())

    def test_serializers_never_expose_legacy_base64(self):
        file_payload = actions.public_file({
            "file_id": "F1", "drive_url": f"data:application/pdf;base64,{PDF_BASE64}", "status": "ACTIVE"
        })
        receipt_payload = actions.public_certificate_request({
            "request_id": "R1", "payment_receipt_url": f"data:application/pdf;base64,{PDF_BASE64}"
        })
        self.assertEqual("", file_payload["driveUrl"])
        self.assertEqual("/api/files/F1/content", file_payload["contentUrl"])
        self.assertEqual("/api/certificate-requests/R1/receipt", receipt_payload["paymentReceiptUrl"])
        self.assertNotIn("base64", str(file_payload).lower())
        self.assertNotIn("base64", str(receipt_payload).lower())

    def test_serializers_do_not_expose_legacy_external_urls(self):
        file_payload = actions.public_file({
            "file_id": "F1", "drive_url": "https://files.example.invalid/private.pdf", "status": "ACTIVE"
        })
        receipt_payload = actions.public_certificate_request({
            "request_id": "R1", "payment_receipt_url": "https://files.example.invalid/receipt.pdf"
        })
        self.assertEqual("", file_payload["driveUrl"])
        self.assertEqual("/api/files/F1/content", file_payload["contentUrl"])
        self.assertEqual("/api/certificate-requests/R1/receipt", receipt_payload["paymentReceiptUrl"])
        self.assertNotIn("example.invalid", str(file_payload))
        self.assertNotIn("example.invalid", str(receipt_payload))

    def test_receipt_ownership_is_checked_before_content_validation(self):
        with (
            patch.object(actions, "student_context", return_value=({}, {"student_id": "S1"})),
            patch.object(actions, "fetch_one", return_value=None),
            patch.object(actions, "validate_upload") as validate,
        ):
            with self.assertRaises(actions.ApiError) as raised:
                actions.submit_professional_certificate_payment({
                    "requestId": "R-OTHER", "receiptFileName": "receipt.pdf"
                })
        self.assertEqual("CERTIFICATE_REQUEST_NOT_FOUND", raised.exception.code)
        validate.assert_not_called()

    def test_student_cannot_download_another_students_file(self):
        with (
            patch.object(actions, "student_context", return_value=({}, {"student_id": "S1"})),
            patch.object(actions, "fetch_one", return_value=None),
            patch.object(actions, "download_private_object") as download,
        ):
            with self.assertRaises(actions.ApiError) as raised:
                actions.submission_file_download_payload({"fileId": "F-OTHER", "sessionToken": "session"})
        self.assertEqual("FILE_NOT_FOUND", raised.exception.code)
        download.assert_not_called()

    def test_legacy_base64_remains_downloadable_after_authorization(self):
        row = {
            "file_id": "F1",
            "student_id": "S1",
            "file_name": "historico.pdf",
            "mime_type": "application/pdf",
            "drive_url": f"data:application/pdf;base64,{PDF_BASE64}",
            "size_bytes": len(PDF_BASE64),
            "status": "ACTIVE",
        }
        with (
            patch.object(actions, "student_context", return_value=({}, {"student_id": "S1"})),
            patch.object(actions, "fetch_one", return_value=row),
            patch.object(actions, "get_settings", return_value=SETTINGS),
        ):
            result = actions.submission_file_download_payload({"fileId": "F1", "sessionToken": "session"})
        self.assertEqual(PDF_BYTES, result["content"])
        self.assertEqual("application/pdf", result["mimeType"])

    def test_checksum_mismatch_blocks_download(self):
        row = {
            "file_id": "F1", "student_id": "S1", "file_name": "stored.pdf",
            "mime_type": "application/pdf", "storage_bucket": "private", "storage_path": "x",
            "storage_status": "READY", "storage_checksum_sha256": "0" * 64, "status": "ACTIVE",
        }
        with (
            patch.object(actions, "student_context", return_value=({}, {"student_id": "S1"})),
            patch.object(actions, "fetch_one", return_value=row),
            patch.object(actions, "get_settings", return_value=SETTINGS),
            patch.object(actions, "download_private_object", return_value=PDF_BYTES),
        ):
            with self.assertRaises(actions.ApiError) as raised:
                actions.submission_file_download_payload({"fileId": "F1", "sessionToken": "session"})
        self.assertEqual("FILE_INTEGRITY_ERROR", raised.exception.code)


class PrivateStorageHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = importlib.import_module("backend.courseplatform.app")
        cls.client = TestClient(cls.api.app)

    def test_binary_endpoint_uses_private_no_store_headers(self):
        result = {"content": PDF_BYTES, "fileName": "trabalho.pdf", "mimeType": "application/pdf"}
        with patch.object(self.api, "submission_file_download_payload", return_value=result) as resolver:
            response = self.client.get("/api/files/F1/content", headers={"x-session-token": "test-session"})
        self.assertEqual(200, response.status_code)
        self.assertEqual(PDF_BYTES, response.content)
        self.assertEqual("private, no-store", response.headers["cache-control"])
        self.assertEqual("nosniff", response.headers["x-content-type-options"])
        self.assertEqual("test-session", resolver.call_args.args[0]["sessionToken"])

    def test_download_disposition_is_explicit(self):
        result = {"content": PDF_BYTES, "fileName": "trabalho.pdf", "mimeType": "application/pdf"}
        with patch.object(self.api, "submission_file_download_payload", return_value=result):
            response = self.client.get(
                "/api/files/F1/content?download=1", headers={"x-admin-token": "test-admin"}
            )
        self.assertTrue(response.headers["content-disposition"].startswith("attachment;"))

    def test_missing_session_is_reported_as_unauthorized(self):
        with patch.object(
            self.api,
            "submission_file_download_payload",
            side_effect=actions.ApiError("SESSION_REQUIRED", "Inicie sessão."),
        ):
            response = self.client.get("/api/files/F1/content")
        self.assertEqual(401, response.status_code)
        self.assertEqual("SESSION_REQUIRED", response.json()["error"]["code"])

    def test_expired_session_is_reported_as_unauthorized(self):
        with patch.object(
            self.api,
            "submission_file_download_payload",
            side_effect=actions.ApiError("SESSION_EXPIRED", "Sessão expirada."),
        ):
            response = self.client.get("/api/files/F1/content", headers={"x-session-token": "expired"})
        self.assertEqual(401, response.status_code)

    def test_forbidden_admin_role_is_reported_as_forbidden(self):
        with patch.object(
            self.api,
            "certificate_receipt_download_payload",
            side_effect=actions.ApiError("FORBIDDEN", "Sem permissão."),
        ):
            response = self.client.get(
                "/api/certificate-requests/R1/receipt", headers={"x-admin-token": "reviewer"}
            )
        self.assertEqual(403, response.status_code)


class PrivateStorageMigrationTests(unittest.TestCase):
    def test_migration_is_additive_private_and_versioned(self):
        migration = ROOT / "supabase" / "migrations" / "20260914100000_private_submission_storage.sql"
        sql = migration.read_text(encoding="utf-8").lower()
        self.assertIn("add column if not exists storage_bucket", sql)
        self.assertIn("add column if not exists payment_receipt_bucket", sql)
        self.assertIn("courseplatform-submissions", sql)
        self.assertIn("courseplatform-payment-receipts", sql)
        self.assertIn("public, anon, authenticated", sql)
        self.assertIn("20260914100000", sql)
        self.assertNotIn("drop column", sql)

    def test_backfill_is_dry_run_by_default_and_preserves_legacy_source(self):
        source = (ROOT / "scripts" / "backfill_private_storage.py").read_text(encoding="utf-8")
        self.assertIn('parser.add_argument("--apply", action="store_true"', source)
        self.assertNotIn("set drive_url = ''", source.lower())
        self.assertNotIn("set payment_receipt_url = ''", source.lower())
        self.assertIn("SUBMISSION_FILE_STORAGE_BACKFILLED", source)
        self.assertIn("PAYMENT_RECEIPT_STORAGE_BACKFILLED", source)

    def test_frontend_requests_private_files_with_session_headers(self):
        api_source = (ROOT / "public" / "api.js").read_text(encoding="utf-8")
        student_source = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
        admin_source = (ROOT / "public" / "admin.js").read_text(encoding="utf-8")
        self.assertIn("studentFileContent", api_source)
        self.assertIn("'x-session-token': this.studentToken()", api_source)
        self.assertIn("adminCertificateReceipt", api_source)
        self.assertIn("data-download-student-file", student_source)
        self.assertIn("data-download-protected-admin-file", admin_source)
        for source in (api_source, student_source, admin_source):
            self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY", source)
            self.assertNotIn("SUPABASE_SECRET_KEY", source)


if __name__ == "__main__":
    unittest.main()
