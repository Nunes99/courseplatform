import base64
import json
import mimetypes
import urllib.error
import urllib.request
import re
from datetime import datetime, timedelta, timezone
from typing import Any

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
            "A base de dados esta ligada, mas o schema/tabelas da plataforma nao estao completos.",
            {"errorType": error_name},
        )
    if "authentication" in text or "password" in text or "ecircuitbreaker" in text:
        return ApiError(
            "DATABASE_AUTH_ERROR",
            "A API nao conseguiu autenticar no Postgres. Verifique POSTGRES_URL/POSTGRES_PASSWORD no Vercel.",
            {"errorType": error_name},
        )
    return ApiError(
        "DATABASE_UNAVAILABLE",
        "A base de dados nao esta disponivel neste momento.",
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
        "publicStudentId": row.get("public_student_id") or row["student_id"],
        "fullName": row.get("full_name"),
        "email": row.get("email"),
        "status": row.get("status"),
        "country": row.get("country"),
        "organization": row.get("organization"),
        "phone": row.get("phone"),
        "jobTitle": row.get("job_title"),
        "interests": row.get("interests"),
        "profilePhotoUrl": row.get("profile_photo_url"),
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
    return {
        "progressId": row["progress_id"],
        "lessonId": row.get("lesson_id"),
        "status": row.get("status"),
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
            f"Parabens pela conclusao de {course_title}. "
            "A sua participacao foi registada com sucesso."
        ),
        "surveyQuestions": [
            {"id": "quality", "prompt": "Como avalia a qualidade geral do curso?", "options": ["Excelente", "Muito boa", "Boa", "Precisa melhorar"], "required": True},
            {"id": "methodology", "prompt": "A metodologia facilitou a sua aprendizagem?", "options": ["Sim, totalmente", "Sim, em parte", "Pouco", "Nao"], "required": True},
            {"id": "content_relevance", "prompt": "Os conteudos foram relevantes para os seus objetivos?", "options": ["Muito relevantes", "Relevantes", "Pouco relevantes", "Nao relevantes"], "required": True},
            {"id": "materials", "prompt": "Como avalia os materiais disponibilizados?", "options": ["Muito organizados", "Organizados", "Suficientes", "Insuficientes"], "required": True},
            {"id": "practical_activities", "prompt": "As atividades praticas ajudaram a consolidar o conhecimento?", "options": ["Ajudaram muito", "Ajudaram", "Ajudaram pouco", "Nao ajudaram"], "required": True},
            {"id": "difficulty", "prompt": "Como classifica o nivel de dificuldade do curso?", "options": ["Adequado", "Facil", "Exigente, mas positivo", "Muito dificil"], "required": True},
            {"id": "support", "prompt": "Como avalia o apoio recebido durante o curso?", "options": ["Excelente", "Bom", "Regular", "Insuficiente"], "required": True},
            {"id": "platform_experience", "prompt": "Como foi a experiencia de uso da plataforma?", "options": ["Muito intuitiva", "Intuitiva", "Aceitavel", "Confusa"], "required": True},
            {"id": "application", "prompt": "Pretende aplicar os conhecimentos aprendidos?", "options": ["Sim, imediatamente", "Sim, futuramente", "Talvez", "Nao"], "required": True},
            {"id": "recommendation", "prompt": "Recomendaria este curso a outra pessoa?", "options": ["Sim, com certeza", "Sim", "Talvez", "Nao"], "required": True},
        ],
        "professionalPrice": "",
        "paymentInstructions": "Adicione aqui as instrucoes de pagamento do certificado profissional.",
        "professionalPreviewUrl": "",
        "certificateProfile": default_certificate_profile(course),
    }


def default_certificate_profile(course: dict[str, Any] | None = None):
    course_title = (course or {}).get("title") or "Curso profissional"
    contents = "\n".join([
        "Conteudos essenciais do curso",
        "Atividades praticas e estudos de caso",
        "Discussao tecnica e avaliacao final",
    ])
    return {
        "layoutStyle": "qualification",
        "issuerName": "LMTWEBNAIRS",
        "certificateTitle": "Certificado de Qualificacao",
        "qualificationType": "Qualificacao profissional",
        "issueLocation": "Cidade de Maputo, Mocambique",
        "verificationBaseUrl": "",
        "directorName": "Direcao Academica",
        "directorTitle": "Diretor Academico",
        "coordinatorName": "Coordenacao do Programa",
        "coordinatorTitle": "Coordenador do Programa",
        "productCredit": "LMTWEBNAIRS Summer School, produto da LMTWEB, desenvolvido pela LEMOTE.",
        "certifiedContents": contents if not course_title else contents.replace("curso", course_title),
        "printAccess": "paid",
        "printFee": "",
        "printCurrency": "MZN",
        "paymentAccountName": "",
        "paymentAccountNumber": "",
        "paymentInstructions": "Adicione aqui as instrucoes de pagamento do certificado profissional.",
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
        f"Modulo {int(row.get('lesson_number') or 0)}: {row.get('title') or ''}".strip()
        for row in rows
    )


def course_completion_snapshot(conn, student_id: str, course_id: str):
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
          and p.status = 'APPROVED' and coalesce(l.status, 'ACTIVE') = 'ACTIVE'
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
        raise ApiError("SESSION_REQUIRED", "A sessao nao foi informada.")
    token_hash = hash_secret(token)
    session = fetch_one(
        "select * from courseplatform.sessions where session_token = %s",
        (token_hash,),
    )
    if not session or not session.get("active"):
        raise ApiError("INVALID_SESSION", "A sessao e invalida ou foi encerrada.")
    if session["expires_at"] <= utc_now():
        with connection() as conn:
            conn.execute(
                "update courseplatform.sessions set active = false, revoked_at = now() where session_token = %s",
                (token_hash,),
            )
            conn.commit()
        raise ApiError("SESSION_EXPIRED", "A sessao expirou. Inicie sessao novamente.")
    is_admin = str(session["subject_id"]).startswith("ADMIN:")
    if expected_type == "ADMIN" and not is_admin:
        raise ApiError("ADMIN_SESSION_REQUIRED", "E necessaria uma sessao administrativa.")
    if expected_type == "STUDENT" and is_admin:
        raise ApiError("STUDENT_SESSION_REQUIRED", "E necessaria uma sessao de estudante.")
    return session


def validate_session_with_conn(conn, token: str, expected_type: str):
    if not token:
        raise ApiError("SESSION_REQUIRED", "A sessao nao foi informada.")
    token_hash = hash_secret(token)
    session = conn.execute(
        "select * from courseplatform.sessions where session_token = %s",
        (token_hash,),
    ).fetchone()
    if not session or not session.get("active"):
        raise ApiError("INVALID_SESSION", "A sessao e invalida ou foi encerrada.")
    if session["expires_at"] <= utc_now():
        conn.execute(
            "update courseplatform.sessions set active = false, revoked_at = now() where session_token = %s",
            (token_hash,),
        )
        conn.commit()
        raise ApiError("SESSION_EXPIRED", "A sessao expirou. Inicie sessao novamente.")
    is_admin = str(session["subject_id"]).startswith("ADMIN:")
    if expected_type == "ADMIN" and not is_admin:
        raise ApiError("ADMIN_SESSION_REQUIRED", "E necessaria uma sessao administrativa.")
    if expected_type == "STUDENT" and is_admin:
        raise ApiError("STUDENT_SESSION_REQUIRED", "E necessaria uma sessao de estudante.")
    return session


def require_session_token(payload: dict[str, Any], key: str = "sessionToken") -> str:
    token = payload.get(key, "")
    if not token:
        raise ApiError("SESSION_REQUIRED", "A sessao nao foi informada.")
    return token


def student_context_with_conn(conn, payload: dict[str, Any]):
    session = validate_session_with_conn(conn, require_session_token(payload), "STUDENT")
    student = conn.execute(
        "select * from courseplatform.students where student_id = %s",
        (session["subject_id"],),
    ).fetchone()
    if not student or student.get("status") != "ACTIVE":
        raise ApiError("STUDENT_NOT_ACTIVE", "A conta do estudante nao esta ativa.")
    return session, student


def student_context(payload: dict[str, Any]):
    require_session_token(payload)
    with connection() as conn:
        return student_context_with_conn(conn, payload)


def admin_context(payload: dict[str, Any], allowed_roles: set[str] | None = None):
    token = payload.get("adminToken", "")
    if not token:
        raise ApiError("ADMIN_SESSION_REQUIRED", "E necessaria uma sessao administrativa.")
    session = validate_session(token, "ADMIN")
    admin_id = str(session["subject_id"]).replace("ADMIN:", "", 1)
    admin = fetch_one(
        "select * from courseplatform.admins where admin_id = %s",
        (admin_id,),
    )
    if not admin or admin.get("status") != "ACTIVE":
        raise ApiError("ADMIN_NOT_ACTIVE", "A conta administrativa nao esta ativa.")
    if allowed_roles and admin.get("role") not in allowed_roles:
        raise ApiError("FORBIDDEN", "O seu perfil nao possui permissao para esta operacao.")
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
            db_error_hint = "Conexao Postgres ok, mas o schema courseplatform nao foi encontrado e nao foi possivel cria-lo automaticamente."
    except Exception as error:
        db_ok = False
        db_error = error.__class__.__name__
        db_error_message = diagnostic_error_message(error)
        error_text = str(error).lower()
        if "ecircuitbreaker" in error_text:
            db_error_hint = "Supabase pooler bloqueou novas conexoes por muitas falhas de autenticacao. Aguarde alguns minutos e confirme usuario/senha Postgres."
        elif "authentication" in error_text or "password" in error_text:
            db_error_hint = "Falha de autenticacao Postgres. Confira POSTGRES_USER/POSTGRES_PASSWORD ou DATABASE_URL."
        elif "timeout" in error_text or "timed out" in error_text:
            db_error_hint = "Timeout de conexao. Confira host, porta, rede e se o projeto Supabase esta ativo."
        elif db_error == "ProgrammingError":
            db_error_hint = "Erro de SQL/configuracao Postgres. Confirme se o schema courseplatform foi criado no mesmo projeto apontado por POSTGRES_URL."
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
                "A base de dados ligada ainda nao tem estudantes. Confirme se o POSTGRES_URL aponta para a base migrada.",
            )
        raise ApiError("INVALID_CREDENTIALS", "Email ou codigo de acesso invalido.")
    try:
        if not verify_password(payload["accessCode"], student.get("password_hash")):
            raise ApiError("INVALID_CREDENTIALS", "Email ou codigo de acesso invalido.")
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
            "Nao encontramos uma conta ativa com esse email e ID de estudante.",
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
                "A base de dados ligada ainda nao tem administradores. Confirme se o POSTGRES_URL aponta para a base migrada.",
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
            "A recuperacao administrativa ainda nao esta configurada. Defina ADMIN_RECOVERY_KEY_HASH na Vercel.",
        )
    if not verify_admin_recovery_key(payload.get("recoveryKey")):
        raise ApiError("INVALID_ADMIN_RECOVERY_KEY", "Chave de recuperacao administrativa invalida.")

    email = normalize_email(payload["email"])
    try:
        admin = fetch_one("select * from courseplatform.admins where email = %s", (email,))
    except Exception as error:
        raise database_api_error(error) from error
    if not admin or admin.get("status") != "ACTIVE":
        raise ApiError("ADMIN_RECOVERY_NOT_FOUND", "Nao encontramos uma conta administrativa ativa com esse email.")

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
    return success({"student": public_student(student), "courses": student_courses_payload(rows)})


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
        select l.*, p.progress_id, p.status as progress_status, p.score, p.attempt_count,
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
    with connection() as conn:
        return success(dashboard_payload(conn, student, course_id))


def get_lesson(payload: dict[str, Any]):
    _, student = student_context(payload)
    require_fields(payload, ["lessonId"])
    lesson_id = payload["lessonId"]
    lesson = fetch_one("select * from courseplatform.lessons where lesson_id = %s", (lesson_id,))
    if not lesson:
        raise ApiError("LESSON_NOT_FOUND", "Modulo nao encontrado.")
    progress = fetch_one(
        """
        select *
        from courseplatform.lesson_progress
        where student_id = %s and lesson_id = %s
        """,
        (student["student_id"], lesson_id),
    )
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
    attempt = fetch_one(
        """
        select *
        from courseplatform.attempts
        where attempt_id = %s and student_id = %s
        """,
        (payload["attemptId"], student["student_id"]),
    )
    if not attempt:
        raise ApiError("ATTEMPT_NOT_FOUND", "Tentativa nao encontrada.")
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


def update_my_profile(payload: dict[str, Any]):
    _, student = student_context(payload)
    photo_url = str_value(payload.get("profilePhotoUrl") or student.get("profile_photo_url"))
    if str_value(payload.get("profilePhotoBase64")):
        mime_type = str_value(payload.get("profilePhotoMimeType") or "image/jpeg") or "image/jpeg"
        base64_data = str_value(payload.get("profilePhotoBase64"))
        photo_url = f"data:{mime_type};base64,{base64_data}"
    if as_bool(payload.get("removeProfilePhoto")):
        photo_url = ""

    patch = {
        "full_name": str_value(payload.get("fullName") or student.get("full_name")),
        "country": str_value(payload.get("country")),
        "organization": str_value(payload.get("organization")),
        "phone": str_value(payload.get("phone")),
        "job_title": str_value(payload.get("jobTitle")),
        "interests": str_value(payload.get("interests")),
        "profile_photo_url": photo_url,
    }
    with connection() as conn:
        row = conn.execute(
            """
            update courseplatform.students
            set full_name = %s, country = %s, organization = %s, phone = %s,
                job_title = %s, interests = %s, profile_photo_url = %s, updated_at = now()
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
                student["student_id"],
            ),
        ).fetchone()
        audit(conn, "STUDENT", student["student_id"], "PROFILE_UPDATED", "STUDENT", student["student_id"])
        conn.commit()
    return success({"student": public_student(row)})


def change_my_access_code(payload: dict[str, Any]):
    _, student = student_context(payload)
    require_fields(payload, ["currentAccessCode", "newAccessCode"])
    if not verify_password(payload["currentAccessCode"], student.get("password_hash")):
        raise ApiError("INVALID_CURRENT_ACCESS_CODE", "A senha atual nao esta correta.")
    new_code = str_value(payload.get("newAccessCode"))
    if not valid_password(new_code):
        raise ApiError("WEAK_ACCESS_CODE", "A nova senha deve ter pelo menos 8 caracteres.")
    if verify_password(new_code, student.get("password_hash")):
        raise ApiError("ACCESS_CODE_UNCHANGED", "A nova senha deve ser diferente da atual.")
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


def start_attempt(payload: dict[str, Any]):
    _, student = student_context(payload)
    require_fields(payload, ["lessonId"])
    lesson_id = payload["lessonId"]
    progress = fetch_one(
        """
        select p.*, l.exercise_minutes, l.individual_minutes
        from courseplatform.lesson_progress p
        join courseplatform.lessons l on l.lesson_id = p.lesson_id
        where p.student_id = %s and p.lesson_id = %s
        """,
        (student["student_id"], lesson_id),
    )
    if not progress:
        raise ApiError("LESSON_LOCKED", "Este modulo ainda nao esta disponivel.")
    if progress.get("status") not in {"AVAILABLE", "IN_PROGRESS", "CORRECTION_REQUIRED", "FAILED", "TIME_EXCEEDED"}:
        raise ApiError("ATTEMPT_NOT_AVAILABLE", "Nao e possivel iniciar uma tentativa neste estado.")

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
        return success({"attempt": public_attempt(existing)})

    now = utc_now()
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
            set status = 'IN_PROGRESS', started_at = coalesce(started_at, %s),
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
    attempt = fetch_one(
        "select * from courseplatform.attempts where attempt_id = %s and student_id = %s",
        (payload["attemptId"], student["student_id"]),
    )
    if not attempt or attempt.get("status") != "IN_PROGRESS":
        raise ApiError("ATTEMPT_NOT_EDITABLE", "Esta tentativa ja nao pode ser editada.")
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
        snapshot = cert.get("template_snapshot_json") if cert else None
        if cert and not snapshot:
            snapshot = certificate_template_snapshot(conn, cert.get("course_id"), cert.get("certificate_type"))
        conn.commit()
    return success({"answer": public_answer(answer)})


def upload_file(payload: dict[str, Any]):
    _, student = student_context(payload)
    require_fields(payload, ["attemptId", "fileName"])
    attempt = fetch_one(
        "select * from courseplatform.attempts where attempt_id = %s and student_id = %s",
        (payload["attemptId"], student["student_id"]),
    )
    if not attempt or attempt.get("status") != "IN_PROGRESS":
        raise ApiError("ATTEMPT_NOT_EDITABLE", "Esta tentativa ja nao pode receber ficheiros.")
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
        raise ApiError("FILE_NOT_FOUND", "Ficheiro nao encontrado.")
    return success({"file": public_file(row)})


def submit_attempt(payload: dict[str, Any]):
    _, student = student_context(payload)
    require_fields(payload, ["attemptId"])
    attempt = fetch_one(
        "select * from courseplatform.attempts where attempt_id = %s and student_id = %s",
        (payload["attemptId"], student["student_id"]),
    )
    if not attempt or attempt.get("status") != "IN_PROGRESS":
        raise ApiError("ATTEMPT_NOT_SUBMITTABLE", "Esta tentativa nao pode ser submetida.")
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
            set status = %s, submitted_at = %s, updated_at = %s
            where progress_id = %s
            """,
            (status, now, now, attempt.get("progress_id")),
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
                set survey_answers_json = %s, updated_at = now()
                where request_id = %s
                returning *
                """,
                (json.dumps(survey_answers), existing["request_id"]),
            ).fetchone()
        else:
            request = conn.execute(
                """
                insert into courseplatform.certificate_requests
                  (request_id, student_id, course_id, request_type, status,
                   survey_answers_json, created_at, updated_at)
                values (%s, %s, %s, 'PROFESSIONAL', 'REQUESTED', %s, now(), now())
                returning *
                """,
                (generate_id("CREQ"), student["student_id"], course_id, json.dumps(survey_answers)),
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
        raise ApiError("CERTIFICATE_REQUEST_NOT_FOUND", "Pedido de certificado nao encontrado.")
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
            raise ApiError("CERTIFICATE_NOT_FOUND", "Certificado nao encontrado.")
        if cert.get("status") != "ISSUED":
            raise ApiError("CERTIFICATE_ACCESS_BLOCKED", "O acesso a este certificado nao esta disponivel.")
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
            raise ApiError("CERTIFICATE_NOT_FOUND", "Certificado nao encontrado.")
        if cert.get("status") != "ISSUED":
            raise ApiError("CERTIFICATE_ACCESS_BLOCKED", "O acesso a este certificado nao esta disponivel.")
        max_downloads = cert.get("max_downloads")
        download_count = int(cert.get("download_count") or 0)
        if max_downloads is not None and download_count >= int(max_downloads):
            raise ApiError("DOWNLOAD_LIMIT_REACHED", "O limite de downloads deste certificado foi atingido.")
        snapshot = cert.get("template_snapshot_json") or certificate_template_snapshot(conn, cert.get("course_id"), cert.get("certificate_type"))
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
        conn.commit()
    if not cert:
        raise ApiError("CERTIFICATE_NOT_FOUND", "Certificado nao encontrado.")
    if cert.get("status") == "DELETED":
        raise ApiError("CERTIFICATE_NOT_FOUND", "Certificado nao encontrado.")
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
        raise ApiError("COURSE_NOT_FOUND", "Curso nao encontrado.")
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
    rows = fetch_all(
        """
        select s.*,
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
        ((payload.get("status") or "ALL").upper(), (payload.get("status") or "ALL").upper(), payload.get("query") or "", f"%{(payload.get('query') or '').lower()}%", int(payload.get("limit") or 500)),
    )
    return success({"students": [{"student": public_student(row), "enrollments": [public_enrollment(item) for item in row.get("enrollments", [])], "memberships": [public_group_member(item) for item in row.get("memberships", [])]} for row in rows]})


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
        "full_name": row.get("full_name") or row.get("attempt_student_id") or "Estudante sem cadastro",
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
        "title": row.get("title") or row.get("attempt_lesson_id") or "Modulo sem titulo",
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
        "attempt": public_attempt(row),
        "latestReview": public_review(review),
        "fileCount": int(row.get("file_count") or 0),
    }


def admin_list_submissions(payload: dict[str, Any]):
    admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
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
          lr.review_id, lr.reviewer_id, lr.decision, lr.score as review_score,
          lr.comments, lr.correction_deadline, lr.unlock_next_lesson, lr.reviewed_at as review_reviewed_at,
          coalesce(fc.file_count, 0) as file_count
        from courseplatform.attempts a
        left join courseplatform.students s on s.student_id = a.student_id
        left join courseplatform.lessons l on l.lesson_id = a.lesson_id
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
    attempt = fetch_one("select * from courseplatform.attempts where attempt_id = %s", (payload["attemptId"],))
    if not attempt:
        raise ApiError("ATTEMPT_NOT_FOUND", "Submissao nao encontrada.")
    student = fetch_one("select * from courseplatform.students where student_id = %s", (attempt["student_id"],))
    lesson = fetch_one("select * from courseplatform.lessons where lesson_id = %s", (attempt["lesson_id"],))
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
        "student": public_student(student or {"student_id": attempt["student_id"], "full_name": attempt["student_id"], "email": "", "status": "UNKNOWN"}),
        "lesson": public_lesson(lesson or {"lesson_id": attempt["lesson_id"], "title": attempt["lesson_id"]}),
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
    decision = str_value(payload.get("decision")).upper()
    if decision not in {"APPROVED", "APPROVED_WITH_NOTES", "CORRECTION_REQUIRED", "FAILED"}:
        raise ApiError("INVALID_DECISION", "Decisao invalida.")
    status = "APPROVED" if decision in {"APPROVED", "APPROVED_WITH_NOTES"} else decision
    score = float_value(payload.get("score"))
    now = utc_now()
    attempt = fetch_one("select * from courseplatform.attempts where attempt_id = %s", (payload["attemptId"],))
    if not attempt:
        raise ApiError("ATTEMPT_NOT_FOUND", "Tentativa nao encontrada.")
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
            set status = %s, approved_at = case when %s = 'APPROVED' then %s else approved_at end,
                score = %s, updated_at = %s
            where progress_id = %s
            """,
            (status, status, now, score, now, attempt.get("progress_id")),
        )
        audit(conn, "ADMIN", admin["admin_id"], "SUBMISSION_REVIEWED", "ATTEMPT", attempt["attempt_id"], {"decision": decision, "score": score})
        conn.commit()
    return success({"attempt": public_attempt(updated), "review": public_review(review)})


def admin_authorize_retry(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    require_fields(payload, ["attemptId"])
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
            raise ApiError("ATTEMPT_NOT_FOUND", "Tentativa nao encontrada.")
        conn.execute(
            "update courseplatform.lesson_progress set status = 'AVAILABLE', updated_at = now() where progress_id = %s",
            (attempt.get("progress_id"),),
        )
        audit(conn, "ADMIN", admin["admin_id"], "RETRY_AUTHORIZED", "ATTEMPT", attempt["attempt_id"])
        conn.commit()
    return success({"attempt": public_attempt(attempt)})


def admin_save_media_config(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    media = payload.get("mediaConfig") or {"logoUrl": payload.get("logoUrl"), "videos": payload.get("videos", [])}
    if not isinstance(media, dict):
        raise ApiError("INVALID_MEDIA_CONFIG", "Configuracao de media invalida.")
    media.setdefault("logoUrl", "")
    media.setdefault("videos", [])
    with connection() as conn:
        conn.execute(
            """
            insert into courseplatform.settings (key, value, value_type, description, updated_at)
            values ('MEDIA_CONFIG', %s, 'JSON', 'Logotipo e galeria de videos da plataforma.', now())
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
        raise ApiError("WEAK_PASSWORD", "A senha deve ter pelo menos 8 caracteres.")
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
            raise ApiError("ADMIN_NOT_FOUND", "Staff nao encontrado.")
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


def admin_set_student_status(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["studentId", "status"])
    with connection() as conn:
        row = conn.execute(
            "update courseplatform.students set status = %s, updated_at = now() where student_id = %s returning *",
            (str_value(payload["status"]).upper(), payload["studentId"]),
        ).fetchone()
        if not row:
            raise ApiError("STUDENT_NOT_FOUND", "Estudante nao encontrado.")
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
            raise ApiError("STUDENT_NOT_FOUND", "Estudante nao encontrado.")
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
        "publicId": row.get("public_student_id") or row.get("student_id"),
        "fullName": row.get("full_name"),
        "email": row.get("email"),
        "status": row.get("status"),
        "temporaryPassword": temporary_password,
    }


def admin_restore_credentials(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    target_type = str_value(payload.get("targetType") or "STUDENTS").upper()
    if target_type not in {"STUDENTS", "ADMINS", "ALL"}:
        raise ApiError("INVALID_TARGET", "Tipo de conta invalido para restauracao de credenciais.")
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
    lesson_id = str_value(payload.get("lessonId")) or generate_id("LESSON")
    status = str_value(payload.get("status") or "ACTIVE").upper()
    with connection() as conn:
        row = conn.execute(
            """
            insert into courseplatform.lessons
              (lesson_id, course_id, lesson_number, title, slug, summary, theory_minutes,
               exercise_minutes, individual_minutes, passing_score, prerequisite_lesson_id,
               status, created_at, updated_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
            on conflict (lesson_id) do update
            set course_id = excluded.course_id, lesson_number = excluded.lesson_number,
                title = excluded.title, slug = excluded.slug, summary = excluded.summary,
                theory_minutes = excluded.theory_minutes, exercise_minutes = excluded.exercise_minutes,
                individual_minutes = excluded.individual_minutes, passing_score = excluded.passing_score,
                prerequisite_lesson_id = excluded.prerequisite_lesson_id, status = excluded.status,
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
    status = str_value(payload.get("status") or "AVAILABLE").upper()
    if status not in {"AVAILABLE", "LOCKED", "IN_PROGRESS", "UNDER_REVIEW", "APPROVED", "TIME_EXCEEDED"}:
        raise ApiError("INVALID_STATUS", "Estado de acesso invalido.")
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
        raise ApiError("EMPTY_ACCESS_TARGET", "Selecione modulos e estudantes.")
    updated = 0
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
                conn.execute(
                    """
                    insert into courseplatform.lesson_progress
                      (progress_id, enrollment_id, student_id, lesson_id, status, unlocked_at, attempt_count, updated_at)
                    values (%s, %s, %s, %s, %s, case when %s <> 'LOCKED' then now() else null end, 0, now())
                    on conflict (enrollment_id, lesson_id) do update
                    set status = excluded.status,
                        unlocked_at = case when excluded.status <> 'LOCKED' then coalesce(courseplatform.lesson_progress.unlocked_at, now()) else courseplatform.lesson_progress.unlocked_at end,
                        updated_at = now()
                    """,
                    (generate_id("PRG"), enrollment["enrollment_id"], student_id, lesson_id, status, status),
                )
                updated += 1
        audit(conn, "ADMIN", admin["admin_id"], "LESSON_ACCESS_CHANGED", "LESSON_PROGRESS", "", {"lessonCount": len(lesson_ids), "studentCount": len(student_ids), "status": status})
        conn.commit()
    return success({"studentCount": len(student_ids), "lessonCount": len(lesson_ids), "updatedCount": updated})


def admin_student_details(payload: dict[str, Any]):
    admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    require_fields(payload, ["studentId"])
    student_id = payload["studentId"]
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        student = conn.execute("select * from courseplatform.students where student_id = %s", (student_id,)).fetchone()
        if not student:
            raise ApiError("STUDENT_NOT_FOUND", "Estudante nao encontrado.")
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
        raise ApiError("INVALID_CERTIFICATE_STATUS", "Estado de certificado invalido.")
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
            raise ApiError("CERTIFICATE_NOT_FOUND", "Certificado nao encontrado.")
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
            raise ApiError("CERTIFICATE_NOT_FOUND", "Certificado nao encontrado.")

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
                    "Formato e conteudo do certificado atualizados pelo administrador.",
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
            raise ApiError("CERTIFICATE_NOT_FOUND", "Certificado nao encontrado.")
        audit(conn, "ADMIN", admin["admin_id"], "CERTIFICATE_DELETED", "CERTIFICATE", certificate["certificate_id"], {})
        conn.commit()
    return success({"certificate": public_certificate(certificate)})


def admin_review_certificate_request(payload: dict[str, Any]):
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["requestId", "decision"])
    decision = str_value(payload.get("decision")).upper()
    if decision not in {"APPROVED", "REJECTED"}:
        raise ApiError("INVALID_DECISION", "Decisao invalida.")
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        request = conn.execute(
            "select * from courseplatform.certificate_requests where request_id = %s",
            (payload["requestId"],),
        ).fetchone()
        if not request:
            raise ApiError("CERTIFICATE_REQUEST_NOT_FOUND", "Pedido de certificado nao encontrado.")
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
            raise ApiError("COURSE_NOT_FOUND", "Curso nao encontrado.")
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
        raise ApiError("INVALID_ASSET_KEY", "Tipo de elemento grafico invalido.")
    mime_type = str_value(payload.get("mimeType"))
    if mime_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise ApiError("INVALID_FILE_TYPE", "Use PNG, JPEG ou WebP.")
    data_url = str_value(payload.get("dataUrl"))
    marker = ";base64,"
    if marker not in data_url:
        raise ApiError("INVALID_FILE_DATA", "Ficheiro invalido.")
    encoded = data_url.split(marker, 1)[1]
    try:
        file_bytes = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ApiError("INVALID_FILE_DATA", "Ficheiro invalido.") from exc
    if len(file_bytes) > 3 * 1024 * 1024:
        raise ApiError("FILE_TOO_LARGE", "O ficheiro deve ter ate 3 MB.")

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


def not_implemented(action: str):
    raise ApiError("NOT_IMPLEMENTED", f"A acao {action} ainda nao foi portada para a API Python.")


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
    "getLesson": get_lesson,
    "getAttemptStatus": attempt_status,
    "updateMyProfile": update_my_profile,
    "changeMyAccessCode": change_my_access_code,
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
    "adminListCertificateRequests": admin_list_certificate_requests,
    "adminListCertificates": admin_list_certificates,
    "adminSetCertificateStatus": admin_set_certificate_status,
    "adminRefreshCertificateFormat": admin_refresh_certificate_format,
    "adminDeleteCertificate": admin_delete_certificate,
    "adminReviewCertificateRequest": admin_review_certificate_request,
    "adminGetCertificateSettings": admin_get_certificate_settings,
    "adminSaveCertificateSettings": admin_save_certificate_settings,
    "adminListCertificateSurveys": admin_list_certificate_surveys,
    "adminSaveCertificateSurvey": admin_save_certificate_survey,
    "adminUploadCertificateAsset": admin_upload_certificate_asset,
    "adminSaveMediaConfig": admin_save_media_config,
    "adminSaveStaff": admin_save_staff,
    "adminSetStaffStatus": admin_set_staff_status,
    "adminCreateStudent": admin_create_student,
    "adminSetStudentStatus": admin_set_student_status,
    "adminResetStudentAccessCode": admin_reset_student_access_code,
    "adminRestoreCredentials": admin_restore_credentials,
    "adminSaveCourse": admin_save_course,
    "adminSaveLesson": admin_save_lesson,
    "adminSaveLessonContent": admin_save_lesson_content,
    "adminSaveGroup": admin_save_group,
    "adminAssignStudentsToGroup": admin_assign_students_to_group,
    "adminSetLessonAccess": admin_set_lesson_access,
}


def dispatch(action: str, payload: dict[str, Any]):
    handler = ACTIONS.get(action)
    if not handler:
        return not_implemented(action)
    return handler(payload)
