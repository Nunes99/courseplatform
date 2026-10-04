import unittest
from contextlib import ExitStack
from unittest.mock import patch

from backend.courseplatform import actions


class Result:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class RecordingConnection:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        normalized = " ".join(query.split()).lower()
        self.queries.append((normalized, params))
        if normalized.startswith("select cr.*, s.full_name"):
            return Result(rows=self.rows)
        return Result()

    def commit(self):
        return None


class MultiTenantPaymentMutationTests(unittest.TestCase):
    def setUp(self):
        self.db = RecordingConnection()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(actions, "connection", return_value=self.db))
        self.stack.enter_context(patch.object(actions, "ensure_certificate_feature_schema"))
        self.stack.enter_context(patch.object(actions, "audit"))

    def _student_a(self):
        return patch.object(
            actions,
            "student_context_with_conn",
            return_value=({"organization_id": "ORG-A"}, {"student_id": "STUDENT-A"}),
        )

    def _admin_a(self):
        return patch.object(
            actions,
            "admin_context_with_conn",
            return_value=(
                {"organization_id": "ORG-A"},
                {
                    "admin_id": "ADMIN-A",
                    "role": "ADMIN",
                    "active_organization_id": "ORG-A",
                },
            ),
        )

    def assert_not_found(self, callback, code="CERTIFICATE_REQUEST_NOT_FOUND"):
        with self.assertRaises(actions.ApiError) as raised:
            callback()
        self.assertEqual(code, raised.exception.code)

    def test_student_a_cannot_upload_receipt_for_request_in_organization_b(self):
        with self._student_a(), patch.object(actions, "validate_upload") as validate, patch.object(
            actions, "upload_private_object"
        ) as upload:
            self.assert_not_found(
                lambda: actions.submit_professional_certificate_payment(
                    {"requestId": "REQUEST-B", "receiptFileName": "receipt.pdf"}
                )
            )

        validate.assert_not_called()
        upload.assert_not_called()
        query, params = self.db.queries[0]
        self.assertIn("c.organization_id = %s", query)
        self.assertEqual("ORG-A", params[-1])
        self.assertFalse(any(query.startswith("update ") for query, _ in self.db.queries))

    def test_admin_a_cannot_review_request_in_organization_b(self):
        with self._admin_a():
            self.assert_not_found(
                lambda: actions.admin_review_certificate_request(
                    {"requestId": "REQUEST-B", "decision": "APPROVED"}
                )
            )

        query, params = self.db.queries[0]
        self.assertIn("c.organization_id = %s", query)
        self.assertEqual(("REQUEST-B", "ORG-A"), params)
        self.assertFalse(any(query.startswith(("update ", "insert ")) for query, _ in self.db.queries))

    def test_admin_a_cannot_delete_request_in_organization_b(self):
        with self._admin_a():
            self.assert_not_found(
                lambda: actions.admin_delete_certificate_request({"requestId": "REQUEST-B"})
            )

        query, params = self.db.queries[0]
        self.assertIn("c.organization_id = %s", query)
        self.assertEqual(("REQUEST-B", "ORG-A"), params)
        self.assertFalse(any(query.startswith("delete ") for query, _ in self.db.queries))

    def test_student_a_cannot_download_receipt_from_organization_b(self):
        with self._student_a(), patch.object(actions, "_private_content_payload") as content:
            self.assert_not_found(
                lambda: actions.certificate_receipt_download_payload(
                    {"requestId": "REQUEST-B", "sessionToken": "student-token"}
                ),
                "PAYMENT_RECEIPT_NOT_FOUND",
            )

        content.assert_not_called()
        query, params = self.db.queries[0]
        self.assertIn("c.organization_id = %s", query)
        self.assertEqual(("REQUEST-B", "STUDENT-A", "ORG-A"), params)

    def test_admin_a_cannot_download_receipt_from_organization_b(self):
        with self._admin_a(), patch.object(actions, "_private_content_payload") as content:
            self.assert_not_found(
                lambda: actions.certificate_receipt_download_payload(
                    {"requestId": "REQUEST-B", "adminToken": "admin-token"}
                ),
                "PAYMENT_RECEIPT_NOT_FOUND",
            )

        content.assert_not_called()
        query, params = self.db.queries[0]
        self.assertIn("c.organization_id = %s", query)
        self.assertEqual(("REQUEST-B", "ORG-A"), params)

    def test_admin_list_is_bound_to_active_organization(self):
        with self._admin_a():
            result = actions.admin_list_certificate_requests({"status": "ALL"})["data"]

        self.assertEqual([], result["requests"])
        query, params = self.db.queries[0]
        self.assertIn("where c.organization_id = %s", query)
        self.assertEqual("ORG-A", params[0])


if __name__ == "__main__":
    unittest.main()
