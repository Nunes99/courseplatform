import base64
import ipaddress
import json
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
from .db import connection, ensure_schema, fetch_all, fetch_one, schema_exists
from .security import (
    constant_time_equals,
    generate_id,
    generate_access_code,
    generate_token,
    hash_secret,
    session_expiry,
    utc_now,
)


class ApiError(Exception):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def success(data: dict[str, Any]) -> dict[str, Any]:
    return {"success": True, "data": data}


def public_error(error: Exception) -> dict[str, Any]:
    if isinstance(error, ApiError):
        return {
            "success": False,
            "error": {
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        }
    return {
        "success": False,
        "error": {"code": "API_ERROR", "message": str(error), "details": None},
    }


def database_api_error(error: Exception) -> ApiError:
    error_name = error.__class__.__name__
    text = str(error).lower()
    if "undefinedcolumn" in text or "undefinedtable" in text or error_name == "ProgrammingError":
        return ApiError(
            "DATABASE_SCHEMA_ERROR",
            "A base de dados está ligada, mas o esquema e as tabelas da plataforma não estão completos.",
            {"errorType": error_name},
        )
    if "authentication" in text or "password" in text or "ecircuitbreaker" in text:
        return ApiError(
            "DATABASE_AUTH_ERROR",
            "A API não conseguiu autenticar no Postgres. Verifique POSTGRES_URL/POSTGRES_PASSWORD no Vercel.",
            {"errorType": error_name},
        )
    return ApiError(
        "DATABASE_UNAVAILABLE",
        "A base de dados não está disponível neste momento.",
        {"errorType": error_name},
    )


def diagnostic_error_message(error: Exception) -> str:
    text = str(error)
    text = re.sub(r"postgresql://\S+", "[DATABASE_URL]", text)
    text = re.sub(r"password=[^\s]+", "password=[hidden]", text, flags=re.IGNORECASE)
    return text[:700]


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"true", "1", "yes", "sim"}


def str_value(value: Any) -> str:
    return str(value or "").strip()


def valid_password(value: str) -> bool:
    text = str_value(value)
    return len(text) >= 8


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    row = fetch_one("select %s = crypt(%s, %s) as ok", (password_hash, password, password_hash))
    return bool(row and row.get("ok"))


def int_value(value: Any, fallback: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return fallback


def float_value(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return fallback


def parse_datetime(value: Any):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


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


def progress_access_status(row: dict[str, Any] | None) -> str:
    source = row or {}
    explicit = str_value(source.get("content_access_status")).upper()
    if explicit in CONTENT_ACCESS_STATUSES:
        return explicit
    return "LOCKED" if str_value(source.get("status")).upper() == "LOCKED" else "AVAILABLE"


def progress_evaluation_status(row: dict[str, Any] | None) -> str:
    source = row or {}
    explicit = str_value(source.get("evaluation_status")).upper()
    if explicit in EVALUATION_STATUSES:
        return explicit
    legacy = str_value(source.get("status")).upper()
    return legacy if legacy in EVALUATION_STATUSES else "NOT_STARTED"


def legacy_progress_status(access_status: str, evaluation_status: str) -> str:
    return evaluation_status if evaluation_status != "NOT_STARTED" else access_status


def audit(conn, actor_type: str, actor_id: str, action: str, entity_type: str, entity_id: str, details: dict[str, Any] | None = None):
    conn.execute(
        """
        insert into courseplatform.audit_log
          (log_id, actor_type, actor_id, action, entity_type, entity_id, details_json, created_at)
        values (%s, %s, %s, %s, %s, %s, %s, now())
        """,
        (generate_id("LOG"), actor_type, actor_id, action, entity_type, entity_id, json.dumps(details or {})),
    )


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def public_student_id() -> str:
    import secrets

    return f"STU-{secrets.randbelow(100000):05d}"


def require_fields(payload: dict[str, Any], fields: list[str]) -> None:
    missing = [field for field in fields if payload.get(field) in (None, "")]
    if missing:
        raise ApiError("REQUIRED_FIELDS", "Campos obrigatorios ausentes.", missing)


def pagination(payload: dict[str, Any], default_limit: int = 100, max_limit: int = 500):
    limit = int(payload.get("limit") or default_limit)
    page = int(payload.get("page") or 1)
    limit = max(1, min(limit, max_limit))
    offset = payload.get("offset")
    offset = int(offset) if offset not in (None, "") else (max(1, page) - 1) * limit
    return limit, max(0, offset), max(1, page)


def public_student(row: dict[str, Any] | None):
    if not row:
        return None
    return {
        "studentId": row["student_id"],
        "publicStudentId": row.get("public_student_id") or "",
        "fullName": row.get("full_name"),
        "email": row.get("email"),
        "status": row.get("status"),
        "country": row.get("country"),
        "organization": row.get("organization"),
        "phone": row.get("phone"),
        "jobTitle": row.get("job_title"),
        "interests": row.get("interests"),
        "profilePhotoUrl": row.get("profile_photo_url"),
        "whatsappOptIn": as_bool(row.get("whatsapp_opt_in")),
        "whatsappOptInAt": iso(row.get("whatsapp_opt_in_at")),
        "emailOptIn": as_bool(row.get("email_opt_in")),
        "emailOptInAt": iso(row.get("email_opt_in_at")),
        "telegramLinked": bool(normalize_telegram_recipient(row.get("telegram_chat_id"))),
        "telegramOptIn": as_bool(row.get("telegram_opt_in")),
        "telegramOptInAt": iso(row.get("telegram_opt_in_at")),
        "pushSubscriptionCount": int(row.get("push_subscription_count") or 0),
        "notificationPreferences": notification_preferences(row),
        "createdAt": iso(row.get("created_at")),
        "updatedAt": iso(row.get("updated_at")),
        "lastLoginAt": iso(row.get("last_login_at")),
    }


def public_admin(row: dict[str, Any] | None):
    if not row:
        return None
    return {
        "adminId": row["admin_id"],
        "fullName": row.get("full_name"),
        "email": row.get("email"),
        "role": row.get("role"),
        "status": row.get("status"),
        "createdAt": iso(row.get("created_at")),
        "updatedAt": iso(row.get("updated_at")),
    }


def public_course(row: dict[str, Any] | None):
    if not row:
        return None
    return {
        "courseId": row["course_id"],
        "courseCode": row.get("course_code"),
        "title": row.get("title"),
        "description": row.get("description"),
        "totalHours": float(row.get("total_hours") or 0),
        "passingScore": float(row.get("passing_score") or 0),
        "status": row.get("status"),
        "createdAt": iso(row.get("created_at")),
        "updatedAt": iso(row.get("updated_at")),
    }


def public_lesson(row: dict[str, Any] | None):
    if not row:
        return None
    configured_duration = int_value(row.get("submission_duration_minutes"))
    fallback_duration = int_value(row.get("exercise_minutes")) + int_value(row.get("individual_minutes"))
    submission_duration = configured_duration or fallback_duration or 180
    return {
        "lessonId": row["lesson_id"],
        "courseId": row.get("course_id"),
        "lessonNumber": int(row.get("lesson_number") or 0),
        "title": row.get("title"),
        "slug": row.get("slug"),
        "summary": row.get("summary"),
        "theoryMinutes": float(row.get("theory_minutes") or 0),
        "exerciseMinutes": float(row.get("exercise_minutes") or 0),
        "individualMinutes": float(row.get("individual_minutes") or 0),
        "submissionDurationMinutes": submission_duration,
        "passingScore": float(row.get("passing_score") or 0),
        "prerequisiteLessonId": row.get("prerequisite_lesson_id"),
        "status": row.get("status"),
        "createdAt": iso(row.get("created_at")),
        "updatedAt": iso(row.get("updated_at")),
    }


def public_enrollment(row: dict[str, Any] | None):
    if not row:
        return None
    return {
        "enrollmentId": row["enrollment_id"],
        "studentId": row.get("student_id"),
        "courseId": row.get("course_id"),
        "groupId": row.get("group_id"),
        "status": row.get("status"),
        "enrolledAt": iso(row.get("enrolled_at")),
        "completedAt": iso(row.get("completed_at")),
        "progressPercent": float(row.get("progress_percent") or 0),
        "finalScore": None if row.get("final_score") is None else float(row["final_score"]),
        "certificateId": row.get("certificate_id"),
    }


def public_group_member(row: dict[str, Any] | None):
    if not row:
        return None
    return {
        "groupMemberId": row["group_member_id"],
        "groupId": row.get("group_id"),
        "studentId": row.get("student_id"),
        "status": row.get("status"),
        "joinedAt": iso(row.get("joined_at")),
        "updatedAt": iso(row.get("updated_at")),
    }


def public_content(row: dict[str, Any] | None):
    if not row:
        return None
    return {
        "contentId": row["content_id"],
        "lessonId": row.get("lesson_id"),
        "sectionOrder": int(row.get("section_order") or 0),
        "sectionType": row.get("section_type"),
        "title": row.get("title"),
        "bodyHtml": row.get("body_html"),
        "estimatedMinutes": float(row.get("estimated_minutes") or 0),
        "isRequired": as_bool(row.get("is_required")),
        "status": row.get("status"),
    }


def public_question(row: dict[str, Any] | None):
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


def public_option(row: dict[str, Any] | None):
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
    if not row:
        return None
    access_status = progress_access_status(row)
    evaluation_status = progress_evaluation_status(row)
    return {
        "progressId": row["progress_id"],
        "lessonId": row.get("lesson_id"),
        "status": legacy_progress_status(access_status, evaluation_status),
        "contentAccessStatus": access_status,
        "evaluationStatus": evaluation_status,
        "unlockedAt": iso(row.get("unlocked_at")),
        "startedAt": iso(row.get("started_at")),
        "submittedAt": iso(row.get("submitted_at")),
        "approvedAt": iso(row.get("approved_at")),
        "score": None if row.get("score") is None else float(row["score"]),
        "attemptCount": int(row.get("attempt_count") or 0),
    }


def public_attempt(row: dict[str, Any] | None):
    if not row:
        return None
    deadline = row.get("deadline_at")
    remaining = None
    if isinstance(deadline, datetime):
        remaining = max(0, int((deadline - utc_now()).total_seconds()))
    return {
        "attemptId": row["attempt_id"],
        "progressId": row.get("progress_id"),
        "lessonId": row.get("lesson_id"),
        "attemptNumber": int(row.get("attempt_number") or 0),
        "startedAt": iso(row.get("started_at")),
        "deadlineAt": iso(row.get("deadline_at")),
        "submittedAt": iso(row.get("submitted_at")),
        "status": row.get("status"),
        "score": None if row.get("score") is None else float(row["score"]),
        "reviewedAt": iso(row.get("reviewed_at")),
        "reviewComments": row.get("review_comments"),
        "retryAuthorized": as_bool(row.get("retry_authorized")),
        "remainingSeconds": remaining,
        "createdAt": iso(row.get("created_at")),
        "updatedAt": iso(row.get("updated_at")),
    }


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
            conn.execute(
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


def public_answer(row: dict[str, Any] | None):
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


def public_file(row: dict[str, Any] | None):
    if not row:
        return None
    return {
        "fileId": row["file_id"],
        "attemptId": row.get("attempt_id"),
        "studentId": row.get("student_id"),
        "lessonId": row.get("lesson_id"),
        "fileName": row.get("file_name"),
        "mimeType": row.get("mime_type"),
        "sizeBytes": int(row.get("size_bytes") or 0),
        "driveFileId": row.get("drive_file_id"),
        "driveUrl": row.get("drive_url"),
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
    normalized = str_value(value).upper()
    return NOTIFICATION_STATUS_LABELS.get(normalized, normalized.replace("_", " ").title())


def notification_preferences(row: dict[str, Any] | None) -> dict[str, bool]:
    source = (row or {}).get("notification_preferences_json") or {}
    if isinstance(source, str):
        try:
            source = json.loads(source)
        except json.JSONDecodeError:
            source = {}
    if not isinstance(source, dict):
        source = {}
    return {
        key: as_bool(source.get(key, default_value))
        for key, default_value in DEFAULT_NOTIFICATION_PREFERENCES.items()
    }


NOTIFICATION_FEATURE_SQL = """
alter table courseplatform.students add column if not exists whatsapp_opt_in boolean not null default false;
alter table courseplatform.students add column if not exists whatsapp_opt_in_at timestamptz;
alter table courseplatform.students add column if not exists email_opt_in boolean not null default false;
alter table courseplatform.students add column if not exists email_opt_in_at timestamptz;
alter table courseplatform.students add column if not exists telegram_chat_id text;
alter table courseplatform.students add column if not exists telegram_opt_in boolean not null default false;
alter table courseplatform.students add column if not exists telegram_opt_in_at timestamptz;
alter table courseplatform.students add column if not exists notification_preferences_json jsonb not null default '{"MODULE_AVAILABLE":true,"SUBMISSION_STATUS":true,"REVIEW_FEEDBACK":true,"GENERAL":true}'::jsonb;
create table if not exists courseplatform.notifications (
  notification_id text primary key,
  student_id text not null references courseplatform.students(student_id) on delete cascade,
  created_by_admin_id text references courseplatform.admins(admin_id) on delete set null,
  category text not null default 'GENERAL',
  title text not null,
  message text not null,
  action_url text,
  entity_type text,
  entity_id text,
  priority text not null default 'NORMAL',
  read_at timestamptz,
  created_at timestamptz not null default now()
);
alter table courseplatform.notifications add column if not exists template_key text;
alter table courseplatform.notifications add column if not exists template_variables_json jsonb not null default '{}'::jsonb;
alter table courseplatform.notifications add column if not exists email_subject text;
alter table courseplatform.notifications add column if not exists email_message text;
alter table courseplatform.notifications add column if not exists push_title text;
alter table courseplatform.notifications add column if not exists push_message text;
create table if not exists courseplatform.notification_deliveries (
  delivery_id text primary key,
  notification_id text not null references courseplatform.notifications(notification_id) on delete cascade,
  channel text not null,
  recipient text,
  status text not null default 'PENDING',
  provider text,
  provider_message_id text,
  attempt_count integer not null default 0,
  last_error text,
  created_at timestamptz not null default now(),
  sent_at timestamptz,
  updated_at timestamptz,
  unique(notification_id, channel)
);
create table if not exists courseplatform.notification_channel_settings (
  channel text primary key,
  enabled boolean not null default false,
  phone_number_id text,
  graph_api_version text,
  template_name text,
  template_language text,
  platform_url text,
  access_token_encrypted bytea,
  updated_by text references courseplatform.admins(admin_id) on delete set null,
  updated_at timestamptz
);
alter table courseplatform.notification_channel_settings add column if not exists smtp_host text;
alter table courseplatform.notification_channel_settings add column if not exists smtp_port integer;
alter table courseplatform.notification_channel_settings add column if not exists smtp_username text;
alter table courseplatform.notification_channel_settings add column if not exists smtp_password_encrypted bytea;
alter table courseplatform.notification_channel_settings add column if not exists from_email text;
alter table courseplatform.notification_channel_settings add column if not exists from_name text;
alter table courseplatform.notification_channel_settings add column if not exists use_tls boolean;
alter table courseplatform.notification_channel_settings add column if not exists bot_username text;
alter table courseplatform.notification_channel_settings add column if not exists parse_mode text;
create table if not exists courseplatform.notification_templates (
  template_key text primary key,
  internal_title_template text not null,
  internal_message_template text not null,
  email_subject_template text not null,
  email_message_template text not null,
  push_title_template text not null,
  push_message_template text not null,
  updated_by text references courseplatform.admins(admin_id) on delete set null,
  updated_at timestamptz not null default now()
);
create table if not exists courseplatform.push_subscriptions (
  subscription_id text primary key,
  student_id text not null references courseplatform.students(student_id) on delete cascade,
  endpoint_hash text not null unique,
  endpoint_encrypted bytea not null,
  p256dh_encrypted bytea not null,
  auth_encrypted bytea not null,
  user_agent text,
  device_label text,
  enabled boolean not null default true,
  failure_count integer not null default 0,
  last_success_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create table if not exists courseplatform.telegram_link_tokens (
  token_hash text primary key,
  student_id text not null references courseplatform.students(student_id) on delete cascade,
  expires_at timestamptz not null,
  consumed_at timestamptz,
  telegram_update_id bigint,
  created_at timestamptz not null default now()
);
create index if not exists idx_telegram_link_tokens_student
  on courseplatform.telegram_link_tokens(student_id, created_at desc);
create table if not exists courseplatform.notification_channel_state (
  channel text primary key,
  cursor_value bigint not null default 0,
  updated_at timestamptz
);
create index if not exists idx_notifications_student_created on courseplatform.notifications(student_id, created_at desc);
create index if not exists idx_notifications_student_unread on courseplatform.notifications(student_id, read_at, created_at desc);
create index if not exists idx_notification_deliveries_status on courseplatform.notification_deliveries(channel, status, created_at);
create index if not exists idx_push_subscriptions_student on courseplatform.push_subscriptions(student_id, enabled, updated_at desc);
"""


def ensure_notification_feature_schema(conn) -> None:
    execute_statements(conn, NOTIFICATION_FEATURE_SQL)


def prepare_notification_feature_schema() -> None:
    global _NOTIFICATION_SCHEMA_READY
    if _NOTIFICATION_SCHEMA_READY:
        return
    with connection() as conn:
        ensure_notification_feature_schema(conn)
        conn.commit()
    _NOTIFICATION_SCHEMA_READY = True


_NOTIFICATION_TEMPLATE_COLUMNS = {
    "internalTitleTemplate": "internal_title_template",
    "internalMessageTemplate": "internal_message_template",
    "emailSubjectTemplate": "email_subject_template",
    "emailMessageTemplate": "email_message_template",
    "pushTitleTemplate": "push_title_template",
    "pushMessageTemplate": "push_message_template",
}


def _template_tokens(value: Any) -> set[str]:
    return set(re.findall(r"{{\s*([a-z_][a-z0-9_]*)\s*}}", str(value or ""), flags=re.IGNORECASE))


def _render_notification_template(value: Any, variables: dict[str, Any], fallback: str, limit: int) -> str:
    source = str(value or fallback)
    normalized = {key: str_value(item) for key, item in variables.items() if key in NOTIFICATION_TEMPLATE_VARIABLES}

    def replace(match: re.Match) -> str:
        return normalized.get(match.group(1).lower(), "")

    return re.sub(r"{{\s*([a-z_][a-z0-9_]*)\s*}}", replace, source, flags=re.IGNORECASE).strip()[:limit]


def notification_template_payload(template_key: str, row: dict[str, Any] | None = None) -> dict[str, Any]:
    definition = NOTIFICATION_TEMPLATE_DEFINITIONS[template_key]
    row = row or {}
    payload = {
        "templateKey": template_key,
        "label": definition["label"],
        "category": definition["category"],
        "customized": bool(row),
        "updatedAt": iso(row.get("updated_at")),
        "allowedVariables": sorted(NOTIFICATION_TEMPLATE_VARIABLES),
    }
    for public_name, column_name in _NOTIFICATION_TEMPLATE_COLUMNS.items():
        payload[public_name] = row.get(column_name) if row.get(column_name) is not None else definition[public_name]
        payload[f"default{public_name[0].upper()}{public_name[1:]}"] = definition[public_name]
    return payload


def notification_templates_payload() -> list[dict[str, Any]]:
    prepare_notification_feature_schema()
    rows = {
        row["template_key"]: row
        for row in fetch_all("select * from courseplatform.notification_templates")
        if row.get("template_key") in NOTIFICATION_TEMPLATE_DEFINITIONS
    }
    return [
        notification_template_payload(template_key, rows.get(template_key))
        for template_key in NOTIFICATION_TEMPLATE_DEFINITIONS
    ]


def resolve_notification_content(
    conn,
    template_key: str,
    variables: dict[str, Any] | None,
    title: str,
    message: str,
    *,
    email_subject: str = "",
    email_message: str = "",
    push_title: str = "",
    push_message: str = "",
) -> dict[str, Any]:
    normalized_key = str_value(template_key).upper()
    context = {
        key: str_value(value)[:1800]
        for key, value in (variables or {}).items()
        if key in NOTIFICATION_TEMPLATE_VARIABLES
    }
    if normalized_key not in NOTIFICATION_TEMPLATE_DEFINITIONS:
        return {
            "templateKey": "",
            "variables": context,
            "title": str_value(title)[:180],
            "message": str_value(message)[:1800],
            "emailSubject": str_value(email_subject or title)[:180],
            "emailMessage": str_value(email_message or message)[:5000],
            "pushTitle": str_value(push_title or title)[:120],
            "pushMessage": str_value(push_message or message)[:300],
        }
    row = conn.execute(
        "select * from courseplatform.notification_templates where template_key = %s",
        (normalized_key,),
    ).fetchone() or {}
    template = notification_template_payload(normalized_key, row)
    return {
        "templateKey": normalized_key,
        "variables": context,
        "title": _render_notification_template(template["internalTitleTemplate"], context, title, 180),
        "message": _render_notification_template(template["internalMessageTemplate"], context, message, 1800),
        "emailSubject": _render_notification_template(template["emailSubjectTemplate"], context, email_subject or title, 180),
        "emailMessage": _render_notification_template(template["emailMessageTemplate"], context, email_message or message, 5000),
        "pushTitle": _render_notification_template(template["pushTitleTemplate"], context, push_title or title, 120),
        "pushMessage": _render_notification_template(template["pushMessageTemplate"], context, push_message or message, 300),
    }


def public_notification(row: dict[str, Any] | None):
    if not row:
        return None
    def delivery(channel: str) -> dict[str, Any]:
        prefix = channel.lower()
        # Legacy WhatsApp-only selects expose unprefixed delivery columns.
        fallback = channel == "WHATSAPP"
        status = row.get(f"{prefix}_status") or (row.get("delivery_status") if fallback else None) or "NOT_REQUESTED"
        if status == "PROCESSING":
            status = "PENDING"
        recipient = row.get(f"{prefix}_recipient") or (row.get("delivery_recipient") if fallback else None)
        return {
            "status": status,
            # Telegram chat IDs are private provider identifiers and are never
            # part of an API response, including administrative history.
            "recipient": None if channel in {"TELEGRAM", "PUSH"} else recipient,
            "providerMessageId": row.get(f"{prefix}_provider_message_id") or (row.get("provider_message_id") if fallback else None),
            "attemptCount": int(row.get(f"{prefix}_attempt_count") or (row.get("attempt_count") if fallback else 0) or 0),
            "lastError": row.get(f"{prefix}_last_error") or (row.get("last_error") if fallback else None),
            "sentAt": iso(row.get(f"{prefix}_sent_at") or (row.get("sent_at") if fallback else None)),
        }
    return {
        "notificationId": row.get("notification_id"),
        "studentId": row.get("student_id"),
        "studentName": row.get("student_name") or row.get("full_name"),
        "category": row.get("category") or "GENERAL",
        "title": row.get("title"),
        "message": row.get("message"),
        "actionUrl": row.get("action_url"),
        "entityType": row.get("entity_type"),
        "entityId": row.get("entity_id"),
        "priority": row.get("priority") or "NORMAL",
        "readAt": iso(row.get("read_at")),
        "createdAt": iso(row.get("created_at")),
        "templateKey": row.get("template_key") or "",
        "whatsapp": delivery("WHATSAPP"),
        "email": delivery("EMAIL"),
        "telegram": delivery("TELEGRAM"),
        "push": delivery("PUSH"),
    }


def normalize_whatsapp_recipient(value: Any) -> str:
    text = re.sub(r"[^0-9+]", "", str_value(value))
    if text.startswith("00"):
        text = f"+{text[2:]}"
    digits = re.sub(r"\D", "", text)
    return digits if 8 <= len(digits) <= 15 else ""


def normalize_email_recipient(value: Any) -> str:
    text = normalize_email(str_value(value))
    if len(text) > 254 or "\r" in text or "\n" in text:
        return ""
    local, separator, domain = text.rpartition("@")
    if not separator or not local or not domain or "." not in domain:
        return ""
    if len(local) > 64 or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+", local, re.IGNORECASE):
        return ""
    if not re.fullmatch(r"[a-z0-9.-]+", domain, re.IGNORECASE) or domain.startswith((".", "-")):
        return ""
    return text


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
    text = str_value(value)
    # Student accounts are linked only to private chats. Negative IDs identify
    # groups/channels and must never become a personal notification endpoint.
    return text if re.fullmatch(r"\d{5,20}", text) else ""


def redact_notification_error(value: Any, *secrets_to_hide: Any) -> str:
    text = str(value)
    for secret in secrets_to_hide:
        secret_text = str_value(secret)
        if secret_text:
            text = text.replace(secret_text, "[redacted]")
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+\-/=]+", "Bearer [redacted]", text)
    text = re.sub(r"(?i)(?:bot)?\d{5,20}:[A-Za-z0-9_-]{20,}", "[redacted]", text)
    return text[:700]


def notification_encryption_key(settings: Any | None = None) -> str:
    settings = settings or get_settings()
    return str_value(
        getattr(settings, "notification_config_encryption_key", "")
        or getattr(settings, "whatsapp_config_encryption_key", "")
    )


def decrypt_notification_secret(channel: str, column: str, encryption_key: str) -> str:
    if channel not in {"WHATSAPP", "EMAIL", "TELEGRAM"} or column not in {
        "access_token_encrypted", "smtp_password_encrypted"
    }:
        raise ValueError("Canal ou coluna de segredo inválidos.")
    row = fetch_one(
        f"""
        select pgp_sym_decrypt({column}, %s)::text as secret
        from courseplatform.notification_channel_settings
        where channel = %s
        """,
        (encryption_key, channel),
    ) or {}
    return str_value(row.get("secret"))


def valid_whatsapp_platform_url(value: Any) -> bool:
    text = str_value(value)
    if not text or len(text) > 1000:
        return False
    try:
        parsed = urlsplit(text)
        return bool(
            parsed.scheme in {"https", "http"}
            and parsed.hostname
            and not parsed.username
            and not parsed.password
        )
    except ValueError:
        return False


def valid_notification_host(value: Any) -> bool:
    text = str_value(value)
    if not text or len(text) > 253 or "\r" in text or "\n" in text:
        return False
    # SMTP accepts DNS names and literal IPv4/IPv6 addresses. It must not
    # contain a scheme, path, credentials or an embedded port.
    if "://" in text or any(character in text for character in "/@?#"):
        return False
    candidate = text[1:-1] if text.startswith("[") and text.endswith("]") else text
    try:
        # Prevent the administration form from being used to probe local or
        # private network services through the SMTP client.
        return ipaddress.ip_address(candidate).is_global
    except ValueError:
        normalized = candidate.lower().rstrip(".")
        if normalized == "localhost" or normalized.endswith(".localhost"):
            return False
        return bool(re.fullmatch(r"[a-zA-Z0-9.-]+", candidate) and not candidate.startswith((".", "-")))


def valid_telegram_bot_token(value: Any) -> bool:
    return bool(re.fullmatch(r"\d{5,20}:[A-Za-z0-9_-]{20,}", str_value(value)))


def normalize_telegram_parse_mode(value: Any) -> str:
    normalized = str_value(value).upper()
    if normalized in {"", "NONE", "PLAIN"}:
        return ""
    if normalized == "HTML":
        return "HTML"
    if normalized in {"MARKDOWNV2", "MARKDOWN_V2"}:
        return "MarkdownV2"
    return "HTML"


def safe_notification_action_url(value: Any) -> str:
    text = str_value(value)
    if text.startswith("#/") or text.startswith("https://") or text.startswith("http://"):
        return text[:1000]
    return "#/notifications"


def whatsapp_runtime_configuration() -> dict[str, Any]:
    """Resolve the admin-managed WhatsApp configuration without exposing its token."""
    prepare_notification_feature_schema()
    settings = get_settings()
    row = fetch_one(
        """
        select channel, enabled, phone_number_id, graph_api_version, template_name,
               template_language, platform_url,
               access_token_encrypted is not null as stored_token_configured,
               updated_at
        from courseplatform.notification_channel_settings
        where channel = 'WHATSAPP'
        """
    )
    managed_by_admin = bool(row)
    source = row or {}
    enabled = as_bool(source.get("enabled")) if managed_by_admin else settings.whatsapp_enabled
    phone_number_id = str_value(source.get("phone_number_id")) if managed_by_admin else settings.whatsapp_phone_number_id
    graph_api_version = str_value(source.get("graph_api_version")) if managed_by_admin else settings.whatsapp_graph_api_version
    template_name = str_value(source.get("template_name")) if managed_by_admin else settings.whatsapp_template_name
    template_language = str_value(source.get("template_language")) if managed_by_admin else settings.whatsapp_template_language
    platform_url = str_value(source.get("platform_url")) if managed_by_admin else settings.whatsapp_platform_url
    stored_token_configured = as_bool(source.get("stored_token_configured"))
    encryption_key = notification_encryption_key(settings)
    encryption_key_configured = len(encryption_key.encode("utf-8")) >= 32
    access_token = settings.whatsapp_access_token
    token_source = "ENV" if access_token else "NONE"
    token_error = ""

    if stored_token_configured:
        if encryption_key_configured:
            try:
                decrypted_token = decrypt_notification_secret(
                    "WHATSAPP", "access_token_encrypted", encryption_key
                )
                if decrypted_token:
                    access_token = decrypted_token
                    token_source = "ADMIN"
            except Exception:
                token_error = "O token guardado não pôde ser desencriptado. Confirme a chave do servidor."
        elif not access_token:
            token_error = "Defina WHATSAPP_CONFIG_ENCRYPTION_KEY com pelo menos 32 bytes para utilizar o token guardado."

    configured = bool(
        enabled
        and access_token
        and phone_number_id
        and template_name
        and valid_whatsapp_platform_url(platform_url)
    )
    return {
        "enabled": enabled,
        "configured": configured,
        "phoneNumberId": phone_number_id,
        "phoneNumberConfigured": bool(phone_number_id),
        "graphApiVersion": graph_api_version or "v23.0",
        "templateConfigured": bool(template_name),
        "templateName": template_name,
        "templateLanguage": template_language or "pt_PT",
        "platformUrl": platform_url,
        "accessToken": access_token,
        "tokenConfigured": bool(access_token),
        "storedTokenConfigured": stored_token_configured,
        "tokenSource": token_source,
        "tokenError": token_error,
        "encryptionKeyConfigured": encryption_key_configured,
        "source": "ADMIN" if managed_by_admin else "ENV",
        "updatedAt": iso(source.get("updated_at")),
        "timeoutSeconds": settings.whatsapp_timeout_seconds,
    }


def whatsapp_configuration() -> dict[str, Any]:
    configuration = whatsapp_runtime_configuration()
    return {
        key: value
        for key, value in configuration.items()
        if key not in {"accessToken", "timeoutSeconds"}
    }


def email_runtime_configuration() -> dict[str, Any]:
    """Resolve SMTP settings while keeping the password server-side."""
    prepare_notification_feature_schema()
    settings = get_settings()
    row = fetch_one(
        """
        select channel, enabled, smtp_host, smtp_port, smtp_username,
               from_email, from_name, use_tls,
               smtp_password_encrypted is not null as stored_password_configured,
               updated_at
        from courseplatform.notification_channel_settings
        where channel = 'EMAIL'
        """
    )
    managed_by_admin = bool(row)
    source = row or {}
    enabled = as_bool(source.get("enabled")) if managed_by_admin else settings.email_enabled
    smtp_host = str_value(source.get("smtp_host")) if managed_by_admin else settings.smtp_host
    smtp_port = int_value(source.get("smtp_port"), 587) if managed_by_admin else settings.smtp_port
    smtp_username = str_value(source.get("smtp_username")) if managed_by_admin else settings.smtp_username
    from_email = normalize_email_recipient(source.get("from_email")) if managed_by_admin else normalize_email_recipient(settings.smtp_from_email)
    from_name = str_value(source.get("from_name")) if managed_by_admin else settings.smtp_from_name
    use_tls = as_bool(source.get("use_tls")) if managed_by_admin else settings.smtp_use_tls
    stored_password_configured = as_bool(source.get("stored_password_configured"))
    encryption_key = notification_encryption_key(settings)
    encryption_key_configured = len(encryption_key.encode("utf-8")) >= 32
    smtp_password = settings.smtp_password
    password_source = "ENV" if smtp_password else "NONE"
    password_error = ""
    if stored_password_configured:
        if encryption_key_configured:
            try:
                decrypted = decrypt_notification_secret("EMAIL", "smtp_password_encrypted", encryption_key)
                if decrypted:
                    smtp_password = decrypted
                    password_source = "ADMIN"
            except Exception:
                password_error = "A palavra-passe SMTP guardada não pôde ser desencriptada. Confirme a chave do servidor."
        elif not smtp_password:
            password_error = "Defina NOTIFICATION_CONFIG_ENCRYPTION_KEY com pelo menos 32 bytes."
    authentication_ready = not smtp_username or bool(smtp_password)
    configured = bool(
        enabled
        and valid_notification_host(smtp_host)
        and 1 <= smtp_port <= 65535
        and (smtp_port == 465 or use_tls)
        and from_email
        and authentication_ready
    )
    return {
        "enabled": enabled,
        "configured": configured,
        "smtpHost": smtp_host,
        "smtpPort": smtp_port,
        "smtpUsername": smtp_username,
        "smtpPassword": smtp_password,
        "fromEmail": from_email,
        "fromName": from_name,
        "useTls": use_tls,
        "platformUrl": settings.platform_url,
        "passwordConfigured": bool(smtp_password),
        "storedPasswordConfigured": stored_password_configured,
        "passwordSource": password_source,
        "passwordError": password_error,
        "encryptionKeyConfigured": encryption_key_configured,
        "source": "ADMIN" if managed_by_admin else "ENV",
        "updatedAt": iso(source.get("updated_at")),
        "timeoutSeconds": settings.smtp_timeout_seconds,
    }


def email_configuration() -> dict[str, Any]:
    configuration = email_runtime_configuration()
    return {
        key: value
        for key, value in configuration.items()
        if key not in {"smtpPassword", "timeoutSeconds"}
    }


def telegram_runtime_configuration() -> dict[str, Any]:
    """Resolve Telegram Bot API settings without exposing the bot token."""
    prepare_notification_feature_schema()
    settings = get_settings()
    row = fetch_one(
        """
        select channel, enabled, bot_username, parse_mode,
               access_token_encrypted is not null as stored_token_configured,
               updated_at
        from courseplatform.notification_channel_settings
        where channel = 'TELEGRAM'
        """
    )
    managed_by_admin = bool(row)
    source = row or {}
    enabled = as_bool(source.get("enabled")) if managed_by_admin else settings.telegram_enabled
    bot_username = str_value(source.get("bot_username")) if managed_by_admin else settings.telegram_bot_username
    parse_mode = normalize_telegram_parse_mode(source.get("parse_mode") if managed_by_admin else settings.telegram_parse_mode)
    stored_token_configured = as_bool(source.get("stored_token_configured"))
    encryption_key = notification_encryption_key(settings)
    encryption_key_configured = len(encryption_key.encode("utf-8")) >= 32
    bot_token = settings.telegram_bot_token
    token_source = "ENV" if bot_token else "NONE"
    token_error = ""
    if stored_token_configured:
        if encryption_key_configured:
            try:
                decrypted = decrypt_notification_secret("TELEGRAM", "access_token_encrypted", encryption_key)
                if decrypted:
                    bot_token = decrypted
                    token_source = "ADMIN"
            except Exception:
                token_error = "O token do bot guardado não pôde ser desencriptado. Confirme a chave do servidor."
        elif not bot_token:
            token_error = "Defina NOTIFICATION_CONFIG_ENCRYPTION_KEY com pelo menos 32 bytes."
    configured = bool(enabled and valid_telegram_bot_token(bot_token))
    return {
        "enabled": enabled,
        "configured": configured,
        "botToken": bot_token,
        "botUsername": bot_username,
        "parseMode": parse_mode,
        "platformUrl": settings.platform_url,
        "tokenConfigured": bool(bot_token),
        "storedTokenConfigured": stored_token_configured,
        "tokenSource": token_source,
        "tokenError": token_error,
        "encryptionKeyConfigured": encryption_key_configured,
        "source": "ADMIN" if managed_by_admin else "ENV",
        "updatedAt": iso(source.get("updated_at")),
        "timeoutSeconds": settings.telegram_timeout_seconds,
    }


def telegram_configuration() -> dict[str, Any]:
    configuration = telegram_runtime_configuration()
    return {
        key: value
        for key, value in configuration.items()
        if key not in {"botToken", "timeoutSeconds"}
    }


def valid_vapid_subject(value: Any) -> bool:
    text = str_value(value)
    if text.startswith("mailto:"):
        return bool(normalize_email_recipient(text[7:]))
    try:
        parsed = urlsplit(text)
        return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password
    except ValueError:
        return False


def valid_push_endpoint(value: Any) -> bool:
    text = str_value(value)
    if not text or len(text) > 4096:
        return False
    try:
        parsed = urlsplit(text)
        return bool(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password)
    except ValueError:
        return False


def valid_push_key(value: Any, minimum: int, maximum: int) -> bool:
    text = str_value(value)
    return minimum <= len(text) <= maximum and bool(re.fullmatch(r"[A-Za-z0-9_-]+", text))


def valid_vapid_key(value: Any, expected_bytes: int, require_uncompressed_point: bool = False) -> bool:
    text = str_value(value)
    if not valid_push_key(text, 40, 100):
        return False
    try:
        padding = "=" * ((4 - len(text) % 4) % 4)
        decoded = base64.urlsafe_b64decode(f"{text}{padding}")
    except (ValueError, TypeError):
        return False
    if len(decoded) != expected_bytes:
        return False
    return not require_uncompressed_point or decoded[0] == 4


def web_push_runtime_configuration() -> dict[str, Any]:
    settings = get_settings()
    encryption_key = notification_encryption_key(settings)
    encryption_ready = len(encryption_key.encode("utf-8")) >= 32
    dependency_ready = webpush is not None
    enabled = as_bool(getattr(settings, "web_push_enabled", False))
    public_key = str_value(getattr(settings, "vapid_public_key", ""))
    private_key = str_value(getattr(settings, "vapid_private_key", ""))
    subject = str_value(getattr(settings, "vapid_subject", ""))
    configured = bool(
        enabled
        and valid_vapid_key(public_key, 65, require_uncompressed_point=True)
        and valid_vapid_key(private_key, 32)
        and valid_vapid_subject(subject)
        and encryption_ready
        and dependency_ready
    )
    return {
        "enabled": enabled,
        "configured": configured,
        "publicKey": public_key,
        "privateKey": private_key,
        "subject": subject,
        "platformUrl": str_value(getattr(settings, "platform_url", "")),
        "ttlSeconds": max(60, min(int_value(getattr(settings, "web_push_ttl_seconds", 86400), 86400), 2419200)),
        "timeoutSeconds": max(3, min(int_value(getattr(settings, "web_push_timeout_seconds", 12), 12), 60)),
        "encryptionKey": encryption_key,
        "encryptionKeyConfigured": encryption_ready,
        "dependencyConfigured": dependency_ready,
    }


def web_push_configuration() -> dict[str, Any]:
    configuration = web_push_runtime_configuration()
    return {
        key: value
        for key, value in configuration.items()
        if key not in {"privateKey", "encryptionKey", "ttlSeconds", "timeoutSeconds"}
    }


def student_notification_channel_info() -> dict[str, Any]:
    """Student-safe provider discovery; credentials and SMTP topology stay private."""
    email = email_configuration()
    telegram = telegram_configuration()
    whatsapp = whatsapp_configuration()
    push = web_push_configuration()
    return {
        "whatsapp": {"enabled": bool(whatsapp.get("enabled")), "configured": bool(whatsapp.get("configured"))},
        "email": {"enabled": bool(email.get("enabled")), "configured": bool(email.get("configured"))},
        "telegram": {
            "enabled": bool(telegram.get("enabled")),
            "configured": bool(telegram.get("configured")),
            "botUsername": telegram.get("botUsername") or "",
            "linkingAvailable": bool(
                telegram.get("enabled") and telegram.get("configured") and telegram.get("botUsername")
            ),
        },
        "push": {
            "enabled": bool(push.get("enabled")),
            "configured": bool(push.get("configured")),
            "publicKey": push.get("publicKey") or "",
        },
    }


def create_student_notification(
    conn,
    student_id: str,
    category: str,
    title: str,
    message: str,
    *,
    admin_id: str | None = None,
    action_url: str = "#/notifications",
    entity_type: str = "",
    entity_id: str = "",
    priority: str = "NORMAL",
    template_key: str = "",
    template_variables: dict[str, Any] | None = None,
    email_subject: str = "",
    email_message: str = "",
    push_title: str = "",
    push_message: str = "",
    send_whatsapp: bool = True,
    send_email: bool = True,
    send_telegram: bool = True,
    send_push: bool = True,
) -> str | None:
    student = conn.execute(
        "select * from courseplatform.students where student_id = %s",
        (student_id,),
    ).fetchone()
    if not student:
        return None
    normalized_category = str_value(category).upper() or "GENERAL"
    normalized_action_url = safe_notification_action_url(action_url)
    variables = dict(template_variables or {})
    variables["student_name"] = str_value(student.get("full_name")) or "Estudante"
    variables["action_url"] = normalized_action_url
    content = resolve_notification_content(
        conn,
        template_key,
        variables,
        title,
        message,
        email_subject=email_subject,
        email_message=email_message,
        push_title=push_title,
        push_message=push_message,
    )
    notification_id = generate_id("NTF")
    conn.execute(
        """
        insert into courseplatform.notifications
          (notification_id, student_id, created_by_admin_id, category, title, message,
           action_url, entity_type, entity_id, priority, template_key,
           template_variables_json, email_subject, email_message, push_title,
           push_message, created_at)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s::jsonb, %s, %s, %s, %s, now())
        """,
        (
            notification_id,
            student_id,
            admin_id,
            normalized_category,
            content["title"],
            content["message"],
            normalized_action_url,
            str_value(entity_type)[:80],
            str_value(entity_id)[:160],
            str_value(priority).upper() or "NORMAL",
            content["templateKey"] or None,
            json.dumps(content["variables"]),
            content["emailSubject"],
            content["emailMessage"],
            content["pushTitle"],
            content["pushMessage"],
        ),
    )
    preferences = notification_preferences(student)

    def queue_delivery(
        channel: str,
        recipient: str,
        opted_in: bool,
        provider: str,
        missing_contact_message: str,
    ) -> None:
        consented = opted_in and preferences.get(normalized_category, True)
        delivery_status = "PENDING" if consented and recipient else "SKIPPED"
        skip_reason = "" if delivery_status == "PENDING" else (
            f"Consentimento de {channel.title()} não concedido para este tipo de atualização."
            if not consented else missing_contact_message
        )
        conn.execute(
            """
            insert into courseplatform.notification_deliveries
              (delivery_id, notification_id, channel, recipient, status, provider,
               attempt_count, last_error, created_at, updated_at)
            values (%s, %s, %s, %s, %s, %s, 0, %s, now(), now())
            on conflict (notification_id, channel) do nothing
            """,
            (
                generate_id("NDL"), notification_id, channel, recipient or None,
                delivery_status, provider, skip_reason or None,
            ),
        )

    if send_whatsapp:
        queue_delivery(
            "WHATSAPP", normalize_whatsapp_recipient(student.get("phone")),
            as_bool(student.get("whatsapp_opt_in")), "META_CLOUD_API",
            "Telefone inválido ou sem indicativo internacional.",
        )
    if send_email:
        queue_delivery(
            "EMAIL", normalize_email_recipient(student.get("email")),
            as_bool(student.get("email_opt_in")), "SMTP",
            "Endereço de email inválido ou em falta.",
        )
    if send_telegram:
        queue_delivery(
            "TELEGRAM", normalize_telegram_recipient(student.get("telegram_chat_id")),
            as_bool(student.get("telegram_opt_in")), "TELEGRAM_BOT_API",
            "Chat ID do Telegram inválido ou em falta.",
        )
    if send_push:
        active_push = conn.execute(
            "select count(*) as count from courseplatform.push_subscriptions where student_id = %s and enabled",
            (student_id,),
        ).fetchone() or {}
        queue_delivery(
            "PUSH",
            student_id,
            int(active_push.get("count") or 0) > 0,
            "WEB_PUSH",
            "Nenhum dispositivo possui notificações Push ativas.",
        )
    return notification_id


def send_whatsapp_template(delivery: dict[str, Any], configuration: dict[str, Any] | None = None) -> str:
    configuration = configuration or whatsapp_runtime_configuration()
    if not configuration["configured"]:
        raise RuntimeError("Integração WhatsApp ainda não configurada no servidor.")
    endpoint = (
        f"https://graph.facebook.com/{configuration['graphApiVersion']}/"
        f"{configuration['phoneNumberId']}/messages"
    )
    action_url = str_value(delivery.get("action_url"))
    if not action_url.startswith(("https://", "http://")):
        base = str_value(configuration.get("platformUrl")).rstrip("/")
        action_url = f"{base}/{action_url}" if action_url.startswith("#/") else base
    body = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": delivery["recipient"],
        "type": "template",
        "template": {
            "name": configuration["templateName"],
            "language": {"code": configuration["templateLanguage"]},
            "components": [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": str_value(delivery.get("student_name"))[:120] or "Estudante"},
                    {"type": "text", "text": str_value(delivery.get("title"))[:180]},
                    {"type": "text", "text": str_value(delivery.get("message"))[:900]},
                    {"type": "text", "text": action_url[:1000]},
                ],
            }],
        },
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {configuration['accessToken']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=max(3, int(configuration.get("timeoutSeconds") or 12))) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        response_text = error.read().decode("utf-8", errors="replace")[:700]
        safe_error = redact_notification_error(response_text, configuration.get("accessToken"))
        raise RuntimeError(f"WhatsApp Cloud API HTTP {error.code}: {safe_error}") from error
    messages = result.get("messages") if isinstance(result, dict) else []
    provider_message_id = str_value(messages[0].get("id")) if messages else ""
    if not provider_message_id:
        raise RuntimeError("A API do WhatsApp não devolveu o identificador da mensagem.")
    return provider_message_id


def resolved_notification_action_url(delivery: dict[str, Any], configuration: dict[str, Any]) -> str:
    action_url = str_value(delivery.get("action_url"))
    if action_url.startswith(("https://", "http://")):
        return action_url
    base = str_value(configuration.get("platformUrl")).rstrip("/")
    if base and action_url.startswith("#/"):
        return f"{base}/{action_url}"
    return ""


def _notification_plain_text(delivery: dict[str, Any], action_url: str = "") -> str:
    parts = [
        str_value(delivery.get("student_name")) or "Estudante",
        "",
        str_value(delivery.get("email_subject") or delivery.get("title")) or "Atualização académica",
        "",
        str_value(delivery.get("email_message") or delivery.get("message")),
    ]
    if action_url:
        parts.extend(["", f"Abrir na plataforma: {action_url}"])
    return "\n".join(parts).strip()


def send_email_notification(delivery: dict[str, Any], configuration: dict[str, Any] | None = None) -> str:
    configuration = configuration or email_runtime_configuration()
    if not configuration["configured"]:
        raise RuntimeError("Integração de email ainda não configurada no servidor.")
    recipient = normalize_email_recipient(delivery.get("recipient"))
    if not recipient:
        raise RuntimeError("Endereço de email do destinatário inválido.")

    title = re.sub(r"[\r\n]+", " ", str_value(delivery.get("email_subject") or delivery.get("title")))[:180] or "Atualização académica"
    body_message = str_value(delivery.get("email_message") or delivery.get("message"))[:5000]
    action_url = resolved_notification_action_url(delivery, configuration)
    message = EmailMessage()
    message_id = make_msgid(domain=configuration["fromEmail"].partition("@")[2] or None)
    message["Message-ID"] = message_id
    message["Subject"] = title
    message["From"] = formataddr((configuration.get("fromName") or "", configuration["fromEmail"]))
    message["To"] = recipient
    message.set_content(_notification_plain_text(delivery, action_url))
    student_name = html_escape(str_value(delivery.get("student_name")) or "Estudante")
    brand_name = html_escape(configuration.get("fromName") or "Plataforma de ensino")
    safe_body = html_escape(body_message).replace(chr(10), "<br>")
    action_html = (
        '<p style="margin:28px 0 8px">'
        f'<a href="{html_escape(action_url, quote=True)}" style="display:inline-block;background:#00365B;color:#FFFFFF;text-decoration:none;padding:11px 18px;border-radius:6px;font:600 14px Inter,Arial,sans-serif">Abrir na plataforma</a>'
        "</p>"
        if action_url.startswith(("https://", "http://")) else ""
    )
    message.add_alternative(
        "<!doctype html><html lang=\"pt\"><body style=\"margin:0;background:#FFF8E4;padding:24px\">"
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;background:#FFFFFF;border:1px solid rgba(201,165,91,.35);border-radius:12px;overflow:hidden">'
        f'<tr><td style="background:#00365B;padding:20px 24px;color:#FFF8E4;font:600 16px Manrope,Arial,sans-serif">{brand_name}</td></tr>'
        '<tr><td style="padding:28px 24px;color:#00365B;font:15px/1.6 Inter,Arial,sans-serif">'
        f'<p style="margin:0 0 12px">Olá, {student_name}.</p>'
        f'<h1 style="margin:0 0 16px;font:600 24px/1.25 Manrope,Arial,sans-serif;color:#00365B">{html_escape(title)}</h1>'
        f'<p style="margin:0">{safe_body}</p>{action_html}'
        '</td></tr><tr><td style="border-top:1px solid rgba(201,165,91,.25);padding:16px 24px;color:rgba(0,54,91,.68);font:12px/1.5 Inter,Arial,sans-serif">Mensagem académica automática. Pode gerir os canais e categorias no seu perfil.</td></tr>'
        "</table></td></tr></table></body></html>",
        subtype="html",
    )

    try:
        port = int(configuration["smtpPort"])
        smtp_class = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
        smtp_options: dict[str, Any] = {
            "host": configuration["smtpHost"],
            "port": port,
            "timeout": max(3, int(configuration.get("timeoutSeconds") or 12)),
        }
        if port == 465:
            smtp_options["context"] = ssl.create_default_context()
        with smtp_class(**smtp_options) as smtp:
            smtp.ehlo()
            if port != 465 and configuration.get("useTls"):
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if configuration.get("smtpUsername"):
                smtp.login(configuration["smtpUsername"], configuration.get("smtpPassword") or "")
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError, TimeoutError) as error:
        safe_error = redact_notification_error(error, configuration.get("smtpPassword"))
        raise RuntimeError(f"Falha no envio SMTP: {safe_error}") from error
    return message_id.strip("<>")


def _telegram_markdown_v2(value: Any) -> str:
    return re.sub(r"([_\*\[\]\(\)~`>#+\-=|{}.!])", r"\\\1", str_value(value))


def send_telegram_notification(delivery: dict[str, Any], configuration: dict[str, Any] | None = None) -> str:
    configuration = configuration or telegram_runtime_configuration()
    if not configuration["configured"]:
        raise RuntimeError("Integração Telegram ainda não configurada no servidor.")
    recipient = normalize_telegram_recipient(delivery.get("recipient"))
    if not recipient:
        raise RuntimeError("Chat ID do Telegram inválido.")

    name = str_value(delivery.get("student_name")) or "Estudante"
    title = str_value(delivery.get("title"))[:180]
    body_message = str_value(delivery.get("message"))[:3000]
    action_url = resolved_notification_action_url(delivery, configuration)
    parse_mode = normalize_telegram_parse_mode(configuration.get("parseMode"))
    if parse_mode == "HTML":
        text = f"<b>{html_escape(title)}</b>\n\n{html_escape(name)},\n{html_escape(body_message)}"
        if action_url:
            text += f"\n\n{html_escape(action_url)}"
    elif parse_mode == "MarkdownV2":
        text = f"*{_telegram_markdown_v2(title)}*\n\n{_telegram_markdown_v2(name)},\n{_telegram_markdown_v2(body_message)}"
        if action_url:
            text += f"\n\n{_telegram_markdown_v2(action_url)}"
    else:
        text = f"{title}\n\n{name},\n{body_message}"
        if action_url:
            text += f"\n\n{action_url}"
    if len(text) > 4096:
        # Avoid cutting an HTML entity or a Markdown escape sequence. Oversized
        # formatted content is safely downgraded to plain text.
        parse_mode = ""
        text = f"{title}\n\n{name},\n{body_message}"
        if action_url:
            text += f"\n\n{action_url}"
    request_body: dict[str, Any] = {
        "chat_id": recipient,
        "text": text[:4096],
        "disable_web_page_preview": True,
    }
    if parse_mode:
        request_body["parse_mode"] = parse_mode
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{configuration['botToken']}/sendMessage",
        data=json.dumps(request_body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=max(3, int(configuration.get("timeoutSeconds") or 12)),
        ) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        response_text = error.read().decode("utf-8", errors="replace")[:700]
        safe_error = redact_notification_error(response_text, configuration.get("botToken"))
        raise RuntimeError(f"Telegram Bot API HTTP {error.code}: {safe_error}") from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        safe_error = redact_notification_error(error, configuration.get("botToken"))
        raise RuntimeError(f"Falha no envio pelo Telegram: {safe_error}") from error
    message_id = str_value((result.get("result") or {}).get("message_id")) if isinstance(result, dict) else ""
    if not isinstance(result, dict) or not result.get("ok") or not message_id:
        description = str_value(result.get("description")) if isinstance(result, dict) else "Resposta inválida"
        safe_error = redact_notification_error(description, configuration.get("botToken"))
        raise RuntimeError(f"A API do Telegram rejeitou a mensagem: {safe_error}")
    return message_id


def push_subscriptions_for_student(student_id: str, encryption_key: str) -> list[dict[str, Any]]:
    return fetch_all(
        """
        select subscription_id,
               pgp_sym_decrypt(endpoint_encrypted, %s)::text as endpoint,
               pgp_sym_decrypt(p256dh_encrypted, %s)::text as p256dh,
               pgp_sym_decrypt(auth_encrypted, %s)::text as auth
        from courseplatform.push_subscriptions
        where student_id = %s and enabled
        order by updated_at desc
        """,
        (encryption_key, encryption_key, encryption_key, student_id),
    )


def update_push_subscription_delivery(subscription_id: str, success_result: bool, expired: bool = False) -> None:
    with connection() as conn:
        if success_result:
            conn.execute(
                """
                update courseplatform.push_subscriptions
                set last_success_at = now(), failure_count = 0, updated_at = now()
                where subscription_id = %s
                """,
                (subscription_id,),
            )
        else:
            conn.execute(
                """
                update courseplatform.push_subscriptions
                set failure_count = failure_count + 1,
                    enabled = case when %s or failure_count >= 4 then false else enabled end,
                    updated_at = now()
                where subscription_id = %s
                """,
                (expired, subscription_id),
            )
        conn.commit()


def send_web_push_notification(delivery: dict[str, Any], configuration: dict[str, Any] | None = None) -> str:
    configuration = configuration or web_push_runtime_configuration()
    if not configuration.get("configured") or webpush is None:
        raise RuntimeError("Integração Web Push ainda não configurada no servidor.")
    student_id = str_value(delivery.get("student_id") or delivery.get("recipient"))
    if not student_id:
        raise RuntimeError("Destinatário Push inválido.")
    subscriptions = push_subscriptions_for_student(student_id, configuration["encryptionKey"])
    if not subscriptions:
        raise RuntimeError("Nenhum dispositivo possui notificações Push ativas.")
    action_url = resolved_notification_action_url(delivery, configuration) or str_value(delivery.get("action_url")) or "#/notifications"
    payload = json.dumps({
        "title": str_value(delivery.get("push_title") or delivery.get("title"))[:120],
        "body": str_value(delivery.get("push_message") or delivery.get("message"))[:300],
        "url": action_url,
        "icon": "/assets/app-icon-192.png",
        "badge": "/assets/app-icon-192.png",
        "tag": f"courseplatform-{str_value(delivery.get('notification_id'))[:80]}",
        "notificationId": str_value(delivery.get("notification_id")),
        "priority": str_value(delivery.get("priority") or "NORMAL"),
    }, ensure_ascii=False)
    delivered = 0
    failures: list[str] = []
    for subscription in subscriptions:
        try:
            response = webpush(
                subscription_info={
                    "endpoint": subscription["endpoint"],
                    "keys": {"p256dh": subscription["p256dh"], "auth": subscription["auth"]},
                },
                data=payload,
                vapid_private_key=configuration["privateKey"],
                vapid_claims={"sub": configuration["subject"]},
                ttl=configuration["ttlSeconds"],
                timeout=configuration["timeoutSeconds"],
            )
            status_code = int(getattr(response, "status_code", 201) or 201)
            if status_code >= 400:
                raise RuntimeError(f"Serviço Push HTTP {status_code}.")
            delivered += 1
            update_push_subscription_delivery(subscription["subscription_id"], True)
        except Exception as error:
            response = getattr(error, "response", None)
            status_code = int(getattr(response, "status_code", 0) or 0)
            expired = status_code in {404, 410}
            update_push_subscription_delivery(subscription["subscription_id"], False, expired)
            failures.append(redact_notification_error(error, subscription.get("endpoint")))
    if not delivered:
        raise RuntimeError(failures[-1] if failures else "A notificação Push não foi entregue.")
    return f"{delivered} dispositivo(s)"


def telegram_get_updates(configuration: dict[str, Any], offset: int = 0) -> list[dict[str, Any]]:
    """Read pending bot updates without long polling (used by account linking)."""
    if not configuration.get("configured"):
        raise RuntimeError("Integração Telegram ainda não configurada no servidor.")
    query = urlencode({
        "offset": max(0, int(offset)),
        "limit": 100,
        "timeout": 0,
        "allowed_updates": json.dumps(["message"]),
    })
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{configuration['botToken']}/getUpdates?{query}",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=max(3, int(configuration.get("timeoutSeconds") or 12)),
        ) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        response_text = error.read().decode("utf-8", errors="replace")[:700]
        safe_error = redact_notification_error(response_text, configuration.get("botToken"))
        raise RuntimeError(f"Telegram Bot API HTTP {error.code}: {safe_error}") from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        safe_error = redact_notification_error(error, configuration.get("botToken"))
        raise RuntimeError(f"Falha ao confirmar a ligação ao Telegram: {safe_error}") from error
    updates = result.get("result") if isinstance(result, dict) else None
    if not isinstance(result, dict) or not result.get("ok") or not isinstance(updates, list):
        description = str_value(result.get("description")) if isinstance(result, dict) else "Resposta inválida"
        safe_error = redact_notification_error(description, configuration.get("botToken"))
        raise RuntimeError(f"A API do Telegram rejeitou a consulta: {safe_error}")
    return [item for item in updates if isinstance(item, dict)]


def process_telegram_link_updates(configuration: dict[str, Any] | None = None) -> int:
    """Associate every valid /start token in the queue before advancing its offset."""
    configuration = configuration or telegram_runtime_configuration()
    state = fetch_one(
        "select cursor_value from courseplatform.notification_channel_state where channel = 'TELEGRAM'"
    ) or {}
    offset = int_value(state.get("cursor_value"))
    updates = telegram_get_updates(configuration, offset)
    if not updates:
        return 0
    linked = 0
    highest_update_id = offset - 1
    with connection() as conn:
        for update in updates:
            update_id = int_value(update.get("update_id"), -1)
            highest_update_id = max(highest_update_id, update_id)
            message = update.get("message") if isinstance(update.get("message"), dict) else {}
            chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
            match = re.fullmatch(
                r"/start(?:@[A-Za-z0-9_]+)?\s+([A-Za-z0-9_-]{20,64})",
                str_value(message.get("text")),
            )
            chat_id = normalize_telegram_recipient(chat.get("id"))
            if not match or not chat_id or str_value(chat.get("type")) != "private":
                continue
            token_hash = hash_secret(match.group(1))
            link = conn.execute(
                """
                select * from courseplatform.telegram_link_tokens
                where token_hash = %s and consumed_at is null and expires_at > now()
                for update
                """,
                (token_hash,),
            ).fetchone()
            if not link:
                continue
            conn.execute(
                """
                update courseplatform.students
                set telegram_chat_id = %s, telegram_opt_in = true,
                    telegram_opt_in_at = coalesce(telegram_opt_in_at, now()), updated_at = now()
                where student_id = %s
                """,
                (chat_id, link["student_id"]),
            )
            conn.execute(
                """
                update courseplatform.telegram_link_tokens
                set consumed_at = now(), telegram_update_id = %s
                where token_hash = %s
                """,
                (update_id, token_hash),
            )
            audit(
                conn,
                "STUDENT",
                link["student_id"],
                "TELEGRAM_LINKED",
                "STUDENT",
                link["student_id"],
                {"channel": "TELEGRAM"},
            )
            linked += 1
        if highest_update_id >= offset:
            conn.execute(
                """
                insert into courseplatform.notification_channel_state(channel, cursor_value, updated_at)
                values ('TELEGRAM', %s, now())
                on conflict (channel) do update set
                  cursor_value = greatest(courseplatform.notification_channel_state.cursor_value, excluded.cursor_value),
                  updated_at = now()
                """,
                (highest_update_id + 1,),
            )
        conn.commit()
    return linked


def claim_notification_deliveries(
    channel: str,
    notification_ids: list[str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Atomically lease one channel's queue so workers cannot send duplicates."""
    normalized_channel = str_value(channel).upper()
    if normalized_channel not in {"WHATSAPP", "EMAIL", "TELEGRAM", "PUSH"}:
        raise ValueError("Canal de notificação inválido.")
    notification_filter = ""
    params: list[Any] = [normalized_channel]
    if notification_ids:
        notification_filter = " and d.notification_id = any(%s)"
        params.append(notification_ids)
    params.append(max(1, min(int(limit), 200)))
    query = f"""
        with candidates as (
          select d.delivery_id
          from courseplatform.notification_deliveries d
          where d.channel = %s
            and (
              d.status in ('PENDING', 'FAILED')
              or (
                d.status = 'PROCESSING'
                and coalesce(d.updated_at, d.created_at) < now() - interval '5 minutes'
              )
            )
            and d.attempt_count < 3
            {notification_filter}
          order by d.created_at
          limit %s
          for update of d skip locked
        ), claimed as (
          update courseplatform.notification_deliveries d
          set status = 'PROCESSING',
              attempt_count = d.attempt_count + 1,
              last_error = null,
              updated_at = now()
          from candidates c
          where d.delivery_id = c.delivery_id
          returning d.*
        )
        select claimed.*, n.student_id, n.notification_id, n.title, n.message,
               n.email_subject, n.email_message, n.push_title, n.push_message,
               n.action_url, n.priority, s.full_name as student_name
        from claimed
        join courseplatform.notifications n on n.notification_id = claimed.notification_id
        join courseplatform.students s on s.student_id = n.student_id
        order by claimed.created_at
    """
    with connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
        conn.commit()
    return rows


def claim_whatsapp_deliveries(notification_ids: list[str] | None, limit: int) -> list[dict[str, Any]]:
    return claim_notification_deliveries("WHATSAPP", notification_ids, limit)


def claim_email_deliveries(notification_ids: list[str] | None, limit: int) -> list[dict[str, Any]]:
    return claim_notification_deliveries("EMAIL", notification_ids, limit)


def claim_telegram_deliveries(notification_ids: list[str] | None, limit: int) -> list[dict[str, Any]]:
    return claim_notification_deliveries("TELEGRAM", notification_ids, limit)


def claim_push_deliveries(notification_ids: list[str] | None, limit: int) -> list[dict[str, Any]]:
    return claim_notification_deliveries("PUSH", notification_ids, limit)


def deliver_pending_channel(
    channel: str,
    configuration_loader,
    sender,
    notification_ids: list[str] | None = None,
    limit: int = 50,
) -> dict[str, int]:
    configuration = configuration_loader()
    if not configuration["configured"]:
        return {"sent": 0, "failed": 0, "pending": 0}
    prepare_notification_feature_schema()
    rows = claim_notification_deliveries(channel, notification_ids, limit)
    delivery_results: list[tuple[dict[str, Any], str, str]] = []
    if rows:
        worker_count = min(5, len(rows))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {executor.submit(sender, delivery, configuration): delivery for delivery in rows}
            for future in as_completed(futures):
                delivery = futures[future]
                try:
                    delivery_results.append((delivery, "SENT", future.result()))
                except Exception as error:
                    delivery_results.append((
                        delivery,
                        "FAILED",
                        redact_notification_error(
                            error,
                            configuration.get("accessToken"),
                            configuration.get("smtpPassword"),
                            configuration.get("botToken"),
                            configuration.get("privateKey"),
                            configuration.get("encryptionKey"),
                        ),
                    ))

    sent = 0
    failed = 0
    with connection() as conn:
        for delivery, result_status, result_value in delivery_results:
            if result_status == "SENT":
                conn.execute(
                    """
                    update courseplatform.notification_deliveries
                    set status = 'SENT', provider_message_id = %s,
                        last_error = null, sent_at = now(), updated_at = now()
                    where delivery_id = %s and status = 'PROCESSING'
                    """,
                    (result_value or None, delivery["delivery_id"]),
                )
                sent += 1
            else:
                conn.execute(
                    """
                    update courseplatform.notification_deliveries
                    set status = 'FAILED', last_error = %s, updated_at = now()
                    where delivery_id = %s and status = 'PROCESSING'
                    """,
                    (result_value, delivery["delivery_id"]),
                )
                failed += 1
        conn.commit()
    return {"sent": sent, "failed": failed, "pending": max(0, len(rows) - sent - failed)}


def deliver_pending_whatsapp(notification_ids: list[str] | None = None, limit: int = 50) -> dict[str, int]:
    return deliver_pending_channel(
        "WHATSAPP", whatsapp_runtime_configuration, send_whatsapp_template,
        notification_ids, limit,
    )


def deliver_pending_email(notification_ids: list[str] | None = None, limit: int = 50) -> dict[str, int]:
    return deliver_pending_channel(
        "EMAIL", email_runtime_configuration, send_email_notification,
        notification_ids, limit,
    )


def deliver_pending_telegram(notification_ids: list[str] | None = None, limit: int = 50) -> dict[str, int]:
    return deliver_pending_channel(
        "TELEGRAM", telegram_runtime_configuration, send_telegram_notification,
        notification_ids, limit,
    )


def deliver_pending_push(notification_ids: list[str] | None = None, limit: int = 50) -> dict[str, int]:
    return deliver_pending_channel(
        "PUSH", web_push_runtime_configuration, send_web_push_notification,
        notification_ids, limit,
    )


def dispatch_notification_deliveries(notification_ids: list[str]) -> None:
    if not notification_ids:
        return
    for delivery_function in (
        deliver_pending_whatsapp,
        deliver_pending_email,
        deliver_pending_telegram,
        deliver_pending_push,
    ):
        try:
            # Keep the request bounded while covering a typical class in one
            # operation. Larger campaigns remain safely queued and are exposed
            # through the administrative retry control.
            delivery_function(notification_ids, limit=20)
        except Exception:
            # Internal notifications are the source of truth; a provider outage
            # must never roll back the administrative transaction.
            continue


ASSESSMENT_FEATURE_SQL = """
alter table courseplatform.lessons add column if not exists submission_duration_minutes integer;
alter table courseplatform.lesson_progress add column if not exists content_access_status text;
alter table courseplatform.lesson_progress add column if not exists evaluation_status text;
update courseplatform.lesson_progress
set content_access_status = case when status = 'LOCKED' then 'LOCKED' else 'AVAILABLE' end
where content_access_status is null;
update courseplatform.lesson_progress
set evaluation_status = case
  when status in ('IN_PROGRESS', 'UNDER_REVIEW', 'CORRECTION_REQUIRED', 'APPROVED', 'FAILED', 'TIME_EXCEEDED') then status
  else 'NOT_STARTED'
end
where evaluation_status is null;
alter table courseplatform.lesson_progress alter column content_access_status set default 'LOCKED';
alter table courseplatform.lesson_progress alter column evaluation_status set default 'NOT_STARTED';
create index if not exists idx_progress_access_evaluation
  on courseplatform.lesson_progress(content_access_status, evaluation_status);
"""


CERTIFICATE_FEATURE_SQL = """
alter table courseplatform.certificates add column if not exists certificate_type text not null default 'SIMPLE';
alter table courseplatform.certificates add column if not exists recognition_level text not null default 'PARTICIPATION';
alter table courseplatform.certificates add column if not exists content_summary text;
alter table courseplatform.certificates add column if not exists professional_request_id text;
alter table courseplatform.certificates add column if not exists download_count integer not null default 0;
alter table courseplatform.certificates add column if not exists max_downloads integer;
alter table courseplatform.certificates add column if not exists payment_status text not null default 'NOT_REQUIRED';
alter table courseplatform.certificates add column if not exists approved_by text;
alter table courseplatform.certificates add column if not exists approved_at timestamptz;
alter table courseplatform.certificates add column if not exists status_note text;
alter table courseplatform.certificates add column if not exists status_updated_by text;
alter table courseplatform.certificates add column if not exists status_updated_at timestamptz;
alter table courseplatform.certificates add column if not exists template_snapshot_json jsonb not null default '{}'::jsonb;
create table if not exists courseplatform.certificate_settings (
  course_id text primary key references courseplatform.courses(course_id) on delete cascade,
  congratulations_message text,
  survey_questions_json jsonb not null default '[]'::jsonb,
  professional_price text,
  payment_instructions text,
  professional_preview_url text,
  certificate_profile_json jsonb not null default '{}'::jsonb,
  updated_by text,
  updated_at timestamptz
);
alter table courseplatform.certificate_settings add column if not exists certificate_profile_json jsonb not null default '{}'::jsonb;

create table if not exists courseplatform.certificate_requests (
  request_id text primary key,
  student_id text not null references courseplatform.students(student_id) on delete cascade,
  course_id text not null references courseplatform.courses(course_id) on delete cascade,
  certificate_id text references courseplatform.certificates(certificate_id) on delete set null,
  request_type text not null default 'PROFESSIONAL',
  status text not null default 'REQUESTED',
  survey_answers_json jsonb not null default '{}'::jsonb,
  payment_receipt_name text,
  payment_receipt_url text,
  payment_receipt_mime_type text,
  submitted_at timestamptz,
  reviewed_by text,
  reviewed_at timestamptz,
  admin_notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz
);

create index if not exists idx_certificate_requests_student_course
  on courseplatform.certificate_requests(student_id, course_id, status);
"""


def execute_statements(conn, sql: str) -> None:
    for statement in [part.strip() for part in sql.split(";") if part.strip()]:
        conn.execute(statement)


def ensure_assessment_feature_schema(conn) -> None:
    execute_statements(conn, ASSESSMENT_FEATURE_SQL)


def prepare_assessment_feature_schema() -> None:
    global _ASSESSMENT_SCHEMA_READY
    if _ASSESSMENT_SCHEMA_READY:
        return
    with connection() as conn:
        ensure_assessment_feature_schema(conn)
        conn.commit()
    _ASSESSMENT_SCHEMA_READY = True


def ensure_certificate_feature_schema(conn) -> None:
    execute_statements(conn, CERTIFICATE_FEATURE_SQL)


def public_certificate(row: dict[str, Any] | None):
    if not row:
        return None
    return {
        "certificateId": row["certificate_id"],
        "studentId": row.get("student_id"),
        "courseId": row.get("course_id"),
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
        "templateSnapshot": row.get("template_snapshot_json") or {},
        "courseTitle": row.get("course_title") or row.get("title"),
        "studentName": row.get("student_name") or row.get("full_name"),
    }


def public_certificate_request(row: dict[str, Any] | None):
    if not row:
        return None
    return {
        "requestId": row["request_id"],
        "studentId": row.get("student_id"),
        "courseId": row.get("course_id"),
        "certificateId": row.get("certificate_id"),
        "requestType": row.get("request_type"),
        "status": row.get("status"),
        "surveyAnswers": row.get("survey_answers_json") or {},
        "paymentReceiptName": row.get("payment_receipt_name"),
        "paymentReceiptUrl": row.get("payment_receipt_url"),
        "paymentReceiptMimeType": row.get("payment_receipt_mime_type"),
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
        "assets": {
            "logoUrl": "",
            "productLogoUrl": "",
            "directorSignatureUrl": "",
            "academicStampUrl": "",
            "coordinatorSignatureUrl": "",
            "institutionalSealUrl": "",
        },
    }


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


def certificate_template_snapshot(conn, course_id: str, certificate_type: str = "SIMPLE") -> dict[str, Any]:
    course = conn.execute("select * from courseplatform.courses where course_id = %s", (course_id,)).fetchone()
    row = conn.execute("select * from courseplatform.certificate_settings where course_id = %s", (course_id,)).fetchone()
    settings = certificate_settings_payload(row, course)
    profile = normalize_certificate_profile(settings.get("certificateProfile"), course)
    if not profile.get("certifiedContents"):
        profile["certifiedContents"] = certificate_content_summary(conn, course_id)
    return {
        "version": 1,
        "certificateType": certificate_type,
        "capturedAt": iso(utc_now()),
        "courseId": course_id,
        "courseTitle": (course or {}).get("title"),
        "courseHours": float((course or {}).get("total_hours") or 0),
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


def certificate_content_summary(conn, course_id: str) -> str:
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


def course_completion_snapshot(conn, student_id: str, course_id: str):
    ensure_assessment_feature_schema(conn)
    enrollment = conn.execute(
        "select * from courseplatform.enrollments where student_id = %s and course_id = %s",
        (student_id, course_id),
    ).fetchone()
    course = conn.execute("select * from courseplatform.courses where course_id = %s", (course_id,)).fetchone()
    lesson_total = conn.execute(
        """
        select count(*) as total
        from courseplatform.lessons
        where course_id = %s and coalesce(status, 'ACTIVE') = 'ACTIVE'
        """,
        (course_id,),
    ).fetchone()
    approved_total = conn.execute(
        """
        select count(distinct p.lesson_id) as total
        from courseplatform.lesson_progress p
        join courseplatform.lessons l on l.lesson_id = p.lesson_id
        where p.student_id = %s and l.course_id = %s
          and coalesce(p.evaluation_status, p.status) = 'APPROVED'
          and coalesce(l.status, 'ACTIVE') = 'ACTIVE'
        """,
        (student_id, course_id),
    ).fetchone()
    total = int((lesson_total or {}).get("total") or 0)
    approved = int((approved_total or {}).get("total") or 0)
    progress = float((enrollment or {}).get("progress_percent") or 0)
    completed = bool(enrollment) and (
        enrollment.get("status") == "COMPLETED" or progress >= 100 or (total > 0 and approved >= total)
    )
    return enrollment, course, total, approved, completed


def sync_enrollment_completion(conn, enrollment: dict[str, Any] | None, completed: bool, final_score: float | None = None):
    if not enrollment or not completed:
        return enrollment
    if enrollment.get("status") == "COMPLETED" and float(enrollment.get("progress_percent") or 0) >= 100:
        return enrollment
    return conn.execute(
        """
        update courseplatform.enrollments
        set status = 'COMPLETED',
            progress_percent = 100,
            final_score = coalesce(%s, final_score),
            completed_at = coalesce(completed_at, now()),
            updated_at = now()
        where enrollment_id = %s
        returning *
        """,
        (final_score, enrollment["enrollment_id"]),
    ).fetchone()


def refresh_enrollment_progress(conn, progress_id: str | None):
    if not progress_id:
        return None
    progress = conn.execute(
        "select enrollment_id from courseplatform.lesson_progress where progress_id = %s",
        (progress_id,),
    ).fetchone()
    if not progress:
        return None
    summary = conn.execute(
        """
        select
          count(*) filter (where coalesce(l.status, 'ACTIVE') = 'ACTIVE') as lesson_total,
          count(*) filter (
            where coalesce(l.status, 'ACTIVE') = 'ACTIVE'
              and coalesce(p.evaluation_status, p.status) = 'APPROVED'
          ) as approved_total,
          avg(p.score) filter (
            where coalesce(l.status, 'ACTIVE') = 'ACTIVE' and p.score is not null
          ) as average_score
        from courseplatform.enrollments e
        join courseplatform.lessons l on l.course_id = e.course_id
        left join courseplatform.lesson_progress p
          on p.enrollment_id = e.enrollment_id and p.lesson_id = l.lesson_id
        where e.enrollment_id = %s
        """,
        (progress["enrollment_id"],),
    ).fetchone()
    total = int((summary or {}).get("lesson_total") or 0)
    approved = int((summary or {}).get("approved_total") or 0)
    percent = round((approved / total) * 100, 2) if total else 0
    completed = total > 0 and approved >= total
    return conn.execute(
        """
        update courseplatform.enrollments
        set progress_percent = %s,
            final_score = %s,
            status = case
              when status in ('BLOCKED', 'INACTIVE') then status
              when %s then 'COMPLETED'
              else 'ACTIVE'
            end,
            completed_at = case when %s then coalesce(completed_at, now()) else null end,
            updated_at = now()
        where enrollment_id = %s
        returning *
        """,
        (
            percent,
            None if (summary or {}).get("average_score") is None else float(summary["average_score"]),
            completed,
            completed,
            progress["enrollment_id"],
        ),
    ).fetchone()


def ensure_simple_certificate(conn, student: dict[str, Any], course_id: str):
    ensure_certificate_feature_schema(conn)
    enrollment, course, _, _, completed = course_completion_snapshot(conn, student["student_id"], course_id)
    enrollment = sync_enrollment_completion(conn, enrollment, completed, (enrollment or {}).get("final_score"))
    if not completed:
        return None, enrollment, course, False
    existing = conn.execute(
        """
        select cert.*, c.title as course_title, s.full_name as student_name
        from courseplatform.certificates cert
        join courseplatform.courses c on c.course_id = cert.course_id
        join courseplatform.students s on s.student_id = cert.student_id
        where cert.student_id = %s and cert.course_id = %s
          and coalesce(cert.certificate_type, 'SIMPLE') = 'SIMPLE'
          and coalesce(cert.status, 'ISSUED') <> 'DELETED'
        order by cert.issue_date desc nulls last
        limit 1
        """,
        (student["student_id"], course_id),
    ).fetchone()
    if existing:
        return existing, enrollment, course, True
    cert = conn.execute(
        """
        insert into courseplatform.certificates
          (certificate_id, student_id, course_id, certificate_number, verification_code,
           issue_date, final_score, drive_file_id, drive_url, status, certificate_type,
           recognition_level, content_summary, template_snapshot_json, max_downloads, payment_status)
        values (%s, %s, %s, %s, %s, now(), %s, '', '', 'ISSUED', 'SIMPLE',
                'PARTICIPATION', %s, %s, null, 'NOT_REQUIRED')
        returning *
        """,
        (
            generate_id("CERT"),
            student["student_id"],
            course_id,
            certificate_number(),
            certificate_verification_code(),
            (enrollment or {}).get("final_score"),
            certificate_content_summary(conn, course_id),
            json.dumps(certificate_template_snapshot(conn, course_id, "SIMPLE")),
        ),
    ).fetchone()
    return {**cert, "course_title": (course or {}).get("title"), "student_name": student.get("full_name")}, enrollment, course, True


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
        "select * from courseplatform.admins where admin_id = %s",
        (admin_id,),
    )
    if not admin or admin.get("status") != "ACTIVE":
        raise ApiError("ADMIN_NOT_ACTIVE", "A conta administrativa não está ativa.")
    if allowed_roles and admin.get("role") not in allowed_roles:
        raise ApiError("FORBIDDEN", "O seu perfil não possui permissão para esta operação.")
    return session, admin


def health(_: dict[str, Any]):
    settings = get_settings()
    db_ok = False
    db_error = ""
    db_error_hint = ""
    schema_created = False
    data_diagnostics = {
        "students": 0,
        "studentsWithPassword": 0,
        "admins": 0,
        "adminsWithPassword": 0,
        "courses": 0,
        "lessons": 0,
        "dataReady": False,
    }
    try:
        db_ok = schema_exists()
        if not db_ok:
            schema_created = ensure_schema()
            db_ok = schema_exists()
        if db_ok:
            data_row = fetch_one(
                """
                select
                  (select count(*) from courseplatform.students) as students,
                  (select count(*) from courseplatform.students where password_hash is not null) as students_with_password,
                  (select count(*) from courseplatform.admins) as admins,
                  (select count(*) from courseplatform.admins where password_hash is not null) as admins_with_password,
                  (select count(*) from courseplatform.courses) as courses,
                  (select count(*) from courseplatform.lessons) as lessons
                """
            )
            data_diagnostics = {
                "students": int(data_row.get("students") or 0),
                "studentsWithPassword": int(data_row.get("students_with_password") or 0),
                "admins": int(data_row.get("admins") or 0),
                "adminsWithPassword": int(data_row.get("admins_with_password") or 0),
                "courses": int(data_row.get("courses") or 0),
                "lessons": int(data_row.get("lessons") or 0),
                "dataReady": bool((data_row.get("students") or 0) and (data_row.get("admins") or 0)),
            }
        else:
            db_error = "SchemaMissing"
            db_error_hint = "Conexao Postgres ok, mas o schema courseplatform não foi encontrado e não foi possível cria-lo automaticamente."
    except Exception as error:
        db_ok = False
        db_error = error.__class__.__name__
        db_error_message = diagnostic_error_message(error)
        error_text = str(error).lower()
        if "ecircuitbreaker" in error_text:
            db_error_hint = "O pooler do Supabase bloqueou novas ligações após várias falhas de autenticação. Aguarde alguns minutos e confirme o utilizador e a palavra-passe do Postgres."
        elif "authentication" in error_text or "password" in error_text:
            db_error_hint = "Falha de autenticação no Postgres. Confirme POSTGRES_USER/POSTGRES_PASSWORD ou DATABASE_URL."
        elif "timeout" in error_text or "timed out" in error_text:
            db_error_hint = "Tempo limite de ligação excedido. Confirme o host, a porta, a rede e se o projeto Supabase está ativo."
        elif db_error == "ProgrammingError":
            db_error_hint = "Erro de SQL/configuração Postgres. Confirme se o schema courseplatform foi criado no mesmo projeto apontado por POSTGRES_URL."
    else:
        db_error_message = ""
    return success({
        "version": settings.app_version,
        "database": db_ok,
        "databaseConfigured": bool(settings.database_url),
        "databaseError": "" if db_ok else db_error,
        "databaseErrorHint": "" if db_ok else db_error_hint,
        "databaseErrorMessage": "" if db_ok else db_error_message,
        "schemaCreated": schema_created,
        "dataDiagnostics": data_diagnostics,
        "authConfigured": db_ok
        and data_diagnostics["studentsWithPassword"] > 0
        and data_diagnostics["adminsWithPassword"] > 0,
        "authDiagnostics": {
            "mode": "supabase_postgres_bcrypt",
            "requiresPasswordPepper": False,
            "requiresAdminMasterKeyHash": False,
            "adminRecoveryConfigured": bool(configured_admin_recovery_hashes()),
        },
        "databaseDiagnostics": settings.database_diagnostics,
    })


def public_course_config(payload: dict[str, Any]):
    course_id = payload.get("courseId") or get_settings().default_course_id
    course = fetch_one(
        "select * from courseplatform.courses where course_id = %s and status = 'ACTIVE'",
        (course_id,),
    )
    lessons = fetch_all(
        """
        select * from courseplatform.lessons
        where course_id = %s and status = 'ACTIVE'
        order by lesson_number
        """,
        (course_id,),
    )
    return success({"course": public_course(course), "lessons": [public_lesson(row) for row in lessons]})


def read_media_config(course_id: str):
    key = f"MEDIA_CONFIG:{course_id or get_settings().default_course_id}"
    row = fetch_one("select value from courseplatform.settings where key = %s", (key,))
    if not row:
        row = fetch_one("select value from courseplatform.settings where key = 'MEDIA_CONFIG'")
    if not row or not row.get("value"):
        return {"logoUrl": "", "videos": []}
    try:
        return json.loads(row["value"])
    except json.JSONDecodeError:
        return {"logoUrl": "", "videos": []}


def read_media_config_with_conn(conn, course_id: str):
    key = f"MEDIA_CONFIG:{course_id or get_settings().default_course_id}"
    row = conn.execute("select value from courseplatform.settings where key = %s", (key,)).fetchone()
    if not row:
        row = conn.execute("select value from courseplatform.settings where key = 'MEDIA_CONFIG'").fetchone()
    if not row or not row.get("value"):
        return {"logoUrl": "", "videos": []}
    try:
        return json.loads(row["value"])
    except json.JSONDecodeError:
        return {"logoUrl": "", "videos": []}


def student_visible_media(media: dict[str, Any], student: dict[str, Any]):
    email = normalize_email(student.get("email") or "")
    videos = []
    for video in media.get("videos", []):
        if video.get("status", "ACTIVE") != "ACTIVE":
            continue
        if video.get("visibility") == "SELECTED":
            allowed = [normalize_email(item) for item in video.get("allowedEmails", [])]
            if email not in allowed:
                continue
            videos.append({**video, "allowedEmails": [email]})
        else:
            videos.append({**video, "allowedEmails": []})
    return {**media, "videos": videos}


def student_media_config(payload: dict[str, Any]):
    _, student = student_context(payload)
    media = read_media_config(payload.get("courseId") or get_settings().default_course_id)
    return success({"mediaConfig": student_visible_media(media, student)})


def public_media_config(payload: dict[str, Any]):
    media = read_media_config(payload.get("courseId") or get_settings().default_course_id)
    videos = [
        video
        for video in media.get("videos", [])
        if video.get("status", "ACTIVE") == "ACTIVE" and video.get("visibility") != "SELECTED"
    ]
    return success({"mediaConfig": {**media, "videos": videos}})


def admin_media_config(payload: dict[str, Any]):
    admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    media = read_media_config(payload.get("courseId") or get_settings().default_course_id)
    return success({"mediaConfig": media})


def login(payload: dict[str, Any]):
    require_fields(payload, ["email", "accessCode"])
    email = normalize_email(payload["email"])
    try:
        student = fetch_one("select * from courseplatform.students where email = %s", (email,))
    except Exception as error:
        raise database_api_error(error) from error
    if not student or student.get("status") != "ACTIVE":
        total = fetch_one("select count(*) as total from courseplatform.students")
        if int(total.get("total") or 0) == 0:
            raise ApiError(
                "DATABASE_EMPTY",
                "A base de dados ligada ainda não tem estudantes. Confirme se o POSTGRES_URL aponta para a base migrada.",
            )
        raise ApiError("INVALID_CREDENTIALS", "Email ou código de acesso inválido.")
    try:
        if not verify_password(payload["accessCode"], student.get("password_hash")):
            raise ApiError("INVALID_CREDENTIALS", "Email ou código de acesso inválido.")
        with connection() as conn:
            revoke_sessions(conn, student["student_id"])
            session = create_session(conn, student["student_id"], payload.get("userAgent", ""), payload.get("ipHash", ""))
            conn.execute(
                "update courseplatform.students set last_login_at = now(), updated_at = now() where student_id = %s",
                (student["student_id"],),
            )
            conn.commit()
    except ApiError:
        raise
    except Exception as error:
        raise database_api_error(error) from error
    return success({"sessionToken": session["token"], "expiresAt": iso(session["expiresAt"]), "student": public_student(student)})


def mask_email(email: str) -> str:
    local, separator, domain = (email or "").partition("@")
    if not separator:
        return email
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}{'*' * max(2, len(local) - len(visible))}@{domain}"


def recover_student_access(payload: dict[str, Any]):
    require_fields(payload, ["email", "publicStudentId"])
    email = normalize_email(payload["email"])
    public_id = str_value(payload.get("publicStudentId")).upper()
    try:
        student = fetch_one(
            """
            select *
            from courseplatform.students
            where email = %s and upper(coalesce(public_student_id, '')) = %s
            """,
            (email, public_id),
        )
    except Exception as error:
        raise database_api_error(error) from error
    if not student or student.get("status") != "ACTIVE":
        raise ApiError(
            "RECOVERY_DETAILS_NOT_FOUND",
            "Não encontramos uma conta ativa com esse email e ID de estudante.",
        )

    access_code = generate_access_code(12)
    try:
        with connection() as conn:
            row = conn.execute(
                """
                update courseplatform.students
                set password_hash = crypt(%s, gen_salt('bf', 12)),
                    password_changed_at = now(), password_reset_required = true,
                    access_code = null, updated_at = now()
                where student_id = %s
                returning *
                """,
                (access_code, student["student_id"]),
            ).fetchone()
            conn.execute(
                "update courseplatform.sessions set active = false, revoked_at = now() where subject_id = %s",
                (student["student_id"],),
            )
            audit(
                conn,
                "SYSTEM",
                "STUDENT_RECOVERY",
                "STUDENT_ACCESS_RECOVERED",
                "STUDENT",
                student["student_id"],
                {"publicStudentId": row.get("public_student_id")},
            )
            conn.commit()
    except Exception as error:
        raise database_api_error(error) from error

    return success({
        "email": mask_email(row.get("email") or email),
        "publicStudentId": row.get("public_student_id") or public_id,
        "temporaryPassword": access_code,
    })


def admin_login(payload: dict[str, Any]):
    require_fields(payload, ["email", "adminKey"])
    email = normalize_email(payload["email"])
    try:
        admin = fetch_one("select * from courseplatform.admins where email = %s", (email,))
    except Exception as error:
        raise database_api_error(error) from error
    if not admin or admin.get("status") != "ACTIVE":
        total = fetch_one("select count(*) as total from courseplatform.admins")
        if int(total.get("total") or 0) == 0:
            raise ApiError(
                "DATABASE_EMPTY",
                "A base de dados ligada ainda não tem administradores. Confirme se o POSTGRES_URL aponta para a base migrada.",
            )
        raise ApiError("INVALID_ADMIN_CREDENTIALS", "Credenciais administrativas invalidas.")
    try:
        if not verify_password(payload["adminKey"], admin.get("password_hash")):
            raise ApiError("INVALID_ADMIN_CREDENTIALS", "Credenciais administrativas invalidas.")
        subject_id = f"ADMIN:{admin['admin_id']}"
        with connection() as conn:
            revoke_sessions(conn, subject_id)
            session = create_session(conn, subject_id, payload.get("userAgent", ""), payload.get("ipHash", ""))
            conn.commit()
    except ApiError:
        raise
    except Exception as error:
        raise database_api_error(error) from error
    return success({"adminToken": session["token"], "expiresAt": iso(session["expiresAt"]), "admin": public_admin(admin)})


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
    require_fields(payload, ["email", "recoveryKey"])
    if not configured_admin_recovery_hashes():
        raise ApiError(
            "ADMIN_RECOVERY_NOT_CONFIGURED",
            "A recuperação administrativa ainda não está configurada. Defina ADMIN_RECOVERY_KEY_HASH na Vercel.",
        )
    if not verify_admin_recovery_key(payload.get("recoveryKey")):
        raise ApiError("INVALID_ADMIN_RECOVERY_KEY", "Chave de recuperação administrativa inválida.")

    email = normalize_email(payload["email"])
    try:
        admin = fetch_one("select * from courseplatform.admins where email = %s", (email,))
    except Exception as error:
        raise database_api_error(error) from error
    if not admin or admin.get("status") != "ACTIVE":
        raise ApiError("ADMIN_RECOVERY_NOT_FOUND", "Não encontramos uma conta administrativa ativa com esse email.")

    admin_password = generate_access_code(14)
    try:
        with connection() as conn:
            row = conn.execute(
                """
                update courseplatform.admins
                set password_hash = crypt(%s, gen_salt('bf', 12)),
                    password_changed_at = now(), password_reset_required = true,
                    updated_at = now()
                where admin_id = %s
                returning *
                """,
                (admin_password, admin["admin_id"]),
            ).fetchone()
            conn.execute(
                "update courseplatform.sessions set active = false, revoked_at = now() where subject_id = %s",
                (f"ADMIN:{admin['admin_id']}",),
            )
            audit(
                conn,
                "SYSTEM",
                "ADMIN_RECOVERY",
                "ADMIN_ACCESS_RECOVERED",
                "ADMIN",
                admin["admin_id"],
                {"role": row.get("role"), "email": mask_email(row.get("email") or email)},
            )
            conn.commit()
    except Exception as error:
        raise database_api_error(error) from error

    return success({
        "admin": public_admin(row),
        "email": mask_email(row.get("email") or email),
        "temporaryAdminKey": admin_password,
    })


def logout(payload: dict[str, Any]):
    token = payload.get("sessionToken") or payload.get("adminToken")
    if token:
        with connection() as conn:
            conn.execute(
                "update courseplatform.sessions set active = false, revoked_at = now() where session_token = %s",
                (hash_secret(token),),
            )
            conn.commit()
    return success({"loggedOut": True})


def admin_me(payload: dict[str, Any]):
    _, admin = admin_context(payload)
    return success({"admin": public_admin(admin)})


def my_courses(payload: dict[str, Any]):
    require_session_token(payload)
    with connection() as conn:
        _, student = student_context_with_conn(conn, payload)
        rows = student_courses_rows(conn, student["student_id"])
    return success({
        "student": public_student(student),
        "courses": student_courses_payload(rows),
        "notificationChannelInfo": student_notification_channel_info(),
    })


def student_courses_rows(conn, student_id: str):
    return conn.execute(
        """
        select
          e.enrollment_id, e.student_id, e.course_id as enrollment_course_id,
          e.group_id, e.status as enrollment_status, e.enrolled_at, e.completed_at,
          e.progress_percent, e.final_score, e.certificate_id,
          c.course_id, c.course_code, c.title, c.description, c.total_hours,
          c.passing_score, c.status as course_status, c.created_at, c.updated_at,
          g.name as group_name, g.start_date, g.end_date,
          (
            select count(*)
            from courseplatform.lessons l
            where l.course_id = c.course_id and l.status = 'ACTIVE'
          ) as lesson_count
        from courseplatform.enrollments e
        join courseplatform.courses c on c.course_id = e.course_id
        left join courseplatform.groups g on g.group_id = e.group_id
        where e.student_id = %s and c.status <> 'DELETED'
        order by c.title
        """,
        (student_id,),
    ).fetchall()


def student_courses_payload(rows: list[dict[str, Any]]):
    courses = []
    for row in rows:
        enrollment_row = {
            **row,
            "course_id": row.get("enrollment_course_id"),
            "status": row.get("enrollment_status"),
        }
        course_row = {
            **row,
            "status": row.get("course_status"),
        }
        courses.append({
            "course": public_course(course_row),
            "enrollment": public_enrollment(enrollment_row),
            "group": {
                "name": row.get("group_name"),
                "startDate": iso(row.get("start_date")),
                "endDate": iso(row.get("end_date")),
            } if row.get("group_name") else None,
            "lessonCount": int(row.get("lesson_count") or 0),
        })
    return courses


def dashboard_payload(conn, student: dict[str, Any], course_id: str):
    enrollment = conn.execute(
        "select * from courseplatform.enrollments where student_id = %s and course_id = %s",
        (student["student_id"], course_id),
    ).fetchone()
    course = conn.execute("select * from courseplatform.courses where course_id = %s", (course_id,)).fetchone()
    lessons = conn.execute(
        """
        select l.*, p.progress_id, p.status as progress_status,
               p.content_access_status, p.evaluation_status, p.score, p.attempt_count,
               p.unlocked_at, p.started_at, p.submitted_at, p.approved_at,
               a.attempt_id, a.attempt_number, a.started_at as attempt_started_at,
               a.deadline_at, a.submitted_at as attempt_submitted_at,
               a.status as attempt_status, a.score as attempt_score,
               a.reviewed_at, a.review_comments, a.retry_authorized
        from courseplatform.lessons l
        left join courseplatform.lesson_progress p
          on p.lesson_id = l.lesson_id and p.student_id = %s
        left join lateral (
          select *
          from courseplatform.attempts a
          where a.lesson_id = l.lesson_id and a.student_id = %s
          order by coalesce(a.started_at, a.created_at) desc nulls last
          limit 1
        ) a on true
        where l.course_id = %s and l.status = 'ACTIVE'
        order by l.lesson_number
        """,
        (student["student_id"], student["student_id"], course_id),
    ).fetchall()
    return {
        "student": public_student(student),
        "course": public_course(course),
        "enrollment": public_enrollment(enrollment),
        "lessons": [
            {
                "lesson": public_lesson(row),
                "progress": public_progress({
                    "progress_id": row.get("progress_id"),
                    "lesson_id": row.get("lesson_id"),
                    "status": row.get("progress_status") or "LOCKED",
                    "content_access_status": row.get("content_access_status"),
                    "evaluation_status": row.get("evaluation_status"),
                    "score": row.get("score"),
                    "attempt_count": row.get("attempt_count"),
                    "unlocked_at": row.get("unlocked_at"),
                    "started_at": row.get("started_at"),
                    "submitted_at": row.get("submitted_at"),
                    "approved_at": row.get("approved_at"),
                }),
                "activeAttempt": public_attempt({
                    "attempt_id": row.get("attempt_id"),
                    "progress_id": row.get("progress_id"),
                    "lesson_id": row.get("lesson_id"),
                    "attempt_number": row.get("attempt_number"),
                    "started_at": row.get("attempt_started_at"),
                    "deadline_at": row.get("deadline_at"),
                    "submitted_at": row.get("attempt_submitted_at"),
                    "status": row.get("attempt_status"),
                    "score": row.get("attempt_score"),
                    "reviewed_at": row.get("reviewed_at"),
                    "review_comments": row.get("review_comments"),
                    "retry_authorized": row.get("retry_authorized"),
                }) if row.get("attempt_id") else None,
            }
            for row in lessons
        ],
    }


def student_home(payload: dict[str, Any]):
    require_session_token(payload)
    prepare_assessment_feature_schema()
    with connection() as conn:
        _, student = student_context_with_conn(conn, payload)
        course_rows = student_courses_rows(conn, student["student_id"])
        courses = student_courses_payload(course_rows)
        requested_course_id = payload.get("courseId") or get_settings().default_course_id
        available_course_ids = [item["course"]["courseId"] for item in courses if item.get("course")]
        selected_course_id = requested_course_id if requested_course_id in available_course_ids else (available_course_ids[0] if available_course_ids else requested_course_id)
        dashboard_data = dashboard_payload(conn, student, selected_course_id)
        media = read_media_config_with_conn(conn, selected_course_id)
    return success({
        "student": public_student(student),
        "courses": courses,
        "selectedCourseId": selected_course_id,
        "dashboard": dashboard_data,
        "mediaConfig": student_visible_media(media, student),
    })


def dashboard(payload: dict[str, Any]):
    _, student = student_context(payload)
    course_id = payload.get("courseId") or get_settings().default_course_id
    prepare_assessment_feature_schema()
    with connection() as conn:
        return success(dashboard_payload(conn, student, course_id))


def get_lesson(payload: dict[str, Any]):
    _, student = student_context(payload)
    require_fields(payload, ["lessonId"])
    prepare_assessment_feature_schema()
    lesson_id = payload["lessonId"]
    lesson = fetch_one("select * from courseplatform.lessons where lesson_id = %s", (lesson_id,))
    if not lesson:
        raise ApiError("LESSON_NOT_FOUND", "Módulo não encontrado.")
    progress = fetch_one(
        """
        select *
        from courseplatform.lesson_progress
        where student_id = %s and lesson_id = %s
        """,
        (student["student_id"], lesson_id),
    )
    if not progress or progress_access_status(progress) != "AVAILABLE":
        raise ApiError("LESSON_LOCKED", "Este módulo ainda não está disponível para leitura.")
    content = fetch_all(
        """
        select *
        from courseplatform.lesson_content
        where lesson_id = %s and coalesce(status, 'ACTIVE') = 'ACTIVE'
        order by section_order
        """,
        (lesson_id,),
    )
    questions = fetch_all(
        """
        select *
        from courseplatform.questions
        where lesson_id = %s and coalesce(status, 'ACTIVE') = 'ACTIVE'
        order by question_order
        """,
        (lesson_id,),
    )
    question_ids = [row["question_id"] for row in questions]
    options_by_question: dict[str, list[dict[str, Any]]] = {question_id: [] for question_id in question_ids}
    if question_ids:
        options = fetch_all(
            "select * from courseplatform.question_options where question_id = any(%s) order by option_order",
            (question_ids,),
        )
        for option in options:
            options_by_question[option["question_id"]].append(option)
    return success({
        "lesson": public_lesson(lesson),
        "progress": public_progress(progress or {
            "progress_id": "",
            "lesson_id": lesson_id,
            "status": "LOCKED",
            "attempt_count": 0,
        }),
        "content": [public_content(row) for row in content],
        "questions": [
            {
                **public_question(question),
                "options": [public_option(option) for option in options_by_question.get(question["question_id"], [])],
            }
            for question in questions
        ],
    })


def attempt_status(payload: dict[str, Any]):
    _, student = student_context(payload)
    require_fields(payload, ["attemptId"])
    prepare_assessment_feature_schema()
    attempt = fetch_one(
        """
        select *
        from courseplatform.attempts
        where attempt_id = %s and student_id = %s
        """,
        (payload["attemptId"], student["student_id"]),
    )
    attempt = expire_attempt_if_needed(attempt)
    if not attempt:
        raise ApiError("ATTEMPT_NOT_FOUND", "Tentativa não encontrada.")
    answers = fetch_all(
        "select * from courseplatform.answers where attempt_id = %s order by saved_at",
        (attempt["attempt_id"],),
    )
    files = fetch_all(
        """
        select *
        from courseplatform.files
        where attempt_id = %s and coalesce(status, 'ACTIVE') <> 'DELETED'
        order by uploaded_at
        """,
        (attempt["attempt_id"],),
    )
    latest_review = fetch_one(
        """
        select *
        from courseplatform.reviews
        where attempt_id = %s
        order by reviewed_at desc nulls last
        limit 1
        """,
        (attempt["attempt_id"],),
    )
    return success({
        "attempt": public_attempt(attempt),
        "answers": [public_answer(row) for row in answers],
        "files": [public_file(row) for row in files],
        "latestReview": public_review(latest_review),
    })


def student_push_configuration(payload: dict[str, Any]):
    prepare_notification_feature_schema()
    _, student = student_context(payload)
    configuration = web_push_configuration()
    subscription = fetch_one(
        """
        select count(*) as count, max(updated_at) as updated_at
        from courseplatform.push_subscriptions
        where student_id = %s and enabled
        """,
        (student["student_id"],),
    ) or {}
    return success({
        "pushConfiguration": configuration,
        "subscriptionCount": int(subscription.get("count") or 0),
        "updatedAt": iso(subscription.get("updated_at")),
    })


def student_subscribe_push(payload: dict[str, Any]):
    prepare_notification_feature_schema()
    _, student = student_context(payload)
    configuration = web_push_runtime_configuration()
    if not configuration.get("configured"):
        raise ApiError(
            "WEB_PUSH_NOT_CONFIGURED",
            "As notificações Push ainda não estão configuradas no servidor.",
        )
    subscription = payload.get("subscription") if isinstance(payload.get("subscription"), dict) else payload
    endpoint = str_value(subscription.get("endpoint"))
    keys = subscription.get("keys") if isinstance(subscription.get("keys"), dict) else {}
    p256dh = str_value(keys.get("p256dh") or subscription.get("p256dh"))
    auth_key = str_value(keys.get("auth") or subscription.get("auth"))
    if not valid_push_endpoint(endpoint):
        raise ApiError("INVALID_PUSH_ENDPOINT", "A subscrição Push possui um endereço inválido.")
    if not valid_push_key(p256dh, 60, 200) or not valid_push_key(auth_key, 10, 100):
        raise ApiError("INVALID_PUSH_KEYS", "As chaves da subscrição Push são inválidas.")
    encryption_key = str_value(configuration.get("encryptionKey"))
    if len(encryption_key.encode("utf-8")) < 32:
        raise ApiError(
            "WEAK_NOTIFICATION_ENCRYPTION_KEY",
            "NOTIFICATION_CONFIG_ENCRYPTION_KEY deve possuir pelo menos 32 bytes.",
        )
    endpoint_hash = hash_secret(endpoint)
    device_label = str_value(payload.get("deviceLabel"))[:120]
    user_agent = str_value(payload.get("userAgent"))[:500]
    with connection() as conn:
        row = conn.execute(
            """
            insert into courseplatform.push_subscriptions
              (subscription_id, student_id, endpoint_hash, endpoint_encrypted,
               p256dh_encrypted, auth_encrypted, user_agent, device_label,
               enabled, failure_count, created_at, updated_at)
            values (
              %s, %s, %s,
              pgp_sym_encrypt(%s, %s, 'cipher-algo=aes256'),
              pgp_sym_encrypt(%s, %s, 'cipher-algo=aes256'),
              pgp_sym_encrypt(%s, %s, 'cipher-algo=aes256'),
              %s, %s, true, 0, now(), now()
            )
            on conflict (endpoint_hash) do update set
              student_id = excluded.student_id,
              endpoint_encrypted = excluded.endpoint_encrypted,
              p256dh_encrypted = excluded.p256dh_encrypted,
              auth_encrypted = excluded.auth_encrypted,
              user_agent = excluded.user_agent,
              device_label = excluded.device_label,
              enabled = true,
              failure_count = 0,
              updated_at = now()
            returning subscription_id, device_label, enabled, created_at, updated_at
            """,
            (
                generate_id("PSH"), student["student_id"], endpoint_hash,
                endpoint, encryption_key, p256dh, encryption_key, auth_key, encryption_key,
                user_agent or None, device_label or None,
            ),
        ).fetchone()
        audit(
            conn, "STUDENT", student["student_id"], "PUSH_SUBSCRIBED",
            "PUSH_SUBSCRIPTION", row["subscription_id"],
            {"deviceLabel": device_label, "endpointHash": endpoint_hash[:16]},
        )
        conn.commit()
    return success({
        "subscribed": True,
        "subscription": {
            "subscriptionId": row["subscription_id"],
            "deviceLabel": row.get("device_label") or "",
            "enabled": as_bool(row.get("enabled")),
            "updatedAt": iso(row.get("updated_at")),
        },
    })


def student_unsubscribe_push(payload: dict[str, Any]):
    prepare_notification_feature_schema()
    _, student = student_context(payload)
    endpoint = str_value(payload.get("endpoint"))
    all_devices = as_bool(payload.get("allDevices"))
    if not endpoint and not all_devices:
        raise ApiError("PUSH_SUBSCRIPTION_REQUIRED", "Informe a subscrição Push deste dispositivo.")
    with connection() as conn:
        if all_devices:
            result = conn.execute(
                """
                update courseplatform.push_subscriptions
                set enabled = false, updated_at = now()
                where student_id = %s and enabled
                """,
                (student["student_id"],),
            )
        else:
            result = conn.execute(
                """
                update courseplatform.push_subscriptions
                set enabled = false, updated_at = now()
                where student_id = %s and endpoint_hash = %s and enabled
                """,
                (student["student_id"], hash_secret(endpoint)),
            )
        audit(
            conn, "STUDENT", student["student_id"], "PUSH_UNSUBSCRIBED",
            "PUSH_SUBSCRIPTION", "ALL" if all_devices else hash_secret(endpoint)[:16],
            {"allDevices": all_devices, "updatedCount": result.rowcount},
        )
        conn.commit()
    return success({"unsubscribed": True, "updatedCount": result.rowcount})


def student_start_telegram_link(payload: dict[str, Any]):
    prepare_notification_feature_schema()
    _, student = student_context(payload)
    configuration = telegram_runtime_configuration()
    bot_username = str_value(configuration.get("botUsername")).lstrip("@")
    if not configuration.get("configured") or not bot_username:
        raise ApiError(
            "TELEGRAM_LINK_UNAVAILABLE",
            "A ligação ao Telegram ainda não está disponível. Contacte a administração.",
        )
    token = secrets.token_urlsafe(24)
    with connection() as conn:
        conn.execute(
            """
            update courseplatform.telegram_link_tokens
            set consumed_at = coalesce(consumed_at, now())
            where student_id = %s and consumed_at is null
            """,
            (student["student_id"],),
        )
        conn.execute(
            """
            insert into courseplatform.telegram_link_tokens
              (token_hash, student_id, expires_at, created_at)
            values (%s, %s, now() + interval '15 minutes', now())
            """,
            (hash_secret(token), student["student_id"]),
        )
        conn.commit()
    return success({
        "linkUrl": f"https://t.me/{bot_username}?start={token}",
        "linkToken": token,
        "botUsername": bot_username,
        "expiresInSeconds": 900,
    })


def student_confirm_telegram_link(payload: dict[str, Any]):
    prepare_notification_feature_schema()
    _, student = student_context(payload)
    link_token = str_value(payload.get("linkToken"))
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,64}", link_token):
        raise ApiError("INVALID_TELEGRAM_LINK_TOKEN", "A ligação ao Telegram é inválida ou expirou.")
    pending = fetch_one(
        """
        select token_hash from courseplatform.telegram_link_tokens
        where token_hash = %s and student_id = %s and consumed_at is null and expires_at > now()
        """,
        (hash_secret(link_token), student["student_id"]),
    )
    if not pending:
        raise ApiError("TELEGRAM_LINK_EXPIRED", "A ligação ao Telegram é inválida ou expirou. Gere uma nova ligação.")
    try:
        process_telegram_link_updates()
    except RuntimeError as error:
        raise ApiError("TELEGRAM_LINK_CHECK_FAILED", str(error)) from error
    linked_student = fetch_one(
        "select * from courseplatform.students where student_id = %s",
        (student["student_id"],),
    ) or student
    consumed = fetch_one(
        "select consumed_at from courseplatform.telegram_link_tokens where token_hash = %s and student_id = %s",
        (hash_secret(link_token), student["student_id"]),
    ) or {}
    if not consumed.get("consumed_at") or not normalize_telegram_recipient(linked_student.get("telegram_chat_id")):
        return success({
            "linked": False,
            "student": public_student(linked_student),
            "message": "Abra o bot, toque em Iniciar e volte a confirmar.",
        })
    return success({"linked": True, "student": public_student(linked_student)})


def student_unlink_telegram(payload: dict[str, Any]):
    prepare_notification_feature_schema()
    _, student = student_context(payload)
    with connection() as conn:
        row = conn.execute(
            """
            update courseplatform.students
            set telegram_chat_id = null, telegram_opt_in = false,
                telegram_opt_in_at = null, updated_at = now()
            where student_id = %s
            returning *
            """,
            (student["student_id"],),
        ).fetchone()
        conn.execute(
            """
            update courseplatform.telegram_link_tokens
            set consumed_at = coalesce(consumed_at, now())
            where student_id = %s and consumed_at is null
            """,
            (student["student_id"],),
        )
        audit(
            conn,
            "STUDENT",
            student["student_id"],
            "TELEGRAM_UNLINKED",
            "STUDENT",
            student["student_id"],
            {"channel": "TELEGRAM"},
        )
        conn.commit()
    return success({"unlinked": True, "student": public_student(row)})


def update_my_profile(payload: dict[str, Any]):
    prepare_notification_feature_schema()
    _, student = student_context(payload)
    photo_url = str_value(payload.get("profilePhotoUrl") or student.get("profile_photo_url"))
    if str_value(payload.get("profilePhotoBase64")):
        mime_type = str_value(payload.get("profilePhotoMimeType") or "image/jpeg") or "image/jpeg"
        base64_data = str_value(payload.get("profilePhotoBase64"))
        photo_url = f"data:{mime_type};base64,{base64_data}"
    if as_bool(payload.get("removeProfilePhoto")):
        photo_url = ""

    whatsapp_opt_in = (
        as_bool(payload.get("whatsappOptIn"))
        if "whatsappOptIn" in payload else as_bool(student.get("whatsapp_opt_in"))
    )
    email_opt_in = (
        as_bool(payload.get("emailOptIn"))
        if "emailOptIn" in payload else as_bool(student.get("email_opt_in"))
    )
    telegram_opt_in = (
        as_bool(payload.get("telegramOptIn"))
        if "telegramOptIn" in payload else as_bool(student.get("telegram_opt_in"))
    )
    phone = str_value(payload.get("phone"))
    if whatsapp_opt_in and not normalize_whatsapp_recipient(phone):
        raise ApiError(
            "INVALID_WHATSAPP_PHONE",
            "Para ativar o WhatsApp, informe um telefone com indicativo internacional, por exemplo +258.",
        )
    if email_opt_in and not normalize_email_recipient(student.get("email")):
        raise ApiError("INVALID_NOTIFICATION_EMAIL", "A conta não possui um endereço de email válido.")
    if telegram_opt_in and not normalize_telegram_recipient(student.get("telegram_chat_id")):
        raise ApiError(
            "TELEGRAM_LINK_REQUIRED",
            "Ligue primeiro a sua conta ao bot oficial do Telegram.",
        )
    preferences = notification_preferences(student)
    supplied_preferences = payload.get("notificationPreferences")
    if isinstance(supplied_preferences, dict):
        for key in DEFAULT_NOTIFICATION_PREFERENCES:
            if key in supplied_preferences:
                preferences[key] = as_bool(supplied_preferences[key])

    patch = {
        "full_name": str_value(payload.get("fullName") or student.get("full_name")),
        "country": str_value(payload.get("country")),
        "organization": str_value(payload.get("organization")),
        "phone": phone,
        "job_title": str_value(payload.get("jobTitle")),
        "interests": str_value(payload.get("interests")),
        "profile_photo_url": photo_url,
    }
    with connection() as conn:
        row = conn.execute(
            """
            update courseplatform.students
            set full_name = %s, country = %s, organization = %s, phone = %s,
                job_title = %s, interests = %s, profile_photo_url = %s,
                whatsapp_opt_in = %s,
                whatsapp_opt_in_at = case
                  when %s and not coalesce(whatsapp_opt_in, false) then now()
                  when not %s then null
                  else whatsapp_opt_in_at
                end,
                email_opt_in = %s,
                email_opt_in_at = case
                  when %s and not coalesce(email_opt_in, false) then now()
                  when not %s then null
                  else email_opt_in_at
                end,
                telegram_opt_in = %s,
                telegram_opt_in_at = case
                  when %s and not coalesce(telegram_opt_in, false) then now()
                  when not %s then null
                  else telegram_opt_in_at
                end,
                notification_preferences_json = %s::jsonb,
                updated_at = now()
            where student_id = %s
            returning *
            """,
            (
                patch["full_name"],
                patch["country"],
                patch["organization"],
                patch["phone"],
                patch["job_title"],
                patch["interests"],
                patch["profile_photo_url"],
                whatsapp_opt_in,
                whatsapp_opt_in,
                whatsapp_opt_in,
                email_opt_in,
                email_opt_in,
                email_opt_in,
                telegram_opt_in,
                telegram_opt_in,
                telegram_opt_in,
                json.dumps(preferences),
                student["student_id"],
            ),
        ).fetchone()
        audit(
            conn,
            "STUDENT",
            student["student_id"],
            "PROFILE_UPDATED",
            "STUDENT",
            student["student_id"],
            {
                "notificationConsent": {
                    "whatsapp": whatsapp_opt_in,
                    "email": email_opt_in,
                    "telegram": telegram_opt_in,
                }
            },
        )
        conn.commit()
    return success({
        "student": public_student(row),
        "notificationChannelInfo": student_notification_channel_info(),
    })


def my_notifications(payload: dict[str, Any]):
    prepare_notification_feature_schema()
    _, student = student_context(payload)
    limit, offset, page = pagination(payload, default_limit=40, max_limit=100)
    unread_only = as_bool(payload.get("unreadOnly"))
    where_unread = "and n.read_at is null" if unread_only else ""
    rows = fetch_all(
        f"""
        select n.*,
               w.status as whatsapp_status, w.recipient as whatsapp_recipient,
               w.provider_message_id as whatsapp_provider_message_id,
               w.attempt_count as whatsapp_attempt_count, w.last_error as whatsapp_last_error,
               w.sent_at as whatsapp_sent_at,
               e.status as email_status, e.recipient as email_recipient,
               e.provider_message_id as email_provider_message_id,
               e.attempt_count as email_attempt_count, e.last_error as email_last_error,
               e.sent_at as email_sent_at,
               t.status as telegram_status, t.recipient as telegram_recipient,
               t.provider_message_id as telegram_provider_message_id,
               t.attempt_count as telegram_attempt_count, t.last_error as telegram_last_error,
               t.sent_at as telegram_sent_at,
               p.status as push_status,
               p.provider_message_id as push_provider_message_id,
               p.attempt_count as push_attempt_count, p.last_error as push_last_error,
               p.sent_at as push_sent_at
        from courseplatform.notifications n
        left join courseplatform.notification_deliveries w
          on w.notification_id = n.notification_id and w.channel = 'WHATSAPP'
        left join courseplatform.notification_deliveries e
          on e.notification_id = n.notification_id and e.channel = 'EMAIL'
        left join courseplatform.notification_deliveries t
          on t.notification_id = n.notification_id and t.channel = 'TELEGRAM'
        left join courseplatform.notification_deliveries p
          on p.notification_id = n.notification_id and p.channel = 'PUSH'
        where n.student_id = %s {where_unread}
        order by n.created_at desc
        limit %s offset %s
        """,
        (student["student_id"], limit, offset),
    )
    unread = fetch_one(
        "select count(*) as count from courseplatform.notifications where student_id = %s and read_at is null",
        (student["student_id"],),
    )
    total = fetch_one(
        "select count(*) as count from courseplatform.notifications where student_id = %s",
        (student["student_id"],),
    )
    return success({
        "notifications": [public_notification(row) for row in rows],
        "unreadCount": int((unread or {}).get("count") or 0),
        "total": int((total or {}).get("count") or 0),
        "page": page,
        "limit": limit,
    })


def mark_notification_read(payload: dict[str, Any]):
    prepare_notification_feature_schema()
    _, student = student_context(payload)
    notification_id = str_value(payload.get("notificationId"))
    mark_all = as_bool(payload.get("markAll"))
    if not notification_id and not mark_all:
        raise ApiError("NOTIFICATION_REQUIRED", "Selecione uma notificação.")
    with connection() as conn:
        if mark_all:
            result = conn.execute(
                "update courseplatform.notifications set read_at = coalesce(read_at, now()) where student_id = %s",
                (student["student_id"],),
            )
        else:
            result = conn.execute(
                """
                update courseplatform.notifications
                set read_at = coalesce(read_at, now())
                where notification_id = %s and student_id = %s
                """,
                (notification_id, student["student_id"]),
            )
        updated_count = result.rowcount
        conn.commit()
    return success({"updatedCount": updated_count})


def change_my_access_code(payload: dict[str, Any]):
    _, student = student_context(payload)
    require_fields(payload, ["currentAccessCode", "newAccessCode"])
    if not verify_password(payload["currentAccessCode"], student.get("password_hash")):
        raise ApiError("INVALID_CURRENT_ACCESS_CODE", "A palavra-passe atual não está correta.")
    new_code = str_value(payload.get("newAccessCode"))
    if not valid_password(new_code):
        raise ApiError("WEAK_ACCESS_CODE", "A nova palavra-passe deve ter pelo menos 8 caracteres.")
    if verify_password(new_code, student.get("password_hash")):
        raise ApiError("ACCESS_CODE_UNCHANGED", "A nova palavra-passe deve ser diferente da atual.")
    with connection() as conn:
        conn.execute(
            """
            update courseplatform.students
            set password_hash = crypt(%s, gen_salt('bf', 12)),
                password_changed_at = now(), password_reset_required = false,
                access_code = null, updated_at = now()
            where student_id = %s
            """,
            (new_code, student["student_id"]),
        )
        conn.execute(
            "update courseplatform.sessions set active = false, revoked_at = now() where subject_id = %s",
            (student["student_id"],),
        )
        audit(conn, "STUDENT", student["student_id"], "ACCESS_CODE_CHANGED", "STUDENT", student["student_id"])
        conn.commit()
    return success({"requiresLogin": True})


def change_my_email(payload: dict[str, Any]):
    prepare_notification_feature_schema()
    require_fields(payload, ["currentAccessCode", "newEmail", "confirmEmail"])
    if not as_bool(payload.get("acknowledgeSecurityImpact")):
        raise ApiError(
            "EMAIL_CHANGE_ACKNOWLEDGEMENT_REQUIRED",
            "Confirme que compreende o encerramento das sessões e a suspensão das notificações por email.",
        )
    new_email = validated_email_change(payload)
    current_password = str_value(payload.get("currentAccessCode"))
    if len(current_password) > 1024:
        raise ApiError("INVALID_CURRENT_ACCESS_CODE", "A palavra-passe atual não está correta.")
    try:
        with connection() as conn:
            _, session_student = student_context_with_conn(conn, payload)
            student = conn.execute(
                "select * from courseplatform.students where student_id = %s for update",
                (session_student["student_id"],),
            ).fetchone()
            if not student or student.get("status") != "ACTIVE":
                raise ApiError("STUDENT_NOT_ACTIVE", "A conta do estudante não está ativa.")
            if not verify_password_with_conn(
                conn,
                current_password,
                student.get("password_hash"),
            ):
                raise ApiError("INVALID_CURRENT_ACCESS_CODE", "A palavra-passe atual não está correta.")
            row = secure_student_email_update(
                conn,
                student,
                new_email,
                actor_type="STUDENT",
                actor_id=student["student_id"],
                reason="Alteração solicitada no perfil pessoal.",
            )
            conn.commit()
    except ApiError:
        raise
    except Exception as error:
        text = str(error).lower()
        if "unique" in text or "duplicate" in text:
            raise ApiError(
                "EMAIL_ALREADY_IN_USE",
                "Este endereço de email já está associado a outro estudante.",
            ) from error
        raise database_api_error(error) from error
    return success({
        "student": public_student(row),
        "email": new_email,
        "requiresLogin": True,
    })


def start_attempt(payload: dict[str, Any]):
    _, student = student_context(payload)
    require_fields(payload, ["lessonId"])
    prepare_assessment_feature_schema()
    lesson_id = payload["lessonId"]
    progress = fetch_one(
        """
        select p.*, l.exercise_minutes, l.individual_minutes, l.submission_duration_minutes
        from courseplatform.lesson_progress p
        join courseplatform.lessons l on l.lesson_id = p.lesson_id
        where p.student_id = %s and p.lesson_id = %s
        """,
        (student["student_id"], lesson_id),
    )
    if not progress or progress_access_status(progress) != "AVAILABLE":
        raise ApiError("LESSON_LOCKED", "Este módulo ainda não está disponível.")
    if progress_evaluation_status(progress) not in {"NOT_STARTED", "IN_PROGRESS", "CORRECTION_REQUIRED", "FAILED", "TIME_EXCEEDED"}:
        raise ApiError("ATTEMPT_NOT_AVAILABLE", "Não e possível iniciar uma tentativa neste estado.")

    existing = fetch_one(
        """
        select *
        from courseplatform.attempts
        where student_id = %s and lesson_id = %s and status = 'IN_PROGRESS'
        order by started_at desc nulls last
        limit 1
        """,
        (student["student_id"], lesson_id),
    )
    if existing:
        existing = expire_attempt_if_needed(existing)
        if existing and existing.get("status") == "IN_PROGRESS":
            return success({"attempt": public_attempt(existing)})

    now = utc_now()
    minutes = int_value(progress.get("submission_duration_minutes"))
    if minutes <= 0:
        minutes = int_value(progress.get("exercise_minutes")) + int_value(progress.get("individual_minutes"))
    if minutes <= 0:
        minutes = 180
    attempt_number = int_value(progress.get("attempt_count")) + 1
    with connection() as conn:
        attempt = conn.execute(
            """
            insert into courseplatform.attempts
              (attempt_id, progress_id, student_id, lesson_id, attempt_number, started_at,
               deadline_at, submitted_at, status, score, retry_authorized, created_at, updated_at)
            values (%s, %s, %s, %s, %s, %s, %s, null, 'IN_PROGRESS', null, false, %s, %s)
            returning *
            """,
            (
                generate_id("ATT"),
                progress["progress_id"],
                student["student_id"],
                lesson_id,
                attempt_number,
                now,
                now + timedelta(minutes=minutes),
                now,
                now,
            ),
        ).fetchone()
        conn.execute(
            """
            update courseplatform.lesson_progress
            set status = 'IN_PROGRESS', evaluation_status = 'IN_PROGRESS',
                content_access_status = coalesce(content_access_status, 'AVAILABLE'),
                started_at = coalesce(started_at, %s),
                attempt_count = %s, updated_at = %s
            where progress_id = %s
            """,
            (now, attempt_number, now, progress["progress_id"]),
        )
        audit(conn, "STUDENT", student["student_id"], "ATTEMPT_STARTED", "ATTEMPT", attempt["attempt_id"])
        conn.commit()
    return success({"attempt": public_attempt(attempt)})


def save_answer(payload: dict[str, Any]):
    _, student = student_context(payload)
    require_fields(payload, ["attemptId", "questionId"])
    prepare_assessment_feature_schema()
    attempt = fetch_one(
        "select * from courseplatform.attempts where attempt_id = %s and student_id = %s",
        (payload["attemptId"], student["student_id"]),
    )
    attempt = expire_attempt_if_needed(attempt)
    if not attempt or attempt.get("status") != "IN_PROGRESS":
        raise ApiError("ATTEMPT_NOT_EDITABLE", "Esta tentativa já não pode ser editada.")
    with connection() as conn:
        answer = conn.execute(
            """
            insert into courseplatform.answers
              (answer_id, attempt_id, question_id, answer_text, selected_option_id, saved_at)
            values (%s, %s, %s, %s, %s, now())
            on conflict (attempt_id, question_id) do update
            set answer_text = excluded.answer_text,
                selected_option_id = excluded.selected_option_id,
                saved_at = excluded.saved_at
            returning *
            """,
            (
                generate_id("ANS"),
                attempt["attempt_id"],
                payload["questionId"],
                str_value(payload.get("answerText")),
                str_value(payload.get("selectedOptionId")),
            ),
        ).fetchone()
        conn.commit()
    return success({"answer": public_answer(answer)})


def upload_file(payload: dict[str, Any]):
    _, student = student_context(payload)
    require_fields(payload, ["attemptId", "fileName"])
    prepare_assessment_feature_schema()
    attempt = fetch_one(
        "select * from courseplatform.attempts where attempt_id = %s and student_id = %s",
        (payload["attemptId"], student["student_id"]),
    )
    attempt = expire_attempt_if_needed(attempt)
    if not attempt or attempt.get("status") != "IN_PROGRESS":
        raise ApiError("ATTEMPT_NOT_EDITABLE", "Esta tentativa já não pode receber ficheiros.")
    mime_type = str_value(payload.get("mimeType") or "application/octet-stream")
    base64_data = str_value(payload.get("base64Data"))
    drive_url = f"data:{mime_type};base64,{base64_data}" if base64_data else str_value(payload.get("driveUrl"))
    with connection() as conn:
        row = conn.execute(
            """
            insert into courseplatform.files
              (file_id, attempt_id, student_id, lesson_id, file_name, mime_type,
               size_bytes, drive_file_id, drive_url, uploaded_at, status)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, now(), 'ACTIVE')
            returning *
            """,
            (
                generate_id("FIL"),
                attempt["attempt_id"],
                student["student_id"],
                attempt["lesson_id"],
                str_value(payload.get("fileName")),
                mime_type,
                len(base64_data),
                "",
                drive_url,
            ),
        ).fetchone()
        conn.commit()
    return success({"file": public_file(row)})


def delete_uploaded_file(payload: dict[str, Any]):
    _, student = student_context(payload)
    require_fields(payload, ["fileId"])
    with connection() as conn:
        row = conn.execute(
            """
            update courseplatform.files
            set status = 'DELETED'
            where file_id = %s and student_id = %s
            returning *
            """,
            (payload["fileId"], student["student_id"]),
        ).fetchone()
        conn.commit()
    if not row:
        raise ApiError("FILE_NOT_FOUND", "Ficheiro não encontrado.")
    return success({"file": public_file(row)})


def submit_attempt(payload: dict[str, Any]):
    _, student = student_context(payload)
    require_fields(payload, ["attemptId"])
    prepare_assessment_feature_schema()
    attempt = fetch_one(
        "select * from courseplatform.attempts where attempt_id = %s and student_id = %s",
        (payload["attemptId"], student["student_id"]),
    )
    attempt = expire_attempt_if_needed(attempt)
    if not attempt or attempt.get("status") != "IN_PROGRESS":
        raise ApiError("ATTEMPT_NOT_SUBMITTABLE", "Esta tentativa não pode ser submetida.")
    now = utc_now()
    status = "TIME_EXCEEDED" if attempt.get("deadline_at") and attempt["deadline_at"] < now else "UNDER_REVIEW"
    with connection() as conn:
        updated = conn.execute(
            """
            update courseplatform.attempts
            set status = %s, submitted_at = %s, updated_at = %s
            where attempt_id = %s
            returning *
            """,
            (status, now, now, attempt["attempt_id"]),
        ).fetchone()
        conn.execute(
            """
            update courseplatform.lesson_progress
            set status = %s, evaluation_status = %s, submitted_at = %s, updated_at = %s
            where progress_id = %s
            """,
            (status, status, now, now, attempt.get("progress_id")),
        )
        audit(conn, "STUDENT", student["student_id"], "ATTEMPT_SUBMITTED", "ATTEMPT", attempt["attempt_id"], {"status": status})
        conn.commit()
    return success({"attempt": public_attempt(updated)})


def my_certificate(payload: dict[str, Any]):
    _, student = student_context(payload)
    course_id = payload.get("courseId") or get_settings().default_course_id
    with connection() as conn:
        cert, _, _, _ = ensure_simple_certificate(conn, student, course_id)
        conn.commit()
    return success({"certificate": public_certificate(cert)})


def my_certifications(payload: dict[str, Any]):
    _, student = student_context(payload)
    course_id = payload.get("courseId") or get_settings().default_course_id
    with connection() as conn:
        simple_cert, enrollment, course, completed = ensure_simple_certificate(conn, student, course_id)
        settings_row = conn.execute(
            "select * from courseplatform.certificate_settings where course_id = %s",
            (course_id,),
        ).fetchone()
        certificates = conn.execute(
            """
            select cert.*, c.title as course_title, s.full_name as student_name
            from courseplatform.certificates cert
            join courseplatform.courses c on c.course_id = cert.course_id
            join courseplatform.students s on s.student_id = cert.student_id
            where cert.student_id = %s and cert.course_id = %s
              and coalesce(cert.status, 'ISSUED') <> 'DELETED'
            order by cert.issue_date desc nulls last
            """,
            (student["student_id"], course_id),
        ).fetchall()
        requests = conn.execute(
            """
            select cr.*, s.full_name, s.email, c.title
            from courseplatform.certificate_requests cr
            join courseplatform.students s on s.student_id = cr.student_id
            join courseplatform.courses c on c.course_id = cr.course_id
            where cr.student_id = %s and cr.course_id = %s
            order by coalesce(cr.updated_at, cr.created_at) desc
            """,
            (student["student_id"], course_id),
        ).fetchall()
        conn.commit()
    return success({
        "student": public_student(student),
        "course": public_course(course),
        "enrollment": public_enrollment(enrollment),
        "completed": completed,
        "simpleCertificate": public_certificate(simple_cert),
        "certificates": [public_certificate(row) for row in certificates],
        "requests": [public_certificate_request(row) for row in requests],
        "settings": certificate_settings_payload(settings_row, course),
    })


def request_professional_certificate(payload: dict[str, Any]):
    _, student = student_context(payload)
    course_id = payload.get("courseId") or get_settings().default_course_id
    survey_answers = payload.get("surveyAnswers") if isinstance(payload.get("surveyAnswers"), dict) else {}
    with connection() as conn:
        _, _, _, completed = ensure_simple_certificate(conn, student, course_id)
        if not completed:
            raise ApiError("COURSE_NOT_COMPLETED", "Conclua o curso antes de solicitar o certificado profissional.")
        course = conn.execute("select * from courseplatform.courses where course_id = %s", (course_id,)).fetchone()
        settings_row = conn.execute(
            "select * from courseplatform.certificate_settings where course_id = %s",
            (course_id,),
        ).fetchone()
        profile = certificate_settings_payload(settings_row, course).get("certificateProfile") or {}
        if profile.get("printAccess") == "blocked":
            raise ApiError("CERTIFICATE_PRINT_BLOCKED", "A emissão deste certificado profissional ainda não está disponível.")
        initial_status = "REQUESTED" if profile.get("printAccess") == "paid" else "PAYMENT_SUBMITTED"
        existing = conn.execute(
            """
            select cr.*
            from courseplatform.certificate_requests cr
            left join courseplatform.certificates cert on cert.certificate_id = cr.certificate_id
            where cr.student_id = %s and cr.course_id = %s
              and cr.request_type = 'PROFESSIONAL'
              and cr.status in ('REQUESTED', 'PAYMENT_SUBMITTED', 'APPROVED')
              and not (cr.status = 'APPROVED' and coalesce(cert.status, 'ISSUED') in ('BLOCKED', 'DELETED'))
            order by created_at desc
            limit 1
            """,
            (student["student_id"], course_id),
        ).fetchone()
        if existing:
            request = conn.execute(
                """
                update courseplatform.certificate_requests
                set survey_answers_json = %s,
                    status = case
                      when %s = 'PAYMENT_SUBMITTED' and status = 'REQUESTED' then 'PAYMENT_SUBMITTED'
                      else status
                    end,
                    updated_at = now()
                where request_id = %s
                returning *
                """,
                (json.dumps(survey_answers), initial_status, existing["request_id"]),
            ).fetchone()
        else:
            request = conn.execute(
                """
                insert into courseplatform.certificate_requests
                  (request_id, student_id, course_id, request_type, status,
                   survey_answers_json, created_at, updated_at)
                values (%s, %s, %s, 'PROFESSIONAL', %s, %s, now(), now())
                returning *
                """,
                (generate_id("CREQ"), student["student_id"], course_id, initial_status, json.dumps(survey_answers)),
            ).fetchone()
        conn.commit()
    return success({"request": public_certificate_request(request)})


def submit_professional_certificate_payment(payload: dict[str, Any]):
    _, student = student_context(payload)
    require_fields(payload, ["requestId", "receiptFileName"])
    receipt_mime = str_value(payload.get("receiptMimeType") or "application/octet-stream")
    receipt_base64 = str_value(payload.get("receiptBase64"))
    receipt_url = f"data:{receipt_mime};base64,{receipt_base64}" if receipt_base64 else str_value(payload.get("receiptUrl"))
    if not receipt_url:
        raise ApiError("RECEIPT_REQUIRED", "Carregue o comprovativo de pagamento.")
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        request = conn.execute(
            """
            update courseplatform.certificate_requests
            set status = 'PAYMENT_SUBMITTED',
                payment_receipt_name = %s,
                payment_receipt_url = %s,
                payment_receipt_mime_type = %s,
                submitted_at = now(),
                updated_at = now()
            where request_id = %s and student_id = %s
              and status in ('REQUESTED', 'PAYMENT_SUBMITTED')
              and certificate_id is null
            returning *
            """,
            (
                str_value(payload.get("receiptFileName")),
                receipt_url,
                receipt_mime,
                payload["requestId"],
                student["student_id"],
            ),
        ).fetchone()
        conn.commit()
    if not request:
        raise ApiError("CERTIFICATE_REQUEST_NOT_FOUND", "Pedido de certificado não encontrado.")
    return success({"request": public_certificate_request(request)})


def record_certificate_download(payload: dict[str, Any]):
    _, student = student_context(payload)
    require_fields(payload, ["certificateId"])
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        cert = conn.execute(
            "select * from courseplatform.certificates where certificate_id = %s and student_id = %s",
            (payload["certificateId"], student["student_id"]),
        ).fetchone()
        if not cert:
            raise ApiError("CERTIFICATE_NOT_FOUND", "Certificado não encontrado.")
        if cert.get("status") != "ISSUED":
            raise ApiError("CERTIFICATE_ACCESS_BLOCKED", "O acesso a este certificado não está disponível.")
        max_downloads = cert.get("max_downloads")
        download_count = int(cert.get("download_count") or 0)
        if max_downloads is not None and download_count >= int(max_downloads):
            raise ApiError("DOWNLOAD_LIMIT_REACHED", "O limite de downloads deste certificado foi atingido.")
        cert = conn.execute(
            """
            update courseplatform.certificates
            set download_count = download_count + 1
            where certificate_id = %s
            returning *
            """,
            (payload["certificateId"],),
        ).fetchone()
        snapshot = cert.get("template_snapshot_json") if cert else None
        if cert and not snapshot:
            snapshot = certificate_template_snapshot(conn, cert.get("course_id"), cert.get("certificate_type"))
        conn.commit()
    return success({"certificate": public_certificate(cert)})


def certificate_pdf_payload(payload: dict[str, Any]):
    _, student = student_context(payload)
    require_fields(payload, ["certificateId"])
    verification_base_url = str_value(payload.get("verificationBaseUrl")) or "verify.html"
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        cert = conn.execute(
            """
            select cert.*, c.title as course_title, s.full_name as student_name,
                   e.final_score as enrollment_score
            from courseplatform.certificates cert
            join courseplatform.courses c on c.course_id = cert.course_id
            join courseplatform.students s on s.student_id = cert.student_id
            left join courseplatform.enrollments e
              on e.student_id = cert.student_id and e.course_id = cert.course_id
            where cert.certificate_id = %s and cert.student_id = %s
            """,
            (payload["certificateId"], student["student_id"]),
        ).fetchone()
        if not cert:
            raise ApiError("CERTIFICATE_NOT_FOUND", "Certificado não encontrado.")
        if cert.get("status") != "ISSUED":
            raise ApiError("CERTIFICATE_ACCESS_BLOCKED", "O acesso a este certificado não está disponível.")
        max_downloads = cert.get("max_downloads")
        download_count = int(cert.get("download_count") or 0)
        if max_downloads is not None and download_count >= int(max_downloads):
            raise ApiError("DOWNLOAD_LIMIT_REACHED", "O limite de downloads deste certificado foi atingido.")
        snapshot = cert.get("template_snapshot_json") or certificate_template_snapshot(conn, cert.get("course_id"), cert.get("certificate_type"))
        media = read_media_config_with_conn(conn, cert.get("course_id")) if cert else {"logoUrl": ""}
        conn.commit()
    cert = {
        **cert,
        "course_title": cert.get("course_title"),
        "student_name": cert.get("student_name"),
        "final_score": cert.get("final_score") or cert.get("enrollment_score"),
    }
    certificate = public_certificate(cert)
    model = "professional" if certificate.get("certificateType") == "PROFESSIONAL" else "participation"
    verification_code = certificate.get("verificationCode") or certificate.get("certificateNumber") or ""
    separator = "&" if "?" in verification_base_url else "?"
    verification_url = f"{verification_base_url}{separator}code={verification_code}" if verification_code else verification_base_url
    profile = normalize_certificate_profile((snapshot or {}).get("profile"), {"title": certificate.get("courseTitle")})
    profile["assets"] = {**(profile.get("assets") or {})}
    if not profile["assets"].get("logoUrl") and media.get("logoUrl"):
        profile["assets"]["logoUrl"] = media["logoUrl"]
    workload = f"{int((snapshot or {}).get('courseHours') or 30)} horas" if model == "professional" else "10 horas"
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
            "workload": workload,
            "certificate_profile": profile,
        },
    }


def admin_certificate_pdf_payload(payload: dict[str, Any]):
    admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    require_fields(payload, ["certificateId"])
    verification_base_url = str_value(payload.get("verificationBaseUrl")) or "verify.html"
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        cert = conn.execute(
            """
            select cert.*, c.title as course_title, s.full_name as student_name,
                   e.final_score as enrollment_score
            from courseplatform.certificates cert
            join courseplatform.courses c on c.course_id = cert.course_id
            join courseplatform.students s on s.student_id = cert.student_id
            left join courseplatform.enrollments e
              on e.student_id = cert.student_id and e.course_id = cert.course_id
            where cert.certificate_id = %s
            """,
            (payload["certificateId"],),
        ).fetchone()
        snapshot = cert.get("template_snapshot_json") if cert else None
        if cert and not snapshot:
            snapshot = certificate_template_snapshot(conn, cert.get("course_id"), cert.get("certificate_type"))
        media = read_media_config_with_conn(conn, cert.get("course_id")) if cert else {"logoUrl": ""}
        conn.commit()
    if not cert:
        raise ApiError("CERTIFICATE_NOT_FOUND", "Certificado não encontrado.")
    if cert.get("status") == "DELETED":
        raise ApiError("CERTIFICATE_NOT_FOUND", "Certificado não encontrado.")
    cert = {
        **cert,
        "course_title": cert.get("course_title"),
        "student_name": cert.get("student_name"),
        "final_score": cert.get("final_score") or cert.get("enrollment_score"),
    }
    certificate = public_certificate(cert)
    model = "professional" if certificate.get("certificateType") == "PROFESSIONAL" else "participation"
    verification_code = certificate.get("verificationCode") or certificate.get("certificateNumber") or ""
    separator = "&" if "?" in verification_base_url else "?"
    verification_url = f"{verification_base_url}{separator}code={verification_code}" if verification_code else verification_base_url
    profile = normalize_certificate_profile((snapshot or {}).get("profile"), {"title": certificate.get("courseTitle")})
    profile["assets"] = {**(profile.get("assets") or {})}
    if not profile["assets"].get("logoUrl") and media.get("logoUrl"):
        profile["assets"]["logoUrl"] = media["logoUrl"]
    workload = f"{int((snapshot or {}).get('courseHours') or 30)} horas" if model == "professional" else "10 horas"
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
            "workload": workload,
            "certificate_profile": profile,
        },
    }


def admin_list_courses(payload: dict[str, Any]):
    admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    limit, offset, page = pagination(payload)
    query = f"%{(payload.get('query') or '').lower()}%"
    status = (payload.get("status") or "ALL").upper()
    conditions = ["(%s = 'ALL' or c.status = %s)"]
    params: list[Any] = [status, status]
    if payload.get("query"):
        conditions.append("(lower(c.course_id || ' ' || c.course_code || ' ' || c.title || ' ' || coalesce(c.description,'')) like %s)")
        params.append(query)
    where = " and ".join(conditions)
    rows = fetch_all(
        f"""
        select c.*,
          count(distinct l.lesson_id) as lesson_count,
          count(distinct g.group_id) as group_count,
          count(distinct e.enrollment_id) as enrollment_count,
          count(*) over() as total_count
        from courseplatform.courses c
        left join courseplatform.lessons l on l.course_id = c.course_id
        left join courseplatform.groups g on g.course_id = c.course_id
        left join courseplatform.enrollments e on e.course_id = c.course_id
        where {where}
        group by c.course_id
        order by c.title
        limit %s offset %s
        """,
        (*params, limit, offset),
    )
    total = int(rows[0]["total_count"]) if rows else 0
    return success({"courses": [{"course": public_course(row), "lessonCount": int(row["lesson_count"]), "groupCount": int(row["group_count"]), "enrollmentCount": int(row["enrollment_count"])} for row in rows], "pagination": {"total": total, "page": page, "limit": limit, "offset": offset, "returned": len(rows), "hasMore": offset + len(rows) < total}})


def admin_course_structure(payload: dict[str, Any]):
    admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    course_id = payload.get("courseId") or get_settings().default_course_id
    course = fetch_one("select * from courseplatform.courses where course_id = %s", (course_id,))
    if not course:
        raise ApiError("COURSE_NOT_FOUND", "Curso não encontrado.")
    lessons = fetch_all("select * from courseplatform.lessons where course_id = %s order by lesson_number", (course_id,))
    lesson_ids = [row["lesson_id"] for row in lessons]
    content_by_lesson: dict[str, list[dict[str, Any]]] = {lesson_id: [] for lesson_id in lesson_ids}
    questions_by_lesson: dict[str, list[dict[str, Any]]] = {lesson_id: [] for lesson_id in lesson_ids}
    if lesson_ids:
        content = fetch_all("select * from courseplatform.lesson_content where lesson_id = any(%s) order by section_order", (lesson_ids,))
        questions = fetch_all("select * from courseplatform.questions where lesson_id = any(%s) order by question_order", (lesson_ids,))
        question_ids = [row["question_id"] for row in questions]
        options_by_question: dict[str, list[dict[str, Any]]] = {question_id: [] for question_id in question_ids}
        if question_ids:
            options = fetch_all("select * from courseplatform.question_options where question_id = any(%s) order by option_order", (question_ids,))
            for option in options:
                options_by_question[option["question_id"]].append(option)
        for item in content:
            content_by_lesson[item["lesson_id"]].append(item)
        for question in questions:
            questions_by_lesson[question["lesson_id"]].append({"question": question, "options": options_by_question.get(question["question_id"], [])})
    return success({
        "course": public_course(course),
        "lessons": [
            {
                "lesson": public_lesson(lesson),
                "content": [public_content(item) for item in content_by_lesson.get(lesson["lesson_id"], [])],
                "questions": [
                    {
                        "question": public_question(item["question"]),
                        "options": [public_option(option) for option in item["options"]],
                    }
                    for item in questions_by_lesson.get(lesson["lesson_id"], [])
                ],
            }
            for lesson in lessons
        ],
    })


def admin_list_groups(payload: dict[str, Any]):
    admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    rows = fetch_all(
        """
        select g.*, count(gm.group_member_id) filter (where gm.status = 'ACTIVE') as member_count
        from courseplatform.groups g
        left join courseplatform.group_members gm on gm.group_id = g.group_id
        where (%s = '' or g.course_id = %s)
        group by g.group_id
        order by g.name
        limit 500
        """,
        (payload.get("courseId") or "", payload.get("courseId") or ""),
    )
    return success({"groups": [{"group": {"groupId": row["group_id"], "groupCode": row.get("group_code"), "name": row.get("name"), "courseId": row.get("course_id"), "startDate": iso(row.get("start_date")), "endDate": iso(row.get("end_date")), "status": row.get("status"), "createdAt": iso(row.get("created_at")), "updatedAt": iso(row.get("updated_at"))}, "memberCount": int(row["member_count"] or 0)} for row in rows]})


def admin_list_students(payload: dict[str, Any]):
    admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    prepare_notification_feature_schema()
    status = (payload.get("status") or "ALL").upper()
    query = str_value(payload.get("query"))
    limit = max(1, min(int_value(payload.get("limit"), 500), 2000))
    rows = fetch_all(
        """
        select s.*,
          (select count(*) from courseplatform.push_subscriptions ps where ps.student_id = s.student_id and ps.enabled) as push_subscription_count,
          coalesce(jsonb_agg(distinct to_jsonb(e)) filter (where e.enrollment_id is not null), '[]') as enrollments,
          coalesce(jsonb_agg(distinct to_jsonb(gm)) filter (where gm.group_member_id is not null), '[]') as memberships
        from courseplatform.students s
        left join courseplatform.enrollments e on e.student_id = s.student_id
        left join courseplatform.group_members gm on gm.student_id = s.student_id and gm.status = 'ACTIVE'
        where (%s = 'ALL' or s.status = %s)
          and (%s = '' or lower(s.full_name || ' ' || s.email || ' ' || coalesce(s.organization,'')) like %s)
        group by s.student_id
        order by s.full_name
        limit %s
        """,
        (status, status, query, f"%{query.lower()}%", limit),
    )
    total = fetch_one(
        """
        select count(*) as total
        from courseplatform.students s
        where (%s = 'ALL' or s.status = %s)
          and (%s = '' or lower(s.full_name || ' ' || s.email || ' ' || coalesce(s.organization,'')) like %s)
        """,
        (status, status, query, f"%{query.lower()}%"),
    ) or {}
    return success({
        "students": [
            {
                "student": public_student(row),
                "enrollments": [public_enrollment(item) for item in row.get("enrollments", [])],
                "memberships": [public_group_member(item) for item in row.get("memberships", [])],
            }
            for row in rows
        ],
        "total": int(total.get("total") or 0),
        "limit": limit,
    })


def admin_list_staff(payload: dict[str, Any]):
    _, current_admin = admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    rows = fetch_all(
        """
        select *
        from courseplatform.admins
        where (%s = 'ALL' or status = %s)
          and (%s = '' or lower(full_name || ' ' || email || ' ' || role) like %s)
        order by
          case role when 'OWNER' then 1 when 'ADMIN' then 2 else 3 end,
          full_name
        limit %s
        """,
        (
            (payload.get("status") or "ALL").upper(),
            (payload.get("status") or "ALL").upper(),
            payload.get("query") or "",
            f"%{(payload.get('query') or '').lower()}%",
            int(payload.get("limit") or 500),
        ),
    )
    return success({
        "staff": [public_admin(row) for row in rows],
        "currentAdmin": public_admin(current_admin),
    })


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
        "attempt": public_attempt(row),
        "latestReview": public_review(review),
        "fileCount": int(row.get("file_count") or 0),
    }


def admin_list_submissions(payload: dict[str, Any]):
    admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    expire_overdue_attempts()
    status = (payload.get("status") or "ALL").upper()
    query = (payload.get("query") or "").strip().lower()
    limit = min(int(payload.get("limit") or 300), 500)
    rows = fetch_all(
        """
        with latest_reviews as (
          select distinct on (attempt_id) *
          from courseplatform.reviews
          order by attempt_id, reviewed_at desc nulls last
        ),
        file_counts as (
          select attempt_id, count(*) as file_count
          from courseplatform.files
          where coalesce(status, 'ACTIVE') <> 'DELETED'
          group by attempt_id
        )
        select
          a.*,
          a.student_id as attempt_student_id,
          a.lesson_id as attempt_lesson_id,
          s.student_id, s.public_student_id, s.full_name, s.email, s.status as student_status,
          s.country, s.organization, s.phone, s.job_title, s.interests,
          s.profile_photo_url, s.created_at as student_created_at, s.last_login_at,
          l.lesson_id, l.course_id, l.lesson_number, l.title, l.slug, l.summary,
          l.theory_minutes, l.exercise_minutes, l.individual_minutes, l.passing_score,
          l.prerequisite_lesson_id, l.status as lesson_status,
          p.progress_id, p.status as progress_status, p.content_access_status,
          p.evaluation_status, p.score as progress_score, p.attempt_count as progress_attempt_count,
          lr.review_id, lr.reviewer_id, lr.decision, lr.score as review_score,
          lr.comments, lr.correction_deadline, lr.unlock_next_lesson, lr.reviewed_at as review_reviewed_at,
          coalesce(fc.file_count, 0) as file_count
        from courseplatform.attempts a
        left join courseplatform.students s on s.student_id = a.student_id
        left join courseplatform.lessons l on l.lesson_id = a.lesson_id
        left join courseplatform.lesson_progress p on p.progress_id = a.progress_id
        left join latest_reviews lr on lr.attempt_id = a.attempt_id
        left join file_counts fc on fc.attempt_id = a.attempt_id
        where
          (
            %s = 'ALL'
            or (%s = 'REVIEWED' and a.status in ('APPROVED', 'CORRECTION_REQUIRED', 'FAILED'))
            or a.status = %s
          )
          and (
            %s = ''
            or lower(coalesce(s.full_name, '') || ' ' || coalesce(s.email, '') || ' ' ||
              coalesce(l.title, '') || ' ' || coalesce(a.review_comments, '') || ' ' ||
              coalesce(l.lesson_id, '') || ' ' || coalesce(a.attempt_id, '')) like %s
          )
        order by coalesce(a.submitted_at, a.started_at, a.created_at) desc nulls last
        limit %s
        """,
        (status, status, status, query, f"%{query}%", limit),
    )
    return success({"submissions": [submission_item(row) for row in rows]})


def admin_get_submission(payload: dict[str, Any]):
    admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    require_fields(payload, ["attemptId"])
    prepare_assessment_feature_schema()
    attempt = fetch_one("select * from courseplatform.attempts where attempt_id = %s", (payload["attemptId"],))
    if not attempt:
        raise ApiError("ATTEMPT_NOT_FOUND", "Submissão não encontrada.")
    student = fetch_one("select * from courseplatform.students where student_id = %s", (attempt["student_id"],))
    lesson = fetch_one("select * from courseplatform.lessons where lesson_id = %s", (attempt["lesson_id"],))
    progress = fetch_one(
        "select * from courseplatform.lesson_progress where progress_id = %s",
        (attempt.get("progress_id"),),
    )
    questions = fetch_all(
        """
        select *
        from courseplatform.questions
        where lesson_id = %s and coalesce(status, 'ACTIVE') <> 'DELETED'
        order by question_order
        """,
        (attempt["lesson_id"],),
    )
    answers = fetch_all("select * from courseplatform.answers where attempt_id = %s", (attempt["attempt_id"],))
    answer_by_question = {row["question_id"]: row for row in answers}
    question_ids = [row["question_id"] for row in questions]
    options_by_question: dict[str, list[dict[str, Any]]] = {question_id: [] for question_id in question_ids}
    if question_ids:
        options = fetch_all(
            "select * from courseplatform.question_options where question_id = any(%s) order by option_order",
            (question_ids,),
        )
        for option in options:
            options_by_question[option["question_id"]].append(option)
    files = fetch_all(
        "select * from courseplatform.files where attempt_id = %s and coalesce(status, 'ACTIVE') <> 'DELETED' order by uploaded_at",
        (attempt["attempt_id"],),
    )
    reviews = fetch_all("select * from courseplatform.reviews where attempt_id = %s order by reviewed_at desc nulls last", (attempt["attempt_id"],))
    return success({
        "student": public_student(student or {"student_id": attempt["student_id"], "full_name": "Estudante sem cadastro", "email": "", "status": "UNKNOWN"}),
        "lesson": public_lesson(lesson or {"lesson_id": attempt["lesson_id"], "title": attempt["lesson_id"]}),
        "progress": public_progress(progress) if progress else None,
        "attempt": public_attempt(attempt),
        "answers": [
            {
                "question": {
                    **public_question(question),
                    "options": [public_option(option) for option in options_by_question.get(question["question_id"], [])],
                },
                "answer": public_answer(answer_by_question.get(question["question_id"])) or {
                    "answerId": "",
                    "attemptId": attempt["attempt_id"],
                    "questionId": question["question_id"],
                    "answerText": "",
                    "selectedOptionId": "",
                    "isCorrect": None,
                    "awardedPoints": None,
                    "savedAt": None,
                    "submittedAt": None,
                },
            }
            for question in questions
        ],
        "files": [public_file(row) for row in files],
        "reviews": [public_review(row) for row in reviews],
    })


def admin_review_submission(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    require_fields(payload, ["attemptId", "decision", "score"])
    prepare_assessment_feature_schema()
    prepare_notification_feature_schema()
    decision = str_value(payload.get("decision")).upper()
    if decision not in {"APPROVED", "APPROVED_WITH_NOTES", "CORRECTION_REQUIRED", "FAILED"}:
        raise ApiError("INVALID_DECISION", "Decisão inválida.")
    status = "APPROVED" if decision in {"APPROVED", "APPROVED_WITH_NOTES"} else decision
    score = float_value(payload.get("score"))
    now = utc_now()
    attempt = fetch_one("select * from courseplatform.attempts where attempt_id = %s", (payload["attemptId"],))
    if not attempt:
        raise ApiError("ATTEMPT_NOT_FOUND", "Tentativa não encontrada.")
    notification_ids: list[str] = []
    with connection() as conn:
        review = conn.execute(
            """
            insert into courseplatform.reviews
              (review_id, attempt_id, reviewer_id, decision, score, comments,
               correction_deadline, unlock_next_lesson, reviewed_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning *
            """,
            (
                generate_id("REV"),
                attempt["attempt_id"],
                admin["admin_id"],
                decision,
                score,
                str_value(payload.get("comments")),
                parse_datetime(payload.get("correctionDeadline")),
                status == "APPROVED",
                now,
            ),
        ).fetchone()
        updated = conn.execute(
            """
            update courseplatform.attempts
            set status = %s, score = %s, reviewer_id = %s, reviewed_at = %s,
                review_comments = %s, retry_authorized = false, updated_at = %s
            where attempt_id = %s
            returning *
            """,
            (status, score, admin["admin_id"], now, str_value(payload.get("comments")), now, attempt["attempt_id"]),
        ).fetchone()
        conn.execute(
            """
            update courseplatform.lesson_progress
            set status = %s, evaluation_status = %s,
                content_access_status = coalesce(content_access_status, 'AVAILABLE'),
                approved_at = case when %s = 'APPROVED' then %s else approved_at end,
                score = %s, updated_at = %s
            where progress_id = %s
            """,
            (status, status, status, now, score, now, attempt.get("progress_id")),
        )
        refresh_enrollment_progress(conn, attempt.get("progress_id"))
        lesson = conn.execute(
            "select title from courseplatform.lessons where lesson_id = %s",
            (attempt["lesson_id"],),
        ).fetchone() or {}
        comments = str_value(payload.get("comments"))
        message = f"{lesson.get('title') or 'Atividade'}: {notification_status_label(decision)}."
        if comments:
            message = f"{message} Comentário do avaliador: {comments}"
        notification_id = create_student_notification(
            conn,
            attempt["student_id"],
            "REVIEW_FEEDBACK" if comments else "SUBMISSION_STATUS",
            "Avaliação atualizada",
            message,
            admin_id=admin["admin_id"],
            action_url="#/grades",
            entity_type="ATTEMPT",
            entity_id=attempt["attempt_id"],
            priority="HIGH" if status == "CORRECTION_REQUIRED" else "NORMAL",
            template_key="REVIEW_UPDATED",
            template_variables={
                "activity": lesson.get("title") or "Atividade",
                "status": notification_status_label(decision),
                "feedback": comments,
                "details": message,
            },
        )
        if notification_id:
            notification_ids.append(notification_id)
        audit(conn, "ADMIN", admin["admin_id"], "SUBMISSION_REVIEWED", "ATTEMPT", attempt["attempt_id"], {"decision": decision, "score": score})
        conn.commit()
    dispatch_notification_deliveries(notification_ids)
    return success({"attempt": public_attempt(updated), "review": public_review(review)})


def admin_authorize_retry(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    require_fields(payload, ["attemptId"])
    prepare_assessment_feature_schema()
    prepare_notification_feature_schema()
    notification_ids: list[str] = []
    with connection() as conn:
        attempt = conn.execute(
            """
            update courseplatform.attempts
            set retry_authorized = true, status = 'CORRECTION_REQUIRED', updated_at = now()
            where attempt_id = %s
            returning *
            """,
            (payload["attemptId"],),
        ).fetchone()
        if not attempt:
            raise ApiError("ATTEMPT_NOT_FOUND", "Tentativa não encontrada.")
        conn.execute(
            """
            update courseplatform.lesson_progress
            set status = 'CORRECTION_REQUIRED', evaluation_status = 'CORRECTION_REQUIRED',
                content_access_status = 'AVAILABLE', updated_at = now()
            where progress_id = %s
            """,
            (attempt.get("progress_id"),),
        )
        lesson = conn.execute(
            "select title from courseplatform.lessons where lesson_id = %s",
            (attempt["lesson_id"],),
        ).fetchone() or {}
        notification_id = create_student_notification(
            conn,
            attempt["student_id"],
            "SUBMISSION_STATUS",
            "Nova tentativa autorizada",
            f"Pode realizar uma nova tentativa em {lesson.get('title') or 'atividade'}.",
            admin_id=admin["admin_id"],
            action_url=f"#/lesson/{attempt['lesson_id']}",
            entity_type="ATTEMPT",
            entity_id=attempt["attempt_id"],
            priority="HIGH",
            template_key="RETRY_AUTHORIZED",
            template_variables={"activity": lesson.get("title") or "atividade"},
        )
        if notification_id:
            notification_ids.append(notification_id)
        audit(conn, "ADMIN", admin["admin_id"], "RETRY_AUTHORIZED", "ATTEMPT", attempt["attempt_id"])
        conn.commit()
    dispatch_notification_deliveries(notification_ids)
    return success({"attempt": public_attempt(attempt)})


def admin_update_attempt(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    require_fields(payload, ["attemptId", "status"])
    prepare_assessment_feature_schema()
    prepare_notification_feature_schema()
    status = str_value(payload.get("status")).upper()
    if status not in ATTEMPT_STATUSES:
        raise ApiError("INVALID_ATTEMPT_STATUS", "Estado da tentativa inválido.")
    access_status = str_value(payload.get("contentAccessStatus")).upper()
    if access_status and access_status not in CONTENT_ACCESS_STATUSES:
        raise ApiError("INVALID_ACCESS_STATUS", "Estado de acesso ao conteúdo inválido.")
    deadline_supplied = "deadlineAt" in payload
    deadline = parse_datetime(payload.get("deadlineAt")) if deadline_supplied else None
    if deadline_supplied and payload.get("deadlineAt") not in (None, "") and not deadline:
        raise ApiError("INVALID_DEADLINE", "O prazo indicado não é válido.")
    if deadline and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if status == "IN_PROGRESS" and deadline and deadline <= utc_now():
        raise ApiError("INVALID_DEADLINE", "Uma tentativa em curso precisa de um prazo futuro.")

    notification_ids: list[str] = []
    with connection() as conn:
        attempt = conn.execute(
            "select * from courseplatform.attempts where attempt_id = %s",
            (payload["attemptId"],),
        ).fetchone()
        if not attempt:
            raise ApiError("ATTEMPT_NOT_FOUND", "Tentativa não encontrada.")
        progress = conn.execute(
            "select * from courseplatform.lesson_progress where progress_id = %s",
            (attempt.get("progress_id"),),
        ).fetchone()
        resolved_access = access_status or progress_access_status(progress)
        status_changed = str_value(attempt.get("status")).upper() != status
        deadline_changed = deadline_supplied and iso(attempt.get("deadline_at")) != iso(deadline)
        access_changed = bool(access_status) and progress_access_status(progress) != resolved_access
        updated = conn.execute(
            """
            update courseplatform.attempts
            set status = %s,
                deadline_at = case when %s then %s else deadline_at end,
                submitted_at = case
                  when %s = 'IN_PROGRESS' then null
                  when %s = 'UNDER_REVIEW' then coalesce(submitted_at, now())
                  else submitted_at
                end,
                reviewed_at = case
                  when %s in ('APPROVED', 'CORRECTION_REQUIRED', 'FAILED', 'TIME_EXCEEDED')
                    then coalesce(reviewed_at, now())
                  when %s = 'IN_PROGRESS' then null
                  else reviewed_at
                end,
                retry_authorized = case when %s = 'IN_PROGRESS' then false else retry_authorized end,
                updated_at = now()
            where attempt_id = %s
            returning *
            """,
            (
                status,
                deadline_supplied,
                deadline,
                status,
                status,
                status,
                status,
                status,
                attempt["attempt_id"],
            ),
        ).fetchone()
        updated_progress = None
        if progress:
            updated_progress = conn.execute(
                """
                update courseplatform.lesson_progress
                set status = %s, evaluation_status = %s, content_access_status = %s,
                    approved_at = case when %s = 'APPROVED' then coalesce(approved_at, now()) else approved_at end,
                    updated_at = now()
                where progress_id = %s
                returning *
                """,
                (
                    legacy_progress_status(resolved_access, status),
                    status,
                    resolved_access,
                    status,
                    progress["progress_id"],
                ),
            ).fetchone()
            refresh_enrollment_progress(conn, progress["progress_id"])
        audit(
            conn,
            "ADMIN",
            admin["admin_id"],
            "ATTEMPT_MANAGED",
            "ATTEMPT",
            attempt["attempt_id"],
            {
                "status": status,
                "deadlineAt": iso(deadline) if deadline_supplied else iso(attempt.get("deadline_at")),
                "contentAccessStatus": resolved_access,
            },
        )
        if status_changed or deadline_changed or access_changed:
            lesson = conn.execute(
                "select title from courseplatform.lessons where lesson_id = %s",
                (attempt["lesson_id"],),
            ).fetchone() or {}
            details = f"{lesson.get('title') or 'Atividade'}: {notification_status_label(status)}."
            if deadline_supplied and deadline:
                details = f"{details} Novo prazo: {iso(deadline)}."
            notification_id = create_student_notification(
                conn,
                attempt["student_id"],
                "SUBMISSION_STATUS",
                "Prazo da submissão atualizado" if deadline_changed and not status_changed else "Estado da submissão atualizado",
                details,
                admin_id=admin["admin_id"],
                action_url="#/submissions",
                entity_type="ATTEMPT",
                entity_id=attempt["attempt_id"],
                priority="HIGH" if status in {"CORRECTION_REQUIRED", "TIME_EXCEEDED"} else "NORMAL",
                template_key="SUBMISSION_DEADLINE_UPDATED" if deadline_changed and not status_changed else "SUBMISSION_STATUS_UPDATED",
                template_variables={
                    "activity": lesson.get("title") or "Atividade",
                    "status": notification_status_label(status),
                    "deadline": iso(deadline) if deadline_supplied and deadline else "",
                    "details": details,
                },
            )
            if notification_id:
                notification_ids.append(notification_id)
        conn.commit()
    dispatch_notification_deliveries(notification_ids)
    return success({"attempt": public_attempt(updated), "progress": public_progress(updated_progress) if updated_progress else None})


def admin_save_media_config(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    media = payload.get("mediaConfig") or {"logoUrl": payload.get("logoUrl"), "videos": payload.get("videos", [])}
    if not isinstance(media, dict):
        raise ApiError("INVALID_MEDIA_CONFIG", "Configuração de media inválida.")
    media.setdefault("logoUrl", "")
    media.setdefault("videos", [])
    with connection() as conn:
        conn.execute(
            """
            insert into courseplatform.settings (key, value, value_type, description, updated_at)
            values ('MEDIA_CONFIG', %s, 'JSON', 'Logotipo e galeria de vídeos da plataforma.', now())
            on conflict (key) do update
            set value = excluded.value, value_type = excluded.value_type,
                description = excluded.description, updated_at = excluded.updated_at
            """,
            (json.dumps(media),),
        )
        audit(conn, "ADMIN", admin["admin_id"], "MEDIA_CONFIG_SAVED", "SETTING", "MEDIA_CONFIG")
        conn.commit()
    return success({"mediaConfig": media})


def admin_save_staff(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER"})
    require_fields(payload, ["fullName", "email"])
    admin_id = str_value(payload.get("targetAdminId") or payload.get("adminId")) or generate_id("ADM")
    role = str_value(payload.get("role") or "REVIEWER").upper()
    if role not in {"OWNER", "ADMIN", "REVIEWER"}:
        role = "REVIEWER"
    status = str_value(payload.get("status") or "ACTIVE").upper()
    is_new = not fetch_one("select 1 from courseplatform.admins where admin_id = %s", (admin_id,))
    admin_password = str_value(payload.get("password"))
    if is_new and not admin_password:
        admin_password = generate_access_code(14)
    if admin_password and not valid_password(admin_password):
        raise ApiError("WEAK_PASSWORD", "A palavra-passe deve ter pelo menos 8 caracteres.")
    with connection() as conn:
        row = conn.execute(
            """
            insert into courseplatform.admins
              (admin_id, full_name, email, password_hash, password_changed_at, password_reset_required,
               role, status, created_at, updated_at)
            values (%s, %s, %s, case when %s = '' then null else crypt(%s, gen_salt('bf', 12)) end,
                    case when %s = '' then null else now() end, %s, %s, %s, now(), now())
            on conflict (admin_id) do update
            set full_name = excluded.full_name, email = excluded.email,
                password_hash = coalesce(excluded.password_hash, courseplatform.admins.password_hash),
                password_changed_at = coalesce(excluded.password_changed_at, courseplatform.admins.password_changed_at),
                password_reset_required = case
                  when excluded.password_hash is null then courseplatform.admins.password_reset_required
                  else excluded.password_reset_required
                end,
                role = excluded.role, status = excluded.status, updated_at = now()
            returning *
            """,
            (
                admin_id,
                str_value(payload.get("fullName")),
                normalize_email(payload.get("email")),
                admin_password,
                admin_password,
                admin_password,
                bool(admin_password),
                role,
                status,
            ),
        ).fetchone()
        audit(conn, "ADMIN", admin["admin_id"], "STAFF_SAVED", "ADMIN", admin_id)
        conn.commit()
    return success({"admin": public_admin(row), "adminPassword": admin_password if admin_password else ""})


def admin_set_staff_status(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER"})
    require_fields(payload, ["targetAdminId", "status"])
    with connection() as conn:
        row = conn.execute(
            "update courseplatform.admins set status = %s, updated_at = now() where admin_id = %s returning *",
            (str_value(payload["status"]).upper(), payload["targetAdminId"]),
        ).fetchone()
        if not row:
            raise ApiError("ADMIN_NOT_FOUND", "Staff não encontrado.")
        audit(conn, "ADMIN", admin["admin_id"], "STAFF_STATUS_CHANGED", "ADMIN", payload["targetAdminId"], {"status": payload["status"]})
        conn.commit()
    return success({"admin": public_admin(row)})


def admin_create_student(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["fullName", "email"])
    access_code = generate_access_code(12)
    student_id = generate_id("STU")
    with connection() as conn:
        public_id = public_student_id()
        while conn.execute("select 1 from courseplatform.students where public_student_id = %s", (public_id,)).fetchone():
            public_id = public_student_id()
        row = conn.execute(
            """
            insert into courseplatform.students
              (student_id, public_student_id, full_name, email, access_code, password_hash,
               password_changed_at, password_reset_required, status,
               country, organization, created_at, updated_at)
            values (%s, %s, %s, %s, null, crypt(%s, gen_salt('bf', 12)),
                    now(), true, 'ACTIVE', %s, %s, now(), now())
            returning *
            """,
            (
                student_id,
                public_id,
                str_value(payload.get("fullName")),
                normalize_email(payload.get("email")),
                access_code,
                str_value(payload.get("country")),
                str_value(payload.get("organization")),
            ),
        ).fetchone()
        audit(conn, "ADMIN", admin["admin_id"], "STUDENT_CREATED", "STUDENT", student_id)
        conn.commit()
    return success({"student": public_student(row), "accessCode": access_code})


def admin_change_student_email(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    prepare_notification_feature_schema()
    require_fields(
        payload,
        ["studentId", "newEmail", "confirmEmail", "adminPassword", "reason"],
    )
    if not as_bool(payload.get("verifiedWithStudent")):
        raise ApiError(
            "EMAIL_VERIFICATION_CONFIRMATION_REQUIRED",
            "Confirme que verificou o novo endereço com o estudante.",
        )
    new_email = validated_email_change(payload)
    reason = str_value(payload.get("reason"))
    if len(reason) < 5:
        raise ApiError("EMAIL_CHANGE_REASON_REQUIRED", "Indique brevemente o motivo da correção do email.")
    if len(reason) > 300:
        raise ApiError("EMAIL_CHANGE_REASON_TOO_LONG", "O motivo deve ter no máximo 300 caracteres.")
    admin_password = str_value(payload.get("adminPassword"))
    if len(admin_password) > 1024:
        raise ApiError("INVALID_ADMIN_PASSWORD", "A palavra-passe administrativa não está correta.")
    try:
        with connection() as conn:
            current_admin = conn.execute(
                "select * from courseplatform.admins where admin_id = %s for update",
                (admin["admin_id"],),
            ).fetchone()
            if not current_admin or current_admin.get("status") != "ACTIVE":
                raise ApiError("ADMIN_NOT_ACTIVE", "A conta administrativa não está ativa.")
            if not verify_password_with_conn(
                conn,
                admin_password,
                current_admin.get("password_hash"),
            ):
                raise ApiError(
                    "INVALID_ADMIN_PASSWORD",
                    "A palavra-passe administrativa não está correta.",
                )
            student = conn.execute(
                "select * from courseplatform.students where student_id = %s for update",
                (str_value(payload.get("studentId")),),
            ).fetchone()
            if not student:
                raise ApiError("STUDENT_NOT_FOUND", "Estudante não encontrado.")
            row = secure_student_email_update(
                conn,
                student,
                new_email,
                actor_type="ADMIN",
                actor_id=admin["admin_id"],
                reason=reason,
            )
            conn.commit()
    except ApiError:
        raise
    except Exception as error:
        text = str(error).lower()
        if "unique" in text or "duplicate" in text:
            raise ApiError(
                "EMAIL_ALREADY_IN_USE",
                "Este endereço de email já está associado a outro estudante.",
            ) from error
        raise database_api_error(error) from error
    return success({
        "student": public_student(row),
        "studentSessionsRevoked": True,
        "emailConsentReset": True,
    })


def admin_set_student_status(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["studentId", "status"])
    with connection() as conn:
        row = conn.execute(
            "update courseplatform.students set status = %s, updated_at = now() where student_id = %s returning *",
            (str_value(payload["status"]).upper(), payload["studentId"]),
        ).fetchone()
        if not row:
            raise ApiError("STUDENT_NOT_FOUND", "Estudante não encontrado.")
        audit(conn, "ADMIN", admin["admin_id"], "STUDENT_STATUS_CHANGED", "STUDENT", payload["studentId"], {"status": payload["status"]})
        conn.commit()
    return success({"student": public_student(row)})


def admin_reset_student_access_code(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["studentId"])
    access_code = generate_access_code(12)
    with connection() as conn:
        row = conn.execute(
            """
            update courseplatform.students
            set password_hash = crypt(%s, gen_salt('bf', 12)),
                password_changed_at = now(), password_reset_required = true,
                access_code = null, updated_at = now()
            where student_id = %s
            returning *
            """,
            (access_code, payload["studentId"]),
        ).fetchone()
        if not row:
            raise ApiError("STUDENT_NOT_FOUND", "Estudante não encontrado.")
        conn.execute("update courseplatform.sessions set active = false, revoked_at = now() where subject_id = %s", (payload["studentId"],))
        audit(conn, "ADMIN", admin["admin_id"], "STUDENT_ACCESS_RESET", "STUDENT", payload["studentId"])
        conn.commit()
    return success({"student": public_student(row), "accessCode": access_code})


def credential_restore_item(kind: str, row: dict[str, Any], temporary_password: str) -> dict[str, Any]:
    if kind == "ADMIN":
        return {
            "type": "ADMIN",
            "id": row.get("admin_id"),
            "publicId": row.get("admin_id"),
            "fullName": row.get("full_name"),
            "email": row.get("email"),
            "role": row.get("role"),
            "status": row.get("status"),
            "temporaryPassword": temporary_password,
        }
    return {
        "type": "STUDENT",
        "id": row.get("student_id"),
        "publicId": row.get("public_student_id") or "",
        "fullName": row.get("full_name"),
        "email": row.get("email"),
        "status": row.get("status"),
        "temporaryPassword": temporary_password,
    }


def admin_restore_credentials(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    target_type = str_value(payload.get("targetType") or "STUDENTS").upper()
    if target_type not in {"STUDENTS", "ADMINS", "ALL"}:
        raise ApiError("INVALID_TARGET", "Tipo de conta inválido para restauração de credenciais.")
    if target_type in {"ADMINS", "ALL"} and admin.get("role") != "OWNER":
        raise ApiError("FORBIDDEN", "Apenas o owner pode restaurar credenciais de staff.")

    only_missing_password = as_bool(payload.get("onlyMissingPassword", True))
    include_inactive = as_bool(payload.get("includeInactive", False))
    student_ids = [str_value(item) for item in payload.get("studentIds") or [] if str_value(item)]
    admin_ids = [str_value(item) for item in payload.get("adminIds") or [] if str_value(item)]
    credentials: list[dict[str, Any]] = []

    with connection() as conn:
        if target_type in {"STUDENTS", "ALL"}:
            students = conn.execute(
                """
                select student_id, public_student_id, full_name, email, status, password_hash
                from courseplatform.students
                where (%s or status = 'ACTIVE')
                  and (%s = 0 or student_id = any(%s::text[]))
                  and (%s = false or password_hash is null)
                order by full_name
                limit 1000
                """,
                (include_inactive, len(student_ids), student_ids, only_missing_password),
            ).fetchall()
            for student in students:
                temporary_password = generate_access_code(12)
                row = conn.execute(
                    """
                    update courseplatform.students
                    set password_hash = crypt(%s, gen_salt('bf', 12)),
                        password_changed_at = now(), password_reset_required = true,
                        access_code = null, updated_at = now()
                    where student_id = %s
                    returning student_id, public_student_id, full_name, email, status
                    """,
                    (temporary_password, student["student_id"]),
                ).fetchone()
                conn.execute(
                    "update courseplatform.sessions set active = false, revoked_at = now() where subject_id = %s",
                    (student["student_id"],),
                )
                credentials.append(credential_restore_item("STUDENT", row, temporary_password))

        if target_type in {"ADMINS", "ALL"}:
            admins = conn.execute(
                """
                select admin_id, full_name, email, role, status, password_hash
                from courseplatform.admins
                where (%s or status = 'ACTIVE')
                  and (%s = 0 or admin_id = any(%s::text[]))
                  and (%s = false or password_hash is null)
                order by case role when 'OWNER' then 1 when 'ADMIN' then 2 else 3 end, full_name
                limit 200
                """,
                (include_inactive, len(admin_ids), admin_ids, only_missing_password),
            ).fetchall()
            for staff in admins:
                temporary_password = generate_access_code(14)
                row = conn.execute(
                    """
                    update courseplatform.admins
                    set password_hash = crypt(%s, gen_salt('bf', 12)),
                        password_changed_at = now(), password_reset_required = true,
                        updated_at = now()
                    where admin_id = %s
                    returning admin_id, full_name, email, role, status
                    """,
                    (temporary_password, staff["admin_id"]),
                ).fetchone()
                conn.execute(
                    "update courseplatform.sessions set active = false, revoked_at = now() where subject_id = %s",
                    (f"ADMIN:{staff['admin_id']}",),
                )
                credentials.append(credential_restore_item("ADMIN", row, temporary_password))

        audit(
            conn,
            "ADMIN",
            admin["admin_id"],
            "CREDENTIALS_RESTORED",
            "ACCOUNT",
            target_type,
            {
                "total": len(credentials),
                "targetType": target_type,
                "onlyMissingPassword": only_missing_password,
                "includeInactive": include_inactive,
            },
        )
        conn.commit()

    summary = {
        "students": sum(1 for item in credentials if item["type"] == "STUDENT"),
        "admins": sum(1 for item in credentials if item["type"] == "ADMIN"),
        "total": len(credentials),
        "onlyMissingPassword": only_missing_password,
        "includeInactive": include_inactive,
    }
    return success({"credentials": credentials, "summary": summary})


def admin_save_course(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["title"])
    course_id = str_value(payload.get("courseId")) or generate_id("COURSE")
    status = str_value(payload.get("status") or "ACTIVE").upper()
    with connection() as conn:
        row = conn.execute(
            """
            insert into courseplatform.courses
              (course_id, course_code, title, description, total_hours, passing_score, status, created_at, updated_at)
            values (%s, %s, %s, %s, %s, %s, %s, now(), now())
            on conflict (course_id) do update
            set course_code = excluded.course_code, title = excluded.title,
                description = excluded.description, total_hours = excluded.total_hours,
                passing_score = excluded.passing_score, status = excluded.status, updated_at = now()
            returning *
            """,
            (
                course_id,
                str_value(payload.get("courseCode") or course_id),
                str_value(payload.get("title")),
                str_value(payload.get("description")),
                float_value(payload.get("totalHours")),
                float_value(payload.get("passingScore"), 60),
                status,
            ),
        ).fetchone()
        audit(conn, "ADMIN", admin["admin_id"], "COURSE_SAVED", "COURSE", course_id)
        conn.commit()
    return success({"course": public_course(row)})


def admin_save_lesson(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["courseId", "title"])
    prepare_assessment_feature_schema()
    lesson_id = str_value(payload.get("lessonId")) or generate_id("LESSON")
    status = str_value(payload.get("status") or "ACTIVE").upper()
    submission_duration = int_value(payload.get("submissionDurationMinutes"))
    if submission_duration <= 0:
        submission_duration = int_value(payload.get("exerciseMinutes")) + int_value(payload.get("individualMinutes"))
    submission_duration = max(1, min(submission_duration or 180, 43200))
    with connection() as conn:
        row = conn.execute(
            """
            insert into courseplatform.lessons
              (lesson_id, course_id, lesson_number, title, slug, summary, theory_minutes,
               exercise_minutes, individual_minutes, passing_score, prerequisite_lesson_id,
               submission_duration_minutes, status, created_at, updated_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
            on conflict (lesson_id) do update
            set course_id = excluded.course_id, lesson_number = excluded.lesson_number,
                title = excluded.title, slug = excluded.slug, summary = excluded.summary,
                theory_minutes = excluded.theory_minutes, exercise_minutes = excluded.exercise_minutes,
                individual_minutes = excluded.individual_minutes, passing_score = excluded.passing_score,
                prerequisite_lesson_id = excluded.prerequisite_lesson_id,
                submission_duration_minutes = excluded.submission_duration_minutes,
                status = excluded.status,
                updated_at = now()
            returning *
            """,
            (
                lesson_id,
                payload["courseId"],
                int_value(payload.get("lessonNumber"), 1),
                str_value(payload.get("title")),
                str_value(payload.get("slug")),
                str_value(payload.get("summary")),
                float_value(payload.get("theoryMinutes")),
                float_value(payload.get("exerciseMinutes")),
                float_value(payload.get("individualMinutes")),
                float_value(payload.get("passingScore"), 60),
                str_value(payload.get("prerequisiteLessonId")) or None,
                submission_duration,
                status,
            ),
        ).fetchone()
        audit(conn, "ADMIN", admin["admin_id"], "LESSON_SAVED", "LESSON", lesson_id)
        conn.commit()
    return success({"lesson": public_lesson(row)})


def admin_save_lesson_content(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["lessonId", "title"])
    content_id = str_value(payload.get("contentId")) or generate_id("CNT")
    with connection() as conn:
        row = conn.execute(
            """
            insert into courseplatform.lesson_content
              (content_id, lesson_id, section_order, section_type, title, body_html,
               estimated_minutes, is_required, status, created_at, updated_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
            on conflict (content_id) do update
            set lesson_id = excluded.lesson_id, section_order = excluded.section_order,
                section_type = excluded.section_type, title = excluded.title,
                body_html = excluded.body_html, estimated_minutes = excluded.estimated_minutes,
                is_required = excluded.is_required, status = excluded.status, updated_at = now()
            returning *
            """,
            (
                content_id,
                payload["lessonId"],
                int_value(payload.get("sectionOrder"), 1),
                str_value(payload.get("sectionType") or "TEORIA"),
                str_value(payload.get("title")),
                str_value(payload.get("bodyHtml")),
                float_value(payload.get("estimatedMinutes")),
                as_bool(payload.get("isRequired", True)),
                str_value(payload.get("status") or "ACTIVE").upper(),
            ),
        ).fetchone()
        audit(conn, "ADMIN", admin["admin_id"], "LESSON_CONTENT_SAVED", "LESSON_CONTENT", content_id)
        conn.commit()
    return success({"content": public_content(row)})


def admin_save_group(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["courseId", "name"])
    group_id = str_value(payload.get("groupId")) or generate_id("GRP")
    student_ids = payload.get("studentIds") if isinstance(payload.get("studentIds"), list) else []
    with connection() as conn:
        group = conn.execute(
            """
            insert into courseplatform.groups
              (group_id, group_code, name, course_id, start_date, end_date, status, created_at, updated_at)
            values (%s, %s, %s, %s, %s, %s, %s, now(), now())
            on conflict (group_id) do update
            set group_code = excluded.group_code, name = excluded.name, course_id = excluded.course_id,
                start_date = excluded.start_date, end_date = excluded.end_date,
                status = excluded.status, updated_at = now()
            returning *
            """,
            (
                group_id,
                str_value(payload.get("groupCode") or group_id),
                str_value(payload.get("name")),
                payload["courseId"],
                parse_datetime(payload.get("startDate")),
                parse_datetime(payload.get("endDate")),
                str_value(payload.get("status") or "ACTIVE").upper(),
            ),
        ).fetchone()
        for student_id in student_ids:
            conn.execute(
                """
                insert into courseplatform.group_members
                  (group_member_id, group_id, student_id, status, joined_at, updated_at)
                values (%s, %s, %s, 'ACTIVE', now(), now())
                on conflict (group_id, student_id) do update
                set status = 'ACTIVE', updated_at = now()
                """,
                (generate_id("GM"), group_id, student_id),
            )
        audit(conn, "ADMIN", admin["admin_id"], "GROUP_SAVED", "GROUP", group_id, {"studentCount": len(student_ids)})
        conn.commit()
    return success({"group": {"groupId": group["group_id"], "groupCode": group.get("group_code"), "name": group.get("name"), "courseId": group.get("course_id"), "startDate": iso(group.get("start_date")), "endDate": iso(group.get("end_date")), "status": group.get("status")}})


def admin_assign_students_to_group(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["groupId"])
    student_ids = payload.get("studentIds") if isinstance(payload.get("studentIds"), list) else []
    with connection() as conn:
        for student_id in student_ids:
            conn.execute(
                """
                insert into courseplatform.group_members
                  (group_member_id, group_id, student_id, status, joined_at, updated_at)
                values (%s, %s, %s, 'ACTIVE', now(), now())
                on conflict (group_id, student_id) do update
                set status = 'ACTIVE', updated_at = now()
                """,
                (generate_id("GM"), payload["groupId"], student_id),
            )
        audit(conn, "ADMIN", admin["admin_id"], "GROUP_MEMBERS_ASSIGNED", "GROUP", payload["groupId"], {"studentCount": len(student_ids)})
        conn.commit()
    return success({"studentCount": len(student_ids)})


def admin_set_lesson_access(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    prepare_assessment_feature_schema()
    prepare_notification_feature_schema()
    status = str_value(payload.get("status") or "AVAILABLE").upper()
    if status not in CONTENT_ACCESS_STATUSES:
        raise ApiError("INVALID_STATUS", "Estado de acesso inválido.")
    lesson_ids = payload.get("lessonIds") if isinstance(payload.get("lessonIds"), list) else []
    student_ids = set(payload.get("studentIds") if isinstance(payload.get("studentIds"), list) else [])
    group_ids = payload.get("groupIds") if isinstance(payload.get("groupIds"), list) else []
    if group_ids:
        rows = fetch_all(
            "select student_id from courseplatform.group_members where group_id = any(%s) and status = 'ACTIVE'",
            (group_ids,),
        )
        student_ids.update(row["student_id"] for row in rows)
    if not lesson_ids or not student_ids:
        raise ApiError("EMPTY_ACCESS_TARGET", "Selecione módulos e estudantes.")
    updated = 0
    notification_ids: list[str] = []
    with connection() as conn:
        for student_id in student_ids:
            for lesson_id in lesson_ids:
                lesson = conn.execute("select * from courseplatform.lessons where lesson_id = %s", (lesson_id,)).fetchone()
                if not lesson:
                    continue
                enrollment = conn.execute(
                    """
                    select *
                    from courseplatform.enrollments
                    where student_id = %s and course_id = %s
                    order by enrolled_at desc nulls last
                    limit 1
                    """,
                    (student_id, lesson["course_id"]),
                ).fetchone()
                if not enrollment:
                    enrollment = conn.execute(
                        """
                        insert into courseplatform.enrollments
                          (enrollment_id, student_id, course_id, status, enrolled_at, progress_percent, updated_at)
                        values (%s, %s, %s, 'ACTIVE', now(), 0, now())
                        returning *
                        """,
                        (generate_id("ENR"), student_id, lesson["course_id"]),
                    ).fetchone()
                previous = conn.execute(
                    """
                    select * from courseplatform.lesson_progress
                    where enrollment_id = %s and lesson_id = %s
                    """,
                    (enrollment["enrollment_id"], lesson_id),
                ).fetchone()
                previous_access = progress_access_status(previous)
                conn.execute(
                    """
                    insert into courseplatform.lesson_progress
                      (progress_id, enrollment_id, student_id, lesson_id, status,
                       content_access_status, evaluation_status, unlocked_at, attempt_count, updated_at)
                    values (%s, %s, %s, %s, %s, %s, 'NOT_STARTED',
                            case when %s <> 'LOCKED' then now() else null end, 0, now())
                    on conflict (enrollment_id, lesson_id) do update
                    set content_access_status = excluded.content_access_status,
                        status = case
                          when coalesce(courseplatform.lesson_progress.evaluation_status, 'NOT_STARTED') = 'NOT_STARTED'
                            then excluded.content_access_status
                          else courseplatform.lesson_progress.evaluation_status
                        end,
                        unlocked_at = case when excluded.content_access_status <> 'LOCKED' then coalesce(courseplatform.lesson_progress.unlocked_at, now()) else courseplatform.lesson_progress.unlocked_at end,
                        updated_at = now()
                    """,
                    (generate_id("PRG"), enrollment["enrollment_id"], student_id, lesson_id, status, status, status),
                )
                if previous_access != status:
                    notification_id = create_student_notification(
                        conn,
                        student_id,
                        "MODULE_AVAILABLE",
                        "Novo módulo disponível" if status == "AVAILABLE" else "Acesso ao módulo atualizado",
                        (
                            f"O módulo {lesson.get('title') or lesson_id} está disponível para leitura e exercícios."
                            if status == "AVAILABLE"
                            else f"O acesso ao módulo {lesson.get('title') or lesson_id} foi temporariamente bloqueado."
                        ),
                        admin_id=admin["admin_id"],
                        action_url=f"#/lesson/{lesson_id}" if status == "AVAILABLE" else "#/lessons",
                        entity_type="LESSON",
                        entity_id=lesson_id,
                        template_key="MODULE_ACCESS_UPDATED",
                        template_variables={
                            "module": lesson.get("title") or lesson_id,
                            "status": notification_status_label(status),
                            "details": (
                                f"O módulo {lesson.get('title') or lesson_id} está disponível para leitura e exercícios."
                                if status == "AVAILABLE"
                                else f"O acesso ao módulo {lesson.get('title') or lesson_id} foi temporariamente bloqueado."
                            ),
                        },
                    )
                    if notification_id:
                        notification_ids.append(notification_id)
                updated += 1
        audit(conn, "ADMIN", admin["admin_id"], "LESSON_ACCESS_CHANGED", "LESSON_PROGRESS", "", {"lessonCount": len(lesson_ids), "studentCount": len(student_ids), "status": status})
        conn.commit()
    dispatch_notification_deliveries(notification_ids)
    return success({"studentCount": len(student_ids), "lessonCount": len(lesson_ids), "updatedCount": updated})


def admin_manage_lesson_progress(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    prepare_assessment_feature_schema()
    prepare_notification_feature_schema()
    lesson_ids = payload.get("lessonIds") if isinstance(payload.get("lessonIds"), list) else []
    student_ids = set(payload.get("studentIds") if isinstance(payload.get("studentIds"), list) else [])
    group_ids = payload.get("groupIds") if isinstance(payload.get("groupIds"), list) else []
    access_status = str_value(payload.get("contentAccessStatus")).upper()
    evaluation_status = str_value(payload.get("evaluationStatus")).upper()
    if access_status in {"UNCHANGED", "KEEP"}:
        access_status = ""
    if evaluation_status in {"UNCHANGED", "KEEP"}:
        evaluation_status = ""
    if access_status and access_status not in CONTENT_ACCESS_STATUSES:
        raise ApiError("INVALID_ACCESS_STATUS", "Estado de acesso ao conteúdo inválido.")
    if evaluation_status and evaluation_status not in EVALUATION_STATUSES:
        raise ApiError("INVALID_EVALUATION_STATUS", "Estado de avaliação inválido.")
    duration_supplied = payload.get("submissionDurationMinutes") not in (None, "")
    submission_duration = int_value(payload.get("submissionDurationMinutes")) if duration_supplied else None
    if duration_supplied and (submission_duration < 1 or submission_duration > 43200):
        raise ApiError("INVALID_SUBMISSION_DURATION", "O tempo de submissão deve estar entre 1 e 43200 minutos.")
    if not lesson_ids:
        raise ApiError("EMPTY_LESSON_TARGET", "Selecione pelo menos um módulo.")
    if not access_status and not evaluation_status and not duration_supplied:
        raise ApiError("EMPTY_MANAGEMENT_CHANGE", "Selecione pelo menos uma alteração para aplicar.")

    updated = 0
    enrollment_ids: set[str] = set()
    notification_ids: list[str] = []
    with connection() as conn:
        if group_ids:
            rows = conn.execute(
                "select student_id from courseplatform.group_members where group_id = any(%s) and status = 'ACTIVE'",
                (group_ids,),
            ).fetchall()
            student_ids.update(row["student_id"] for row in rows)
        if (access_status or evaluation_status) and not student_ids:
            raise ApiError("EMPTY_PROGRESS_TARGET", "Selecione pelo menos uma turma ou estudante.")

        if duration_supplied:
            conn.execute(
                """
                update courseplatform.lessons
                set submission_duration_minutes = %s, updated_at = now()
                where lesson_id = any(%s)
                """,
                (submission_duration, lesson_ids),
            )

        for student_id in student_ids:
            for lesson_id in lesson_ids:
                lesson = conn.execute(
                    "select * from courseplatform.lessons where lesson_id = %s",
                    (lesson_id,),
                ).fetchone()
                if not lesson:
                    continue
                enrollment = conn.execute(
                    """
                    select * from courseplatform.enrollments
                    where student_id = %s and course_id = %s
                    order by enrolled_at desc nulls last
                    limit 1
                    """,
                    (student_id, lesson["course_id"]),
                ).fetchone()
                if not enrollment:
                    enrollment = conn.execute(
                        """
                        insert into courseplatform.enrollments
                          (enrollment_id, student_id, course_id, status, enrolled_at, progress_percent, updated_at)
                        values (%s, %s, %s, 'ACTIVE', now(), 0, now())
                        returning *
                        """,
                        (generate_id("ENR"), student_id, lesson["course_id"]),
                    ).fetchone()
                progress = conn.execute(
                    """
                    select * from courseplatform.lesson_progress
                    where enrollment_id = %s and lesson_id = %s
                    """,
                    (enrollment["enrollment_id"], lesson_id),
                ).fetchone()
                previous_access = progress_access_status(progress)
                previous_evaluation = progress_evaluation_status(progress)
                resolved_access = access_status or progress_access_status(progress)
                resolved_evaluation = evaluation_status or progress_evaluation_status(progress)
                resolved_legacy = legacy_progress_status(resolved_access, resolved_evaluation)
                if progress:
                    progress = conn.execute(
                        """
                        update courseplatform.lesson_progress
                        set status = %s, content_access_status = %s, evaluation_status = %s,
                            unlocked_at = case
                              when %s = 'AVAILABLE' then coalesce(unlocked_at, now())
                              else unlocked_at
                            end,
                            approved_at = case
                              when %s = 'APPROVED' then coalesce(approved_at, now())
                              else approved_at
                            end,
                            updated_at = now()
                        where progress_id = %s
                        returning *
                        """,
                        (
                            resolved_legacy,
                            resolved_access,
                            resolved_evaluation,
                            resolved_access,
                            resolved_evaluation,
                            progress["progress_id"],
                        ),
                    ).fetchone()
                else:
                    progress = conn.execute(
                        """
                        insert into courseplatform.lesson_progress
                          (progress_id, enrollment_id, student_id, lesson_id, status,
                           content_access_status, evaluation_status, unlocked_at,
                           approved_at, attempt_count, updated_at)
                        values (%s, %s, %s, %s, %s, %s, %s,
                                case when %s = 'AVAILABLE' then now() else null end,
                                case when %s = 'APPROVED' then now() else null end, 0, now())
                        returning *
                        """,
                        (
                            generate_id("PRG"),
                            enrollment["enrollment_id"],
                            student_id,
                            lesson_id,
                            resolved_legacy,
                            resolved_access,
                            resolved_evaluation,
                            resolved_access,
                            resolved_evaluation,
                        ),
                    ).fetchone()
                if evaluation_status in ATTEMPT_STATUSES:
                    conn.execute(
                        """
                        update courseplatform.attempts
                        set status = %s,
                            submitted_at = case
                              when %s = 'IN_PROGRESS' then null
                              when %s = 'UNDER_REVIEW' then coalesce(submitted_at, now())
                              else submitted_at
                            end,
                            reviewed_at = case
                              when %s in ('APPROVED', 'CORRECTION_REQUIRED', 'FAILED', 'TIME_EXCEEDED')
                                then coalesce(reviewed_at, now())
                              when %s = 'IN_PROGRESS' then null
                              else reviewed_at
                            end,
                            updated_at = now()
                        where attempt_id = (
                          select attempt_id from courseplatform.attempts
                          where student_id = %s and lesson_id = %s
                          order by coalesce(updated_at, created_at) desc nulls last
                          limit 1
                        )
                        """,
                        (
                            evaluation_status,
                            evaluation_status,
                            evaluation_status,
                            evaluation_status,
                            evaluation_status,
                            student_id,
                            lesson_id,
                        ),
                    )
                access_changed = previous_access != resolved_access
                evaluation_changed = previous_evaluation != resolved_evaluation
                if access_changed or evaluation_changed:
                    message_parts = []
                    if access_changed:
                        message_parts.append(f"Conteúdo: {notification_status_label(resolved_access)}")
                    if evaluation_changed:
                        message_parts.append(f"Avaliação: {notification_status_label(resolved_evaluation)}")
                    notification_id = create_student_notification(
                        conn,
                        student_id,
                        "MODULE_AVAILABLE" if access_changed else "SUBMISSION_STATUS",
                        "Novo módulo disponível" if access_changed and resolved_access == "AVAILABLE" else "Módulo atualizado",
                        f"{lesson.get('title') or lesson_id}. {'; '.join(message_parts)}.",
                        admin_id=admin["admin_id"],
                        action_url=f"#/lesson/{lesson_id}" if resolved_access == "AVAILABLE" else "#/lessons",
                        entity_type="LESSON_PROGRESS",
                        entity_id=progress["progress_id"],
                        priority="HIGH" if resolved_evaluation == "CORRECTION_REQUIRED" else "NORMAL",
                        template_key="MODULE_PROGRESS_UPDATED",
                        template_variables={
                            "module": lesson.get("title") or lesson_id,
                            "status": notification_status_label(resolved_evaluation),
                            "details": f"{lesson.get('title') or lesson_id}. {'; '.join(message_parts)}.",
                        },
                    )
                    if notification_id:
                        notification_ids.append(notification_id)
                enrollment_ids.add(enrollment["enrollment_id"])
                updated += 1

        for enrollment_id in enrollment_ids:
            progress = conn.execute(
                "select progress_id from courseplatform.lesson_progress where enrollment_id = %s limit 1",
                (enrollment_id,),
            ).fetchone()
            refresh_enrollment_progress(conn, progress.get("progress_id") if progress else None)
        audit(
            conn,
            "ADMIN",
            admin["admin_id"],
            "LESSON_PROGRESS_MANAGED",
            "LESSON_PROGRESS",
            "",
            {
                "lessonCount": len(lesson_ids),
                "studentCount": len(student_ids),
                "contentAccessStatus": access_status or "UNCHANGED",
                "evaluationStatus": evaluation_status or "UNCHANGED",
                "submissionDurationMinutes": submission_duration if duration_supplied else None,
            },
        )
        conn.commit()
    dispatch_notification_deliveries(notification_ids)
    return success({
        "studentCount": len(student_ids),
        "lessonCount": len(lesson_ids),
        "updatedCount": updated,
        "submissionDurationMinutes": submission_duration if duration_supplied else None,
    })


def admin_student_details(payload: dict[str, Any]):
    admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    require_fields(payload, ["studentId"])
    prepare_assessment_feature_schema()
    student_id = payload["studentId"]
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        student = conn.execute("select * from courseplatform.students where student_id = %s", (student_id,)).fetchone()
        if not student:
            raise ApiError("STUDENT_NOT_FOUND", "Estudante não encontrado.")
        enrollment_rows = conn.execute(
            """
            select e.*, c.title as course_title, c.course_code, g.name as group_name
            from courseplatform.enrollments e
            left join courseplatform.courses c on c.course_id = e.course_id
            left join courseplatform.groups g on g.group_id = e.group_id
            where e.student_id = %s
            order by coalesce(e.updated_at, e.enrolled_at) desc nulls last
            """,
            (student_id,),
        ).fetchall()
        progress_rows = conn.execute(
            """
            select p.*, l.course_id, l.lesson_number, l.title as lesson_title,
                   a.attempt_id, a.attempt_number, a.status as attempt_status,
                   a.score as attempt_score, a.submitted_at as attempt_submitted_at,
                   a.reviewed_at as attempt_reviewed_at,
                   coalesce(f.file_count, 0) as file_count
            from courseplatform.lesson_progress p
            join courseplatform.lessons l on l.lesson_id = p.lesson_id
            left join lateral (
              select *
              from courseplatform.attempts a
              where a.student_id = p.student_id and a.lesson_id = p.lesson_id
              order by coalesce(a.updated_at, a.created_at) desc nulls last
              limit 1
            ) a on true
            left join lateral (
              select count(*) as file_count
              from courseplatform.files f
              where f.student_id = p.student_id and f.lesson_id = p.lesson_id
                and coalesce(f.status, 'ACTIVE') <> 'DELETED'
            ) f on true
            where p.student_id = %s
            order by l.course_id, l.lesson_number
            """,
            (student_id,),
        ).fetchall()
        group_rows = conn.execute(
            """
            select gm.*, g.name, g.group_code, g.course_id, g.start_date, g.end_date
            from courseplatform.group_members gm
            join courseplatform.groups g on g.group_id = gm.group_id
            where gm.student_id = %s
            order by g.name
            """,
            (student_id,),
        ).fetchall()
        certificates = conn.execute(
            """
            select cert.*, c.title as course_title, s.full_name as student_name
            from courseplatform.certificates cert
            join courseplatform.courses c on c.course_id = cert.course_id
            join courseplatform.students s on s.student_id = cert.student_id
            where cert.student_id = %s
            order by cert.issue_date desc nulls last
            """,
            (student_id,),
        ).fetchall()
        requests = conn.execute(
            """
            select cr.*, s.full_name, s.email, c.title
            from courseplatform.certificate_requests cr
            join courseplatform.students s on s.student_id = cr.student_id
            join courseplatform.courses c on c.course_id = cr.course_id
            where cr.student_id = %s
            order by coalesce(cr.updated_at, cr.created_at) desc
            """,
            (student_id,),
        ).fetchall()
    return success({
        "student": public_student(student),
        "enrollments": [
            {
                **public_enrollment(row),
                "courseTitle": row.get("course_title"),
                "courseCode": row.get("course_code"),
                "groupName": row.get("group_name"),
            }
            for row in enrollment_rows
        ],
        "lessonProgress": [
            {
                "progress": public_progress(row),
                "courseId": row.get("course_id"),
                "lesson": {
                    "lessonId": row.get("lesson_id"),
                    "lessonNumber": int(row.get("lesson_number") or 0),
                    "title": row.get("lesson_title"),
                },
                "attempt": public_attempt({
                    "attempt_id": row.get("attempt_id"),
                    "progress_id": row.get("progress_id"),
                    "lesson_id": row.get("lesson_id"),
                    "attempt_number": row.get("attempt_number"),
                    "status": row.get("attempt_status"),
                    "score": row.get("attempt_score"),
                    "submitted_at": row.get("attempt_submitted_at"),
                    "reviewed_at": row.get("attempt_reviewed_at"),
                }) if row.get("attempt_id") else None,
                "fileCount": int(row.get("file_count") or 0),
            }
            for row in progress_rows
        ],
        "groups": [
            {
                "groupMember": public_group_member(row),
                "group": {
                    "groupId": row.get("group_id"),
                    "groupCode": row.get("group_code"),
                    "name": row.get("name"),
                    "courseId": row.get("course_id"),
                    "startDate": iso(row.get("start_date")),
                    "endDate": iso(row.get("end_date")),
                },
            }
            for row in group_rows
        ],
        "certificates": [public_certificate(row) for row in certificates],
        "certificateRequests": [public_certificate_request(row) for row in requests],
    })


def admin_list_certificate_requests(payload: dict[str, Any]):
    admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    status = (payload.get("status") or "ALL").upper()
    query = (payload.get("query") or "").strip().lower()
    limit = min(int(payload.get("limit") or 200), 500)
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        rows = conn.execute(
            """
            select cr.*, s.full_name, s.email, c.title,
                   cert.certificate_number, cert.verification_code, cert.issue_date,
                   cert.final_score, cert.certificate_type, cert.content_summary
            from courseplatform.certificate_requests cr
            join courseplatform.students s on s.student_id = cr.student_id
            join courseplatform.courses c on c.course_id = cr.course_id
            left join courseplatform.certificates cert on cert.certificate_id = cr.certificate_id
            where (%s = 'ALL' or cr.status = %s)
              and (
                %s = ''
                or lower(coalesce(s.full_name, '') || ' ' || coalesce(s.email, '') || ' ' ||
                  coalesce(c.title, '') || ' ' || coalesce(cr.request_id, '')) like %s
              )
            order by coalesce(cr.submitted_at, cr.updated_at, cr.created_at) desc
            limit %s
            """,
            (status, status, query, f"%{query}%", limit),
        ).fetchall()
        conn.commit()
    return success({"requests": [public_certificate_request(row) for row in rows]})


def admin_list_certificates(payload: dict[str, Any]):
    admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    status = (payload.get("status") or "ACTIVE").upper()
    query = str_value(payload.get("query")).lower()
    limit = min(int(payload.get("limit") or 200), 500)
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        rows = conn.execute(
            """
            select cert.*, s.full_name as student_name, s.email, c.title as course_title
            from courseplatform.certificates cert
            join courseplatform.students s on s.student_id = cert.student_id
            join courseplatform.courses c on c.course_id = cert.course_id
            where (
                %s = 'ALL'
                or (%s = 'ACTIVE' and coalesce(cert.status, 'ISSUED') <> 'DELETED')
                or cert.status = %s
              )
              and (
                %s = ''
                or lower(coalesce(s.full_name, '') || ' ' || coalesce(s.email, '') || ' ' ||
                  coalesce(c.title, '') || ' ' || coalesce(cert.certificate_number, '') || ' ' ||
                  coalesce(cert.verification_code, '')) like %s
              )
            order by cert.issue_date desc nulls last
            limit %s
            """,
            (status, status, status, query, f"%{query}%", limit),
        ).fetchall()
        conn.commit()
    return success({"certificates": [public_certificate(row) for row in rows]})


def admin_set_certificate_status(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["certificateId", "status"])
    status = str_value(payload.get("status")).upper()
    if status not in {"ISSUED", "BLOCKED"}:
        raise ApiError("INVALID_CERTIFICATE_STATUS", "Estado de certificado inválido.")
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        certificate = conn.execute(
            """
            update courseplatform.certificates
            set status = %s,
                status_note = %s,
                status_updated_by = %s,
                status_updated_at = now()
            where certificate_id = %s
            returning *
            """,
            (status, str_value(payload.get("statusNote")), admin["admin_id"], payload["certificateId"]),
        ).fetchone()
        if not certificate:
            raise ApiError("CERTIFICATE_NOT_FOUND", "Certificado não encontrado.")
        audit(conn, "ADMIN", admin["admin_id"], "CERTIFICATE_STATUS_CHANGED", "CERTIFICATE", certificate["certificate_id"], {"status": status})
        conn.commit()
    return success({"certificate": public_certificate(certificate)})


def admin_refresh_certificate_format(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    certificate_id = str_value(payload.get("certificateId"))
    course_id = str_value(payload.get("courseId"))
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        if certificate_id:
            rows = conn.execute(
                """
                select certificate_id, course_id, certificate_type
                from courseplatform.certificates
                where certificate_id = %s
                """,
                (certificate_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                select certificate_id, course_id, certificate_type
                from courseplatform.certificates
                where coalesce(status, 'ISSUED') <> 'DELETED'
                  and (%s = '' or course_id = %s)
                order by issue_date desc nulls last
                limit 500
                """,
                (course_id, course_id),
            ).fetchall()
        if not rows:
            raise ApiError("CERTIFICATE_NOT_FOUND", "Certificado não encontrado.")

        refreshed = []
        for row in rows:
            summary = certificate_content_summary(conn, row["course_id"])
            snapshot = certificate_template_snapshot(conn, row["course_id"], row.get("certificate_type") or "SIMPLE")
            certificate = conn.execute(
                """
                update courseplatform.certificates
                set content_summary = %s,
                    template_snapshot_json = %s,
                    status_note = %s,
                    status_updated_by = %s,
                    status_updated_at = now()
                where certificate_id = %s
                returning *
                """,
                (
                    summary,
                    json.dumps(snapshot),
                    "Formato e conteúdo do certificado atualizados pelo administrador.",
                    admin["admin_id"],
                    row["certificate_id"],
                ),
            ).fetchone()
            if certificate:
                refreshed.append(certificate)
                audit(conn, "ADMIN", admin["admin_id"], "CERTIFICATE_FORMAT_REFRESHED", "CERTIFICATE", certificate["certificate_id"], {})
        conn.commit()
    return success({"updated": len(refreshed), "certificates": [public_certificate(row) for row in refreshed]})


def admin_delete_certificate(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["certificateId"])
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        certificate = conn.execute(
            """
            update courseplatform.certificates
            set status = 'DELETED',
                status_note = %s,
                status_updated_by = %s,
                status_updated_at = now()
            where certificate_id = %s and coalesce(status, 'ISSUED') <> 'DELETED'
            returning *
            """,
            (str_value(payload.get("statusNote")) or "Apagado pelo administrador.", admin["admin_id"], payload["certificateId"]),
        ).fetchone()
        if not certificate:
            raise ApiError("CERTIFICATE_NOT_FOUND", "Certificado não encontrado.")
        audit(conn, "ADMIN", admin["admin_id"], "CERTIFICATE_DELETED", "CERTIFICATE", certificate["certificate_id"], {})
        conn.commit()
    return success({"certificate": public_certificate(certificate)})


def admin_review_certificate_request(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["requestId", "decision"])
    decision = str_value(payload.get("decision")).upper()
    if decision not in {"APPROVED", "REJECTED"}:
        raise ApiError("INVALID_DECISION", "Decisão inválida.")
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        request = conn.execute(
            "select * from courseplatform.certificate_requests where request_id = %s for update",
            (payload["requestId"],),
        ).fetchone()
        if not request:
            raise ApiError("CERTIFICATE_REQUEST_NOT_FOUND", "Pedido de certificado não encontrado.")
        if request.get("status") != "PAYMENT_SUBMITTED" or request.get("certificate_id"):
            raise ApiError(
                "CERTIFICATE_REQUEST_ALREADY_REVIEWED",
                "Este pedido já foi revisto ou ainda não está pronto para avaliação.",
            )
        certificate = None
        if decision == "APPROVED":
            student = conn.execute("select * from courseplatform.students where student_id = %s", (request["student_id"],)).fetchone()
            course = conn.execute("select * from courseplatform.courses where course_id = %s", (request["course_id"],)).fetchone()
            certificate = conn.execute(
                """
                insert into courseplatform.certificates
                  (certificate_id, student_id, course_id, certificate_number, verification_code,
                   issue_date, final_score, drive_file_id, drive_url, status, certificate_type,
                   recognition_level, content_summary, template_snapshot_json, professional_request_id,
                   download_count, max_downloads, payment_status, approved_by, approved_at)
                values (%s, %s, %s, %s, %s, now(),
                  (select final_score from courseplatform.enrollments where student_id = %s and course_id = %s limit 1),
                  '', '', 'ISSUED', 'PROFESSIONAL', 'CONTENT_DETAILED', %s, %s, %s, 0, 5,
                  'CONFIRMED', %s, now())
                returning *
                """,
                (
                    generate_id("CERT"),
                    request["student_id"],
                    request["course_id"],
                    certificate_number(),
                    certificate_verification_code(),
                    request["student_id"],
                    request["course_id"],
                    certificate_content_summary(conn, request["course_id"]),
                    json.dumps(certificate_template_snapshot(conn, request["course_id"], "PROFESSIONAL")),
                    request["request_id"],
                    admin["admin_id"],
                ),
            ).fetchone()
            request = conn.execute(
                """
                update courseplatform.certificate_requests
                set status = 'APPROVED',
                    certificate_id = %s,
                    reviewed_by = %s,
                    reviewed_at = now(),
                    admin_notes = %s,
                    updated_at = now()
                where request_id = %s
                returning *
                """,
                (certificate["certificate_id"], admin["admin_id"], str_value(payload.get("adminNotes")), request["request_id"]),
            ).fetchone()
            certificate = {**certificate, "course_title": (course or {}).get("title"), "student_name": (student or {}).get("full_name")}
        else:
            request = conn.execute(
                """
                update courseplatform.certificate_requests
                set status = 'REJECTED',
                    reviewed_by = %s,
                    reviewed_at = now(),
                    admin_notes = %s,
                    updated_at = now()
                where request_id = %s
                returning *
                """,
                (admin["admin_id"], str_value(payload.get("adminNotes")), request["request_id"]),
            ).fetchone()
        audit(conn, "ADMIN", admin["admin_id"], "CERTIFICATE_REQUEST_REVIEWED", "CERTIFICATE_REQUEST", request["request_id"], {"decision": decision})
        conn.commit()
    return success({"request": public_certificate_request(request), "certificate": public_certificate(certificate)})


def admin_delete_certificate_request(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["requestId"])
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        request = conn.execute(
            "select * from courseplatform.certificate_requests where request_id = %s for update",
            (payload["requestId"],),
        ).fetchone()
        if not request:
            raise ApiError("CERTIFICATE_REQUEST_NOT_FOUND", "Pedido de certificado não encontrado.")
        if request.get("certificate_id"):
            raise ApiError(
                "CERTIFICATE_REQUEST_PROTECTED",
                "Este pedido está associado a um certificado e não pode ser apagado.",
            )
        if request.get("payment_receipt_url") or request.get("submitted_at"):
            raise ApiError(
                "CERTIFICATE_REQUEST_PROTECTED",
                "Pedidos com comprovativo submetido devem ser preservados para auditoria.",
            )
        if request.get("status") not in {"REQUESTED", "REJECTED"}:
            raise ApiError(
                "CERTIFICATE_REQUEST_PROTECTED",
                "Apenas pedidos solicitados ou rejeitados, sem comprovativo, podem ser apagados.",
            )
        deleted = conn.execute(
            "delete from courseplatform.certificate_requests where request_id = %s returning *",
            (request["request_id"],),
        ).fetchone()
        audit(
            conn,
            "ADMIN",
            admin["admin_id"],
            "CERTIFICATE_REQUEST_DELETED",
            "CERTIFICATE_REQUEST",
            request["request_id"],
            {"status": request.get("status")},
        )
        conn.commit()
    return success({"request": public_certificate_request(deleted)})


def admin_get_certificate_settings(payload: dict[str, Any]):
    admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    course_id = payload.get("courseId") or get_settings().default_course_id
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        course = conn.execute("select * from courseplatform.courses where course_id = %s", (course_id,)).fetchone()
        row = conn.execute("select * from courseplatform.certificate_settings where course_id = %s", (course_id,)).fetchone()
        conn.commit()
    return success({"settings": certificate_settings_payload(row, course), "course": public_course(course)})


def admin_save_certificate_settings(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    course_id = payload.get("courseId") or get_settings().default_course_id
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        course = conn.execute("select * from courseplatform.courses where course_id = %s", (course_id,)).fetchone()
        current = conn.execute("select * from courseplatform.certificate_settings where course_id = %s", (course_id,)).fetchone()
        current_payload = certificate_settings_payload(current, course)
        survey_questions = normalize_survey_questions(payload.get("surveyQuestions")) if isinstance(payload.get("surveyQuestions"), list) else current_payload.get("surveyQuestions", [])
        profile = normalize_certificate_profile(payload.get("certificateProfile") or current_payload.get("certificateProfile"), course)
        row = conn.execute(
            """
            insert into courseplatform.certificate_settings
              (course_id, congratulations_message, survey_questions_json,
               professional_price, payment_instructions, professional_preview_url,
               certificate_profile_json, updated_by, updated_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s, now())
            on conflict (course_id) do update
            set congratulations_message = excluded.congratulations_message,
                survey_questions_json = excluded.survey_questions_json,
                professional_price = excluded.professional_price,
                payment_instructions = excluded.payment_instructions,
                professional_preview_url = excluded.professional_preview_url,
                certificate_profile_json = excluded.certificate_profile_json,
                updated_by = excluded.updated_by,
                updated_at = now()
            returning *
            """,
            (
                course_id,
                str_value(payload.get("congratulationsMessage")) or current_payload.get("congratulationsMessage"),
                json.dumps(survey_questions),
                str_value(payload.get("professionalPrice")) or profile.get("printFee") or current_payload.get("professionalPrice"),
                str_value(payload.get("paymentInstructions")) or profile.get("paymentInstructions") or current_payload.get("paymentInstructions"),
                str_value(payload.get("professionalPreviewUrl")) or current_payload.get("professionalPreviewUrl"),
                json.dumps(profile),
                admin["admin_id"],
            ),
        ).fetchone()
        audit(conn, "ADMIN", admin["admin_id"], "CERTIFICATE_SETTINGS_SAVED", "COURSE", course_id)
        conn.commit()
    return success({"settings": certificate_settings_payload(row, course), "course": public_course(course)})


def admin_list_certificate_surveys(payload: dict[str, Any]):
    admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        rows = conn.execute(
            """
            select c.*, cs.survey_questions_json, cs.congratulations_message, cs.updated_at
            from courseplatform.courses c
            left join courseplatform.certificate_settings cs on cs.course_id = c.course_id
            where coalesce(c.status, 'ACTIVE') <> 'DELETED'
            order by c.title
            """
        ).fetchall()
        conn.commit()
    surveys = []
    for row in rows:
        settings = certificate_settings_payload(row, row)
        surveys.append({
            "course": public_course(row),
            "congratulationsMessage": settings.get("congratulationsMessage"),
            "surveyQuestions": settings.get("surveyQuestions"),
            "questionCount": len(settings.get("surveyQuestions") or []),
            "updatedAt": iso(row.get("updated_at")),
        })
    return success({"surveys": surveys})


def admin_save_certificate_survey(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    course_id = payload.get("courseId") or get_settings().default_course_id
    survey_questions = normalize_survey_questions(payload.get("surveyQuestions") if isinstance(payload.get("surveyQuestions"), list) else [])
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        course = conn.execute("select * from courseplatform.courses where course_id = %s", (course_id,)).fetchone()
        if not course:
            raise ApiError("COURSE_NOT_FOUND", "Curso não encontrado.")
        current = conn.execute("select * from courseplatform.certificate_settings where course_id = %s", (course_id,)).fetchone()
        current_payload = certificate_settings_payload(current, course)
        profile = normalize_certificate_profile(current_payload.get("certificateProfile"), course)
        row = conn.execute(
            """
            insert into courseplatform.certificate_settings
              (course_id, congratulations_message, survey_questions_json,
               professional_price, payment_instructions, professional_preview_url,
               certificate_profile_json, updated_by, updated_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s, now())
            on conflict (course_id) do update
            set congratulations_message = excluded.congratulations_message,
                survey_questions_json = excluded.survey_questions_json,
                updated_by = excluded.updated_by,
                updated_at = now()
            returning *
            """,
            (
                course_id,
                str_value(payload.get("congratulationsMessage")) or current_payload.get("congratulationsMessage"),
                json.dumps(survey_questions),
                current_payload.get("professionalPrice"),
                current_payload.get("paymentInstructions"),
                current_payload.get("professionalPreviewUrl"),
                json.dumps(profile),
                admin["admin_id"],
            ),
        ).fetchone()
        audit(conn, "ADMIN", admin["admin_id"], "CERTIFICATE_SURVEY_SAVED", "COURSE", course_id)
        conn.commit()
    return success({"settings": certificate_settings_payload(row, course), "course": public_course(course)})


def admin_upload_certificate_asset(payload: dict[str, Any]):
    admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["courseId", "assetKey", "fileName", "mimeType", "dataUrl"])
    course_id = str_value(payload.get("courseId"))
    asset_key = str_value(payload.get("assetKey"))
    allowed_keys = set(default_certificate_profile().get("assets", {}).keys())
    if asset_key not in allowed_keys:
        raise ApiError("INVALID_ASSET_KEY", "Tipo de elemento gráfico inválido.")
    mime_type = str_value(payload.get("mimeType"))
    if mime_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise ApiError("INVALID_FILE_TYPE", "Use PNG, JPEG ou WebP.")
    data_url = str_value(payload.get("dataUrl"))
    marker = ";base64,"
    if marker not in data_url:
        raise ApiError("INVALID_FILE_DATA", "Ficheiro inválido.")
    encoded = data_url.split(marker, 1)[1]
    try:
        file_bytes = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ApiError("INVALID_FILE_DATA", "Ficheiro inválido.") from exc
    if len(file_bytes) > 3 * 1024 * 1024:
        raise ApiError("FILE_TOO_LARGE", "O ficheiro deve ter até 3 MB.")

    settings = get_settings()
    extension = mimetypes.guess_extension(mime_type) or ".png"
    object_path = f"{course_id}/{asset_key}-{certificate_token(8)}{extension}"
    storage_saved = False
    storage_error = ""
    if settings.supabase_url and settings.supabase_service_role_key:
        try:
            request = urllib.request.Request(
                f"{settings.supabase_url}/storage/v1/object/{settings.supabase_storage_bucket}/{object_path}",
                data=file_bytes,
                method="POST",
                headers={
                    "Authorization": f"Bearer {settings.supabase_service_role_key}",
                    "apikey": settings.supabase_service_role_key,
                    "Content-Type": mime_type,
                    "x-upsert": "true",
                },
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                storage_saved = 200 <= response.status < 300
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            storage_error = str(exc)

    return success({
        "assetKey": asset_key,
        "assetUrl": data_url,
        "storagePath": object_path if storage_saved else "",
        "storageSaved": storage_saved,
        "storageError": storage_error,
    })


def verify_certificate(payload: dict[str, Any]):
    code = payload.get("code") or payload.get("verificationCode") or ""
    certificate = fetch_one(
        """
        select cert.*, s.full_name, c.title
        from courseplatform.certificates cert
        join courseplatform.students s on s.student_id = cert.student_id
        join courseplatform.courses c on c.course_id = cert.course_id
        where cert.verification_code = %s or cert.certificate_number = %s
        """,
        (code, code),
    )
    if not certificate:
        return success({"valid": False})
    return success({"valid": certificate.get("status") == "ISSUED", "certificate": {"certificateNumber": certificate.get("certificate_number"), "verificationCode": certificate.get("verification_code"), "issueDate": iso(certificate.get("issue_date")), "finalScore": float(certificate.get("final_score") or 0), "status": certificate.get("status")}, "student": {"fullName": certificate.get("full_name")}, "course": {"title": certificate.get("title")}})


def admin_list_notifications(payload: dict[str, Any]):
    _, _admin = admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    prepare_notification_feature_schema()
    limit, offset, page = pagination(payload, default_limit=80, max_limit=200)
    rows = fetch_all(
        """
        select n.*, s.full_name as student_name,
               w.status as whatsapp_status, w.recipient as whatsapp_recipient,
               w.provider_message_id as whatsapp_provider_message_id,
               w.attempt_count as whatsapp_attempt_count, w.last_error as whatsapp_last_error,
               w.sent_at as whatsapp_sent_at,
               e.status as email_status, e.recipient as email_recipient,
               e.provider_message_id as email_provider_message_id,
               e.attempt_count as email_attempt_count, e.last_error as email_last_error,
               e.sent_at as email_sent_at,
               t.status as telegram_status, t.recipient as telegram_recipient,
               t.provider_message_id as telegram_provider_message_id,
               t.attempt_count as telegram_attempt_count, t.last_error as telegram_last_error,
               t.sent_at as telegram_sent_at,
               p.status as push_status,
               p.provider_message_id as push_provider_message_id,
               p.attempt_count as push_attempt_count, p.last_error as push_last_error,
               p.sent_at as push_sent_at
        from courseplatform.notifications n
        join courseplatform.students s on s.student_id = n.student_id
        left join courseplatform.notification_deliveries w
          on w.notification_id = n.notification_id and w.channel = 'WHATSAPP'
        left join courseplatform.notification_deliveries e
          on e.notification_id = n.notification_id and e.channel = 'EMAIL'
        left join courseplatform.notification_deliveries t
          on t.notification_id = n.notification_id and t.channel = 'TELEGRAM'
        left join courseplatform.notification_deliveries p
          on p.notification_id = n.notification_id and p.channel = 'PUSH'
        order by n.created_at desc
        limit %s offset %s
        """,
        (limit, offset),
    )
    totals = fetch_one(
        """
        select
          (select count(*) from courseplatform.notifications) as internal_total,
          count(*) filter (where d.channel = 'WHATSAPP' and d.status = 'SENT') as whatsapp_sent,
          count(*) filter (where d.channel = 'WHATSAPP' and d.status in ('PENDING', 'PROCESSING')) as whatsapp_pending,
          count(*) filter (where d.channel = 'WHATSAPP' and d.status = 'FAILED') as whatsapp_failed,
          count(*) filter (where d.channel = 'WHATSAPP' and d.status = 'SKIPPED') as whatsapp_skipped,
          count(*) filter (where d.channel = 'EMAIL' and d.status = 'SENT') as email_sent,
          count(*) filter (where d.channel = 'EMAIL' and d.status in ('PENDING', 'PROCESSING')) as email_pending,
          count(*) filter (where d.channel = 'EMAIL' and d.status = 'FAILED') as email_failed,
          count(*) filter (where d.channel = 'EMAIL' and d.status = 'SKIPPED') as email_skipped,
          count(*) filter (where d.channel = 'TELEGRAM' and d.status = 'SENT') as telegram_sent,
          count(*) filter (where d.channel = 'TELEGRAM' and d.status in ('PENDING', 'PROCESSING')) as telegram_pending,
          count(*) filter (where d.channel = 'TELEGRAM' and d.status = 'FAILED') as telegram_failed,
          count(*) filter (where d.channel = 'TELEGRAM' and d.status = 'SKIPPED') as telegram_skipped,
          count(*) filter (where d.channel = 'PUSH' and d.status = 'SENT') as push_sent,
          count(*) filter (where d.channel = 'PUSH' and d.status in ('PENDING', 'PROCESSING')) as push_pending,
          count(*) filter (where d.channel = 'PUSH' and d.status = 'FAILED') as push_failed,
          count(*) filter (where d.channel = 'PUSH' and d.status = 'SKIPPED') as push_skipped
        from courseplatform.notification_deliveries d
        """
    ) or {}
    return success({
        "notifications": [public_notification(row) for row in rows],
        "summary": {
            "internalTotal": int(totals.get("internal_total") or 0),
            "whatsappSent": int(totals.get("whatsapp_sent") or 0),
            "whatsappPending": int(totals.get("whatsapp_pending") or 0),
            "whatsappFailed": int(totals.get("whatsapp_failed") or 0),
            "whatsappSkipped": int(totals.get("whatsapp_skipped") or 0),
            "emailSent": int(totals.get("email_sent") or 0),
            "emailPending": int(totals.get("email_pending") or 0),
            "emailFailed": int(totals.get("email_failed") or 0),
            "emailSkipped": int(totals.get("email_skipped") or 0),
            "telegramSent": int(totals.get("telegram_sent") or 0),
            "telegramPending": int(totals.get("telegram_pending") or 0),
            "telegramFailed": int(totals.get("telegram_failed") or 0),
            "telegramSkipped": int(totals.get("telegram_skipped") or 0),
            "pushSent": int(totals.get("push_sent") or 0),
            "pushPending": int(totals.get("push_pending") or 0),
            "pushFailed": int(totals.get("push_failed") or 0),
            "pushSkipped": int(totals.get("push_skipped") or 0),
        },
        "whatsappConfiguration": whatsapp_configuration(),
        "emailConfiguration": email_configuration(),
        "telegramConfiguration": telegram_configuration(),
        "pushConfiguration": web_push_configuration(),
        "notificationTemplates": notification_templates_payload(),
        "page": page,
        "limit": limit,
    })


def admin_create_notification(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    prepare_notification_feature_schema()
    require_fields(payload, ["title", "message"])
    notify_all = as_bool(payload.get("notifyAll"))
    student_ids = payload.get("studentIds") if isinstance(payload.get("studentIds"), list) else []
    student_ids = [str_value(student_id) for student_id in student_ids if str_value(student_id)]
    if notify_all:
        student_ids = [
            row["student_id"]
            for row in fetch_all("select student_id from courseplatform.students where status = 'ACTIVE' order by full_name")
        ]
    if not student_ids:
        raise ApiError("NOTIFICATION_RECIPIENT_REQUIRED", "Selecione pelo menos um estudante.")
    notification_ids: list[str] = []
    with connection() as conn:
        for student_id in dict.fromkeys(student_ids):
            notification_id = create_student_notification(
                conn,
                student_id,
                str_value(payload.get("category") or "GENERAL"),
                str_value(payload.get("title")),
                str_value(payload.get("message")),
                admin_id=admin["admin_id"],
                action_url=safe_notification_action_url(payload.get("actionUrl")),
                entity_type="MANUAL_UPDATE",
                entity_id="",
                priority=str_value(payload.get("priority") or "NORMAL"),
                email_subject=str_value(payload.get("emailSubject")),
                email_message=str_value(payload.get("emailMessage")),
                push_title=str_value(payload.get("pushTitle")),
                push_message=str_value(payload.get("pushMessage")),
                send_whatsapp=as_bool(payload.get("sendWhatsApp")),
                send_email=as_bool(payload.get("sendEmail")),
                send_telegram=as_bool(payload.get("sendTelegram")),
                send_push=as_bool(payload.get("sendPush")),
            )
            if notification_id:
                notification_ids.append(notification_id)
        audit(
            conn,
            "ADMIN",
            admin["admin_id"],
            "NOTIFICATION_SENT",
            "NOTIFICATION",
            "",
            {
                "studentCount": len(notification_ids),
                "sendWhatsApp": as_bool(payload.get("sendWhatsApp")),
                "sendEmail": as_bool(payload.get("sendEmail")),
                "sendTelegram": as_bool(payload.get("sendTelegram")),
                "sendPush": as_bool(payload.get("sendPush")),
            },
        )
        conn.commit()
    dispatch_notification_deliveries(notification_ids)
    return success({"notificationCount": len(notification_ids), "notificationIds": notification_ids})


def admin_save_notification_template(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    prepare_notification_feature_schema()
    source = payload.get("notificationTemplate") if isinstance(payload.get("notificationTemplate"), dict) else payload
    template_key = str_value(source.get("templateKey")).upper()
    if template_key not in NOTIFICATION_TEMPLATE_DEFINITIONS:
        raise ApiError("INVALID_NOTIFICATION_TEMPLATE", "Selecione um modelo de notificação válido.")
    limits = {
        "internalTitleTemplate": 180,
        "internalMessageTemplate": 1800,
        "emailSubjectTemplate": 180,
        "emailMessageTemplate": 5000,
        "pushTitleTemplate": 120,
        "pushMessageTemplate": 300,
    }
    values: dict[str, str] = {}
    for field, limit in limits.items():
        value = str_value(source.get(field))
        if not value:
            raise ApiError("NOTIFICATION_TEMPLATE_FIELD_REQUIRED", "Todos os textos do modelo são obrigatórios.", {"field": field})
        if len(value) > limit:
            raise ApiError("NOTIFICATION_TEMPLATE_TOO_LONG", "Um dos textos excede o tamanho permitido.", {"field": field, "limit": limit})
        unknown_tokens = _template_tokens(value) - NOTIFICATION_TEMPLATE_VARIABLES
        if unknown_tokens:
            raise ApiError(
                "INVALID_NOTIFICATION_TEMPLATE_VARIABLE",
                "O modelo contém variáveis não suportadas.",
                {"field": field, "variables": sorted(unknown_tokens)},
            )
        values[field] = value
    with connection() as conn:
        row = conn.execute(
            """
            insert into courseplatform.notification_templates
              (template_key, internal_title_template, internal_message_template,
               email_subject_template, email_message_template,
               push_title_template, push_message_template, updated_by, updated_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s, now())
            on conflict (template_key) do update set
              internal_title_template = excluded.internal_title_template,
              internal_message_template = excluded.internal_message_template,
              email_subject_template = excluded.email_subject_template,
              email_message_template = excluded.email_message_template,
              push_title_template = excluded.push_title_template,
              push_message_template = excluded.push_message_template,
              updated_by = excluded.updated_by,
              updated_at = now()
            returning *
            """,
            (
                template_key,
                values["internalTitleTemplate"], values["internalMessageTemplate"],
                values["emailSubjectTemplate"], values["emailMessageTemplate"],
                values["pushTitleTemplate"], values["pushMessageTemplate"],
                admin["admin_id"],
            ),
        ).fetchone()
        audit(
            conn, "ADMIN", admin["admin_id"], "NOTIFICATION_TEMPLATE_UPDATED",
            "NOTIFICATION_TEMPLATE", template_key,
        )
        conn.commit()
    return success({
        "notificationTemplate": notification_template_payload(template_key, row),
        "notificationTemplates": notification_templates_payload(),
    })


def admin_reset_notification_template(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    prepare_notification_feature_schema()
    template_key = str_value(payload.get("templateKey")).upper()
    if template_key not in NOTIFICATION_TEMPLATE_DEFINITIONS:
        raise ApiError("INVALID_NOTIFICATION_TEMPLATE", "Selecione um modelo de notificação válido.")
    with connection() as conn:
        conn.execute("delete from courseplatform.notification_templates where template_key = %s", (template_key,))
        audit(
            conn, "ADMIN", admin["admin_id"], "NOTIFICATION_TEMPLATE_RESET",
            "NOTIFICATION_TEMPLATE", template_key,
        )
        conn.commit()
    return success({
        "notificationTemplate": notification_template_payload(template_key),
        "notificationTemplates": notification_templates_payload(),
    })


def admin_save_whatsapp_configuration(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    prepare_notification_feature_schema()
    settings = get_settings()
    configuration = payload.get("whatsappConfiguration")
    if not isinstance(configuration, dict):
        configuration = payload

    enabled = as_bool(configuration.get("enabled"))
    phone_number_id = str_value(configuration.get("phoneNumberId"))
    graph_api_version = str_value(configuration.get("graphApiVersion")) or "v23.0"
    template_name = str_value(configuration.get("templateName"))
    template_language = str_value(configuration.get("templateLanguage")) or "pt_PT"
    platform_url = str_value(configuration.get("platformUrl")).rstrip("/")
    access_token = str_value(configuration.get("accessToken"))
    remove_access_token = as_bool(configuration.get("removeAccessToken"))

    if access_token and remove_access_token:
        raise ApiError(
            "AMBIGUOUS_WHATSAPP_TOKEN_UPDATE",
            "Escolha entre substituir ou remover o token de acesso.",
        )
    if len(access_token) > 8192:
        raise ApiError("INVALID_WHATSAPP_ACCESS_TOKEN", "O token de acesso excede o tamanho permitido.")
    if phone_number_id and not re.fullmatch(r"\d{6,30}", phone_number_id):
        raise ApiError("INVALID_WHATSAPP_PHONE_ID", "O Phone Number ID deve conter apenas números.")
    if not re.fullmatch(r"v\d+\.\d+", graph_api_version):
        raise ApiError("INVALID_WHATSAPP_API_VERSION", "Utilize uma versão da Graph API no formato v23.0.")
    if template_name and not re.fullmatch(r"[a-z0-9_]{1,512}", template_name):
        raise ApiError("INVALID_WHATSAPP_TEMPLATE", "O nome do modelo deve usar letras minúsculas, números e underscores.")
    if not re.fullmatch(r"[a-z]{2,3}(?:_[A-Z]{2})?", template_language):
        raise ApiError("INVALID_WHATSAPP_LANGUAGE", "Utilize um idioma no formato pt_PT.")
    if platform_url and not valid_whatsapp_platform_url(platform_url):
        raise ApiError("INVALID_WHATSAPP_PLATFORM_URL", "Informe um endereço http:// ou https:// completo e válido.")
    encryption_key = notification_encryption_key(settings)
    if access_token and not encryption_key:
        raise ApiError(
            "WHATSAPP_ENCRYPTION_KEY_REQUIRED",
            "Defina NOTIFICATION_CONFIG_ENCRYPTION_KEY no servidor antes de guardar o token pelo painel.",
        )
    if access_token and len(encryption_key.encode("utf-8")) < 32:
        raise ApiError(
            "WEAK_WHATSAPP_ENCRYPTION_KEY",
            "NOTIFICATION_CONFIG_ENCRYPTION_KEY deve possuir pelo menos 32 bytes.",
        )

    with connection() as conn:
        existing = conn.execute(
            """
            select access_token_encrypted,
                   access_token_encrypted is not null as token_configured
            from courseplatform.notification_channel_settings
            where channel = 'WHATSAPP'
            """
        ).fetchone() or {}
        encrypted_token = None if remove_access_token else existing.get("access_token_encrypted")
        if access_token:
            encrypted_token = conn.execute(
                "select pgp_sym_encrypt(%s, %s, 'cipher-algo=aes256') as encrypted_token",
                (access_token, encryption_key),
            ).fetchone()["encrypted_token"]

        encryption_key_configured = len(encryption_key.encode("utf-8")) >= 32
        token_available = bool(
            access_token
            or (encrypted_token is not None and encryption_key_configured)
            or settings.whatsapp_access_token
        )
        if enabled and not (phone_number_id and template_name and platform_url and token_available):
            raise ApiError(
                "INCOMPLETE_WHATSAPP_CONFIGURATION",
                "Preencha o Phone Number ID, o modelo, o endereço da plataforma e um token antes de ativar o WhatsApp.",
            )

        conn.execute(
            """
            insert into courseplatform.notification_channel_settings
              (channel, enabled, phone_number_id, graph_api_version, template_name,
               template_language, platform_url, access_token_encrypted, updated_by, updated_at)
            values ('WHATSAPP', %s, %s, %s, %s, %s, %s, %s, %s, now())
            on conflict (channel) do update set
              enabled = excluded.enabled,
              phone_number_id = excluded.phone_number_id,
              graph_api_version = excluded.graph_api_version,
              template_name = excluded.template_name,
              template_language = excluded.template_language,
              platform_url = excluded.platform_url,
              access_token_encrypted = excluded.access_token_encrypted,
              updated_by = excluded.updated_by,
              updated_at = now()
            """,
            (
                enabled,
                phone_number_id or None,
                graph_api_version,
                template_name or None,
                template_language,
                platform_url or None,
                encrypted_token,
                admin["admin_id"],
            ),
        )
        audit(
            conn,
            "ADMIN",
            admin["admin_id"],
            "WHATSAPP_CONFIGURATION_UPDATED",
            "NOTIFICATION_CHANNEL",
            "WHATSAPP",
            {
                "enabled": enabled,
                "phoneNumberConfigured": bool(phone_number_id),
                "templateName": template_name,
                "tokenChanged": bool(access_token or remove_access_token),
            },
        )
        conn.commit()
    return success({"whatsappConfiguration": whatsapp_configuration()})


def admin_save_email_configuration(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    prepare_notification_feature_schema()
    settings = get_settings()
    configuration = payload.get("emailConfiguration")
    if not isinstance(configuration, dict):
        configuration = payload
    enabled = as_bool(configuration.get("enabled"))
    smtp_host = str_value(configuration.get("smtpHost"))
    smtp_port = int_value(configuration.get("smtpPort"), 587)
    smtp_username = str_value(configuration.get("smtpUsername"))
    smtp_password = str_value(configuration.get("smtpPassword"))
    from_email = normalize_email_recipient(configuration.get("fromEmail"))
    raw_from_email = str_value(configuration.get("fromEmail"))
    from_name = str_value(configuration.get("fromName"))
    use_tls = as_bool(configuration.get("useTls"))
    remove_password = as_bool(configuration.get("removeSmtpPassword"))
    encryption_key = notification_encryption_key(settings)
    if smtp_password and remove_password:
        raise ApiError("AMBIGUOUS_SMTP_PASSWORD_UPDATE", "Escolha entre substituir ou remover a palavra-passe SMTP.")
    if smtp_host and not valid_notification_host(smtp_host):
        raise ApiError("INVALID_SMTP_HOST", "Informe apenas um hostname SMTP válido, sem protocolo ou caminho.")
    if not 1 <= smtp_port <= 65535:
        raise ApiError("INVALID_SMTP_PORT", "A porta SMTP deve estar entre 1 e 65535.")
    if enabled and smtp_port != 465 and not use_tls:
        raise ApiError(
            "INSECURE_SMTP_TRANSPORT",
            "Ative TLS para proteger as credenciais e o conteúdo do email. A porta 465 utiliza TLS implícito.",
        )
    if len(smtp_username) > 320:
        raise ApiError("INVALID_SMTP_USERNAME", "O utilizador SMTP excede o tamanho permitido.")
    if len(smtp_password) > 8192:
        raise ApiError("INVALID_SMTP_PASSWORD", "A palavra-passe SMTP excede o tamanho permitido.")
    if raw_from_email and not from_email:
        raise ApiError("INVALID_SMTP_FROM_EMAIL", "Informe um endereço de remetente válido.")
    if len(from_name) > 120 or "\r" in from_name or "\n" in from_name:
        raise ApiError("INVALID_SMTP_FROM_NAME", "O nome do remetente é inválido.")
    if smtp_password and len(encryption_key.encode("utf-8")) < 32:
        raise ApiError(
            "WEAK_NOTIFICATION_ENCRYPTION_KEY",
            "NOTIFICATION_CONFIG_ENCRYPTION_KEY deve possuir pelo menos 32 bytes.",
        )
    with connection() as conn:
        existing = conn.execute(
            """
            select smtp_password_encrypted
            from courseplatform.notification_channel_settings where channel = 'EMAIL'
            """
        ).fetchone() or {}
        encrypted_password = None if remove_password else existing.get("smtp_password_encrypted")
        if smtp_password:
            encrypted_password = conn.execute(
                "select pgp_sym_encrypt(%s, %s, 'cipher-algo=aes256') as encrypted_secret",
                (smtp_password, encryption_key),
            ).fetchone()["encrypted_secret"]
        stored_password_available = bool(
            smtp_password
            or (encrypted_password is not None and len(encryption_key.encode("utf-8")) >= 32)
            or settings.smtp_password
        )
        if enabled and not (
            smtp_host and from_email and (not smtp_username or stored_password_available)
        ):
            raise ApiError(
                "INCOMPLETE_EMAIL_CONFIGURATION",
                "Preencha o servidor, o remetente e, quando houver autenticação, a palavra-passe SMTP.",
            )
        conn.execute(
            """
            insert into courseplatform.notification_channel_settings
              (channel, enabled, smtp_host, smtp_port, smtp_username,
               smtp_password_encrypted, from_email, from_name, use_tls, updated_by, updated_at)
            values ('EMAIL', %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            on conflict (channel) do update set
              enabled = excluded.enabled, smtp_host = excluded.smtp_host,
              smtp_port = excluded.smtp_port, smtp_username = excluded.smtp_username,
              smtp_password_encrypted = excluded.smtp_password_encrypted,
              from_email = excluded.from_email, from_name = excluded.from_name,
              use_tls = excluded.use_tls, updated_by = excluded.updated_by, updated_at = now()
            """,
            (
                enabled, smtp_host or None, smtp_port, smtp_username or None,
                encrypted_password, from_email or None, from_name or None,
                use_tls, admin["admin_id"],
            ),
        )
        audit(
            conn, "ADMIN", admin["admin_id"], "EMAIL_CONFIGURATION_UPDATED",
            "NOTIFICATION_CHANNEL", "EMAIL",
            {
                "enabled": enabled, "smtpHostConfigured": bool(smtp_host),
                "fromEmailConfigured": bool(from_email),
                "passwordChanged": bool(smtp_password or remove_password),
            },
        )
        conn.commit()
    return success({"emailConfiguration": email_configuration()})


def admin_save_telegram_configuration(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    prepare_notification_feature_schema()
    settings = get_settings()
    configuration = payload.get("telegramConfiguration")
    if not isinstance(configuration, dict):
        configuration = payload
    enabled = as_bool(configuration.get("enabled"))
    bot_token = str_value(configuration.get("botToken"))
    bot_username = str_value(configuration.get("botUsername")).lstrip("@")
    raw_parse_mode = str_value(configuration.get("parseMode")) or "HTML"
    parse_mode = normalize_telegram_parse_mode(raw_parse_mode)
    remove_token = as_bool(configuration.get("removeBotToken"))
    encryption_key = notification_encryption_key(settings)
    if bot_token and remove_token:
        raise ApiError("AMBIGUOUS_TELEGRAM_TOKEN_UPDATE", "Escolha entre substituir ou remover o token do bot.")
    if bot_token and not valid_telegram_bot_token(bot_token):
        raise ApiError("INVALID_TELEGRAM_BOT_TOKEN", "O token do bot Telegram possui um formato inválido.")
    if bot_username and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", bot_username):
        raise ApiError("INVALID_TELEGRAM_BOT_USERNAME", "Informe o username do bot sem @, com 5 a 32 caracteres.")
    if raw_parse_mode.upper() not in {"HTML", "MARKDOWNV2", "MARKDOWN_V2", "NONE", "PLAIN"}:
        raise ApiError("INVALID_TELEGRAM_PARSE_MODE", "Utilize HTML, MarkdownV2 ou sem formatação.")
    if len(bot_token) > 256:
        raise ApiError("INVALID_TELEGRAM_BOT_TOKEN", "O token do bot excede o tamanho permitido.")
    if bot_token and len(encryption_key.encode("utf-8")) < 32:
        raise ApiError(
            "WEAK_NOTIFICATION_ENCRYPTION_KEY",
            "NOTIFICATION_CONFIG_ENCRYPTION_KEY deve possuir pelo menos 32 bytes.",
        )
    with connection() as conn:
        existing = conn.execute(
            """
            select access_token_encrypted
            from courseplatform.notification_channel_settings where channel = 'TELEGRAM'
            """
        ).fetchone() or {}
        encrypted_token = None if remove_token else existing.get("access_token_encrypted")
        if bot_token:
            encrypted_token = conn.execute(
                "select pgp_sym_encrypt(%s, %s, 'cipher-algo=aes256') as encrypted_secret",
                (bot_token, encryption_key),
            ).fetchone()["encrypted_secret"]
        token_available = bool(
            bot_token
            or (encrypted_token is not None and len(encryption_key.encode("utf-8")) >= 32)
            or settings.telegram_bot_token
        )
        if enabled and not (bot_username and token_available):
            raise ApiError(
                "INCOMPLETE_TELEGRAM_CONFIGURATION",
                "Preencha o username e o token do bot antes de ativar o Telegram.",
            )
        conn.execute(
            """
            insert into courseplatform.notification_channel_settings
              (channel, enabled, bot_username, parse_mode, access_token_encrypted, updated_by, updated_at)
            values ('TELEGRAM', %s, %s, %s, %s, %s, now())
            on conflict (channel) do update set
              enabled = excluded.enabled, bot_username = excluded.bot_username,
              parse_mode = excluded.parse_mode,
              access_token_encrypted = excluded.access_token_encrypted,
              updated_by = excluded.updated_by, updated_at = now()
            """,
            (enabled, bot_username or None, parse_mode or None, encrypted_token, admin["admin_id"]),
        )
        audit(
            conn, "ADMIN", admin["admin_id"], "TELEGRAM_CONFIGURATION_UPDATED",
            "NOTIFICATION_CHANNEL", "TELEGRAM",
            {
                "enabled": enabled, "botUsernameConfigured": bool(bot_username),
                "parseMode": parse_mode, "tokenChanged": bool(bot_token or remove_token),
            },
        )
        conn.commit()
    return success({"telegramConfiguration": telegram_configuration()})


def admin_retry_notification_deliveries(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    prepare_notification_feature_schema()
    limit = max(1, min(int_value(payload.get("limit"), 20), 20))
    requested = payload.get("channels") if isinstance(payload.get("channels"), list) else []
    channels = [str_value(channel).upper() for channel in requested]
    channels = [channel for channel in dict.fromkeys(channels) if channel in {"WHATSAPP", "EMAIL", "TELEGRAM", "PUSH"}]
    if not channels:
        channels = ["WHATSAPP", "EMAIL", "TELEGRAM", "PUSH"]
    delivery_functions = {
        "WHATSAPP": deliver_pending_whatsapp,
        "EMAIL": deliver_pending_email,
        "TELEGRAM": deliver_pending_telegram,
        "PUSH": deliver_pending_push,
    }
    deliveries: dict[str, dict[str, int]] = {}
    for channel in channels:
        try:
            deliveries[channel.lower()] = delivery_functions[channel](limit=limit)
        except Exception as error:
            deliveries[channel.lower()] = {
                "sent": 0, "failed": 1, "pending": 0,
                "error": redact_notification_error(error),
            }
    result = {
        key: sum(int(channel_result.get(key) or 0) for channel_result in deliveries.values())
        for key in ("sent", "failed", "pending")
    }
    with connection() as conn:
        audit(
            conn, "ADMIN", admin["admin_id"], "NOTIFICATION_DELIVERIES_RETRIED",
            "NOTIFICATION", "", {"total": result, "channels": channels},
        )
        conn.commit()
    return success({
        "delivery": result,
        "deliveries": deliveries,
        "whatsappConfiguration": whatsapp_configuration(),
        "emailConfiguration": email_configuration(),
        "telegramConfiguration": telegram_configuration(),
        "pushConfiguration": web_push_configuration(),
    })


def not_implemented(action: str):
    raise ApiError("NOT_IMPLEMENTED", f"A ação {action} ainda não foi portada para a API Python.")


ACTIONS = {
    "health": health,
    "publicCourseConfig": public_course_config,
    "publicMediaConfig": public_media_config,
    "getMediaConfig": student_media_config,
    "verifyCertificate": verify_certificate,
    "login": login,
    "recoverStudentAccess": recover_student_access,
    "logout": logout,
    "adminLogin": admin_login,
    "recoverAdminAccess": recover_admin_access,
    "adminLogout": logout,
    "adminMe": admin_me,
    "adminGetMediaConfig": admin_media_config,
    "adminListStaff": admin_list_staff,
    "adminListSubmissions": admin_list_submissions,
    "adminListPendingSubmissions": admin_list_submissions,
    "getDashboard": dashboard,
    "getStudentHome": student_home,
    "getMyCourses": my_courses,
    "studentStartTelegramLink": student_start_telegram_link,
    "studentConfirmTelegramLink": student_confirm_telegram_link,
    "studentUnlinkTelegram": student_unlink_telegram,
    "getPushConfiguration": student_push_configuration,
    "subscribePush": student_subscribe_push,
    "unsubscribePush": student_unsubscribe_push,
    "getLesson": get_lesson,
    "getAttemptStatus": attempt_status,
    "updateMyProfile": update_my_profile,
    "getMyNotifications": my_notifications,
    "markNotificationRead": mark_notification_read,
    "changeMyAccessCode": change_my_access_code,
    "changeMyEmail": change_my_email,
    "getMyCertifications": my_certifications,
    "requestProfessionalCertificate": request_professional_certificate,
    "submitProfessionalCertificatePayment": submit_professional_certificate_payment,
    "recordCertificateDownload": record_certificate_download,
    "startAttempt": start_attempt,
    "saveAnswer": save_answer,
    "uploadFile": upload_file,
    "deleteUploadedFile": delete_uploaded_file,
    "submitAttempt": submit_attempt,
    "getMyCertificate": my_certificate,
    "adminListCourses": admin_list_courses,
    "adminGetCourseStructure": admin_course_structure,
    "adminListGroups": admin_list_groups,
    "adminListStudents": admin_list_students,
    "adminGetStudentDetails": admin_student_details,
    "adminGetSubmission": admin_get_submission,
    "adminReviewSubmission": admin_review_submission,
    "adminAuthorizeRetry": admin_authorize_retry,
    "adminUpdateAttempt": admin_update_attempt,
    "adminListCertificateRequests": admin_list_certificate_requests,
    "adminListCertificates": admin_list_certificates,
    "adminSetCertificateStatus": admin_set_certificate_status,
    "adminRefreshCertificateFormat": admin_refresh_certificate_format,
    "adminDeleteCertificate": admin_delete_certificate,
    "adminReviewCertificateRequest": admin_review_certificate_request,
    "adminDeleteCertificateRequest": admin_delete_certificate_request,
    "adminGetCertificateSettings": admin_get_certificate_settings,
    "adminSaveCertificateSettings": admin_save_certificate_settings,
    "adminListCertificateSurveys": admin_list_certificate_surveys,
    "adminSaveCertificateSurvey": admin_save_certificate_survey,
    "adminUploadCertificateAsset": admin_upload_certificate_asset,
    "adminListNotifications": admin_list_notifications,
    "adminCreateNotification": admin_create_notification,
    "adminSaveNotificationTemplate": admin_save_notification_template,
    "adminResetNotificationTemplate": admin_reset_notification_template,
    "adminSaveWhatsAppConfiguration": admin_save_whatsapp_configuration,
    "adminSaveEmailConfiguration": admin_save_email_configuration,
    "adminSaveTelegramConfiguration": admin_save_telegram_configuration,
    "adminRetryNotificationDeliveries": admin_retry_notification_deliveries,
    "adminSaveMediaConfig": admin_save_media_config,
    "adminSaveStaff": admin_save_staff,
    "adminSetStaffStatus": admin_set_staff_status,
    "adminCreateStudent": admin_create_student,
    "adminChangeStudentEmail": admin_change_student_email,
    "adminSetStudentStatus": admin_set_student_status,
    "adminResetStudentAccessCode": admin_reset_student_access_code,
    "adminRestoreCredentials": admin_restore_credentials,
    "adminSaveCourse": admin_save_course,
    "adminSaveLesson": admin_save_lesson,
    "adminSaveLessonContent": admin_save_lesson_content,
    "adminSaveGroup": admin_save_group,
    "adminAssignStudentsToGroup": admin_assign_students_to_group,
    "adminSetLessonAccess": admin_set_lesson_access,
    "adminManageLessonProgress": admin_manage_lesson_progress,
}


def dispatch(action: str, payload: dict[str, Any]):
    handler = ACTIONS.get(action)
    if not handler:
        return not_implemented(action)
    return handler(payload)
