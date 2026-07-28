import json
from datetime import datetime, timezone
from typing import Any

from .config import get_settings
from .db import connection, fetch_all, fetch_one
from .security import (
    constant_time_equals,
    generate_id,
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


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"true", "1", "yes", "sim"}


def iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


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
    db_ok = False
    try:
        row = fetch_one("select 1 as ok")
        db_ok = bool(row and row["ok"] == 1)
    except Exception:
        db_ok = False
    return success({"version": get_settings().app_version, "database": db_ok})


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


def public_media_config(payload: dict[str, Any]):
    media = read_media_config(payload.get("courseId") or get_settings().default_course_id)
    videos = [
        video
        for video in media.get("videos", [])
        if video.get("status", "ACTIVE") == "ACTIVE" and video.get("visibility") != "SELECTED"
    ]
    return success({"mediaConfig": {**media, "videos": videos}})


def login(payload: dict[str, Any]):
    require_fields(payload, ["email", "accessCode"])
    email = normalize_email(payload["email"])
    student = fetch_one("select * from courseplatform.students where email = %s", (email,))
    if not student or student.get("status") != "ACTIVE":
        raise ApiError("INVALID_CREDENTIALS", "Email ou codigo de acesso invalido.")
    if not constant_time_equals(hash_secret(payload["accessCode"]), student["access_code"]):
        raise ApiError("INVALID_CREDENTIALS", "Email ou codigo de acesso invalido.")
    with connection() as conn:
        revoke_sessions(conn, student["student_id"])
        session = create_session(conn, student["student_id"], payload.get("userAgent", ""), payload.get("ipHash", ""))
        conn.execute(
            "update courseplatform.students set last_login_at = now(), updated_at = now() where student_id = %s",
            (student["student_id"],),
        )
        conn.commit()
    return success({"sessionToken": session["token"], "expiresAt": iso(session["expiresAt"]), "student": public_student(student)})


def admin_login(payload: dict[str, Any]):
    require_fields(payload, ["email", "adminKey"])
    email = normalize_email(payload["email"])
    admin = fetch_one("select * from courseplatform.admins where email = %s", (email,))
    if not admin or admin.get("status") != "ACTIVE":
        raise ApiError("INVALID_ADMIN_CREDENTIALS", "Credenciais administrativas invalidas.")
    expected = get_settings().admin_master_key_hash
    if not expected or not constant_time_equals(hash_secret(payload["adminKey"]), expected):
        raise ApiError("INVALID_ADMIN_CREDENTIALS", "Credenciais administrativas invalidas.")
    subject_id = f"ADMIN:{admin['admin_id']}"
    with connection() as conn:
        revoke_sessions(conn, subject_id)
        session = create_session(conn, subject_id, payload.get("userAgent", ""), payload.get("ipHash", ""))
        conn.commit()
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
               p.unlocked_at, p.started_at, p.submitted_at, p.approved_at
        from courseplatform.lessons l
        left join courseplatform.lesson_progress p
          on p.lesson_id = l.lesson_id and p.student_id = %s
        where l.course_id = %s and l.status = 'ACTIVE'
        order by l.lesson_number
        """,
        (student["student_id"], course_id),
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
            }
            for row in lessons
        ],
    })


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
    "verifyCertificate": verify_certificate,
    "login": login,
    "logout": logout,
    "adminLogin": admin_login,
    "adminLogout": logout,
    "adminMe": admin_me,
    "getDashboard": dashboard,
    "getMyCourses": my_courses,
    "adminListCourses": admin_list_courses,
    "adminGetCourseStructure": admin_course_structure,
    "adminListGroups": admin_list_groups,
    "adminListStudents": admin_list_students,
}


def dispatch(action: str, payload: dict[str, Any]):
    handler = ACTIONS.get(action)
    if not handler:
        return not_implemented(action)
    return handler(payload)
