import importlib
import inspect
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.courseplatform import actions, contracts, serializers
from backend.courseplatform.domains import administration, communication, identity, learning
from backend.courseplatform.domains.registry import DOMAIN_ACTION_BINDINGS


ROOT = Path(__file__).resolve().parents[1]


class BackendModuleBoundaryTests(unittest.TestCase):
    def test_dispatcher_is_grouped_into_the_nine_expected_domains(self):
        self.assertEqual(
            {
                "identity",
                "catalog",
                "enrollments",
                "learning",
                "assessments",
                "certificates",
                "financial",
                "communication",
                "administration",
            },
            set(DOMAIN_ACTION_BINDINGS),
        )
        action_names = [name for bindings in DOMAIN_ACTION_BINDINGS.values() for name, _ in bindings]
        self.assertEqual(126, len(action_names))
        self.assertEqual(len(action_names), len(set(action_names)))
        self.assertEqual(set(action_names), set(actions.ACTIONS))
        self.assertTrue(all(callable(handler) for handler in actions.ACTIONS.values()))

    def test_legacy_action_contracts_are_reexported(self):
        self.assertIs(actions.ApiError, contracts.ApiError)
        self.assertIs(actions.normalize_email, identity.normalize_email)
        self.assertIs(actions.valid_password, identity.valid_password)
        self.assertIs(actions.ACTIONS["logout"], actions.ACTIONS["adminLogout"])

    def test_application_import_has_no_domain_cycle(self):
        module = importlib.import_module("backend.courseplatform.app")
        self.assertIsNotNone(module.app)

    def test_actions_uses_registry_instead_of_a_second_action_manifest(self):
        source = (ROOT / "backend" / "courseplatform" / "actions.py").read_text(encoding="utf-8")
        self.assertIn("ACTIONS = build_action_registry(globals())", source)
        self.assertNotIn("ACTIONS = {", source)
        self.assertLess(len(source.splitlines()), 11200)

    def test_identity_handlers_are_sql_free_compatibility_adapters(self):
        adapters = {
            "login": "login_action",
            "register_student_account": "register_student_account_action",
            "complete_student_account_verification": "complete_student_account_verification_action",
            "recover_student_access": "recover_student_access_action",
            "complete_student_password_reset": "complete_student_password_reset_action",
            "admin_login": "admin_login_action",
            "recover_admin_access": "recover_admin_access_action",
            "logout": "logout_action",
            "admin_me": "admin_me_action",
            "update_my_profile": "update_my_profile_action",
            "change_my_access_code": "change_my_access_code_action",
            "change_my_email": "change_my_email_action",
        }
        for adapter_name, domain_name in adapters.items():
            source = inspect.getsource(getattr(actions, adapter_name))
            self.assertIn(f"identity_domain.{domain_name}", source, adapter_name)
            self.assertNotRegex(source.lower(), r"\b(select|insert|update|delete)\b", adapter_name)
            self.assertLessEqual(len(source.splitlines()), 3, adapter_name)

    def test_identity_runtime_resolves_patchable_dependencies_at_call_time(self):
        replacement = object()
        with patch.object(actions, "fetch_one", replacement):
            runtime = actions._identity_runtime()
        self.assertIs(runtime.fetch_one, replacement)
        self.assertIs(runtime.default_notification_preferences, actions.DEFAULT_NOTIFICATION_PREFERENCES)

    def test_password_reset_public_contract_is_reexported(self):
        self.assertEqual(
            identity.PASSWORD_RESET_GENERIC_MESSAGE,
            actions.PASSWORD_RESET_GENERIC_MESSAGE,
        )

    def test_assessment_handlers_are_sql_free_compatibility_adapters(self):
        adapters = {
            "attempt_status": "attempt_status_action",
            "start_attempt": "start_attempt_action",
            "start_attempt_with_conn": "start_attempt_with_conn_action",
            "save_answer": "save_answer_action",
            "upload_file": "upload_file_action",
            "delete_uploaded_file": "delete_uploaded_file_action",
            "submit_attempt": "submit_attempt_action",
            "submission_file_download_payload": "submission_file_download_payload_action",
            "admin_list_submissions": "admin_list_submissions_action",
            "admin_get_submission": "admin_get_submission_action",
            "admin_review_submission": "admin_review_submission_action",
            "admin_authorize_retry": "admin_authorize_retry_action",
            "admin_update_attempt": "admin_update_attempt_action",
        }
        for adapter_name, domain_name in adapters.items():
            source = inspect.getsource(getattr(actions, adapter_name))
            self.assertIn(f"assessment_domain.{domain_name}", source, adapter_name)
            self.assertNotRegex(source.lower(), r"\b(select|insert|update|delete)\b", adapter_name)
            self.assertLessEqual(len(source.splitlines()), 9, adapter_name)

    def test_assessment_runtime_resolves_patchable_dependencies_at_call_time(self):
        replacement = object()
        with patch.object(actions, "connection", replacement):
            runtime = actions._assessment_runtime()
        self.assertIs(runtime.connection, replacement)
        self.assertIs(runtime.editable_attempt, actions.editable_attempt)

    def test_certificate_handlers_are_sql_free_compatibility_adapters(self):
        adapters = {
            "ensure_simple_certificate": "ensure_simple_certificate_action",
            "my_certificate": "my_certificate_action",
            "my_certifications": "my_certifications_action",
            "request_participation_certificate": "request_participation_certificate_action",
            "request_professional_certificate": "request_professional_certificate_action",
            "record_certificate_download": "record_certificate_download_action",
            "certificate_pdf_payload": "certificate_pdf_payload_action",
            "admin_certificate_pdf_payload": "admin_certificate_pdf_payload_action",
            "admin_list_certificates": "admin_list_certificates_action",
            "admin_set_certificate_status": "admin_set_certificate_status_action",
            "admin_refresh_certificate_format": "admin_refresh_certificate_format_action",
            "admin_delete_certificate": "admin_delete_certificate_action",
            "admin_get_certificate_settings": "admin_get_certificate_settings_action",
            "admin_save_certificate_settings": "admin_save_certificate_settings_action",
            "admin_list_certificate_surveys": "admin_list_certificate_surveys_action",
            "admin_save_certificate_survey": "admin_save_certificate_survey_action",
            "admin_upload_certificate_asset": "admin_upload_certificate_asset_action",
            "verify_certificate": "verify_certificate_action",
        }
        for adapter_name, domain_name in adapters.items():
            source = inspect.getsource(getattr(actions, adapter_name))
            self.assertIn(f"certificate_domain.{domain_name}", source, adapter_name)
            self.assertNotRegex(source.lower(), r"\b(select|insert|update|delete)\b", adapter_name)
            self.assertLessEqual(len(source.splitlines()), 14, adapter_name)

    def test_certificate_runtime_resolves_patchable_dependencies_at_call_time(self):
        replacement = object()
        with patch.object(actions, "connection", replacement):
            runtime = actions._certificate_runtime()
        self.assertIs(runtime.connection, replacement)
        self.assertIs(runtime.ensure_simple_certificate, actions.ensure_simple_certificate)

    def test_financial_handlers_are_sql_free_compatibility_adapters(self):
        adapters = {
            "submit_professional_certificate_payment": "submit_professional_certificate_payment_action",
            "admin_list_certificate_requests": "admin_list_certificate_requests_action",
            "admin_review_certificate_request": "admin_review_certificate_request_action",
            "admin_delete_certificate_request": "admin_delete_certificate_request_action",
            "certificate_receipt_download_payload": "certificate_receipt_download_payload_action",
            "approve_participation_request": "approve_participation_request_action",
        }
        for adapter_name, domain_name in adapters.items():
            source = inspect.getsource(getattr(actions, adapter_name))
            self.assertIn(f"financial_domain.{domain_name}", source, adapter_name)
            self.assertNotRegex(source.lower(), r"\b(select|insert|update|delete)\b", adapter_name)
            self.assertLessEqual(len(source.splitlines()), 9, adapter_name)

    def test_financial_runtime_resolves_patchable_dependencies_at_call_time(self):
        replacement = object()
        with patch.object(actions, "upload_private_object", replacement):
            runtime = actions._financial_runtime()
        self.assertIs(runtime.upload_private_object, replacement)
        self.assertIs(runtime.approve_participation_request, actions.approve_participation_request)

    def test_catalog_handlers_are_sql_free_compatibility_adapters(self):
        adapters = {
            "public_course_config": "public_course_config_action",
            "read_media_config": "read_media_config_action",
            "read_media_config_with_conn": "read_media_config_with_conn_action",
            "persist_media_config": "persist_media_config_action",
            "student_visible_media": "student_visible_media_action",
            "student_media_config": "student_media_config_action",
            "public_media_config": "public_media_config_action",
            "admin_media_config": "admin_media_config_action",
            "course_structure_snapshot_with_conn": "course_structure_snapshot_with_conn_action",
            "admin_list_courses": "admin_list_courses_action",
            "admin_course_structure": "admin_course_structure_action",
            "admin_create_course_version": "admin_create_course_version_action",
            "admin_refresh_course_version_draft": "admin_refresh_course_version_draft_action",
            "admin_edit_course_version_draft": "admin_edit_course_version_draft_action",
            "admin_preview_course_version": "admin_preview_course_version_action",
            "admin_publish_course_version": "admin_publish_course_version_action",
            "admin_save_media_config": "admin_save_media_config_action",
            "admin_save_course": "admin_save_course_action",
            "admin_save_lesson": "admin_save_lesson_action",
            "admin_save_lesson_content": "admin_save_lesson_content_action",
        }
        for adapter_name, domain_name in adapters.items():
            source = inspect.getsource(getattr(actions, adapter_name))
            self.assertIn(f"catalog_domain.{domain_name}", source, adapter_name)
            self.assertNotRegex(source.lower(), r"\b(select|insert|update|delete)\b", adapter_name)
            self.assertLessEqual(len(source.splitlines()), 14, adapter_name)

    def test_catalog_runtime_resolves_patchable_dependencies_at_call_time(self):
        replacement = object()
        with patch.object(actions, "fetch_all", replacement):
            runtime = actions._catalog_runtime()
        self.assertIs(runtime.fetch_all, replacement)
        self.assertIs(runtime.course_structure_snapshot_with_conn, actions.course_structure_snapshot_with_conn)

    def test_enrollment_handlers_are_sql_free_compatibility_adapters(self):
        adapters = {
            "resolve_course_offering_with_conn": "resolve_course_offering_with_conn_action",
            "resolve_student_enrollment_with_conn": "resolve_student_enrollment_with_conn_action",
            "initialize_enrollment_progress_with_conn": "initialize_enrollment_progress_with_conn_action",
            "ensure_offering_enrollment_with_conn": "ensure_offering_enrollment_with_conn_action",
            "student_courses_rows": "student_courses_rows_action",
            "student_courses_payload": "student_courses_payload_action",
            "my_courses": "my_courses_action",
            "admin_list_groups": "admin_list_groups_action",
            "admin_save_course_offering": "admin_save_course_offering_action",
            "admin_enroll_students_in_offering": "admin_enroll_students_in_offering_action",
            "admin_list_course_reconciliation_issues": "admin_list_course_reconciliation_issues_action",
            "admin_save_group": "admin_save_group_action",
            "admin_assign_students_to_group": "admin_assign_students_to_group_action",
        }
        for adapter_name, domain_name in adapters.items():
            source = inspect.getsource(getattr(actions, adapter_name))
            self.assertIn(f"enrollment_domain.{domain_name}", source, adapter_name)
            self.assertNotRegex(source.lower(), r"\b(select|insert|update|delete)\b", adapter_name)
            self.assertLessEqual(len(source.splitlines()), 14, adapter_name)

    def test_enrollment_runtime_resolves_patchable_dependencies_at_call_time(self):
        replacement = object()
        with patch.object(actions, "initialize_enrollment_progress_with_conn", replacement):
            runtime = actions._enrollment_runtime()
        self.assertIs(runtime.initialize_enrollment_progress_with_conn, replacement)
        self.assertIs(runtime.resolve_course_offering_with_conn, actions.resolve_course_offering_with_conn)

    def test_communication_handlers_are_sql_free_compatibility_adapters(self):
        adapters = {
            handler_name: f"{handler_name}_action"
            for _, handler_name in communication.ACTION_BINDINGS
        }
        for adapter_name, domain_name in adapters.items():
            source = inspect.getsource(getattr(actions, adapter_name))
            self.assertIn(f"communication_domain.{domain_name}", source, adapter_name)
            self.assertNotRegex(source.lower(), r"\b(select|insert|update|delete)\b", adapter_name)
            self.assertLessEqual(len(source.splitlines()), 8, adapter_name)

    def test_communication_helpers_are_sql_free_compatibility_adapters(self):
        adapters = {
            "ensure_notification_feature_schema": "ensure_notification_feature_schema_action",
            "create_student_notification": "create_student_notification_action",
            "dispatch_notification_deliveries": "dispatch_notification_deliveries_action",
            "ensure_chat_feature_schema": "ensure_chat_feature_schema_action",
            "chat_realtime_token": "chat_realtime_token_action",
            "student_can_access_chat_room": "student_can_access_chat_room_action",
            "public_chat_message": "public_chat_message_action",
            "public_chat_room": "public_chat_room_action",
        }
        for adapter_name, domain_name in adapters.items():
            source = inspect.getsource(getattr(actions, adapter_name))
            self.assertIn(f"communication_domain.{domain_name}", source, adapter_name)
            self.assertNotRegex(source.lower(), r"\b(select|insert|update|delete)\b", adapter_name)
            self.assertLessEqual(len(source.splitlines()), 8, adapter_name)

    def test_communication_runtime_resolves_patchable_dependencies_at_call_time(self):
        replacement_connection = object()
        replacement_webpush = object()
        with (
            patch.object(actions, "connection", replacement_connection),
            patch.object(actions, "webpush", replacement_webpush),
        ):
            runtime = actions._communication_runtime()
        self.assertIs(runtime.connection, replacement_connection)
        self.assertIs(runtime.webpush, replacement_webpush)
        self.assertIs(runtime.create_student_notification, actions.create_student_notification)

    def test_learning_handlers_are_sql_free_compatibility_adapters(self):
        adapters = {
            handler_name: f"{handler_name}_action"
            for _, handler_name in learning.ACTION_BINDINGS
        }
        for adapter_name, domain_name in adapters.items():
            source = inspect.getsource(getattr(actions, adapter_name))
            self.assertIn(f"learning_domain.{domain_name}", source, adapter_name)
            self.assertNotRegex(source.lower(), r"\b(select|insert|update|delete)\b", adapter_name)
            self.assertLessEqual(len(source.splitlines()), 8, adapter_name)

    def test_learning_helpers_are_sql_free_compatibility_adapters(self):
        adapters = {
            "progress_access_status": "progress_access_status_action",
            "progress_evaluation_status": "progress_evaluation_status_action",
            "legacy_progress_status": "legacy_progress_status_action",
            "public_lesson": "public_lesson_action",
            "public_content": "public_content_action",
            "public_progress": "public_progress_action",
            "student_question": "student_question_action",
            "student_option": "student_option_action",
            "sync_enrollment_completion": "sync_enrollment_completion_action",
            "refresh_enrollment_progress": "refresh_enrollment_progress_action",
            "dashboard_payload": "dashboard_payload_action",
        }
        for adapter_name, domain_name in adapters.items():
            source = inspect.getsource(getattr(actions, adapter_name))
            self.assertIn(f"learning_domain.{domain_name}", source, adapter_name)
            self.assertNotRegex(source.lower(), r"\b(select|insert|update|delete)\b", adapter_name)
            self.assertLessEqual(len(source.splitlines()), 8, adapter_name)

    def test_learning_runtime_resolves_patchable_dependencies_at_call_time(self):
        replacement_connection = object()
        replacement_resolver = object()
        with (
            patch.object(actions, "connection", replacement_connection),
            patch.object(actions, "resolve_student_enrollment_with_conn", replacement_resolver),
        ):
            runtime = actions._learning_runtime()
        self.assertIs(runtime.connection, replacement_connection)
        self.assertIs(runtime.resolve_student_enrollment_with_conn, replacement_resolver)
        self.assertIs(runtime.student_question, actions.student_question)

    def test_administration_handlers_are_sql_free_compatibility_adapters(self):
        adapters = {
            handler_name: f"{handler_name}_action"
            for _, handler_name in administration.ACTION_BINDINGS
        }
        for adapter_name, domain_name in adapters.items():
            source = inspect.getsource(getattr(actions, adapter_name))
            self.assertIn(f"administration_domain.{domain_name}", source, adapter_name)
            self.assertNotRegex(source.lower(), r"\b(select|insert|update|delete)\b", adapter_name)
            self.assertLessEqual(len(source.splitlines()), 8, adapter_name)

    def test_administration_helpers_are_sql_free_compatibility_adapters(self):
        adapters = {
            "public_admin": "public_admin_action",
            "decode_raster_data_url": "decode_raster_data_url_action",
            "raster_signature_matches": "raster_signature_matches_action",
            "normalize_brand_logo_url": "normalize_brand_logo_url_action",
            "upload_raster_asset_to_storage": "upload_raster_asset_to_storage_action",
            "credential_restore_item": "credential_restore_item_action",
        }
        for adapter_name, domain_name in adapters.items():
            source = inspect.getsource(getattr(actions, adapter_name))
            self.assertIn(f"administration_domain.{domain_name}", source, adapter_name)
            self.assertNotRegex(source.lower(), r"\b(select|insert|update|delete)\b", adapter_name)
            self.assertLessEqual(len(source.splitlines()), 8, adapter_name)

    def test_administration_runtime_resolves_patchable_dependencies_at_call_time(self):
        replacement_connection = object()
        replacement_schema_status = object()
        replacement_upload = object()
        with (
            patch.object(actions, "connection", replacement_connection),
            patch.object(actions, "schema_status", replacement_schema_status),
            patch.object(actions, "upload_raster_asset_to_storage", replacement_upload),
        ):
            runtime = actions._administration_runtime()
        self.assertIs(runtime.connection, replacement_connection)
        self.assertIs(runtime.schema_status, replacement_schema_status)
        self.assertIs(runtime.upload_raster_asset_to_storage, replacement_upload)

    def test_shared_academic_serializers_have_compatibility_adapters(self):
        adapters = {
            "public_course": "serialize_course",
            "public_course_version": "serialize_course_version",
            "public_course_offering": "serialize_course_offering",
            "public_enrollment": "serialize_enrollment",
            "public_group_member": "serialize_group_member",
        }
        for adapter_name, serializer_name in adapters.items():
            source = inspect.getsource(getattr(actions, adapter_name))
            self.assertIn(f"shared_serializers.{serializer_name}", source, adapter_name)
            self.assertLessEqual(len(source.splitlines()), 2, adapter_name)

    def test_shared_serializers_resolve_iso_dependency_at_call_time(self):
        row = {
            "enrollment_id": "ENR1",
            "enrolled_at": "enrolled",
            "completed_at": "completed",
        }
        with patch.object(actions, "iso", side_effect=lambda value: f"iso:{value}"):
            result = actions.public_enrollment(row)
        self.assertEqual("iso:enrolled", result["enrolledAt"])
        self.assertEqual("iso:completed", result["completedAt"])
        self.assertIsNotNone(serializers.serialize_enrollment(row, as_iso=lambda value: value))


class FrontendSourceTests(unittest.TestCase):
    def test_public_tree_matches_generated_distribution_tree(self):
        source_root = ROOT / "public"
        target_root = ROOT / "backend" / "courseplatform" / "static"
        source_files = sorted(path.relative_to(source_root) for path in source_root.rglob("*") if path.is_file())
        target_files = sorted(path.relative_to(target_root) for path in target_root.rglob("*") if path.is_file())
        self.assertEqual(source_files, target_files)
        for relative in source_files:
            self.assertEqual((source_root / relative).read_bytes(), (target_root / relative).read_bytes(), relative)

    def test_frontend_entrypoints_use_extracted_modules(self):
        admin_source = (ROOT / "public" / "admin.js").read_text(encoding="utf-8")
        student_source = (ROOT / "public" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "public" / "assets" / "css" / "styles.css").read_text(encoding="utf-8")
        tokens = (ROOT / "public" / "assets" / "css" / "tokens.css").read_text(encoding="utf-8")
        self.assertIn("./admin/pagination.js", admin_source)
        self.assertIn("./student/routes.js", student_source)
        self.assertTrue(styles.startswith('@import url("./tokens.css");'))
        self.assertIn(":root {", tokens)
        self.assertNotRegex(styles, r"(?m)^:root\s*\{")

    def test_package_exposes_sync_and_parity_commands(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertEqual("node scripts/sync_frontend.cjs", package["scripts"]["sync:frontend"])
        self.assertEqual("node scripts/sync_frontend.cjs --check", package["scripts"]["check:frontend"])


if __name__ == "__main__":
    unittest.main()
