import base64
import hashlib
import hmac
import ipaddress
import json
import math
import mimetypes
import secrets
import smtplib
import ssl
import urllib.error
import urllib.request
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from html import escape as html_escape
from typing import Any
from urllib.parse import urlencode, urlsplit

try:
    from pywebpush import WebPushException, webpush
except ImportError:  # pragma: no cover - deployment validation reports this cleanly.
    WebPushException = RuntimeError
    webpush = None

from .config import get_settings
from .contracts import (
    ApiError,
    as_bool,
    cursor_page_limit,
    cursor_pagination_result,
    cursor_scope,
    database_api_error,
    decode_list_cursor,
    encode_list_cursor,
    float_value,
    int_value,
    iso,
    pagination,
    parse_datetime,
    public_error,
    require_fields,
    storage_api_error,
    str_value,
    success,
)
from .db import EXPECTED_SCHEMA_VERSION, connection, fetch_all, fetch_one, schema_status
from .domains import administration as administration_domain
from .domains import assessments as assessment_domain
from .domains import catalog as catalog_domain
from .domains import certificates as certificate_domain
from .domains import communication as communication_domain
from .domains import enrollments as enrollment_domain
from .domains import financial as financial_domain
from .domains import identity as identity_domain
from .domains import learning as learning_domain
from .domains.identity import (
    normalize_email,
    public_student_id,
    serialize_admin,
    serialize_student,
    valid_password,
)
from .domains.registry import build_action_registry
from . import serializers as shared_serializers
from .security import (
    constant_time_equals,
    generate_id,
    generate_access_code,
    generate_token,
    hash_secret,
    session_expiry,
    utc_now,
)
from .storage import (
    StorageError,
    decode_legacy_data_url,
    download_private_object,
    legacy_external_url,
    storage_service_headers,
    storage_object_path,
    upload_private_object,
    validate_upload,
)

RASTER_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}
BRAND_LOGO_MAX_BYTES = 1024 * 1024
PASSWORD_RESET_GENERIC_MESSAGE = identity_domain.PASSWORD_RESET_GENERIC_MESSAGE
REGISTRATION_GENERIC_MESSAGE = identity_domain.REGISTRATION_GENERIC_MESSAGE
ACCOUNT_VERIFICATION_DELIVERY_FAILED_MESSAGE = identity_domain.ACCOUNT_VERIFICATION_DELIVERY_FAILED_MESSAGE


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    row = fetch_one("select %s = crypt(%s, %s) as ok", (password_hash, password, password_hash))
    return bool(row and row.get("ok"))


CONTENT_ACCESS_STATUSES = {"LOCKED", "AVAILABLE"}
EVALUATION_STATUSES = {
    "NOT_STARTED",
    "IN_PROGRESS",
    "UNDER_REVIEW",
    "CORRECTION_REQUIRED",
    "APPROVED",
    "FAILED",
    "TIME_EXCEEDED",
}
ATTEMPT_STATUSES = EVALUATION_STATUSES - {"NOT_STARTED"}
_ASSESSMENT_SCHEMA_READY = False
_NOTIFICATION_SCHEMA_READY = False
_CHAT_SCHEMA_READY = False
_CHAT_REALTIME_SCHEMA_READY = False
_CERTIFICATE_SCHEMA_READY = False
_APPLICATION_SCHEMA_READY = False


def progress_access_status(row: dict[str, Any] | None) -> str:
    return learning_domain.progress_access_status_action(row, runtime=_learning_runtime())


def progress_evaluation_status(row: dict[str, Any] | None) -> str:
    return learning_domain.progress_evaluation_status_action(row, runtime=_learning_runtime())


def legacy_progress_status(access_status: str, evaluation_status: str) -> str:
    return learning_domain.legacy_progress_status_action(access_status, evaluation_status, runtime=_learning_runtime())


def audit(conn, actor_type: str, actor_id: str, action: str, entity_type: str, entity_id: str, details: dict[str, Any] | None = None):
    conn.execute(
        """
        insert into courseplatform.audit_log
          (log_id, actor_type, actor_id, action, entity_type, entity_id, details_json, created_at)
        values (%s, %s, %s, %s, %s, %s, %s, now())
        """,
        (generate_id("LOG"), actor_type, actor_id, action, entity_type, entity_id, json.dumps(details or {})),
    )


def public_student(row: dict[str, Any] | None):
    return serialize_student(
        row,
        as_boolean=as_bool,
        as_iso=iso,
        telegram_recipient=normalize_telegram_recipient,
        preferences=notification_preferences,
    )


def public_admin(row: dict[str, Any] | None):
    return administration_domain.public_admin_action(row, runtime=_administration_runtime())


def public_course(row: dict[str, Any] | None):
    return shared_serializers.serialize_course(row, as_iso=iso)


def public_course_version(row: dict[str, Any] | None):
    return shared_serializers.serialize_course_version(row, as_iso=iso)


def public_course_offering(row: dict[str, Any] | None):
    return shared_serializers.serialize_course_offering(row, as_iso=iso)


def public_lesson(row: dict[str, Any] | None):
    return learning_domain.public_lesson_action(row, runtime=_learning_runtime())


def public_enrollment(row: dict[str, Any] | None):
    return shared_serializers.serialize_enrollment(row, as_iso=iso)


def public_group_member(row: dict[str, Any] | None):
    return shared_serializers.serialize_group_member(row, as_iso=iso)


def public_content(row: dict[str, Any] | None):
    return learning_domain.public_content_action(row, runtime=_learning_runtime())


def staff_question(row: dict[str, Any] | None):
    if not row:
        return None
    return {
        "questionId": row["question_id"],
        "lessonId": row.get("lesson_id"),
        "questionOrder": int(row.get("question_order") or 0),
        "questionType": row.get("question_type"),
        "prompt": row.get("prompt"),
        "points": float(row.get("points") or 0),
        "correctAnswer": row.get("correct_answer"),
        "explanation": row.get("explanation"),
        "isRequired": as_bool(row.get("is_required")),
        "status": row.get("status"),
    }


def staff_option(row: dict[str, Any] | None):
    if not row:
        return None
    return {
        "optionId": row["option_id"],
        "questionId": row.get("question_id"),
        "optionOrder": int(row.get("option_order") or 0),
        "optionLabel": row.get("option_label"),
        "optionText": row.get("option_text"),
        "isCorrect": as_bool(row.get("is_correct")),
    }


def public_progress(row: dict[str, Any] | None):
    return learning_domain.public_progress_action(row, runtime=_learning_runtime())


def student_attempt(row: dict[str, Any] | None):
    if not row:
        return None
    deadline = row.get("deadline_at")
    remaining = None
    if isinstance(deadline, datetime):
        remaining = max(0, int((deadline - utc_now()).total_seconds()))
    result = {
        "attemptId": row["attempt_id"],
        "progressId": row.get("progress_id"),
        "lessonId": row.get("lesson_id"),
        "attemptNumber": int(row.get("attempt_number") or 0),
        "startedAt": iso(row.get("started_at")),
        "deadlineAt": iso(row.get("deadline_at")),
        "submittedAt": iso(row.get("submitted_at")),
        "status": row.get("status"),
        "retryAuthorized": as_bool(row.get("retry_authorized")),
        "remainingSeconds": remaining,
        "createdAt": iso(row.get("created_at")),
        "updatedAt": iso(row.get("updated_at")),
    }
    if row.get("reviewed_at"):
        result.update({
            "score": None if row.get("score") is None else float(row["score"]),
            "reviewedAt": iso(row.get("reviewed_at")),
            "reviewComments": row.get("review_comments"),
        })
    return result


def staff_attempt(row: dict[str, Any] | None):
    if not row:
        return None
    result = student_attempt(row)
    result.update({
        "score": None if row.get("score") is None else float(row["score"]),
        "objectiveScore": None if row.get("objective_score") is None else float(row["objective_score"]),
        "reviewerId": row.get("reviewer_id"),
        "reviewedAt": iso(row.get("reviewed_at")),
        "reviewComments": row.get("review_comments"),
    })
    return result


def expire_attempt_if_needed(attempt: dict[str, Any] | None):
    if not attempt or attempt.get("status") != "IN_PROGRESS" or not attempt.get("deadline_at"):
        return attempt
    deadline = parse_datetime(attempt.get("deadline_at"))
    if not deadline:
        return attempt
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if deadline >= utc_now():
        return attempt
    prepare_assessment_feature_schema()
    with connection() as conn:
        updated = conn.execute(
            """
            update courseplatform.attempts
            set status = 'TIME_EXCEEDED', updated_at = now()
            where attempt_id = %s and status = 'IN_PROGRESS'
            returning *
            """,
            (attempt["attempt_id"],),
        ).fetchone()
        if updated:
            changed = conn.execute(
                """
                update courseplatform.lesson_progress
                set status = 'TIME_EXCEEDED', evaluation_status = 'TIME_EXCEEDED', updated_at = now()
                where progress_id = %s
                """,
                (updated.get("progress_id"),),
            )
            audit(
                conn,
                "SYSTEM",
                updated.get("student_id") or "",
                "ATTEMPT_TIME_EXCEEDED",
                "ATTEMPT",
                updated["attempt_id"],
            )
            conn.commit()
            return updated
        conn.commit()
    return fetch_one("select * from courseplatform.attempts where attempt_id = %s", (attempt["attempt_id"],))


def expire_overdue_attempts() -> int:
    prepare_assessment_feature_schema()
    with connection() as conn:
        rows = conn.execute(
            """
            update courseplatform.attempts
            set status = 'TIME_EXCEEDED', updated_at = now()
            where status = 'IN_PROGRESS' and deadline_at is not null and deadline_at < now()
            returning attempt_id, progress_id
            """
        ).fetchall()
        progress_ids = [row["progress_id"] for row in rows if row.get("progress_id")]
        if progress_ids:
            conn.execute(
                """
                update courseplatform.lesson_progress
                set status = 'TIME_EXCEEDED', evaluation_status = 'TIME_EXCEEDED', updated_at = now()
                where progress_id = any(%s)
                """,
                (progress_ids,),
            )
        conn.commit()
    return len(rows)


def public_review(row: dict[str, Any] | None):
    if not row:
        return None
    return {
        "reviewId": row["review_id"],
        "attemptId": row.get("attempt_id"),
        "reviewerId": row.get("reviewer_id"),
        "decision": row.get("decision"),
        "score": None if row.get("score") is None else float(row["score"]),
        "comments": row.get("comments"),
        "correctionDeadline": iso(row.get("correction_deadline")),
        "unlockNextLesson": as_bool(row.get("unlock_next_lesson")),
        "reviewedAt": iso(row.get("reviewed_at")),
    }


def student_review(row: dict[str, Any] | None):
    if not row:
        return None
    return {
        "decision": row.get("decision"),
        "score": None if row.get("score") is None else float(row["score"]),
        "comments": row.get("comments"),
        "correctionDeadline": iso(row.get("correction_deadline")),
        "reviewedAt": iso(row.get("reviewed_at")),
    }


def staff_answer(row: dict[str, Any] | None):
    if not row:
        return None
    return {
        "answerId": row["answer_id"],
        "attemptId": row.get("attempt_id"),
        "questionId": row.get("question_id"),
        "answerText": row.get("answer_text"),
        "selectedOptionId": row.get("selected_option_id"),
        "isCorrect": None if row.get("is_correct") is None else as_bool(row.get("is_correct")),
        "awardedPoints": None if row.get("awarded_points") is None else float(row["awarded_points"]),
        "savedAt": iso(row.get("saved_at")),
        "submittedAt": iso(row.get("submitted_at")),
    }


FEEDBACK_RELEASE_MODES = {"NEVER", "AFTER_SUBMISSION", "AFTER_REVIEW"}
OBJECTIVE_QUESTION_TYPES = {"SINGLE_CHOICE", "TRUE_FALSE", "MULTIPLE_CHOICE"}


def feedback_release_mode(value: Any) -> str:
    mode = str_value(value).upper() or "AFTER_REVIEW"
    return mode if mode in FEEDBACK_RELEASE_MODES else "AFTER_REVIEW"


def feedback_policy(row: dict[str, Any] | None) -> dict[str, Any]:
    source = row or {}
    return {
        "releaseMode": feedback_release_mode(source.get("feedback_release_mode") or source.get("releaseMode")),
        "showCorrectAnswers": as_bool(source.get("show_correct_answers", source.get("showCorrectAnswers"))),
        "showExplanations": as_bool(source.get("show_explanations", source.get("showExplanations"))),
    }


def student_question(row: dict[str, Any] | None, *, reveal_answers: bool=False, reveal_explanations: bool=False):
    return learning_domain.student_question_action(row, reveal_answers=reveal_answers, reveal_explanations=reveal_explanations, runtime=_learning_runtime())


def student_option(row: dict[str, Any] | None, *, reveal_answers: bool=False):
    return learning_domain.student_option_action(row, reveal_answers=reveal_answers, runtime=_learning_runtime())


def student_answer(row: dict[str, Any] | None, *, reveal_answers: bool = False):
    if not row:
        return None
    result = {
        "answerId": row["answer_id"],
        "attemptId": row.get("attempt_id"),
        "questionId": row.get("question_id"),
        "answerText": row.get("answer_text"),
        "selectedOptionId": row.get("selected_option_id"),
        "savedAt": iso(row.get("saved_at")),
        "submittedAt": iso(row.get("submitted_at")),
    }
    if reveal_answers:
        result["isCorrect"] = None if row.get("is_correct") is None else as_bool(row.get("is_correct"))
    return result


def selected_option_ids(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        values = value
    else:
        raw = str_value(value)
        if not raw:
            return []
        values = [raw]
        if raw.startswith("[") and raw.endswith("]"):
            try:
                decoded = json.loads(raw)
            except (TypeError, ValueError):
                legacy_values = re.findall(r"['\"]([^'\"]+)['\"]", raw)
                decoded = legacy_values if legacy_values else None
            if isinstance(decoded, (list, tuple, set)):
                values = decoded
    return list(dict.fromkeys(str_value(item) for item in values if str_value(item)))


def selected_option_storage(value: Any, question_type: str) -> str:
    selected = selected_option_ids(value)
    if question_type == "MULTIPLE_CHOICE":
        return json.dumps(selected, ensure_ascii=True, separators=(",", ":"))
    return selected[0] if selected else ""


def public_file(row: dict[str, Any] | None):
    if not row:
        return None
    content_available = bool(
        (row.get("storage_status") == "READY" and row.get("storage_bucket") and row.get("storage_path"))
        or str_value(row.get("drive_url"))
    )
    return {
        "fileId": row["file_id"],
        "attemptId": row.get("attempt_id"),
        "studentId": row.get("student_id"),
        "lessonId": row.get("lesson_id"),
        "fileName": row.get("file_name"),
        "mimeType": row.get("mime_type"),
        "sizeBytes": int(row.get("size_bytes") or 0),
        "driveFileId": row.get("drive_file_id"),
        "driveUrl": "",
        "contentUrl": f"/api/files/{row['file_id']}/content" if content_available else "",
        "storageStatus": row.get("storage_status") or ("LEGACY" if row.get("drive_url") else None),
        "uploadedAt": iso(row.get("uploaded_at")),
        "status": row.get("status"),
    }


DEFAULT_NOTIFICATION_PREFERENCES = {
    "MODULE_AVAILABLE": True,
    "SUBMISSION_STATUS": True,
    "REVIEW_FEEDBACK": True,
    "GENERAL": True,
}

NOTIFICATION_TEMPLATE_FIELDS = (
    "internalTitleTemplate",
    "internalMessageTemplate",
    "emailSubjectTemplate",
    "emailMessageTemplate",
    "pushTitleTemplate",
    "pushMessageTemplate",
)

NOTIFICATION_TEMPLATE_VARIABLES = {
    "student_name",
    "course",
    "module",
    "activity",
    "status",
    "deadline",
    "feedback",
    "details",
    "action_url",
}

NOTIFICATION_TEMPLATE_DEFINITIONS = {
    "EMAIL_CHANGED": {
        "label": "Email de acesso alterado",
        "category": "GENERAL",
        "internalTitleTemplate": "Email de acesso alterado",
        "internalMessageTemplate": "O email de acesso foi atualizado. As notificações por email permanecem suspensas até nova autorização no perfil.",
        "emailSubjectTemplate": "Email de acesso alterado",
        "emailMessageTemplate": "Olá, {{student_name}}. O email de acesso foi atualizado. Confirme as preferências de notificações no seu perfil.",
        "pushTitleTemplate": "Email de acesso alterado",
        "pushMessageTemplate": "Reveja as preferências de segurança e notificações no seu perfil.",
    },
    "REVIEW_UPDATED": {
        "label": "Avaliação atualizada",
        "category": "REVIEW_FEEDBACK",
        "internalTitleTemplate": "Avaliação atualizada",
        "internalMessageTemplate": "{{details}}",
        "emailSubjectTemplate": "Atualização da avaliação: {{activity}}",
        "emailMessageTemplate": "Olá, {{student_name}}. A sua avaliação foi atualizada. {{details}}",
        "pushTitleTemplate": "Avaliação atualizada",
        "pushMessageTemplate": "Existe uma atualização em {{activity}}. Consulte os detalhes na plataforma.",
    },
    "RETRY_AUTHORIZED": {
        "label": "Nova tentativa autorizada",
        "category": "SUBMISSION_STATUS",
        "internalTitleTemplate": "Nova tentativa autorizada",
        "internalMessageTemplate": "Pode realizar uma nova tentativa em {{activity}}.",
        "emailSubjectTemplate": "Nova tentativa disponível: {{activity}}",
        "emailMessageTemplate": "Olá, {{student_name}}. Foi autorizada uma nova tentativa em {{activity}}.",
        "pushTitleTemplate": "Nova tentativa disponível",
        "pushMessageTemplate": "Já pode realizar uma nova tentativa em {{activity}}.",
    },
    "SUBMISSION_STATUS_UPDATED": {
        "label": "Estado da submissão atualizado",
        "category": "SUBMISSION_STATUS",
        "internalTitleTemplate": "Estado da submissão atualizado",
        "internalMessageTemplate": "{{details}}",
        "emailSubjectTemplate": "Estado atualizado: {{activity}}",
        "emailMessageTemplate": "Olá, {{student_name}}. O estado da sua submissão foi atualizado. {{details}}",
        "pushTitleTemplate": "Submissão atualizada",
        "pushMessageTemplate": "O estado de {{activity}} foi atualizado. Abra a plataforma para consultar.",
    },
    "SUBMISSION_DEADLINE_UPDATED": {
        "label": "Prazo da submissão atualizado",
        "category": "SUBMISSION_STATUS",
        "internalTitleTemplate": "Prazo da submissão atualizado",
        "internalMessageTemplate": "{{details}}",
        "emailSubjectTemplate": "Novo prazo: {{activity}}",
        "emailMessageTemplate": "Olá, {{student_name}}. O prazo da sua submissão foi atualizado. {{details}}",
        "pushTitleTemplate": "Prazo atualizado",
        "pushMessageTemplate": "Consulte o novo prazo de {{activity}} na plataforma.",
    },
    "MODULE_ACCESS_UPDATED": {
        "label": "Acesso ao módulo atualizado",
        "category": "MODULE_AVAILABLE",
        "internalTitleTemplate": "Acesso ao módulo atualizado",
        "internalMessageTemplate": "{{details}}",
        "emailSubjectTemplate": "Atualização do módulo: {{module}}",
        "emailMessageTemplate": "Olá, {{student_name}}. {{details}}",
        "pushTitleTemplate": "Módulo atualizado",
        "pushMessageTemplate": "Existe uma atualização no módulo {{module}}.",
    },
    "MODULE_PROGRESS_UPDATED": {
        "label": "Estado do módulo atualizado",
        "category": "MODULE_AVAILABLE",
        "internalTitleTemplate": "Módulo atualizado",
        "internalMessageTemplate": "{{details}}",
        "emailSubjectTemplate": "Estado do módulo: {{module}}",
        "emailMessageTemplate": "Olá, {{student_name}}. Os estados do módulo foram atualizados. {{details}}",
        "pushTitleTemplate": "Módulo atualizado",
        "pushMessageTemplate": "Os estados de {{module}} foram atualizados.",
    },
}

NOTIFICATION_STATUS_LABELS = {
    "LOCKED": "Bloqueado",
    "AVAILABLE": "Disponível",
    "NOT_STARTED": "Não iniciado",
    "IN_PROGRESS": "Em curso",
    "UNDER_REVIEW": "Em avaliação",
    "CORRECTION_REQUIRED": "Correção solicitada",
    "APPROVED": "Aprovado",
    "APPROVED_WITH_NOTES": "Aprovado com observações",
    "FAILED": "Não aprovado",
    "TIME_EXCEEDED": "Tempo excedido",
}


def notification_status_label(value: Any) -> str:
    return communication_domain.notification_status_label_action(value, runtime=_communication_runtime())


def notification_preferences(row: dict[str, Any] | None) -> dict[str, bool]:
    return communication_domain.notification_preferences_action(row, runtime=_communication_runtime())


def require_schema_capabilities(
    conn,
    feature: str,
    relations: tuple[str, ...],
    columns: tuple[str, ...] = (),
) -> None:
    missing_relations = [
        row["object_name"]
        for row in conn.execute(
            """
            select object_name
            from unnest(%s::text[]) as requested(object_name)
            where to_regclass(object_name) is null
            order by object_name
            """,
            (list(relations),),
        ).fetchall()
    ]
    missing_columns = []
    if columns:
        missing_columns = [
            row["object_name"]
            for row in conn.execute(
                """
                select object_name
                from unnest(%s::text[]) as requested(object_name)
                where not exists (
                  select 1
                  from information_schema.columns available
                  where available.table_schema = split_part(object_name, '.', 1)
                    and available.table_name = split_part(object_name, '.', 2)
                    and available.column_name = split_part(object_name, '.', 3)
                )
                order by object_name
                """,
                (list(columns),),
            ).fetchall()
        ]
    missing = missing_relations + missing_columns
    if missing:
        raise ApiError(
            "DATABASE_MIGRATION_REQUIRED",
            f"A migração necessária para {feature} ainda não foi aplicada.",
            {"feature": feature, "missingObjects": missing},
        )


def ensure_notification_feature_schema(conn) -> None:
    return communication_domain.ensure_notification_feature_schema_action(conn, runtime=_communication_runtime())


def prepare_notification_feature_schema() -> None:
    return communication_domain.prepare_notification_feature_schema_action(runtime=_communication_runtime())


_NOTIFICATION_TEMPLATE_COLUMNS = {
    "internalTitleTemplate": "internal_title_template",
    "internalMessageTemplate": "internal_message_template",
    "emailSubjectTemplate": "email_subject_template",
    "emailMessageTemplate": "email_message_template",
    "pushTitleTemplate": "push_title_template",
    "pushMessageTemplate": "push_message_template",
}


def _template_tokens(value: Any) -> set[str]:
    return communication_domain._template_tokens_action(value, runtime=_communication_runtime())


def _render_notification_template(value: Any, variables: dict[str, Any], fallback: str, limit: int) -> str:
    return communication_domain._render_notification_template_action(value, variables, fallback, limit, runtime=_communication_runtime())


def notification_template_payload(template_key: str, row: dict[str, Any] | None=None) -> dict[str, Any]:
    return communication_domain.notification_template_payload_action(template_key, row, runtime=_communication_runtime())


def notification_templates_payload() -> list[dict[str, Any]]:
    return communication_domain.notification_templates_payload_action(runtime=_communication_runtime())


def resolve_notification_content(conn, template_key: str, variables: dict[str, Any] | None, title: str, message: str, *, email_subject: str='', email_message: str='', push_title: str='', push_message: str='') -> dict[str, Any]:
    return communication_domain.resolve_notification_content_action(conn, template_key, variables, title, message, email_subject=email_subject, email_message=email_message, push_title=push_title, push_message=push_message, runtime=_communication_runtime())


def public_notification(row: dict[str, Any] | None):
    return communication_domain.public_notification_action(row, runtime=_communication_runtime())


def normalize_whatsapp_recipient(value: Any) -> str:
    return communication_domain.normalize_whatsapp_recipient_action(value, runtime=_communication_runtime())


def normalize_email_recipient(value: Any) -> str:
    return communication_domain.normalize_email_recipient_action(value, runtime=_communication_runtime())


def validated_email_change(payload: dict[str, Any]) -> str:
    """Validate the new account identifier and its explicit confirmation."""
    require_fields(payload, ["newEmail", "confirmEmail"])
    new_email = normalize_email_recipient(payload.get("newEmail"))
    confirmed_email = normalize_email_recipient(payload.get("confirmEmail"))
    if not new_email:
        raise ApiError("INVALID_ACCOUNT_EMAIL", "Informe um endereço de email válido.")
    if not confirmed_email or new_email != confirmed_email:
        raise ApiError("EMAIL_CONFIRMATION_MISMATCH", "A confirmação do novo email não corresponde.")
    return new_email


def verify_password_with_conn(conn, password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    row = conn.execute(
        "select %s = crypt(%s, %s) as ok",
        (password_hash, password, password_hash),
    ).fetchone()
    return bool(row and row.get("ok"))


def secure_student_email_update(
    conn,
    student: dict[str, Any],
    new_email: str,
    *,
    actor_type: str,
    actor_id: str,
    reason: str = "",
) -> dict[str, Any]:
    """Change a login email atomically and retire every unsafe old destination."""
    student_id = student["student_id"]
    old_email = normalize_email(student.get("email"))
    if new_email == old_email:
        raise ApiError("EMAIL_UNCHANGED", "O novo email deve ser diferente do email atual.")
    conflict = conn.execute(
        """
        select student_id
        from courseplatform.students
        where lower(email) = %s and student_id <> %s
        limit 1
        """,
        (new_email, student_id),
    ).fetchone()
    if conflict:
        raise ApiError("EMAIL_ALREADY_IN_USE", "Este endereço de email já está associado a outro estudante.")
    admin_conflict = conn.execute(
        """
        select admin_id
        from courseplatform.admins
        where lower(email) = %s
          and coalesce(student_id, '') <> %s
        limit 1
        """,
        (new_email, student_id),
    ).fetchone()
    if admin_conflict:
        raise ApiError("EMAIL_ALREADY_IN_USE", "Este endereço de email já está associado a outra conta.")

    row = conn.execute(
        """
        update courseplatform.students
        set email = %s,
            email_opt_in = false,
            email_opt_in_at = null,
            updated_at = now()
        where student_id = %s
        returning *
        """,
        (new_email, student_id),
    ).fetchone()
    if not row:
        raise ApiError("STUDENT_NOT_FOUND", "Estudante não encontrado.")

    conn.execute(
        """
        update courseplatform.admins
        set email = %s, updated_at = now()
        where student_id = %s
        """,
        (new_email, student_id),
    )

    conn.execute(
        """
        update courseplatform.notification_deliveries d
        set status = 'SKIPPED',
            last_error = 'Endereço de email alterado; entrega cancelada por segurança.',
            updated_at = now()
        from courseplatform.notifications n
        where n.notification_id = d.notification_id
          and n.student_id = %s
          and d.channel = 'EMAIL'
          and d.status in ('PENDING', 'FAILED', 'PROCESSING')
        """,
        (student_id,),
    )
    revoke_sessions(conn, student_id)
    conn.execute(
        """
        update courseplatform.sessions ses
        set active = false, revoked_at = now()
        where ses.active = true
          and ses.subject_id in (
            select 'ADMIN:' || a.admin_id
            from courseplatform.admins a
            where a.student_id = %s
          )
        """,
        (student_id,),
    )
    create_student_notification(
        conn,
        student_id,
        "GENERAL",
        "Email de acesso alterado",
        "O email de acesso foi atualizado. As notificações por email permanecem suspensas até nova autorização no perfil.",
        action_url="#/profile",
        entity_type="ACCOUNT_SECURITY",
        entity_id=student_id,
        priority="HIGH",
        template_key="EMAIL_CHANGED",
        send_whatsapp=False,
        send_email=False,
        send_telegram=False,
        send_push=False,
    )
    audit(
        conn,
        actor_type,
        actor_id,
        "STUDENT_EMAIL_CHANGED",
        "STUDENT",
        student_id,
        {
            "oldEmail": mask_email(old_email),
            "newEmail": mask_email(new_email),
            "reason": str_value(reason)[:300],
            "sessionsRevoked": True,
            "emailConsentReset": True,
        },
    )
    return row


def normalize_telegram_recipient(value: Any) -> str:
    return communication_domain.normalize_telegram_recipient_action(value, runtime=_communication_runtime())


def redact_notification_error(value: Any, *secrets_to_hide: Any) -> str:
    return communication_domain.redact_notification_error_action(value, *secrets_to_hide, runtime=_communication_runtime())


def notification_encryption_key(settings: Any | None=None) -> str:
    return communication_domain.notification_encryption_key_action(settings, runtime=_communication_runtime())


def decrypt_notification_secret(channel: str, column: str, encryption_key: str) -> str:
    return communication_domain.decrypt_notification_secret_action(channel, column, encryption_key, runtime=_communication_runtime())


def valid_whatsapp_platform_url(value: Any) -> bool:
    return communication_domain.valid_whatsapp_platform_url_action(value, runtime=_communication_runtime())


def valid_notification_host(value: Any) -> bool:
    return communication_domain.valid_notification_host_action(value, runtime=_communication_runtime())


def valid_telegram_bot_token(value: Any) -> bool:
    return communication_domain.valid_telegram_bot_token_action(value, runtime=_communication_runtime())


def normalize_telegram_parse_mode(value: Any) -> str:
    return communication_domain.normalize_telegram_parse_mode_action(value, runtime=_communication_runtime())


def safe_notification_action_url(value: Any) -> str:
    return communication_domain.safe_notification_action_url_action(value, runtime=_communication_runtime())


def whatsapp_runtime_configuration() -> dict[str, Any]:
    return communication_domain.whatsapp_runtime_configuration_action(runtime=_communication_runtime())


def whatsapp_configuration() -> dict[str, Any]:
    return communication_domain.whatsapp_configuration_action(runtime=_communication_runtime())


def email_runtime_configuration(*, prepare_schema: bool=True) -> dict[str, Any]:
    return communication_domain.email_runtime_configuration_action(prepare_schema=prepare_schema, runtime=_communication_runtime())


def email_configuration() -> dict[str, Any]:
    return communication_domain.email_configuration_action(runtime=_communication_runtime())


def telegram_runtime_configuration() -> dict[str, Any]:
    return communication_domain.telegram_runtime_configuration_action(runtime=_communication_runtime())


def telegram_configuration() -> dict[str, Any]:
    return communication_domain.telegram_configuration_action(runtime=_communication_runtime())


def valid_vapid_subject(value: Any) -> bool:
    return communication_domain.valid_vapid_subject_action(value, runtime=_communication_runtime())


def valid_push_endpoint(value: Any) -> bool:
    return communication_domain.valid_push_endpoint_action(value, runtime=_communication_runtime())


def valid_push_key(value: Any, minimum: int, maximum: int) -> bool:
    return communication_domain.valid_push_key_action(value, minimum, maximum, runtime=_communication_runtime())


def valid_vapid_key(value: Any, expected_bytes: int, require_uncompressed_point: bool=False) -> bool:
    return communication_domain.valid_vapid_key_action(value, expected_bytes, require_uncompressed_point, runtime=_communication_runtime())


def web_push_runtime_configuration() -> dict[str, Any]:
    return communication_domain.web_push_runtime_configuration_action(runtime=_communication_runtime())


def web_push_configuration() -> dict[str, Any]:
    return communication_domain.web_push_configuration_action(runtime=_communication_runtime())


def student_notification_channel_info() -> dict[str, Any]:
    return communication_domain.student_notification_channel_info_action(runtime=_communication_runtime())


def create_student_notification(conn, student_id: str, category: str, title: str, message: str, *, admin_id: str | None=None, action_url: str='#/notifications', entity_type: str='', entity_id: str='', priority: str='NORMAL', template_key: str='', template_variables: dict[str, Any] | None=None, email_subject: str='', email_message: str='', push_title: str='', push_message: str='', send_whatsapp: bool=True, send_email: bool=True, send_telegram: bool=True, send_push: bool=True) -> str | None:
    return communication_domain.create_student_notification_action(conn, student_id, category, title, message, admin_id=admin_id, action_url=action_url, entity_type=entity_type, entity_id=entity_id, priority=priority, template_key=template_key, template_variables=template_variables, email_subject=email_subject, email_message=email_message, push_title=push_title, push_message=push_message, send_whatsapp=send_whatsapp, send_email=send_email, send_telegram=send_telegram, send_push=send_push, runtime=_communication_runtime())


def send_whatsapp_template(delivery: dict[str, Any], configuration: dict[str, Any] | None=None) -> str:
    return communication_domain.send_whatsapp_template_action(delivery, configuration, runtime=_communication_runtime())


def resolved_notification_action_url(delivery: dict[str, Any], configuration: dict[str, Any]) -> str:
    return communication_domain.resolved_notification_action_url_action(delivery, configuration, runtime=_communication_runtime())


def _notification_plain_text(delivery: dict[str, Any], action_url: str='') -> str:
    return communication_domain._notification_plain_text_action(delivery, action_url, runtime=_communication_runtime())


def send_email_notification(delivery: dict[str, Any], configuration: dict[str, Any] | None=None) -> str:
    return communication_domain.send_email_notification_action(delivery, configuration, runtime=_communication_runtime())


def dispatch_student_password_reset(reset_id: str, token: str, request_base_url: str='') -> None:
    return communication_domain.dispatch_student_password_reset_action(reset_id, token, request_base_url, runtime=_communication_runtime())


def dispatch_student_account_verification(verification_id: str, token: str, request_base_url: str='') -> bool:
    return communication_domain.dispatch_student_account_verification_action(
        verification_id,
        token,
        request_base_url,
        runtime=_communication_runtime(),
    )


def _telegram_markdown_v2(value: Any) -> str:
    return communication_domain._telegram_markdown_v2_action(value, runtime=_communication_runtime())


def send_telegram_notification(delivery: dict[str, Any], configuration: dict[str, Any] | None=None) -> str:
    return communication_domain.send_telegram_notification_action(delivery, configuration, runtime=_communication_runtime())


def push_subscriptions_for_student(student_id: str, encryption_key: str) -> list[dict[str, Any]]:
    return communication_domain.push_subscriptions_for_student_action(student_id, encryption_key, runtime=_communication_runtime())


def update_push_subscription_delivery(subscription_id: str, success_result: bool, expired: bool=False) -> None:
    return communication_domain.update_push_subscription_delivery_action(subscription_id, success_result, expired, runtime=_communication_runtime())


def send_web_push_notification(delivery: dict[str, Any], configuration: dict[str, Any] | None=None) -> str:
    return communication_domain.send_web_push_notification_action(delivery, configuration, runtime=_communication_runtime())


def student_unread_badge_count(student_id: str) -> int:
    return communication_domain.student_unread_badge_count_action(student_id, runtime=_communication_runtime())


def telegram_get_updates(configuration: dict[str, Any], offset: int=0) -> list[dict[str, Any]]:
    return communication_domain.telegram_get_updates_action(configuration, offset, runtime=_communication_runtime())


def process_telegram_link_updates(configuration: dict[str, Any] | None=None) -> int:
    return communication_domain.process_telegram_link_updates_action(configuration, runtime=_communication_runtime())


def claim_notification_deliveries(channel: str, notification_ids: list[str] | None, limit: int) -> list[dict[str, Any]]:
    return communication_domain.claim_notification_deliveries_action(channel, notification_ids, limit, runtime=_communication_runtime())


def claim_whatsapp_deliveries(notification_ids: list[str] | None, limit: int) -> list[dict[str, Any]]:
    return communication_domain.claim_whatsapp_deliveries_action(notification_ids, limit, runtime=_communication_runtime())


def claim_email_deliveries(notification_ids: list[str] | None, limit: int) -> list[dict[str, Any]]:
    return communication_domain.claim_email_deliveries_action(notification_ids, limit, runtime=_communication_runtime())


def claim_telegram_deliveries(notification_ids: list[str] | None, limit: int) -> list[dict[str, Any]]:
    return communication_domain.claim_telegram_deliveries_action(notification_ids, limit, runtime=_communication_runtime())


def claim_push_deliveries(notification_ids: list[str] | None, limit: int) -> list[dict[str, Any]]:
    return communication_domain.claim_push_deliveries_action(notification_ids, limit, runtime=_communication_runtime())


def deliver_pending_channel(channel: str, configuration_loader, sender, notification_ids: list[str] | None=None, limit: int=50) -> dict[str, int]:
    return communication_domain.deliver_pending_channel_action(channel, configuration_loader, sender, notification_ids, limit, runtime=_communication_runtime())


def deliver_pending_whatsapp(notification_ids: list[str] | None=None, limit: int=50) -> dict[str, int]:
    return communication_domain.deliver_pending_whatsapp_action(notification_ids, limit, runtime=_communication_runtime())


def deliver_pending_email(notification_ids: list[str] | None=None, limit: int=50) -> dict[str, int]:
    return communication_domain.deliver_pending_email_action(notification_ids, limit, runtime=_communication_runtime())


def deliver_pending_telegram(notification_ids: list[str] | None=None, limit: int=50) -> dict[str, int]:
    return communication_domain.deliver_pending_telegram_action(notification_ids, limit, runtime=_communication_runtime())


def deliver_pending_push(notification_ids: list[str] | None=None, limit: int=50) -> dict[str, int]:
    return communication_domain.deliver_pending_push_action(notification_ids, limit, runtime=_communication_runtime())


def dispatch_notification_deliveries(notification_ids: list[str]) -> None:
    return communication_domain.dispatch_notification_deliveries_action(notification_ids, runtime=_communication_runtime())


def ensure_chat_feature_schema(conn) -> None:
    return communication_domain.ensure_chat_feature_schema_action(conn, runtime=_communication_runtime())


def prepare_chat_feature_schema() -> None:
    return communication_domain.prepare_chat_feature_schema_action(runtime=_communication_runtime())


def ensure_chat_realtime_schema(conn) -> bool:
    return communication_domain.ensure_chat_realtime_schema_action(conn, runtime=_communication_runtime())


def _jwt_segment(value: dict[str, Any]) -> str:
    return communication_domain._jwt_segment_action(value, runtime=_communication_runtime())


def chat_realtime_token(actor: dict[str, Any], secret: str, lifetime_minutes: int) -> tuple[str, datetime]:
    return communication_domain.chat_realtime_token_action(actor, secret, lifetime_minutes, runtime=_communication_runtime())


def ensure_assessment_feature_schema(conn) -> None:
    global _ASSESSMENT_SCHEMA_READY
    if _ASSESSMENT_SCHEMA_READY:
        return
    require_schema_capabilities(
        conn,
        "avaliações",
        (
            "courseplatform.lessons",
            "courseplatform.lesson_progress",
            "courseplatform.attempts",
        ),
        (
            "courseplatform.lessons.submission_duration_minutes",
            "courseplatform.lesson_progress.content_access_status",
            "courseplatform.lesson_progress.evaluation_status",
            "courseplatform.attempts.retry_authorized",
            "courseplatform.attempts.assessment_snapshot_json",
        ),
    )
    _ASSESSMENT_SCHEMA_READY = True


def prepare_assessment_feature_schema() -> None:
    if _ASSESSMENT_SCHEMA_READY:
        return
    with connection() as conn:
        ensure_assessment_feature_schema(conn)


def ensure_certificate_feature_schema(conn) -> None:
    global _CERTIFICATE_SCHEMA_READY
    if _CERTIFICATE_SCHEMA_READY:
        return
    require_schema_capabilities(
        conn,
        "certificados",
        (
            "courseplatform.certificates",
            "courseplatform.certificate_settings",
            "courseplatform.certificate_requests",
        ),
        (
            "courseplatform.certificates.certificate_type",
            "courseplatform.certificates.template_snapshot_json",
            "courseplatform.certificates.download_count",
            "courseplatform.certificate_settings.certificate_profile_json",
        ),
    )
    _CERTIFICATE_SCHEMA_READY = True


def public_certificate(row: dict[str, Any] | None):
    if not row:
        return None
    return {
        "certificateId": row["certificate_id"],
        "studentId": row.get("student_id"),
        "courseId": row.get("course_id"),
        "enrollmentId": row.get("enrollment_id"),
        "offeringId": row.get("offering_id"),
        "courseVersionId": row.get("course_version_id"),
        "certificateNumber": row.get("certificate_number"),
        "verificationCode": row.get("verification_code"),
        "issueDate": iso(row.get("issue_date")),
        "finalScore": None if row.get("final_score") is None else float(row["final_score"]),
        "driveUrl": row.get("drive_url"),
        "status": row.get("status"),
        "certificateType": row.get("certificate_type") or "SIMPLE",
        "recognitionLevel": row.get("recognition_level") or "PARTICIPATION",
        "contentSummary": row.get("content_summary"),
        "downloadCount": int(row.get("download_count") or 0),
        "maxDownloads": None if row.get("max_downloads") is None else int(row["max_downloads"]),
        "paymentStatus": row.get("payment_status") or "NOT_REQUIRED",
        "statusNote": row.get("status_note"),
        "statusUpdatedAt": iso(row.get("status_updated_at")),
        "approvedAt": iso(row.get("approved_at")),
        "templateSnapshot": row.get("template_snapshot_json") or {},
        "courseTitle": row.get("course_title") or row.get("title"),
        "studentName": row.get("student_name") or row.get("full_name"),
    }


def public_certificate_request(row: dict[str, Any] | None):
    if not row:
        return None
    receipt_available = bool(
        (
            row.get("payment_receipt_storage_status") == "READY"
            and row.get("payment_receipt_bucket")
            and row.get("payment_receipt_path")
        )
        or str_value(row.get("payment_receipt_url"))
    )
    return {
        "requestId": row["request_id"],
        "studentId": row.get("student_id"),
        "courseId": row.get("course_id"),
        "enrollmentId": row.get("enrollment_id"),
        "offeringId": row.get("offering_id"),
        "courseVersionId": row.get("course_version_id"),
        "certificateId": row.get("certificate_id"),
        "requestType": row.get("request_type"),
        "status": row.get("status"),
        "surveyAnswers": row.get("survey_answers_json") or {},
        "paymentReceiptName": row.get("payment_receipt_name"),
        "paymentReceiptUrl": (
            f"/api/certificate-requests/{row['request_id']}/receipt" if receipt_available else ""
        ),
        "paymentReceiptMimeType": row.get("payment_receipt_mime_type"),
        "paymentReceiptSizeBytes": int(row.get("payment_receipt_size_bytes") or 0),
        "paymentReceiptStorageStatus": row.get("payment_receipt_storage_status") or (
            "LEGACY" if row.get("payment_receipt_url") else None
        ),
        "submittedAt": iso(row.get("submitted_at")),
        "reviewedBy": row.get("reviewed_by"),
        "reviewedAt": iso(row.get("reviewed_at")),
        "adminNotes": row.get("admin_notes"),
        "createdAt": iso(row.get("created_at")),
        "updatedAt": iso(row.get("updated_at")),
        "studentName": row.get("full_name"),
        "studentEmail": row.get("email"),
        "courseTitle": row.get("title"),
        "certificateNumber": row.get("certificate_number"),
        "verificationCode": row.get("verification_code"),
        "certificateIssueDate": iso(row.get("issue_date")),
        "certificateFinalScore": None if row.get("final_score") is None else float(row["final_score"]),
        "certificateType": row.get("certificate_type"),
        "contentSummary": row.get("content_summary"),
    }


def default_certificate_settings(course: dict[str, Any] | None = None):
    course_title = (course or {}).get("title") or "o curso"
    return {
        "congratulationsMessage": (
            f"Parabens pela conclusão de {course_title}. "
            "A sua participação foi registada com sucesso."
        ),
        "surveyQuestions": [
            {"id": "quality", "prompt": "Como avalia a qualidade geral do curso?", "options": ["Excelente", "Muito boa", "Boa", "Precisa melhorar"], "required": True},
            {"id": "methodology", "prompt": "A metodologia facilitou a sua aprendizagem?", "options": ["Sim, totalmente", "Sim, em parte", "Pouco", "Não"], "required": True},
            {"id": "content_relevance", "prompt": "Os conteúdos foram relevantes para os seus objetivos?", "options": ["Muito relevantes", "Relevantes", "Pouco relevantes", "Não relevantes"], "required": True},
            {"id": "materials", "prompt": "Como avalia os materiais disponibilizados?", "options": ["Muito organizados", "Organizados", "Suficientes", "Insuficientes"], "required": True},
            {"id": "practical_activities", "prompt": "As atividades práticas ajudaram a consolidar o conhecimento?", "options": ["Ajudaram muito", "Ajudaram", "Ajudaram pouco", "Não ajudaram"], "required": True},
            {"id": "difficulty", "prompt": "Como classifica o nível de dificuldade do curso?", "options": ["Adequado", "Fácil", "Exigente, mas positivo", "Muito difícil"], "required": True},
            {"id": "support", "prompt": "Como avalia o apoio recebido durante o curso?", "options": ["Excelente", "Bom", "Regular", "Insuficiente"], "required": True},
            {"id": "platform_experience", "prompt": "Como foi a experiencia de uso da plataforma?", "options": ["Muito intuitiva", "Intuitiva", "Aceitavel", "Confusa"], "required": True},
            {"id": "application", "prompt": "Pretende aplicar os conhecimentos aprendidos?", "options": ["Sim, imediatamente", "Sim, futuramente", "Talvez", "Não"], "required": True},
            {"id": "recommendation", "prompt": "Recomendaria este curso a outra pessoa?", "options": ["Sim, com certeza", "Sim", "Talvez", "Não"], "required": True},
        ],
        "professionalPrice": "",
        "paymentInstructions": "Adicione aqui as instruções de pagamento do certificado profissional.",
        "professionalPreviewUrl": "",
        "certificateProfile": default_certificate_profile(course),
    }


def default_certificate_profile(course: dict[str, Any] | None = None):
    course_title = (course or {}).get("title") or "Curso profissional"
    contents = "\n".join([
        "Conteúdos essenciais do curso",
        "Atividades práticas e estudos de caso",
        "Discussão técnica e avaliação final",
    ])
    return {
        "layoutStyle": "qualification",
        "issuerName": "LMTWEBNAIRS",
        "certificateTitle": "Certificado de Qualificação",
        "qualificationType": "Qualificação profissional",
        "issueLocation": "Cidade de Maputo, Moçambique",
        "verificationBaseUrl": "",
        "directorName": "Direção Académica",
        "directorTitle": "Diretor Académico",
        "coordinatorName": "Coordenação do Programa",
        "coordinatorTitle": "Coordenador do Programa",
        "productCredit": "LMTWEBNAIRS Summer School, produto da LMTWEB, desenvolvido pela LEMOTE.",
        "certifiedContents": contents if not course_title else contents.replace("curso", course_title),
        "printAccess": "paid",
        "printFee": "",
        "printCurrency": "MZN",
        "paymentAccountName": "",
        "paymentAccountNumber": "",
        "paymentInstructions": "Adicione aqui as instruções de pagamento do certificado profissional.",
        "participation": normalize_participation_policy(),
        "assets": {
            "logoUrl": "",
            "productLogoUrl": "",
            "directorSignatureUrl": "",
            "academicStampUrl": "",
            "coordinatorSignatureUrl": "",
            "institutionalSealUrl": "",
        },
    }


def normalize_participation_policy(value: Any = None) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    mode = source.get("releaseMode", "automatic")
    if mode not in {"automatic", "approval"}:
        raise ApiError("INVALID_CERTIFICATE_POLICY", "Condição de disponibilização inválida.")
    limit = source.get("maxDownloads")
    if limit not in (None, ""):
        if isinstance(limit, bool) or not str(limit).isdigit() or not 1 <= int(limit) <= 1000:
            raise ApiError("INVALID_CERTIFICATE_POLICY", "O limite deve ser um número inteiro entre 1 e 1000.")
        limit = int(limit)
    else:
        limit = None
    dates = {}
    for key in ("availableFrom", "availableUntil"):
        raw = source.get(key)
        parsed = parse_datetime(raw) if raw else None
        if raw and (not parsed or parsed.tzinfo is None):
            raise ApiError("INVALID_CERTIFICATE_POLICY", "Indique uma data válida com fuso horário.")
        dates[key] = iso(parsed) if parsed else None
    if dates["availableFrom"] and dates["availableUntil"]:
        if parse_datetime(dates["availableUntil"]) <= parse_datetime(dates["availableFrom"]):
            raise ApiError("INVALID_CERTIFICATE_POLICY", "O fim do período deve ser posterior ao início.")
    return {
        "enabled": as_bool(source["enabled"]) if "enabled" in source else True,
        "releaseMode": mode,
        "maxDownloads": limit,
        **dates,
        "instructions": str_value(source.get("instructions"))[:2000],
    }


def participation_policy(conn, course_id: str) -> dict[str, Any]:
    row = conn.execute(
        "select * from courseplatform.certificate_settings where course_id = %s", (course_id,),
    ).fetchone()
    return normalize_participation_policy(((row or {}).get("certificate_profile_json") or {}).get("participation"))


def certificate_download_access(cert: dict[str, Any], policy: dict[str, Any] | None = None):
    count = int(cert.get("download_count") or 0)
    limit = cert.get("max_downloads")
    code, message = "", ""
    if (cert.get("certificate_type") or "SIMPLE") == "SIMPLE":
        policy = normalize_participation_policy(policy)
        limits = [int(value) for value in (limit, policy["maxDownloads"]) if value is not None]
        limit = min(limits) if limits else None
        if not policy["enabled"]:
            code, message = "PARTICIPATION_DISABLED", "Este curso não disponibiliza certificado de participação."
        elif policy["availableFrom"] and utc_now() < parse_datetime(policy["availableFrom"]):
            code, message = "CERTIFICATE_NOT_YET_AVAILABLE", "O período de download ainda não começou."
        elif policy["availableUntil"] and utc_now() >= parse_datetime(policy["availableUntil"]):
            code, message = "CERTIFICATE_WINDOW_CLOSED", "O período de download terminou. Contacte a administração."
        elif policy["releaseMode"] == "approval" and not cert.get("approved_at"):
            code, message = "CERTIFICATE_APPROVAL_REQUIRED", "Solicite a aprovação da administração para baixar o certificado."
    if not code and cert.get("status") != "ISSUED":
        code, message = "CERTIFICATE_ACCESS_BLOCKED", "O acesso a este certificado não está disponível."
    if not code and limit is not None and count >= int(limit):
        code, message = "DOWNLOAD_LIMIT_REACHED", "O limite de downloads deste certificado foi atingido."
    return {"allowed": not code, "code": code, "message": message, "maxDownloads": limit,
            "remainingDownloads": None if limit is None else max(0, int(limit) - count)}


def require_certificate_download_access(conn, cert):
    policy = participation_policy(conn, cert["course_id"]) if (cert.get("certificate_type") or "SIMPLE") == "SIMPLE" else None
    access = certificate_download_access(cert, policy)
    if not access["allowed"]:
        raise ApiError(access["code"], access["message"])
    return access


def student_certificate_payload(cert, policy):
    if not cert or cert.get("status") == "DELETED":
        return None
    if (cert.get("certificate_type") or "SIMPLE") == "SIMPLE" and not policy["enabled"]:
        return None
    result = public_certificate(cert)
    result["downloadAccess"] = certificate_download_access(cert, policy)
    # Withhold document content when the student is not allowed to obtain it.
    if not result["downloadAccess"]["allowed"]:
        result["templateSnapshot"] = {}
        result["driveUrl"] = ""
    return result


def normalize_certificate_profile(value: Any, course: dict[str, Any] | None = None) -> dict[str, Any]:
    defaults = default_certificate_profile(course)
    source = value if isinstance(value, dict) else {}
    assets = source.get("assets") if isinstance(source.get("assets"), dict) else {}
    normalized = {**defaults}
    for key in [
        "layoutStyle",
        "issuerName",
        "certificateTitle",
        "qualificationType",
        "issueLocation",
        "verificationBaseUrl",
        "directorName",
        "directorTitle",
        "coordinatorName",
        "coordinatorTitle",
        "productCredit",
        "certifiedContents",
        "printAccess",
        "printFee",
        "printCurrency",
        "paymentAccountName",
        "paymentAccountNumber",
        "paymentInstructions",
    ]:
        if key in source:
            normalized[key] = str_value(source.get(key))
    normalized["printAccess"] = normalized["printAccess"] if normalized["printAccess"] in {"free", "paid", "blocked"} else defaults["printAccess"]
    normalized["printCurrency"] = normalized["printCurrency"] or defaults["printCurrency"]
    normalized["participation"] = normalize_participation_policy(source.get("participation"))
    normalized["assets"] = {
        key: str_value(assets.get(key))
        for key in defaults["assets"].keys()
    }
    return normalized


def normalize_survey_questions(value: Any) -> list[dict[str, Any]]:
    source = value if isinstance(value, list) else []
    normalized: list[dict[str, Any]] = []
    fallback_options = ["Excelente", "Bom", "Regular", "Precisa melhorar"]
    for index, item in enumerate(source[:10], start=1):
        if isinstance(item, dict):
            prompt = str_value(item.get("prompt") or item.get("question") or item.get("text"))
            options = item.get("options") if isinstance(item.get("options"), list) else []
            clean_options = [str_value(option) for option in options if str_value(option)]
            question_id = str_value(item.get("id")) or f"q{index}"
            required = True if item.get("required") is None else as_bool(item.get("required"))
        else:
            prompt = str_value(item)
            clean_options = fallback_options
            question_id = f"q{index}"
            required = True
        if not prompt:
            continue
        normalized.append({
            "id": question_id,
            "prompt": prompt,
            "options": clean_options[:6] or fallback_options,
            "required": required,
        })
    defaults = default_certificate_settings().get("surveyQuestions", [])
    while len(normalized) < 10 and len(normalized) < len(defaults):
        normalized.append(defaults[len(normalized)])
    return normalized[:10]


def certificate_settings_payload(row: dict[str, Any] | None, course: dict[str, Any] | None = None):
    defaults = default_certificate_settings(course)
    if not row:
        return defaults
    survey_questions = row.get("survey_questions_json") or defaults["surveyQuestions"]
    profile = normalize_certificate_profile(row.get("certificate_profile_json"), course)
    return {
        "congratulationsMessage": row.get("congratulations_message") or defaults["congratulationsMessage"],
        "surveyQuestions": normalize_survey_questions(survey_questions),
        "professionalPrice": row.get("professional_price") or "",
        "paymentInstructions": row.get("payment_instructions") or defaults["paymentInstructions"],
        "professionalPreviewUrl": row.get("professional_preview_url") or "",
        "certificateProfile": profile,
    }


def certificate_template_snapshot(
    conn,
    course_id: str,
    certificate_type: str = "SIMPLE",
    course_version: dict[str, Any] | None = None,
) -> dict[str, Any]:
    course = conn.execute("select * from courseplatform.courses where course_id = %s", (course_id,)).fetchone()
    version = course_version or {}
    document_course = {
        **(course or {}),
        "title": version.get("title") or (course or {}).get("title"),
        "description": version.get("description") or (course or {}).get("description"),
        "total_hours": version.get("total_hours") if version.get("total_hours") is not None else (course or {}).get("total_hours"),
        "passing_score": version.get("passing_score") if version.get("passing_score") is not None else (course or {}).get("passing_score"),
    }
    row = conn.execute("select * from courseplatform.certificate_settings where course_id = %s", (course_id,)).fetchone()
    settings = certificate_settings_payload(row, document_course)
    profile = normalize_certificate_profile(settings.get("certificateProfile"), document_course)
    if not profile.get("certifiedContents"):
        profile["certifiedContents"] = certificate_content_summary(conn, course_id, version)
    return {
        "version": 1,
        "certificateType": certificate_type,
        "capturedAt": iso(utc_now()),
        "courseId": course_id,
        "courseVersionId": version.get("course_version_id"),
        "courseTitle": document_course.get("title"),
        "courseHours": float(document_course.get("total_hours") or 0),
        "profile": profile,
    }


def certificate_token(length: int = 10) -> str:
    import secrets

    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def certificate_number(prefix: str = "LSS") -> str:
    return f"{prefix}-{utc_now().year}-{certificate_token(10)}"


def certificate_verification_code() -> str:
    return f"LSS{utc_now().year}{certificate_token(10)}"


def certificate_content_summary(
    conn,
    course_id: str,
    course_version: dict[str, Any] | None = None,
) -> str:
    version_snapshot = (course_version or {}).get("content_snapshot_json") or {}
    version_lessons = version_snapshot.get("lessons") if isinstance(version_snapshot, dict) else None
    if isinstance(version_lessons, list):
        rows = [
            row for row in version_lessons
            if isinstance(row, dict)
            and str_value(row.get("status") or "ACTIVE").upper() == "ACTIVE"
        ]
        return "\n".join(
            f"Módulo {int(row.get('lesson_number') or 0)}: {row.get('title') or ''}".strip()
            for row in rows
        )
    rows = conn.execute(
        """
        select lesson_number, title, coalesce(summary, '') as summary
        from courseplatform.lessons
        where course_id = %s and coalesce(status, 'ACTIVE') = 'ACTIVE'
        order by lesson_number
        """,
        (course_id,),
    ).fetchall()
    return "\n".join(
        f"Módulo {int(row.get('lesson_number') or 0)}: {row.get('title') or ''}".strip()
        for row in rows
    )


def course_completion_snapshot(
    conn,
    student_id: str,
    course_id: str,
    enrollment_id: str = "",
):
    ensure_assessment_feature_schema(conn)
    enrollment = resolve_student_enrollment_with_conn(conn, student_id, course_id, enrollment_id)
    course = conn.execute("select * from courseplatform.courses where course_id = %s", (course_id,)).fetchone()
    version = conn.execute(
        "select * from courseplatform.course_versions where course_version_id = %s",
        (enrollment["course_version_id"],),
    ).fetchone()
    snapshot = (version or {}).get("content_snapshot_json") or {}
    lessons = [
        item for item in (snapshot.get("lessons") or [])
        if isinstance(item, dict)
        and str_value(item.get("status") or "ACTIVE").upper() == "ACTIVE"
    ]
    lesson_ids = [item.get("lesson_id") for item in lessons if item.get("lesson_id")]
    approved_total = {"total": 0}
    if lesson_ids:
        approved_total = conn.execute(
            """
            select count(distinct lesson_id) as total
            from courseplatform.lesson_progress
            where enrollment_id = %s and lesson_id = any(%s)
              and coalesce(evaluation_status, status) = 'APPROVED'
            """,
            (enrollment["enrollment_id"], lesson_ids),
        ).fetchone()
    total = len(lesson_ids)
    approved = int((approved_total or {}).get("total") or 0)
    progress = float((enrollment or {}).get("progress_percent") or 0)
    completed = bool(enrollment) and (
        enrollment.get("status") == "COMPLETED" or progress >= 100 or (total > 0 and approved >= total)
    )
    document_course = {
        **(course or {}),
        "title": (version or {}).get("title") or (course or {}).get("title"),
        "description": (version or {}).get("description") or (course or {}).get("description"),
        "total_hours": (version or {}).get("total_hours"),
        "passing_score": (version or {}).get("passing_score"),
    }
    return enrollment, document_course, version, total, approved, completed


def sync_enrollment_completion(conn, enrollment: dict[str, Any] | None, completed: bool, final_score: float | None=None):
    return learning_domain.sync_enrollment_completion_action(conn, enrollment, completed, final_score, runtime=_learning_runtime())


def refresh_enrollment_progress(conn, progress_id: str | None):
    return learning_domain.refresh_enrollment_progress_action(conn, progress_id, runtime=_learning_runtime())


def ensure_simple_certificate(
    conn,
    student: dict[str, Any],
    course_id: str,
    enrollment_id: str = "",
):
    return certificate_domain.ensure_simple_certificate_action(
        conn,
        student,
        course_id,
        enrollment_id,
        runtime=_certificate_runtime(),
    )


def create_session(conn, subject_id: str, user_agent: str = "", ip_hash: str = ""):
    plain_token = generate_token()
    token_hash = hash_secret(plain_token)
    expires = session_expiry()
    conn.execute(
        """
        insert into courseplatform.sessions
          (session_token, subject_id, created_at, expires_at, active, user_agent, ip_hash, revoked_at)
        values (%s, %s, %s, %s, true, %s, %s, null)
        """,
        (token_hash, subject_id, utc_now(), expires, user_agent[:500], ip_hash[:128]),
    )
    return {"token": plain_token, "expiresAt": expires}


def revoke_sessions(conn, subject_id: str) -> None:
    conn.execute(
        """
        update courseplatform.sessions
        set active = false, revoked_at = now()
        where subject_id = %s and active = true
        """,
        (subject_id,),
    )


def validate_session(token: str, expected_type: str):
    if not token:
        raise ApiError("SESSION_REQUIRED", "A sessão não foi informada.")
    token_hash = hash_secret(token)
    session = fetch_one(
        "select * from courseplatform.sessions where session_token = %s",
        (token_hash,),
    )
    if not session or not session.get("active"):
        raise ApiError("INVALID_SESSION", "A sessão e inválida ou foi encerrada.")
    if session["expires_at"] <= utc_now():
        with connection() as conn:
            conn.execute(
                "update courseplatform.sessions set active = false, revoked_at = now() where session_token = %s",
                (token_hash,),
            )
            conn.commit()
        raise ApiError("SESSION_EXPIRED", "A sessão expirou. Inicie sessão novamente.")
    is_admin = str(session["subject_id"]).startswith("ADMIN:")
    if expected_type == "ADMIN" and not is_admin:
        raise ApiError("ADMIN_SESSION_REQUIRED", "É necessária uma sessão administrativa.")
    if expected_type == "STUDENT" and is_admin:
        raise ApiError("STUDENT_SESSION_REQUIRED", "É necessária uma sessão de estudante.")
    return session


def validate_session_with_conn(conn, token: str, expected_type: str):
    if not token:
        raise ApiError("SESSION_REQUIRED", "A sessão não foi informada.")
    token_hash = hash_secret(token)
    session = conn.execute(
        "select * from courseplatform.sessions where session_token = %s",
        (token_hash,),
    ).fetchone()
    if not session or not session.get("active"):
        raise ApiError("INVALID_SESSION", "A sessão e inválida ou foi encerrada.")
    if session["expires_at"] <= utc_now():
        conn.execute(
            "update courseplatform.sessions set active = false, revoked_at = now() where session_token = %s",
            (token_hash,),
        )
        conn.commit()
        raise ApiError("SESSION_EXPIRED", "A sessão expirou. Inicie sessão novamente.")
    is_admin = str(session["subject_id"]).startswith("ADMIN:")
    if expected_type == "ADMIN" and not is_admin:
        raise ApiError("ADMIN_SESSION_REQUIRED", "É necessária uma sessão administrativa.")
    if expected_type == "STUDENT" and is_admin:
        raise ApiError("STUDENT_SESSION_REQUIRED", "É necessária uma sessão de estudante.")
    return session


def require_session_token(payload: dict[str, Any], key: str = "sessionToken") -> str:
    token = payload.get(key, "")
    if not token:
        raise ApiError("SESSION_REQUIRED", "A sessão não foi informada.")
    return token


def student_context_with_conn(conn, payload: dict[str, Any]):
    session = validate_session_with_conn(conn, require_session_token(payload), "STUDENT")
    student = conn.execute(
        "select * from courseplatform.students where student_id = %s",
        (session["subject_id"],),
    ).fetchone()
    if not student or student.get("status") != "ACTIVE":
        raise ApiError("STUDENT_NOT_ACTIVE", "A conta do estudante não está ativa.")
    return session, student


def student_context(payload: dict[str, Any]):
    require_session_token(payload)
    with connection() as conn:
        return student_context_with_conn(conn, payload)


def admin_context(payload: dict[str, Any], allowed_roles: set[str] | None = None):
    token = payload.get("adminToken", "")
    if not token:
        raise ApiError("ADMIN_SESSION_REQUIRED", "É necessária uma sessão administrativa.")
    session = validate_session(token, "ADMIN")
    admin_id = str(session["subject_id"]).replace("ADMIN:", "", 1)
    admin = fetch_one(
        """
        select a.*,
               s.student_id as identity_student_id,
               s.email as identity_email,
               s.password_hash as identity_password_hash,
               s.status as identity_status
        from courseplatform.admins a
        left join courseplatform.students s on s.student_id = a.student_id
        where a.admin_id = %s
        """,
        (admin_id,),
    )
    if (
        not admin
        or admin.get("status") != "ACTIVE"
        or (admin.get("student_id") and admin.get("identity_status") != "ACTIVE")
    ):
        raise ApiError("ADMIN_NOT_ACTIVE", "A conta administrativa não está ativa.")
    if allowed_roles and admin.get("role") not in allowed_roles:
        raise ApiError("FORBIDDEN", "O seu perfil não possui permissão para esta operação.")
    return session, admin


def health(_: dict[str, Any]):
    return administration_domain.health_action(_, runtime=_administration_runtime())


def health_diagnostics(payload: dict[str, Any]):
    return administration_domain.health_diagnostics_action(payload, runtime=_administration_runtime())


def public_course_config(payload: dict[str, Any]):
    return catalog_domain.public_course_config_action(payload, runtime=_catalog_runtime())


def read_media_config(course_id: str):
    return catalog_domain.read_media_config_action(course_id, runtime=_catalog_runtime())


def read_media_config_with_conn(conn, course_id: str):
    return catalog_domain.read_media_config_with_conn_action(conn, course_id, runtime=_catalog_runtime())


def persist_media_config(conn, media: dict[str, Any]):
    return catalog_domain.persist_media_config_action(conn, media, runtime=_catalog_runtime())


def decode_raster_data_url(data_url: Any, mime_type: Any, max_bytes: int) -> tuple[str, str, bytes]:
    return administration_domain.decode_raster_data_url_action(data_url, mime_type, max_bytes, runtime=_administration_runtime())


def raster_signature_matches(mime_type: str, file_bytes: bytes) -> bool:
    return administration_domain.raster_signature_matches_action(mime_type, file_bytes, runtime=_administration_runtime())


def normalize_brand_logo_url(value: Any) -> str:
    return administration_domain.normalize_brand_logo_url_action(value, runtime=_administration_runtime())


def upload_raster_asset_to_storage(file_bytes: bytes, mime_type: str, object_path: str) -> tuple[bool, str]:
    return administration_domain.upload_raster_asset_to_storage_action(file_bytes, mime_type, object_path, runtime=_administration_runtime())


def student_visible_media(media: dict[str, Any], student: dict[str, Any]):
    return catalog_domain.student_visible_media_action(media, student, runtime=_catalog_runtime())


def student_media_config(payload: dict[str, Any]):
    return catalog_domain.student_media_config_action(payload, runtime=_catalog_runtime())


def public_media_config(payload: dict[str, Any]):
    return catalog_domain.public_media_config_action(payload, runtime=_catalog_runtime())


def admin_media_config(payload: dict[str, Any]):
    return catalog_domain.admin_media_config_action(payload, runtime=_catalog_runtime())


def _administration_runtime() -> administration_domain.AdministrationRuntime:
    return administration_domain.AdministrationRuntime(
        BRAND_LOGO_MAX_BYTES=BRAND_LOGO_MAX_BYTES,
        EXPECTED_SCHEMA_VERSION=EXPECTED_SCHEMA_VERSION,
        RASTER_IMAGE_MIME_TYPES=RASTER_IMAGE_MIME_TYPES,
        admin_context=admin_context,
        as_bool=as_bool,
        audit=audit,
        certificate_token=certificate_token,
        configured_admin_recovery_hashes=configured_admin_recovery_hashes,
        connection=connection,
        credential_restore_item=credential_restore_item,
        cursor_page_limit=cursor_page_limit,
        cursor_pagination_result=cursor_pagination_result,
        cursor_scope=cursor_scope,
        database_api_error=database_api_error,
        decode_list_cursor=decode_list_cursor,
        decode_raster_data_url=decode_raster_data_url,
        ensure_certificate_feature_schema=ensure_certificate_feature_schema,
        fetch_all=fetch_all,
        fetch_one=fetch_one,
        generate_access_code=generate_access_code,
        generate_id=generate_id,
        get_settings=get_settings,
        iso=iso,
        normalize_email=normalize_email,
        persist_media_config=persist_media_config,
        prepare_assessment_feature_schema=prepare_assessment_feature_schema,
        prepare_chat_feature_schema=prepare_chat_feature_schema,
        prepare_notification_feature_schema=prepare_notification_feature_schema,
        public_admin=public_admin,
        public_certificate=public_certificate,
        public_certificate_request=public_certificate_request,
        public_enrollment=public_enrollment,
        public_group_member=public_group_member,
        public_progress=public_progress,
        public_student=public_student,
        public_student_id=public_student_id,
        raster_signature_matches=raster_signature_matches,
        read_media_config=read_media_config,
        require_fields=require_fields,
        schema_status=schema_status,
        secure_student_email_update=secure_student_email_update,
        serialize_admin=serialize_admin,
        staff_attempt=staff_attempt,
        storage_service_headers=storage_service_headers,
        str_value=str_value,
        success=success,
        upload_raster_asset_to_storage=upload_raster_asset_to_storage,
        utc_now=utc_now,
        valid_password=valid_password,
        validated_email_change=validated_email_change,
        verify_password_with_conn=verify_password_with_conn,
    )


def _learning_runtime() -> learning_domain.LearningRuntime:
    return learning_domain.LearningRuntime(
        ATTEMPT_STATUSES=ATTEMPT_STATUSES,
        CONTENT_ACCESS_STATUSES=CONTENT_ACCESS_STATUSES,
        EVALUATION_STATUSES=EVALUATION_STATUSES,
        admin_context=admin_context,
        as_bool=as_bool,
        audit=audit,
        connection=connection,
        create_student_notification=create_student_notification,
        dashboard_payload=dashboard_payload,
        dispatch_notification_deliveries=dispatch_notification_deliveries,
        ensure_offering_enrollment_with_conn=ensure_offering_enrollment_with_conn,
        feedback_release_mode=feedback_release_mode,
        fetch_all=fetch_all,
        generate_id=generate_id,
        get_settings=get_settings,
        int_value=int_value,
        iso=iso,
        legacy_progress_status=legacy_progress_status,
        notification_status_label=notification_status_label,
        prepare_assessment_feature_schema=prepare_assessment_feature_schema,
        prepare_notification_feature_schema=prepare_notification_feature_schema,
        progress_access_status=progress_access_status,
        progress_evaluation_status=progress_evaluation_status,
        public_content=public_content,
        public_course=public_course,
        public_course_offering=public_course_offering,
        public_course_version=public_course_version,
        public_enrollment=public_enrollment,
        public_lesson=public_lesson,
        public_progress=public_progress,
        public_student=public_student,
        read_media_config_with_conn=read_media_config_with_conn,
        refresh_enrollment_progress=refresh_enrollment_progress,
        require_fields=require_fields,
        require_session_token=require_session_token,
        resolve_course_offering_with_conn=resolve_course_offering_with_conn,
        resolve_student_enrollment_with_conn=resolve_student_enrollment_with_conn,
        str_value=str_value,
        student_attempt=student_attempt,
        student_context=student_context,
        student_context_with_conn=student_context_with_conn,
        student_courses_payload=student_courses_payload,
        student_courses_rows=student_courses_rows,
        student_option=student_option,
        student_question=student_question,
        student_visible_media=student_visible_media,
        success=success,
    )


def _communication_runtime() -> communication_domain.CommunicationRuntime:
    return communication_domain.CommunicationRuntime(
        DEFAULT_NOTIFICATION_PREFERENCES=DEFAULT_NOTIFICATION_PREFERENCES,
        NOTIFICATION_STATUS_LABELS=NOTIFICATION_STATUS_LABELS,
        NOTIFICATION_TEMPLATE_DEFINITIONS=NOTIFICATION_TEMPLATE_DEFINITIONS,
        NOTIFICATION_TEMPLATE_VARIABLES=NOTIFICATION_TEMPLATE_VARIABLES,
        _NOTIFICATION_TEMPLATE_COLUMNS=_NOTIFICATION_TEMPLATE_COLUMNS,
        _jwt_segment=_jwt_segment,
        _notification_plain_text=_notification_plain_text,
        _render_notification_template=_render_notification_template,
        _telegram_markdown_v2=_telegram_markdown_v2,
        _template_tokens=_template_tokens,
        accessible_chat_room=accessible_chat_room,
        admin_context=admin_context,
        as_bool=as_bool,
        audit=audit,
        chat_actor_with_conn=chat_actor_with_conn,
        chat_direct_pair=chat_direct_pair,
        chat_message_body=chat_message_body,
        chat_message_row=chat_message_row,
        chat_message_rows=chat_message_rows,
        chat_realtime_token=chat_realtime_token,
        chat_room_participant_count=chat_room_participant_count,
        chat_room_summary_context=chat_room_summary_context,
        claim_notification_deliveries=claim_notification_deliveries,
        connection=connection,
        create_student_notification=create_student_notification,
        cursor_page_limit=cursor_page_limit,
        cursor_pagination_result=cursor_pagination_result,
        cursor_scope=cursor_scope,
        decode_list_cursor=decode_list_cursor,
        decrypt_notification_secret=decrypt_notification_secret,
        deliver_pending_channel=deliver_pending_channel,
        deliver_pending_email=deliver_pending_email,
        deliver_pending_push=deliver_pending_push,
        deliver_pending_telegram=deliver_pending_telegram,
        deliver_pending_whatsapp=deliver_pending_whatsapp,
        dispatch_notification_deliveries=dispatch_notification_deliveries,
        email_configuration=email_configuration,
        email_runtime_configuration=email_runtime_configuration,
        ensure_chat_feature_schema=ensure_chat_feature_schema,
        ensure_chat_realtime_schema=ensure_chat_realtime_schema,
        ensure_notification_feature_schema=ensure_notification_feature_schema,
        fetch_all=fetch_all,
        fetch_one=fetch_one,
        generate_id=generate_id,
        get_settings=get_settings,
        hash_secret=hash_secret,
        int_value=int_value,
        iso=iso,
        mark_chat_room_read_with_conn=mark_chat_room_read_with_conn,
        normalize_email=normalize_email,
        normalize_email_recipient=normalize_email_recipient,
        normalize_telegram_parse_mode=normalize_telegram_parse_mode,
        normalize_telegram_recipient=normalize_telegram_recipient,
        normalize_whatsapp_recipient=normalize_whatsapp_recipient,
        notification_encryption_key=notification_encryption_key,
        notification_preferences=notification_preferences,
        notification_template_payload=notification_template_payload,
        notification_templates_payload=notification_templates_payload,
        pagination=pagination,
        parse_datetime=parse_datetime,
        prepare_chat_feature_schema=prepare_chat_feature_schema,
        prepare_notification_feature_schema=prepare_notification_feature_schema,
        process_telegram_link_updates=process_telegram_link_updates,
        public_chat_message=public_chat_message,
        public_chat_room=public_chat_room,
        public_notification=public_notification,
        public_student=public_student,
        push_subscriptions_for_student=push_subscriptions_for_student,
        record_chat_message_receipts=record_chat_message_receipts,
        redact_notification_error=redact_notification_error,
        require_fields=require_fields,
        require_schema_capabilities=require_schema_capabilities,
        resolve_notification_content=resolve_notification_content,
        resolved_notification_action_url=resolved_notification_action_url,
        safe_notification_action_url=safe_notification_action_url,
        send_email_notification=send_email_notification,
        send_telegram_notification=send_telegram_notification,
        send_web_push_notification=send_web_push_notification,
        send_whatsapp_template=send_whatsapp_template,
        str_value=str_value,
        student_can_access_chat_room=student_can_access_chat_room,
        student_context=student_context,
        student_context_with_conn=student_context_with_conn,
        student_unread_badge_count=student_unread_badge_count,
        success=success,
        sync_chat_rooms=sync_chat_rooms,
        telegram_configuration=telegram_configuration,
        telegram_get_updates=telegram_get_updates,
        telegram_runtime_configuration=telegram_runtime_configuration,
        touch_chat_presence=touch_chat_presence,
        update_push_subscription_delivery=update_push_subscription_delivery,
        upsert_chat_room=upsert_chat_room,
        upsert_chat_room_read_cursor=upsert_chat_room_read_cursor,
        utc_now=utc_now,
        valid_notification_host=valid_notification_host,
        valid_push_endpoint=valid_push_endpoint,
        valid_push_key=valid_push_key,
        valid_telegram_bot_token=valid_telegram_bot_token,
        valid_vapid_key=valid_vapid_key,
        valid_vapid_subject=valid_vapid_subject,
        valid_whatsapp_platform_url=valid_whatsapp_platform_url,
        validate_session_with_conn=validate_session_with_conn,
        web_push_configuration=web_push_configuration,
        web_push_runtime_configuration=web_push_runtime_configuration,
        webpush=webpush,
        whatsapp_configuration=whatsapp_configuration,
        whatsapp_runtime_configuration=whatsapp_runtime_configuration,
    )


def _catalog_runtime() -> catalog_domain.CatalogRuntime:
    return catalog_domain.CatalogRuntime(
        FEEDBACK_RELEASE_MODES=FEEDBACK_RELEASE_MODES,
        admin_context=admin_context,
        as_bool=as_bool,
        audit=audit,
        connection=connection,
        course_structure_snapshot_with_conn=course_structure_snapshot_with_conn,
        cursor_page_limit=cursor_page_limit,
        cursor_pagination_result=cursor_pagination_result,
        cursor_scope=cursor_scope,
        decode_list_cursor=decode_list_cursor,
        feedback_release_mode=feedback_release_mode,
        fetch_all=fetch_all,
        fetch_one=fetch_one,
        float_value=float_value,
        generate_id=generate_id,
        get_settings=get_settings,
        int_value=int_value,
        iso=iso,
        normalize_brand_logo_url=normalize_brand_logo_url,
        normalize_email=normalize_email,
        persist_media_config=persist_media_config,
        prepare_assessment_feature_schema=prepare_assessment_feature_schema,
        public_content=public_content,
        public_course=public_course,
        public_course_offering=public_course_offering,
        public_course_version=public_course_version,
        public_lesson=public_lesson,
        read_media_config=read_media_config,
        require_fields=require_fields,
        staff_option=staff_option,
        staff_question=staff_question,
        str_value=str_value,
        student_context=student_context,
        student_visible_media=student_visible_media,
        success=success,
        utc_now=utc_now,
    )


def _enrollment_runtime() -> enrollment_domain.EnrollmentRuntime:
    return enrollment_domain.EnrollmentRuntime(
        admin_context=admin_context,
        audit=audit,
        connection=connection,
        cursor_page_limit=cursor_page_limit,
        cursor_pagination_result=cursor_pagination_result,
        cursor_scope=cursor_scope,
        decode_list_cursor=decode_list_cursor,
        ensure_offering_enrollment_with_conn=ensure_offering_enrollment_with_conn,
        fetch_all=fetch_all,
        generate_id=generate_id,
        initialize_enrollment_progress_with_conn=initialize_enrollment_progress_with_conn,
        int_value=int_value,
        iso=iso,
        parse_datetime=parse_datetime,
        public_course=public_course,
        public_course_offering=public_course_offering,
        public_course_version=public_course_version,
        public_enrollment=public_enrollment,
        public_student=public_student,
        require_fields=require_fields,
        require_session_token=require_session_token,
        resolve_course_offering_with_conn=resolve_course_offering_with_conn,
        str_value=str_value,
        student_context_with_conn=student_context_with_conn,
        student_courses_payload=student_courses_payload,
        student_courses_rows=student_courses_rows,
        student_notification_channel_info=student_notification_channel_info,
        success=success,
    )


def _certificate_runtime() -> certificate_domain.CertificateRuntime:
    return certificate_domain.CertificateRuntime(
        admin_context=admin_context,
        as_bool=as_bool,
        audit=audit,
        certificate_content_summary=certificate_content_summary,
        certificate_document_payload=certificate_document_payload,
        certificate_download_access=certificate_download_access,
        certificate_number=certificate_number,
        certificate_settings_payload=certificate_settings_payload,
        certificate_template_snapshot=certificate_template_snapshot,
        certificate_token=certificate_token,
        certificate_verification_code=certificate_verification_code,
        connection=connection,
        course_completion_snapshot=course_completion_snapshot,
        cursor_page_limit=cursor_page_limit,
        cursor_pagination_result=cursor_pagination_result,
        cursor_scope=cursor_scope,
        decode_list_cursor=decode_list_cursor,
        decode_raster_data_url=decode_raster_data_url,
        default_certificate_profile=default_certificate_profile,
        ensure_certificate_feature_schema=ensure_certificate_feature_schema,
        ensure_simple_certificate=ensure_simple_certificate,
        fetch_one=fetch_one,
        generate_id=generate_id,
        get_settings=get_settings,
        iso=iso,
        normalize_certificate_profile=normalize_certificate_profile,
        normalize_participation_policy=normalize_participation_policy,
        normalize_survey_questions=normalize_survey_questions,
        participation_policy=participation_policy,
        public_certificate=public_certificate,
        public_certificate_request=public_certificate_request,
        public_course=public_course,
        public_enrollment=public_enrollment,
        public_student=public_student,
        require_certificate_download_access=require_certificate_download_access,
        require_fields=require_fields,
        str_value=str_value,
        student_certificate_payload=student_certificate_payload,
        student_context=student_context,
        success=success,
        sync_enrollment_completion=sync_enrollment_completion,
        upload_raster_asset_to_storage=upload_raster_asset_to_storage,
    )


def _financial_runtime() -> financial_domain.FinancialRuntime:
    return financial_domain.FinancialRuntime(
        _private_content_payload=_private_content_payload,
        admin_context=admin_context,
        approve_participation_request=approve_participation_request,
        as_bool=as_bool,
        audit=audit,
        certificate_content_summary=certificate_content_summary,
        certificate_number=certificate_number,
        certificate_template_snapshot=certificate_template_snapshot,
        certificate_verification_code=certificate_verification_code,
        connection=connection,
        cursor_page_limit=cursor_page_limit,
        cursor_pagination_result=cursor_pagination_result,
        cursor_scope=cursor_scope,
        decode_list_cursor=decode_list_cursor,
        ensure_certificate_feature_schema=ensure_certificate_feature_schema,
        ensure_simple_certificate=ensure_simple_certificate,
        fetch_one=fetch_one,
        generate_id=generate_id,
        get_settings=get_settings,
        public_certificate=public_certificate,
        public_certificate_request=public_certificate_request,
        require_fields=require_fields,
        resolve_student_enrollment_with_conn=resolve_student_enrollment_with_conn,
        storage_api_error=storage_api_error,
        storage_object_path=storage_object_path,
        str_value=str_value,
        student_context=student_context,
        success=success,
        upload_private_object=upload_private_object,
        validate_upload=validate_upload,
    )


def _identity_runtime() -> identity_domain.IdentityRuntime:
    return identity_domain.IdentityRuntime(
        require_fields=require_fields,
        fetch_one=fetch_one,
        database_api_error=database_api_error,
        verify_password=verify_password,
        connection=connection,
        revoke_sessions=revoke_sessions,
        create_session=create_session,
        public_student=public_student,
        public_admin=public_admin,
        iso=iso,
        success=success,
        get_settings=get_settings,
        utc_now=utc_now,
        generate_id=generate_id,
        hash_secret=hash_secret,
        audit=audit,
        parse_datetime=parse_datetime,
        create_student_notification=create_student_notification,
        configured_admin_recovery_hashes=configured_admin_recovery_hashes,
        verify_admin_recovery_key=verify_admin_recovery_key,
        generate_access_code=generate_access_code,
        mask_email=mask_email,
        prepare_chat_feature_schema=prepare_chat_feature_schema,
        admin_context=admin_context,
        student_context=student_context,
        prepare_notification_feature_schema=prepare_notification_feature_schema,
        as_bool=as_bool,
        normalize_whatsapp_recipient=normalize_whatsapp_recipient,
        normalize_email_recipient=normalize_email_recipient,
        normalize_telegram_recipient=normalize_telegram_recipient,
        notification_preferences=notification_preferences,
        default_notification_preferences=DEFAULT_NOTIFICATION_PREFERENCES,
        student_notification_channel_info=student_notification_channel_info,
        validated_email_change=validated_email_change,
        student_context_with_conn=student_context_with_conn,
        verify_password_with_conn=verify_password_with_conn,
        secure_student_email_update=secure_student_email_update,
    )


def login(payload: dict[str, Any]):
    return identity_domain.login_action(payload, _identity_runtime())


def mask_email(email: str) -> str:
    return identity_domain.mask_email(email)


def password_reset_private_digest(kind: str, value: str) -> str:
    return identity_domain.password_reset_private_digest(kind, value, get_settings())


def password_reset_public_result() -> dict[str, Any]:
    return identity_domain.password_reset_public_result(success)


def recover_student_access(payload: dict[str, Any]):
    return identity_domain.recover_student_access_action(payload, _identity_runtime())


def register_student_account(payload: dict[str, Any]):
    return identity_domain.register_student_account_action(payload, _identity_runtime())


def complete_student_account_verification(payload: dict[str, Any]):
    return identity_domain.complete_student_account_verification_action(payload, _identity_runtime())


def complete_student_password_reset(payload: dict[str, Any]):
    return identity_domain.complete_student_password_reset_action(payload, _identity_runtime())


def admin_login(payload: dict[str, Any]):
    return identity_domain.admin_login_action(payload, _identity_runtime())


def configured_admin_recovery_hashes() -> list[str]:
    settings = get_settings()
    hashes = []
    if settings.admin_recovery_key_hash:
        hashes.append(settings.admin_recovery_key_hash.lower())
    if settings.admin_recovery_key:
        hashes.append(hash_secret(settings.admin_recovery_key))
    return hashes


def verify_admin_recovery_key(recovery_key: str) -> bool:
    provided_hash = hash_secret(str_value(recovery_key))
    return any(constant_time_equals(provided_hash, expected_hash) for expected_hash in configured_admin_recovery_hashes())


def recover_admin_access(payload: dict[str, Any]):
    return identity_domain.recover_admin_access_action(payload, _identity_runtime())


def logout(payload: dict[str, Any]):
    return identity_domain.logout_action(payload, _identity_runtime())


def admin_me(payload: dict[str, Any]):
    return identity_domain.admin_me_action(payload, _identity_runtime())


def course_structure_snapshot_with_conn(conn, course_id: str) -> dict[str, Any]:
    return catalog_domain.course_structure_snapshot_with_conn_action(
        conn,
        course_id,
        runtime=_catalog_runtime(),
    )


def resolve_course_offering_with_conn(conn, course_id: str, offering_id: str = "") -> dict[str, Any]:
    return enrollment_domain.resolve_course_offering_with_conn_action(
        conn,
        course_id,
        offering_id,
        runtime=_enrollment_runtime(),
    )


def resolve_student_enrollment_with_conn(
    conn,
    student_id: str,
    course_id: str = "",
    enrollment_id: str = "",
) -> dict[str, Any]:
    return enrollment_domain.resolve_student_enrollment_with_conn_action(
        conn,
        student_id,
        course_id,
        enrollment_id,
        runtime=_enrollment_runtime(),
    )


def ensure_offering_enrollment_with_conn(
    conn,
    student_id: str,
    offering: dict[str, Any],
    group_id: str | None = None,
) -> dict[str, Any]:
    return enrollment_domain.ensure_offering_enrollment_with_conn_action(
        conn,
        student_id,
        offering,
        group_id,
        runtime=_enrollment_runtime(),
    )


def initialize_enrollment_progress_with_conn(conn, enrollment: dict[str, Any]) -> int:
    return enrollment_domain.initialize_enrollment_progress_with_conn_action(
        conn,
        enrollment,
        runtime=_enrollment_runtime(),
    )


def my_courses(payload: dict[str, Any]):
    return enrollment_domain.my_courses_action(payload, runtime=_enrollment_runtime())


def student_courses_rows(conn, student_id: str):
    return enrollment_domain.student_courses_rows_action(conn, student_id, runtime=_enrollment_runtime())


def student_courses_payload(rows: list[dict[str, Any]]):
    return enrollment_domain.student_courses_payload_action(rows, runtime=_enrollment_runtime())


def dashboard_payload(conn, student: dict[str, Any], course_id: str='', enrollment_id: str=''):
    return learning_domain.dashboard_payload_action(conn, student, course_id, enrollment_id, runtime=_learning_runtime())


def student_home(payload: dict[str, Any]):
    return learning_domain.student_home_action(payload, runtime=_learning_runtime())


def dashboard(payload: dict[str, Any]):
    return learning_domain.dashboard_action(payload, runtime=_learning_runtime())


def get_lesson(payload: dict[str, Any]):
    return learning_domain.get_lesson_action(payload, runtime=_learning_runtime())


def _assessment_runtime() -> assessment_domain.AssessmentRuntime:
    return assessment_domain.AssessmentRuntime(
        ATTEMPT_STATUSES=ATTEMPT_STATUSES,
        CONTENT_ACCESS_STATUSES=CONTENT_ACCESS_STATUSES,
        _private_content_payload=_private_content_payload,
        admin_context=admin_context,
        admin_review_submission=admin_review_submission,
        as_bool=as_bool,
        assessment_snapshot_from_version_lesson=assessment_snapshot_from_version_lesson,
        audit=audit,
        connection=connection,
        correction_deadline=correction_deadline,
        create_student_notification=create_student_notification,
        cursor_page_limit=cursor_page_limit,
        cursor_pagination_result=cursor_pagination_result,
        cursor_scope=cursor_scope,
        decode_list_cursor=decode_list_cursor,
        dispatch_notification_deliveries=dispatch_notification_deliveries,
        editable_attempt=editable_attempt,
        expire_attempt_if_needed=expire_attempt_if_needed,
        expire_overdue_attempts=expire_overdue_attempts,
        feedback_policy=feedback_policy,
        feedback_visibility=feedback_visibility,
        fetch_all=fetch_all,
        fetch_one=fetch_one,
        float_value=float_value,
        generate_id=generate_id,
        get_settings=get_settings,
        grade_objective_answers=grade_objective_answers,
        int_value=int_value,
        iso=iso,
        legacy_progress_status=legacy_progress_status,
        notification_status_label=notification_status_label,
        parse_assessment_snapshot=parse_assessment_snapshot,
        parse_datetime=parse_datetime,
        prepare_assessment_feature_schema=prepare_assessment_feature_schema,
        prepare_notification_feature_schema=prepare_notification_feature_schema,
        progress_access_status=progress_access_status,
        progress_evaluation_status=progress_evaluation_status,
        public_file=public_file,
        public_lesson=public_lesson,
        public_progress=public_progress,
        public_review=public_review,
        public_student=public_student,
        refresh_enrollment_progress=refresh_enrollment_progress,
        require_fields=require_fields,
        require_latest_attempt=require_latest_attempt,
        selected_option_ids=selected_option_ids,
        selected_option_storage=selected_option_storage,
        snapshot_for_attempt_with_conn=snapshot_for_attempt_with_conn,
        staff_answer=staff_answer,
        staff_attempt=staff_attempt,
        staff_option=staff_option,
        staff_question=staff_question,
        start_attempt_with_conn=start_attempt_with_conn,
        storage_api_error=storage_api_error,
        storage_object_path=storage_object_path,
        str_value=str_value,
        student_answer=student_answer,
        student_attempt=student_attempt,
        student_context=student_context,
        student_review=student_review,
        student_snapshot_questions=student_snapshot_questions,
        submission_item=submission_item,
        success=success,
        upload_private_object=upload_private_object,
        utc_now=utc_now,
        validate_upload=validate_upload,
    )


def attempt_status(payload: dict[str, Any]):
    return assessment_domain.attempt_status_action(payload, _assessment_runtime())


def student_push_configuration(payload: dict[str, Any]):
    return communication_domain.student_push_configuration_action(payload, runtime=_communication_runtime())


def student_subscribe_push(payload: dict[str, Any]):
    return communication_domain.student_subscribe_push_action(payload, runtime=_communication_runtime())


def student_unsubscribe_push(payload: dict[str, Any]):
    return communication_domain.student_unsubscribe_push_action(payload, runtime=_communication_runtime())


def student_start_telegram_link(payload: dict[str, Any]):
    return communication_domain.student_start_telegram_link_action(payload, runtime=_communication_runtime())


def student_confirm_telegram_link(payload: dict[str, Any]):
    return communication_domain.student_confirm_telegram_link_action(payload, runtime=_communication_runtime())


def student_unlink_telegram(payload: dict[str, Any]):
    return communication_domain.student_unlink_telegram_action(payload, runtime=_communication_runtime())


def update_my_profile(payload: dict[str, Any]):
    return identity_domain.update_my_profile_action(payload, _identity_runtime())


def my_notifications(payload: dict[str, Any]):
    return communication_domain.my_notifications_action(payload, runtime=_communication_runtime())


def mark_notification_read(payload: dict[str, Any]):
    return communication_domain.mark_notification_read_action(payload, runtime=_communication_runtime())


def change_my_access_code(payload: dict[str, Any]):
    return identity_domain.change_my_access_code_action(payload, _identity_runtime())


def change_my_email(payload: dict[str, Any]):
    return identity_domain.change_my_email_action(payload, _identity_runtime())


def correction_deadline(payload: dict[str, Any]):
    deadline = parse_datetime(payload.get("correctionDeadline"))
    if deadline and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if not deadline or deadline <= utc_now():
        raise ApiError("INVALID_CORRECTION_DEADLINE", "Indique um prazo futuro para o novo envio.")
    return deadline


def require_latest_attempt(conn, attempt):
    newer = conn.execute(
        """select attempt_id from courseplatform.attempts
           where progress_id = %s and attempt_number > %s limit 1""",
        (attempt["progress_id"], attempt["attempt_number"]),
    ).fetchone()
    if newer:
        raise ApiError("ATTEMPT_SUPERSEDED", "Já existe uma tentativa mais recente. Abra essa tentativa para gerir o reenvio.")


def editable_attempt(conn, attempt_id, student_id):
    conn.execute(
        """select p.progress_id from courseplatform.lesson_progress p
           join courseplatform.attempts a on a.progress_id = p.progress_id
           where a.attempt_id = %s and a.student_id = %s for update of p""",
        (attempt_id, student_id),
    ).fetchone()
    attempt = conn.execute(
        """select a.*, p.content_access_status, p.status as progress_status
           from courseplatform.attempts a
           join courseplatform.lesson_progress p on p.progress_id = a.progress_id
           where a.attempt_id = %s and a.student_id = %s for update of a""",
        (attempt_id, student_id),
    ).fetchone()
    if not attempt or attempt["status"] != "IN_PROGRESS":
        raise ApiError("ATTEMPT_NOT_EDITABLE", "Esta tentativa já não pode ser alterada. Solicite autorização para um novo envio.")
    deadline = parse_datetime(attempt.get("deadline_at"))
    if deadline and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if deadline and deadline <= utc_now():
        raise ApiError("ATTEMPT_TIME_EXCEEDED", "O prazo terminou. Solicite à administração autorização para um novo envio.")
    access = attempt.get("content_access_status") or ("LOCKED" if attempt.get("progress_status") == "LOCKED" else "AVAILABLE")
    if access != "AVAILABLE":
        raise ApiError("LESSON_LOCKED", "Este módulo não está disponível para alterações.")
    require_latest_attempt(conn, attempt)
    return attempt


def parse_assessment_snapshot(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def assessment_snapshot_with_conn(conn, lesson_id: str, lesson: dict[str, Any] | None = None) -> dict[str, Any]:
    lesson_row = lesson or conn.execute(
        """select lesson_id, feedback_release_mode, show_correct_answers, show_explanations
           from courseplatform.lessons where lesson_id = %s""",
        (lesson_id,),
    ).fetchone()
    if not lesson_row:
        raise ApiError("LESSON_NOT_FOUND", "Módulo não encontrado.")
    questions = conn.execute(
        """select question_id, lesson_id, question_order, question_type, prompt, points,
                  correct_answer, explanation, is_required, status
           from courseplatform.questions
           where lesson_id = %s and coalesce(status, 'ACTIVE') = 'ACTIVE'
           order by question_order""",
        (lesson_id,),
    ).fetchall()
    question_ids = [row["question_id"] for row in questions]
    options_by_question: dict[str, list[dict[str, Any]]] = {question_id: [] for question_id in question_ids}
    if question_ids:
        options = conn.execute(
            """select option_id, question_id, option_order, option_label, option_text, is_correct
               from courseplatform.question_options
               where question_id = any(%s)
               order by question_id, option_order""",
            (question_ids,),
        ).fetchall()
        for option in options:
            options_by_question[option["question_id"]].append({
                "option_id": option["option_id"],
                "question_id": option.get("question_id"),
                "option_order": int_value(option.get("option_order")),
                "option_label": option.get("option_label"),
                "option_text": option.get("option_text"),
                "is_correct": as_bool(option.get("is_correct")),
            })
    snapshot_questions = [
        {
            "question_id": question["question_id"],
            "lesson_id": question.get("lesson_id"),
            "question_order": int_value(question.get("question_order")),
            "question_type": question.get("question_type"),
            "prompt": question.get("prompt"),
            "points": float_value(question.get("points")),
            "correct_answer": question.get("correct_answer"),
            "explanation": question.get("explanation"),
            "is_required": as_bool(question.get("is_required")),
            "status": question.get("status"),
            "options": options_by_question.get(question["question_id"], []),
        }
        for question in questions
    ]
    policy = feedback_policy(lesson_row)
    digest_payload = json.dumps(
        {"feedbackPolicy": policy, "questions": snapshot_questions},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return {
        "version": 1,
        "capturedAt": iso(utc_now()),
        "feedbackPolicy": policy,
        "questions": snapshot_questions,
        "digest": hashlib.sha256(digest_payload.encode("utf-8")).hexdigest(),
    }


def assessment_snapshot_from_version_lesson(lesson: dict[str, Any]) -> dict[str, Any]:
    questions = [
        question for question in (lesson.get("questions") or [])
        if isinstance(question, dict)
        and str_value(question.get("status") or "ACTIVE").upper() == "ACTIVE"
    ]
    policy = feedback_policy(lesson)
    digest_payload = json.dumps(
        {"feedbackPolicy": policy, "questions": questions},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return {
        "version": 1,
        "capturedAt": iso(utc_now()),
        "feedbackPolicy": policy,
        "questions": questions,
        "digest": hashlib.sha256(digest_payload.encode("utf-8")).hexdigest(),
    }


def snapshot_for_attempt_with_conn(conn, attempt: dict[str, Any]) -> dict[str, Any]:
    snapshot = parse_assessment_snapshot(attempt.get("assessment_snapshot_json"))
    if isinstance(snapshot.get("questions"), list):
        return snapshot
    raise ApiError(
        "ASSESSMENT_SNAPSHOT_MISSING",
        "A versão desta avaliação não está disponível. A administração deve validar a migração antes de continuar.",
    )


def feedback_visibility(attempt: dict[str, Any], snapshot: dict[str, Any]) -> tuple[bool, bool]:
    policy = feedback_policy(snapshot.get("feedbackPolicy"))
    mode = policy["releaseMode"]
    released = mode == "AFTER_SUBMISSION" and bool(attempt.get("submitted_at"))
    released = released or (
        mode == "AFTER_REVIEW"
        and bool(attempt.get("reviewed_at"))
        and str_value(attempt.get("status")).upper() in {"APPROVED", "CORRECTION_REQUIRED", "FAILED"}
    )
    if mode == "NEVER":
        released = False
    return (
        released and policy["showCorrectAnswers"],
        released and policy["showExplanations"],
    )


def student_snapshot_questions(attempt: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    reveal_answers, reveal_explanations = feedback_visibility(attempt, snapshot)
    return [
        {
            **student_question(
                question,
                reveal_answers=reveal_answers,
                reveal_explanations=reveal_explanations,
            ),
            "options": [
                student_option(option, reveal_answers=reveal_answers)
                for option in question.get("options", [])
            ],
        }
        for question in snapshot.get("questions", [])
        if isinstance(question, dict)
    ]


def grade_objective_answers(
    snapshot: dict[str, Any],
    answers: list[dict[str, Any]],
) -> tuple[float | None, list[tuple[bool, float, str]]]:
    answer_by_question = {row["question_id"]: row for row in answers}
    total_points = 0.0
    awarded_total = 0.0
    results: list[tuple[bool, float, str]] = []
    for question in snapshot.get("questions", []):
        if not isinstance(question, dict) or str_value(question.get("question_type")).upper() not in OBJECTIVE_QUESTION_TYPES:
            continue
        points = max(0.0, float_value(question.get("points")))
        total_points += points
        answer = answer_by_question.get(question.get("question_id")) or {}
        selected = set(selected_option_ids(answer.get("selected_option_id")))
        correct = {
            str_value(option.get("option_id"))
            for option in question.get("options", [])
            if isinstance(option, dict) and as_bool(option.get("is_correct"))
        }
        if not correct and question.get("correct_answer") not in (None, ""):
            correct = set(selected_option_ids(question.get("correct_answer")))
        is_correct = bool(correct) and selected == correct
        awarded = points if is_correct else 0.0
        awarded_total += awarded
        if answer.get("answer_id"):
            results.append((is_correct, awarded, answer["answer_id"]))
    score = round((awarded_total / total_points) * 100, 2) if total_points > 0 else None
    return score, results


def start_attempt(payload: dict[str, Any]):
    return assessment_domain.start_attempt_action(payload, _assessment_runtime())


def start_attempt_with_conn(conn, student, lesson_id, enrollment_id: str = ""):
    return assessment_domain.start_attempt_with_conn_action(
        conn,
        student,
        lesson_id,
        enrollment_id,
        runtime=_assessment_runtime(),
    )


def save_answer(payload: dict[str, Any]):
    return assessment_domain.save_answer_action(payload, _assessment_runtime())


def upload_file(payload: dict[str, Any]):
    return assessment_domain.upload_file_action(payload, _assessment_runtime())


def delete_uploaded_file(payload: dict[str, Any]):
    return assessment_domain.delete_uploaded_file_action(payload, _assessment_runtime())


def submit_attempt(payload: dict[str, Any]):
    return assessment_domain.submit_attempt_action(payload, _assessment_runtime())


def my_certificate(payload: dict[str, Any]):
    return certificate_domain.my_certificate_action(payload, _certificate_runtime())


def my_certifications(payload: dict[str, Any]):
    return certificate_domain.my_certifications_action(payload, _certificate_runtime())


def request_participation_certificate(payload: dict[str, Any]):
    return certificate_domain.request_participation_certificate_action(payload, _certificate_runtime())


def request_professional_certificate(payload: dict[str, Any]):
    return certificate_domain.request_professional_certificate_action(payload, _certificate_runtime())


def submit_professional_certificate_payment(payload: dict[str, Any]):
    return financial_domain.submit_professional_certificate_payment_action(payload, _financial_runtime())


def _private_content_payload(
    row: dict[str, Any],
    *,
    bucket_field: str,
    path_field: str,
    checksum_field: str,
    status_field: str,
    legacy_url_field: str,
    file_name_field: str,
    mime_type_field: str,
    size_field: str,
) -> dict[str, Any]:
    settings = get_settings()
    legacy_url = str_value(row.get(legacy_url_field))
    if row.get(status_field) == "READY" and row.get(bucket_field) and row.get(path_field):
        try:
            content = download_private_object(
                row[bucket_field],
                row[path_field],
                settings.storage_legacy_read_max_bytes,
            )
        except StorageError as error:
            raise storage_api_error(error) from error
        expected_checksum = str_value(row.get(checksum_field))
        if expected_checksum and not hmac.compare_digest(hashlib.sha256(content).hexdigest(), expected_checksum):
            raise ApiError("FILE_INTEGRITY_ERROR", "A integridade do ficheiro armazenado não pôde ser confirmada.")
        return {
            "content": content,
            "fileName": row.get(file_name_field) or "ficheiro",
            "mimeType": row.get(mime_type_field) or "application/octet-stream",
        }
    external_url = legacy_external_url(legacy_url)
    if external_url:
        return {"redirectUrl": external_url, "fileName": row.get(file_name_field) or "ficheiro"}
    try:
        content, legacy_mime = decode_legacy_data_url(legacy_url, settings.storage_legacy_read_max_bytes)
    except StorageError as error:
        raise storage_api_error(error) from error
    return {
        "content": content,
        "fileName": row.get(file_name_field) or "ficheiro",
        "mimeType": row.get(mime_type_field) or legacy_mime or "application/octet-stream",
        "sizeBytes": int(row.get(size_field) or len(content)),
    }


def submission_file_download_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return assessment_domain.submission_file_download_payload_action(payload, _assessment_runtime())


def certificate_receipt_download_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return financial_domain.certificate_receipt_download_payload_action(payload, _financial_runtime())


def record_certificate_download(payload: dict[str, Any]):
    return certificate_domain.record_certificate_download_action(payload, _certificate_runtime())


def certificate_pdf_payload(payload: dict[str, Any]):
    return certificate_domain.certificate_pdf_payload_action(payload, _certificate_runtime())


def admin_certificate_pdf_payload(payload: dict[str, Any]):
    return certificate_domain.admin_certificate_pdf_payload_action(payload, _certificate_runtime())


def certificate_workload_label(snapshot: dict[str, Any] | None, course_hours: Any = None) -> str:
    snapshot_hours = snapshot.get("courseHours") if isinstance(snapshot, dict) else None
    raw_hours = snapshot_hours if snapshot_hours not in (None, "") else course_hours
    try:
        hours = float(raw_hours)
    except (TypeError, ValueError):
        hours = 0
    if not math.isfinite(hours) or hours <= 0:
        raise ApiError(
            "CERTIFICATE_DATA_INCOMPLETE",
            "A carga horária do certificado não está definida. Atualize o formato antes de gerar o PDF.",
        )
    value = str(int(hours)) if hours.is_integer() else f"{hours:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{value} horas"


def certificate_document_payload(
    row: dict[str, Any],
    snapshot: dict[str, Any] | None,
    verification_base_url: str,
) -> dict[str, Any]:
    final_score = row.get("final_score")
    if final_score is None:
        final_score = row.get("enrollment_score")
    certificate = public_certificate({**row, "final_score": final_score})
    model = "professional" if certificate.get("certificateType") == "PROFESSIONAL" else "participation"
    verification_code = certificate.get("verificationCode") or certificate.get("certificateNumber") or ""
    separator = "&" if "?" in verification_base_url else "?"
    verification_url = (
        f"{verification_base_url}{separator}code={verification_code}"
        if verification_code
        else verification_base_url
    )
    profile = normalize_certificate_profile(
        (snapshot or {}).get("profile"),
        {"title": certificate.get("courseTitle")},
    )
    profile["assets"] = {**(profile.get("assets") or {})}
    return {
        "certificate": certificate,
        "model": model,
        "pdfData": {
            "issuer_name": profile.get("issuerName") or "LMTWEBNAIRS Summer School",
            "student_name": certificate.get("studentName"),
            "course_title": certificate.get("courseTitle"),
            "certificate_number": certificate.get("certificateNumber"),
            "verification_code": verification_code,
            "verification_url": verification_url,
            "issue_date": certificate.get("issueDate"),
            "final_score": certificate.get("finalScore"),
            "content_summary": profile.get("certifiedContents") or certificate.get("contentSummary"),
            "workload": certificate_workload_label(snapshot, row.get("course_hours")),
            "certificate_profile": profile,
        },
    }


def admin_platform_statistics(payload: dict[str, Any]):
    return administration_domain.admin_platform_statistics_action(payload, runtime=_administration_runtime())


def admin_list_courses(payload: dict[str, Any]):
    return catalog_domain.admin_list_courses_action(payload, runtime=_catalog_runtime())


def admin_course_structure(payload: dict[str, Any]):
    return catalog_domain.admin_course_structure_action(payload, runtime=_catalog_runtime())


def admin_list_groups(payload: dict[str, Any]):
    return enrollment_domain.admin_list_groups_action(payload, runtime=_enrollment_runtime())


def admin_list_students(payload: dict[str, Any]):
    return administration_domain.admin_list_students_action(payload, runtime=_administration_runtime())


def admin_list_staff(payload: dict[str, Any]):
    return administration_domain.admin_list_staff_action(payload, runtime=_administration_runtime())


def submission_item(row: dict[str, Any]):
    student = {
        "student_id": row.get("attempt_student_id") or row.get("student_id"),
        "public_student_id": row.get("public_student_id"),
        "full_name": row.get("full_name") or "Estudante sem cadastro",
        "email": row.get("email") or "",
        "status": row.get("student_status") or "UNKNOWN",
        "country": row.get("country"),
        "organization": row.get("organization"),
        "phone": row.get("phone"),
        "job_title": row.get("job_title"),
        "interests": row.get("interests"),
        "profile_photo_url": row.get("profile_photo_url"),
        "created_at": row.get("student_created_at"),
        "last_login_at": row.get("last_login_at"),
    }
    lesson = {
        "lesson_id": row.get("attempt_lesson_id") or row.get("lesson_id"),
        "course_id": row.get("course_id"),
        "lesson_number": row.get("lesson_number"),
        "title": row.get("title") or row.get("attempt_lesson_id") or "Módulo sem título",
        "slug": row.get("slug"),
        "summary": row.get("summary"),
        "theory_minutes": row.get("theory_minutes"),
        "exercise_minutes": row.get("exercise_minutes"),
        "individual_minutes": row.get("individual_minutes"),
        "passing_score": row.get("passing_score"),
        "prerequisite_lesson_id": row.get("prerequisite_lesson_id"),
        "status": row.get("lesson_status"),
    }
    review = None
    if row.get("review_id"):
        review = {
            "review_id": row.get("review_id"),
            "attempt_id": row.get("attempt_id"),
            "reviewer_id": row.get("reviewer_id"),
            "decision": row.get("decision"),
            "score": row.get("review_score"),
            "comments": row.get("comments"),
            "correction_deadline": row.get("correction_deadline"),
            "unlock_next_lesson": row.get("unlock_next_lesson"),
            "reviewed_at": row.get("review_reviewed_at"),
        }
    return {
        "student": public_student(student),
        "lesson": public_lesson(lesson),
        "progress": public_progress({
            "progress_id": row.get("progress_id") or "",
            "lesson_id": row.get("attempt_lesson_id") or row.get("lesson_id"),
            "status": row.get("progress_status") or row.get("status"),
            "content_access_status": row.get("content_access_status"),
            "evaluation_status": row.get("evaluation_status"),
            "score": row.get("progress_score"),
            "attempt_count": row.get("progress_attempt_count"),
        }),
        "attempt": staff_attempt(row),
        "latestReview": public_review(review),
        "fileCount": int(row.get("file_count") or 0),
    }


def admin_list_submissions(payload: dict[str, Any]):
    return assessment_domain.admin_list_submissions_action(payload, _assessment_runtime())


def admin_create_course_version(payload: dict[str, Any]):
    return catalog_domain.admin_create_course_version_action(payload, runtime=_catalog_runtime())


def admin_publish_course_version(payload: dict[str, Any]):
    return catalog_domain.admin_publish_course_version_action(payload, runtime=_catalog_runtime())


def admin_save_course_offering(payload: dict[str, Any]):
    return enrollment_domain.admin_save_course_offering_action(payload, runtime=_enrollment_runtime())


def admin_enroll_students_in_offering(payload: dict[str, Any]):
    return enrollment_domain.admin_enroll_students_in_offering_action(payload, runtime=_enrollment_runtime())


def admin_list_course_reconciliation_issues(payload: dict[str, Any]):
    return enrollment_domain.admin_list_course_reconciliation_issues_action(payload, runtime=_enrollment_runtime())


def admin_get_submission(payload: dict[str, Any]):
    return assessment_domain.admin_get_submission_action(payload, _assessment_runtime())


def admin_review_submission(payload: dict[str, Any]):
    return assessment_domain.admin_review_submission_action(payload, _assessment_runtime())


def admin_authorize_retry(payload: dict[str, Any]):
    return assessment_domain.admin_authorize_retry_action(payload, _assessment_runtime())


def admin_update_attempt(payload: dict[str, Any]):
    return assessment_domain.admin_update_attempt_action(payload, _assessment_runtime())


def admin_save_media_config(payload: dict[str, Any]):
    return catalog_domain.admin_save_media_config_action(payload, runtime=_catalog_runtime())


def admin_save_staff(payload: dict[str, Any]):
    return administration_domain.admin_save_staff_action(payload, runtime=_administration_runtime())


def admin_set_staff_status(payload: dict[str, Any]):
    return administration_domain.admin_set_staff_status_action(payload, runtime=_administration_runtime())


def admin_create_student(payload: dict[str, Any]):
    return administration_domain.admin_create_student_action(payload, runtime=_administration_runtime())


def admin_change_student_email(payload: dict[str, Any]):
    return administration_domain.admin_change_student_email_action(payload, runtime=_administration_runtime())


def admin_set_student_status(payload: dict[str, Any]):
    return administration_domain.admin_set_student_status_action(payload, runtime=_administration_runtime())


def admin_reset_student_access_code(payload: dict[str, Any]):
    return administration_domain.admin_reset_student_access_code_action(payload, runtime=_administration_runtime())


def credential_restore_item(kind: str, row: dict[str, Any], temporary_password: str) -> dict[str, Any]:
    return administration_domain.credential_restore_item_action(kind, row, temporary_password, runtime=_administration_runtime())


def admin_restore_credentials(payload: dict[str, Any]):
    return administration_domain.admin_restore_credentials_action(payload, runtime=_administration_runtime())


def admin_save_course(payload: dict[str, Any]):
    return catalog_domain.admin_save_course_action(payload, runtime=_catalog_runtime())


def admin_save_lesson(payload: dict[str, Any]):
    return catalog_domain.admin_save_lesson_action(payload, runtime=_catalog_runtime())


def admin_save_lesson_content(payload: dict[str, Any]):
    return catalog_domain.admin_save_lesson_content_action(payload, runtime=_catalog_runtime())


def admin_save_group(payload: dict[str, Any]):
    return enrollment_domain.admin_save_group_action(payload, runtime=_enrollment_runtime())


def admin_assign_students_to_group(payload: dict[str, Any]):
    return enrollment_domain.admin_assign_students_to_group_action(payload, runtime=_enrollment_runtime())


def admin_set_lesson_access(payload: dict[str, Any]):
    return learning_domain.admin_set_lesson_access_action(payload, runtime=_learning_runtime())


def admin_manage_lesson_progress(payload: dict[str, Any]):
    return learning_domain.admin_manage_lesson_progress_action(payload, runtime=_learning_runtime())


def admin_student_details(payload: dict[str, Any]):
    return administration_domain.admin_student_details_action(payload, runtime=_administration_runtime())


def admin_list_certificate_requests(payload: dict[str, Any]):
    return financial_domain.admin_list_certificate_requests_action(payload, _financial_runtime())


def admin_list_certificates(payload: dict[str, Any]):
    return certificate_domain.admin_list_certificates_action(payload, _certificate_runtime())


def admin_set_certificate_status(payload: dict[str, Any]):
    return certificate_domain.admin_set_certificate_status_action(payload, _certificate_runtime())


def admin_refresh_certificate_format(payload: dict[str, Any]):
    return certificate_domain.admin_refresh_certificate_format_action(payload, _certificate_runtime())


def admin_delete_certificate(payload: dict[str, Any]):
    return certificate_domain.admin_delete_certificate_action(payload, _certificate_runtime())


def approve_participation_request(conn, request, admin):
    return financial_domain.approve_participation_request_action(
        conn,
        request,
        admin,
        _financial_runtime(),
    )


def admin_review_certificate_request(payload: dict[str, Any]):
    return financial_domain.admin_review_certificate_request_action(payload, _financial_runtime())


def admin_delete_certificate_request(payload: dict[str, Any]):
    return financial_domain.admin_delete_certificate_request_action(payload, _financial_runtime())


def admin_get_certificate_settings(payload: dict[str, Any]):
    return certificate_domain.admin_get_certificate_settings_action(payload, _certificate_runtime())


def admin_save_certificate_settings(payload: dict[str, Any]):
    return certificate_domain.admin_save_certificate_settings_action(payload, _certificate_runtime())


def admin_list_certificate_surveys(payload: dict[str, Any]):
    return certificate_domain.admin_list_certificate_surveys_action(payload, _certificate_runtime())


def admin_save_certificate_survey(payload: dict[str, Any]):
    return certificate_domain.admin_save_certificate_survey_action(payload, _certificate_runtime())


def admin_upload_certificate_asset(payload: dict[str, Any]):
    return certificate_domain.admin_upload_certificate_asset_action(payload, _certificate_runtime())


def admin_upload_brand_logo(payload: dict[str, Any]):
    return administration_domain.admin_upload_brand_logo_action(payload, runtime=_administration_runtime())


def verify_certificate(payload: dict[str, Any]):
    return certificate_domain.verify_certificate_action(payload, _certificate_runtime())


def admin_list_notifications(payload: dict[str, Any]):
    return communication_domain.admin_list_notifications_action(payload, runtime=_communication_runtime())


def admin_create_notification(payload: dict[str, Any]):
    return communication_domain.admin_create_notification_action(payload, runtime=_communication_runtime())


def admin_save_notification_template(payload: dict[str, Any]):
    return communication_domain.admin_save_notification_template_action(payload, runtime=_communication_runtime())


def admin_reset_notification_template(payload: dict[str, Any]):
    return communication_domain.admin_reset_notification_template_action(payload, runtime=_communication_runtime())


def admin_save_whatsapp_configuration(payload: dict[str, Any]):
    return communication_domain.admin_save_whatsapp_configuration_action(payload, runtime=_communication_runtime())


def admin_save_email_configuration(payload: dict[str, Any]):
    return communication_domain.admin_save_email_configuration_action(payload, runtime=_communication_runtime())


def admin_save_telegram_configuration(payload: dict[str, Any]):
    return communication_domain.admin_save_telegram_configuration_action(payload, runtime=_communication_runtime())


def admin_retry_notification_deliveries(payload: dict[str, Any]):
    return communication_domain.admin_retry_notification_deliveries_action(payload, runtime=_communication_runtime())


def chat_message_body(value: Any) -> str:
    return communication_domain.chat_message_body_action(value, runtime=_communication_runtime())


def touch_chat_presence(conn, actor: dict[str, Any], room_id: str='') -> None:
    return communication_domain.touch_chat_presence_action(conn, actor, room_id, runtime=_communication_runtime())


def chat_actor_with_conn(conn, payload: dict[str, Any]) -> dict[str, Any]:
    return communication_domain.chat_actor_with_conn_action(conn, payload, runtime=_communication_runtime())


def upsert_chat_room(conn, room_key: str, room_type: str, name: str, description: str, *, course_id: str | None=None, group_id: str | None=None, owner_student_id: str | None=None, direct_student_one_id: str | None=None, direct_student_two_id: str | None=None) -> dict[str, Any] | None:
    return communication_domain.upsert_chat_room_action(conn, room_key, room_type, name, description, course_id=course_id, group_id=group_id, owner_student_id=owner_student_id, direct_student_one_id=direct_student_one_id, direct_student_two_id=direct_student_two_id, runtime=_communication_runtime())


def chat_direct_pair(student_a: str, student_b: str) -> tuple[str, str]:
    return communication_domain.chat_direct_pair_action(student_a, student_b, runtime=_communication_runtime())


def sync_chat_rooms(conn, actor: dict[str, Any]) -> None:
    return communication_domain.sync_chat_rooms_action(conn, actor, runtime=_communication_runtime())


def student_can_access_chat_room(conn, student_id: str, room: dict[str, Any]) -> bool:
    return communication_domain.student_can_access_chat_room_action(conn, student_id, room, runtime=_communication_runtime())


def accessible_chat_room(conn, room_id: str, actor: dict[str, Any]) -> dict[str, Any]:
    return communication_domain.accessible_chat_room_action(conn, room_id, actor, runtime=_communication_runtime())


def chat_realtime_configuration(payload: dict[str, Any]):
    return communication_domain.chat_realtime_configuration_action(payload, runtime=_communication_runtime())


def chat_message_rows(conn, message_ids: list[str]) -> list[dict[str, Any]]:
    return communication_domain.chat_message_rows_action(conn, message_ids, runtime=_communication_runtime())


def chat_message_row(conn, message_id: str) -> dict[str, Any] | None:
    return communication_domain.chat_message_row_action(conn, message_id, runtime=_communication_runtime())


def public_chat_message(row: dict[str, Any] | None, actor: dict[str, Any]) -> dict[str, Any] | None:
    return communication_domain.public_chat_message_action(row, actor, runtime=_communication_runtime())


def record_chat_message_receipts(conn, message_ids: list[str], actor: dict[str, Any], *, mark_read: bool=False) -> None:
    return communication_domain.record_chat_message_receipts_action(conn, message_ids, actor, mark_read=mark_read, runtime=_communication_runtime())


def mark_chat_room_read_with_conn(conn, room_id: str, actor: dict[str, Any]) -> None:
    return communication_domain.mark_chat_room_read_with_conn_action(conn, room_id, actor, runtime=_communication_runtime())


def upsert_chat_room_read_cursor(conn, room_id: str, actor: dict[str, Any]) -> None:
    return communication_domain.upsert_chat_room_read_cursor_action(conn, room_id, actor, runtime=_communication_runtime())


def chat_room_summary_context(conn, rooms: list[dict[str, Any]], actor: dict[str, Any], active_admin_count: int) -> dict[str, dict[str, Any]]:
    return communication_domain.chat_room_summary_context_action(conn, rooms, actor, active_admin_count, runtime=_communication_runtime())


def chat_room_participant_count(conn, room: dict[str, Any], active_admin_count: int | None=None) -> int:
    return communication_domain.chat_room_participant_count_action(conn, room, active_admin_count, runtime=_communication_runtime())


def public_chat_room(conn, room: dict[str, Any], actor: dict[str, Any], active_admin_count: int | None=None, summary: dict[str, Any] | None=None) -> dict[str, Any]:
    return communication_domain.public_chat_room_action(conn, room, actor, active_admin_count, summary, runtime=_communication_runtime())


def chat_list_contacts(payload: dict[str, Any]):
    return communication_domain.chat_list_contacts_action(payload, runtime=_communication_runtime())


def chat_start_direct(payload: dict[str, Any]):
    return communication_domain.chat_start_direct_action(payload, runtime=_communication_runtime())


def chat_presence_heartbeat(payload: dict[str, Any]):
    return communication_domain.chat_presence_heartbeat_action(payload, runtime=_communication_runtime())


def chat_list_rooms(payload: dict[str, Any]):
    return communication_domain.chat_list_rooms_action(payload, runtime=_communication_runtime())


def chat_list_messages(payload: dict[str, Any]):
    return communication_domain.chat_list_messages_action(payload, runtime=_communication_runtime())


def chat_send_message(payload: dict[str, Any]):
    return communication_domain.chat_send_message_action(payload, runtime=_communication_runtime())


def chat_edit_message(payload: dict[str, Any]):
    return communication_domain.chat_edit_message_action(payload, runtime=_communication_runtime())


def chat_delete_message(payload: dict[str, Any]):
    return communication_domain.chat_delete_message_action(payload, runtime=_communication_runtime())


def chat_mark_read(payload: dict[str, Any]):
    return communication_domain.chat_mark_read_action(payload, runtime=_communication_runtime())


def chat_report_message(payload: dict[str, Any]):
    return communication_domain.chat_report_message_action(payload, runtime=_communication_runtime())


def not_implemented(action: str):
    raise ApiError("NOT_IMPLEMENTED", f"A ação {action} ainda não foi portada para a API Python.")


def require_application_schema() -> None:
    global _APPLICATION_SCHEMA_READY
    if _APPLICATION_SCHEMA_READY:
        return
    try:
        status = schema_status()
    except Exception as error:
        raise database_api_error(error) from error
    if not status["compatible"]:
        raise ApiError(
            "DATABASE_MIGRATION_REQUIRED",
            "A versão do esquema da base de dados não é compatível com esta versão da aplicação.",
            {
                "expectedVersion": status["expectedVersion"],
                "installedVersion": status["installedVersion"],
            },
        )
    _APPLICATION_SCHEMA_READY = True


ACTIONS = build_action_registry(globals())


def dispatch(action: str, payload: dict[str, Any]):
    handler = ACTIONS.get(action)
    if not handler:
        return not_implemented(action)
    if action not in {"health", "healthDiagnostics"}:
        require_application_schema()
    return handler(payload)
