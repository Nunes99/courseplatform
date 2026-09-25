import inspect
import unittest
from pathlib import Path

from backend.courseplatform.contracts import ApiError
from backend.courseplatform.domains import assessments as assessment_domain
from backend.courseplatform.domains import certificates as certificate_domain
from backend.courseplatform.reviewer_scopes import (
    normalize_scope_payload,
    require_attempt_scope,
    require_certificate_scope,
    require_course_scope,
    require_student_scope,
    reviewer_course_predicate,
    reviewer_scope_predicate,
)


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "20260925043513_add_reviewer_scopes.sql"


class _Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, row=None):
        self.row = row
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return _Result(self.row)


class ReviewerScopeUnitTests(unittest.TestCase):
    def test_non_reviewer_predicate_is_unrestricted(self):
        sql, params = reviewer_scope_predicate(
            {"role": "ADMIN", "admin_id": "ADM-1"}, course_expr="e.course_id"
        )
        self.assertEqual("true", sql)
        self.assertEqual((), params)

    def test_reviewer_predicate_covers_course_offering_and_group(self):
        sql, params = reviewer_scope_predicate(
            {"role": "REVIEWER", "admin_id": "ADM-2"},
            course_expr="e.course_id",
            offering_expr="e.offering_id",
            group_expr="e.group_id",
        )
        self.assertIn("rs.course_id = e.course_id", sql)
        self.assertIn("rs.offering_id = e.offering_id", sql)
        self.assertIn("rs.group_id = e.group_id", sql)
        self.assertIn("select max(", sql)
        self.assertIn("effective_scope.status = 'ACTIVE'", sql)
        self.assertEqual(("ADM-2",), params)

    def test_course_parent_is_visible_for_any_scope_below_it(self):
        sql, params = reviewer_course_predicate(
            {"role": "REVIEWER", "admin_id": "ADM-3"}, "c.course_id"
        )
        self.assertIn("rs.course_id = c.course_id", sql)
        self.assertEqual(("ADM-3",), params)

    def test_global_scope_cannot_be_combined(self):
        with self.assertRaises(ApiError):
            normalize_scope_payload([
                {"scopeType": "GLOBAL"},
                {"scopeType": "COURSE", "courseId": "COURSE-1"},
            ])

    def test_course_and_group_scopes_cannot_be_combined(self):
        with self.assertRaises(ApiError) as error:
            normalize_scope_payload([
                {"scopeType": "COURSE", "courseId": "COURSE-1"},
                {
                    "scopeType": "GROUP",
                    "courseId": "COURSE-1",
                    "offeringId": "OFF-1",
                    "groupId": "GROUP-1",
                },
            ])
        self.assertEqual("INVALID_REVIEWER_SCOPE", error.exception.code)

    def test_multiple_scopes_at_the_same_level_are_allowed(self):
        scopes = normalize_scope_payload([
            {"scopeType": "COURSE", "courseId": "COURSE-1"},
            {"scopeType": "COURSE", "courseId": "COURSE-2"},
        ])
        self.assertEqual(2, len(scopes))
        self.assertEqual({"COURSE"}, {scope["scopeType"] for scope in scopes})

    def test_attempt_outside_scope_is_denied(self):
        connection = _Connection(row=None)
        with self.assertRaises(ApiError) as error:
            require_attempt_scope(
                connection,
                {"role": "REVIEWER", "admin_id": "ADM-4"},
                "ATT-1",
            )
        self.assertEqual("REVIEWER_SCOPE_REQUIRED", error.exception.code)

    def test_course_outside_scope_is_denied(self):
        with self.assertRaises(ApiError) as error:
            require_course_scope(
                _Connection(row=None),
                {"role": "REVIEWER", "admin_id": "ADM-4"},
                "COURSE-OUTSIDE",
            )
        self.assertEqual("REVIEWER_SCOPE_REQUIRED", error.exception.code)

    def test_student_outside_scope_is_denied(self):
        with self.assertRaises(ApiError) as error:
            require_student_scope(
                _Connection(row=None),
                {"role": "REVIEWER", "admin_id": "ADM-4"},
                "STU-OUTSIDE",
            )
        self.assertEqual("REVIEWER_SCOPE_REQUIRED", error.exception.code)

    def test_certificate_download_outside_scope_is_denied(self):
        with self.assertRaises(ApiError) as error:
            require_certificate_scope(
                _Connection(row=None),
                {"role": "REVIEWER", "admin_id": "ADM-4"},
                "CERT-OUTSIDE",
            )
        self.assertEqual("REVIEWER_SCOPE_REQUIRED", error.exception.code)


class ReviewerScopeContractTests(unittest.TestCase):
    def test_migration_is_additive_private_and_backfills_existing_reviewers(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("create table if not exists courseplatform.reviewer_scopes", sql)
        self.assertIn("a.role = 'REVIEWER'", sql)
        self.assertIn("'GLOBAL'", sql)
        self.assertIn("enable row level security", sql)
        self.assertIn("revoke all privileges", sql)
        self.assertIn("courseplatform_runtime", sql)

    def test_frontend_exposes_scope_editor_and_hides_restricted_controls(self):
        source = (ROOT / "public" / "admin.js").read_text(encoding="utf-8")
        self.assertIn("reviewerScopeOptionsTemplate", source)
        self.assertIn("reviewerEffectiveAccess", source)
        self.assertIn("reviewerScopeMode", source)
        self.assertIn("values.reviewScopes", source)
        self.assertIn("function canManagePlatform()", source)
        self.assertIn("Comprovativo protegido. Apenas administradores", source)

    def test_sensitive_reviewer_operations_enforce_resource_scope(self):
        download_source = inspect.getsource(assessment_domain.submission_file_download_payload_action)
        review_source = inspect.getsource(assessment_domain.admin_review_submission_action)
        certificate_source = inspect.getsource(certificate_domain.admin_certificate_pdf_payload_action)

        self.assertIn("require_attempt_scope(conn, admin, row.get(\"attempt_id\"))", download_source)
        self.assertIn("require_attempt_scope(conn, admin, attempt[\"attempt_id\"])", review_source)
        self.assertIn(
            "require_certificate_scope(conn, admin, cert[\"certificate_id\"])",
            certificate_source,
        )


if __name__ == "__main__":
    unittest.main()
