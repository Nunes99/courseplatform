import unittest
from contextlib import contextmanager
from unittest.mock import Mock, patch

from backend.courseplatform import actions


class Result:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows if rows is not None else ([] if row is None else [row])

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class CertificateTenantConnection:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.queries = []

    def execute(self, query, params=()):
        normalized = " ".join(query.lower().split())
        self.queries.append((normalized, params))
        if normalized.startswith("select cert.* from courseplatform.certificates cert"):
            return Result()
        if normalized.startswith("select course_id from courseplatform.courses"):
            return Result()
        if "from courseplatform.certificates cert" in normalized and "order by cert.issue_date" in normalized:
            return Result(rows=self.rows)
        raise AssertionError(normalized)

    def commit(self):
        return None


def connection_for(database):
    @contextmanager
    def connect():
        yield database

    return connect


class CertificateTenantIsolationTests(unittest.TestCase):
    def test_student_cannot_increment_download_for_another_organization(self):
        database = CertificateTenantConnection()
        with (
            patch.object(actions, "connection", connection_for(database)),
            patch.object(actions, "ensure_certificate_feature_schema"),
            patch.object(
                actions,
                "student_context_with_conn",
                return_value=({"organization_id": "ORG-A"}, {"student_id": "STUDENT-1"}),
            ),
        ):
            with self.assertRaises(actions.ApiError) as raised:
                actions.record_certificate_download({"certificateId": "CERT-ORG-B"})

        self.assertEqual("CERTIFICATE_NOT_FOUND", raised.exception.code)
        self.assertFalse(any(query.startswith("update courseplatform.certificates") for query, _ in database.queries))
        self.assertIn("c.organization_id = %s", database.queries[0][0])
        self.assertEqual("ORG-A", database.queries[0][1][-1])

    def test_admin_cannot_change_certificate_from_another_organization(self):
        database = CertificateTenantConnection()
        with (
            patch.object(actions, "connection", connection_for(database)),
            patch.object(actions, "ensure_certificate_feature_schema"),
            patch.object(
                actions,
                "admin_context_with_conn",
                return_value=(
                    {"organization_id": "ORG-A"},
                    {"admin_id": "ADMIN-1", "role": "ADMIN", "active_organization_id": "ORG-A"},
                ),
            ),
        ):
            with self.assertRaises(actions.ApiError) as raised:
                actions.admin_set_certificate_status(
                    {"certificateId": "CERT-ORG-B", "status": "BLOCKED"}
                )

        self.assertEqual("CERTIFICATE_NOT_FOUND", raised.exception.code)
        self.assertFalse(any(query.startswith("update courseplatform.certificates") for query, _ in database.queries))

    def test_admin_cannot_upload_asset_for_course_from_another_organization(self):
        database = CertificateTenantConnection()
        decode = Mock()
        upload = Mock()
        with (
            patch.object(actions, "connection", connection_for(database)),
            patch.object(
                actions,
                "admin_context_with_conn",
                return_value=(
                    {"organization_id": "ORG-A"},
                    {"admin_id": "ADMIN-1", "role": "ADMIN", "active_organization_id": "ORG-A"},
                ),
            ),
            patch.object(actions, "decode_raster_data_url", decode),
            patch.object(actions, "upload_raster_asset_to_storage", upload),
        ):
            with self.assertRaises(actions.ApiError) as raised:
                actions.admin_upload_certificate_asset(
                    {
                        "courseId": "COURSE-ORG-B",
                        "assetKey": "logoUrl",
                        "fileName": "logo.png",
                        "mimeType": "image/png",
                        "dataUrl": "data:image/png;base64,AAAA",
                    }
                )

        self.assertEqual("COURSE_NOT_FOUND", raised.exception.code)
        decode.assert_not_called()
        upload.assert_not_called()

    def test_admin_certificate_list_is_bound_to_active_organization(self):
        database = CertificateTenantConnection()
        with (
            patch.object(actions, "connection", connection_for(database)),
            patch.object(actions, "ensure_certificate_feature_schema"),
            patch.object(
                actions,
                "admin_context_with_conn",
                return_value=(
                    {"organization_id": "ORG-A"},
                    {"admin_id": "ADMIN-1", "role": "ADMIN", "active_organization_id": "ORG-A"},
                ),
            ),
        ):
            result = actions.admin_list_certificates({"status": "ALL"})

        self.assertEqual([], result["data"]["certificates"])
        query, params = database.queries[0]
        self.assertIn("c.organization_id = %s", query)
        self.assertEqual("ORG-A", params[3])


if __name__ == "__main__":
    unittest.main()
