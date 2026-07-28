import json
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import get_settings
from .db import connection, ensure_schema, fetch_all, fetch_one, schema_exists
from .security import (
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


def student_context(payload: dict[str, Any]):
    session = validate_session(payload.get("sessionToken", ""), "STUDENT")
    student = fetch_one(
        "select * from courseplatform.students where student_id = %s",
        (session["subject_id"],),
    )
    if not student or student.get("status") != "ACTIVE":
        raise ApiError("STUDENT_NOT_ACTIVE", "A conta do estudante nao esta ativa.")
    return session, student


def admin_context(payload: dict[str, Any], allowed_roles: set[str] | None = None):
    session = validate_session(payload.get("adminToken", ""), "ADMIN")
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
        error_text = str(error).lower()
        if "ecircuitbreaker" in error_text:
            db_error_hint = "Supabase pooler bloqueou novas conexoes por muitas falhas de autenticacao. Aguarde alguns minutos e confirme usuario/senha Postgres."
        elif "authentication" in error_text or "password" in error_text:
            db_error_hint = "Falha de autenticacao Postgres. Confira POSTGRES_USER/POSTGRES_PASSWORD ou DATABASE_URL."
        elif "timeout" in error_text or "timed out" in error_text:
            db_error_hint = "Timeout de conexao. Confira host, porta, rede e se o projeto Supabase esta ativo."
        elif db_error == "ProgrammingError":
            db_error_hint = "Erro de SQL/configuracao Postgres. Confirme se o schema courseplatform foi criado no mesmo projeto apontado por POSTGRES_URL."
    return success({
        "version": settings.app_version,
        "database": db_ok,
        "databaseConfigured": bool(settings.database_url),
        "databaseError": "" if db_ok else db_error,
        "databaseErrorHint": "" if db_ok else db_error_hint,
        "schemaCreated": schema_created,
        "dataDiagnostics": data_diagnostics,
        "authConfigured": db_ok
        and data_diagnostics["studentsWithPassword"] > 0
        and data_diagnostics["adminsWithPassword"] > 0,
        "authDiagnostics": {
            "mode": "supabase_postgres_bcrypt",
            "requiresPasswordPepper": False,
            "requiresAdminMasterKeyHash": False,
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


def student_media_config(payload: dict[str, Any]):
    _, student = student_context(payload)
    media = read_media_config(payload.get("courseId") or get_settings().default_course_id)
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
    return success({"mediaConfig": {**media, "videos": videos}})


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
    _, student = student_context(payload)
    rows = fetch_all(
        """
        select e.*, c.*, g.name as group_name, g.start_date, g.end_date
        from courseplatform.enrollments e
        join courseplatform.courses c on c.course_id = e.course_id
        left join courseplatform.groups g on g.group_id = e.group_id
        where e.student_id = %s and c.status <> 'DELETED'
        order by c.title
        """,
        (student["student_id"],),
    )
    return success({"courses": [{"course": public_course(row), "enrollment": public_enrollment(row), "group": {"name": row.get("group_name"), "startDate": iso(row.get("start_date")), "endDate": iso(row.get("end_date"))} if row.get("group_name") else None} for row in rows]})


def dashboard(payload: dict[str, Any]):
    _, student = student_context(payload)
    course_id = payload.get("courseId") or get_settings().default_course_id
    enrollment = fetch_one(
        "select * from courseplatform.enrollments where student_id = %s and course_id = %s",
        (student["student_id"], course_id),
    )
    course = fetch_one("select * from courseplatform.courses where course_id = %s", (course_id,))
    lessons = fetch_all(
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
    )
    return success({
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
    })


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
    cert = fetch_one(
        """
        select cert.*, c.title
        from courseplatform.certificates cert
        left join courseplatform.courses c on c.course_id = cert.course_id
        where cert.student_id = %s and cert.course_id = %s
        order by cert.issue_date desc nulls last
        limit 1
        """,
        (student["student_id"], course_id),
    )
    return success({"certificate": {
        "certificateId": cert.get("certificate_id"),
        "certificateNumber": cert.get("certificate_number"),
        "verificationCode": cert.get("verification_code"),
        "issueDate": iso(cert.get("issue_date")),
        "finalScore": None if cert.get("final_score") is None else float(cert.get("final_score")),
        "driveUrl": cert.get("drive_url"),
        "status": cert.get("status"),
        "courseTitle": cert.get("title"),
    } if cert else None})


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
    answers = fetch_all(
        """
        select q.*, a.*
        from courseplatform.answers a
        left join courseplatform.questions q on q.question_id = a.question_id
        where a.attempt_id = %s
        order by q.question_order nulls last, a.saved_at
        """,
        (attempt["attempt_id"],),
    )
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
                "question": public_question(row) if row.get("question_id") else None,
                "answer": public_answer(row),
            }
            for row in answers
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
    "logout": logout,
    "adminLogin": admin_login,
    "adminLogout": logout,
    "adminMe": admin_me,
    "adminGetMediaConfig": admin_media_config,
    "adminListStaff": admin_list_staff,
    "adminListSubmissions": admin_list_submissions,
    "adminListPendingSubmissions": admin_list_submissions,
    "getDashboard": dashboard,
    "getMyCourses": my_courses,
    "getLesson": get_lesson,
    "getAttemptStatus": attempt_status,
    "updateMyProfile": update_my_profile,
    "changeMyAccessCode": change_my_access_code,
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
    "adminGetSubmission": admin_get_submission,
    "adminReviewSubmission": admin_review_submission,
    "adminAuthorizeRetry": admin_authorize_retry,
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
