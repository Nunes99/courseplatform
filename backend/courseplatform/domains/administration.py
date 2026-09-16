import base64
import mimetypes
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from ..contracts import ApiError


ACTION_BINDINGS = (
    ("health", "health"),
    ("healthDiagnostics", "health_diagnostics"),
    ("adminGetPlatformStatistics", "admin_platform_statistics"),
    ("adminListStaff", "admin_list_staff"),
    ("adminListStudents", "admin_list_students"),
    ("adminGetStudentDetails", "admin_student_details"),
    ("adminUploadBrandLogo", "admin_upload_brand_logo"),
    ("adminSaveStaff", "admin_save_staff"),
    ("adminSetStaffStatus", "admin_set_staff_status"),
    ("adminCreateStudent", "admin_create_student"),
    ("adminChangeStudentEmail", "admin_change_student_email"),
    ("adminSetStudentStatus", "admin_set_student_status"),
    ("adminResetStudentAccessCode", "admin_reset_student_access_code"),
    ("adminRestoreCredentials", "admin_restore_credentials"),
)


@dataclass(frozen=True)
class AdministrationRuntime:
    BRAND_LOGO_MAX_BYTES: Any
    EXPECTED_SCHEMA_VERSION: Any
    RASTER_IMAGE_MIME_TYPES: Any
    admin_context: Any
    as_bool: Any
    audit: Any
    certificate_token: Any
    configured_admin_recovery_hashes: Any
    connection: Any
    credential_restore_item: Any
    cursor_page_limit: Any
    cursor_pagination_result: Any
    cursor_scope: Any
    database_api_error: Any
    decode_list_cursor: Any
    decode_raster_data_url: Any
    ensure_certificate_feature_schema: Any
    fetch_all: Any
    fetch_one: Any
    generate_access_code: Any
    generate_id: Any
    get_settings: Any
    iso: Any
    normalize_email: Any
    persist_media_config: Any
    prepare_assessment_feature_schema: Any
    prepare_chat_feature_schema: Any
    prepare_notification_feature_schema: Any
    public_admin: Any
    public_certificate: Any
    public_certificate_request: Any
    public_enrollment: Any
    public_group_member: Any
    public_progress: Any
    public_student: Any
    public_student_id: Any
    raster_signature_matches: Any
    read_media_config: Any
    require_fields: Any
    schema_status: Any
    secure_student_email_update: Any
    serialize_admin: Any
    staff_attempt: Any
    storage_service_headers: Any
    str_value: Any
    success: Any
    upload_raster_asset_to_storage: Any
    utc_now: Any
    valid_password: Any
    validated_email_change: Any
    verify_password_with_conn: Any


def public_admin_action(row: dict[str, Any] | None, *, runtime: AdministrationRuntime):
    iso = runtime.iso
    serialize_admin = runtime.serialize_admin
    return serialize_admin(row, as_iso=iso)


def health_action(_: dict[str, Any], *, runtime: AdministrationRuntime):
    """Compatibility action for the public readiness check."""
    schema_status = runtime.schema_status
    success = runtime.success
    try:
        status = schema_status()
    except Exception:
        return success({"status": "not_ready"})
    return success({"status": "ready" if status["compatible"] else "not_ready"})


def health_diagnostics_action(payload: dict[str, Any], *, runtime: AdministrationRuntime):
    """Return operational detail only to active owners and administrators."""
    EXPECTED_SCHEMA_VERSION = runtime.EXPECTED_SCHEMA_VERSION
    admin_context = runtime.admin_context
    configured_admin_recovery_hashes = runtime.configured_admin_recovery_hashes
    fetch_one = runtime.fetch_one
    schema_status = runtime.schema_status
    success = runtime.success
    admin_context(payload, {"OWNER", "ADMIN"})
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
        status = schema_status()
        if status["compatible"]:
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
            ) or {}
            data_diagnostics = {
                "students": int(data_row.get("students") or 0),
                "studentsWithPassword": int(data_row.get("students_with_password") or 0),
                "admins": int(data_row.get("admins") or 0),
                "adminsWithPassword": int(data_row.get("admins_with_password") or 0),
                "courses": int(data_row.get("courses") or 0),
                "lessons": int(data_row.get("lessons") or 0),
                "dataReady": bool((data_row.get("students") or 0) and (data_row.get("admins") or 0)),
            }
        dependency_error = ""
    except Exception as error:
        status = {
            "compatible": False,
            "installedVersion": None,
            "expectedVersion": EXPECTED_SCHEMA_VERSION,
            "reason": "DATABASE_UNAVAILABLE",
        }
        dependency_error = error.__class__.__name__

    return success({
        "status": "ready" if status["compatible"] else "not_ready",
        "schema": status,
        "dependencyError": dependency_error,
        "data": data_diagnostics,
        "authentication": {
            "mode": "supabase_postgres_bcrypt",
            "configured": status["compatible"]
            and data_diagnostics["studentsWithPassword"] > 0
            and data_diagnostics["adminsWithPassword"] > 0,
            "adminRecoveryConfigured": bool(configured_admin_recovery_hashes()),
        },
    })


def decode_raster_data_url_action(data_url: Any, mime_type: Any, max_bytes: int, *, runtime: AdministrationRuntime) -> tuple[str, str, bytes]:
    RASTER_IMAGE_MIME_TYPES = runtime.RASTER_IMAGE_MIME_TYPES
    raster_signature_matches = runtime.raster_signature_matches
    str_value = runtime.str_value
    normalized_mime = str_value(mime_type).lower()
    if normalized_mime not in RASTER_IMAGE_MIME_TYPES:
        raise ApiError("INVALID_FILE_TYPE", "Use PNG, JPEG ou WebP.")

    normalized_data_url = str_value(data_url)
    prefix = f"data:{normalized_mime};base64,"
    if not normalized_data_url.startswith(prefix):
        raise ApiError("INVALID_FILE_DATA", "O conteúdo da imagem não corresponde ao formato indicado.")

    encoded = normalized_data_url[len(prefix):]
    if not encoded or len(encoded) > ((max_bytes + 2) // 3) * 4 + 8:
        raise ApiError("FILE_TOO_LARGE", f"O ficheiro deve ter até {max_bytes // (1024 * 1024)} MB.")
    try:
        file_bytes = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ApiError("INVALID_FILE_DATA", "O ficheiro de imagem é inválido.") from exc
    if not file_bytes:
        raise ApiError("INVALID_FILE_DATA", "O ficheiro de imagem está vazio.")
    if len(file_bytes) > max_bytes:
        raise ApiError("FILE_TOO_LARGE", f"O ficheiro deve ter até {max_bytes // (1024 * 1024)} MB.")
    if not raster_signature_matches(normalized_mime, file_bytes):
        raise ApiError("INVALID_FILE_DATA", "A assinatura do ficheiro não corresponde a PNG, JPEG ou WebP.")

    canonical_data = base64.b64encode(file_bytes).decode("ascii")
    return normalized_mime, f"data:{normalized_mime};base64,{canonical_data}", file_bytes


def raster_signature_matches_action(mime_type: str, file_bytes: bytes, *, runtime: AdministrationRuntime) -> bool:
    if mime_type == "image/png":
        return file_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    if mime_type == "image/jpeg":
        return file_bytes.startswith(b"\xff\xd8\xff")
    if mime_type == "image/webp":
        return len(file_bytes) >= 12 and file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP"
    return False


def normalize_brand_logo_url_action(value: Any, *, runtime: AdministrationRuntime) -> str:
    BRAND_LOGO_MAX_BYTES = runtime.BRAND_LOGO_MAX_BYTES
    decode_raster_data_url = runtime.decode_raster_data_url
    str_value = runtime.str_value
    logo_url = str_value(value)
    if not logo_url:
        return ""
    if logo_url.startswith("data:image/"):
        match = re.match(r"^data:(image/(?:png|jpeg|webp));base64,", logo_url, flags=re.IGNORECASE)
        if not match:
            raise ApiError("INVALID_BRAND_LOGO", "O logotipo guardado possui um formato inválido.")
        _, normalized_data_url, _ = decode_raster_data_url(logo_url, match.group(1), BRAND_LOGO_MAX_BYTES)
        return normalized_data_url

    parsed = urlsplit(logo_url)
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        return logo_url
    raise ApiError("INVALID_BRAND_LOGO", "O logotipo deve ser um ficheiro carregado ou um link HTTPS legado válido.")


def upload_raster_asset_to_storage_action(file_bytes: bytes, mime_type: str, object_path: str, *, runtime: AdministrationRuntime) -> tuple[bool, str]:
    get_settings = runtime.get_settings
    storage_service_headers = runtime.storage_service_headers
    settings = get_settings()
    service_headers = storage_service_headers(settings)
    if not settings.supabase_url or not service_headers:
        return False, ""
    try:
        request = urllib.request.Request(
            f"{settings.supabase_url}/storage/v1/object/{settings.supabase_storage_bucket}/{object_path}",
            data=file_bytes,
            method="POST",
            headers={
                **service_headers,
                "Content-Type": mime_type,
                "x-upsert": "true",
            },
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            return 200 <= response.status < 300, ""
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        return False, str(exc)


def admin_platform_statistics_action(payload: dict[str, Any], *, runtime: AdministrationRuntime):
    admin_context = runtime.admin_context
    connection = runtime.connection
    iso = runtime.iso
    prepare_chat_feature_schema = runtime.prepare_chat_feature_schema
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    success = runtime.success
    utc_now = runtime.utc_now
    admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    prepare_chat_feature_schema()
    prepare_notification_feature_schema()
    with connection() as conn:
        summary = conn.execute(
            """
            select
              (select count(*) from courseplatform.students where status = 'ACTIVE') as active_students,
              (select count(*) from courseplatform.chat_presence p
               join courseplatform.students s on s.student_id = p.actor_id and s.status = 'ACTIVE'
               where p.actor_type = 'STUDENT' and p.last_seen_at > now() - interval '75 seconds') as online_students,
              (select count(*) from courseplatform.courses where status = 'ACTIVE') as active_courses,
              (select count(*) from courseplatform.enrollments where status in ('ACTIVE', 'COMPLETED')) as enrollments,
              (select count(*) from courseplatform.attempts where status in ('SUBMITTED', 'UNDER_REVIEW')) as pending_reviews,
              (select count(*) from courseplatform.certificates where coalesce(status, 'ISSUED') = 'ISSUED') as issued_certificates
            """
        ).fetchone() or {}
        engagement = conn.execute(
            """
            select
              (select count(*) from courseplatform.students s
               where s.status = 'ACTIVE' and (
                 s.last_login_at >= now() - interval '24 hours'
                 or exists (select 1 from courseplatform.chat_presence p where p.actor_type = 'STUDENT' and p.actor_id = s.student_id and p.last_seen_at >= now() - interval '24 hours')
               )) as active_today,
              (select count(*) from courseplatform.students s
               where s.status = 'ACTIVE' and (
                 s.last_login_at >= now() - interval '7 days'
                 or exists (select 1 from courseplatform.chat_presence p where p.actor_type = 'STUDENT' and p.actor_id = s.student_id and p.last_seen_at >= now() - interval '7 days')
               )) as active_7_days,
              (select count(*) from courseplatform.students s
               where s.status = 'ACTIVE' and (
                 s.last_login_at >= now() - interval '30 days'
                 or exists (select 1 from courseplatform.chat_presence p where p.actor_type = 'STUDENT' and p.actor_id = s.student_id and p.last_seen_at >= now() - interval '30 days')
               )) as active_30_days,
              (select count(*) from courseplatform.chat_messages
               where status = 'ACTIVE' and created_at >= now() - interval '7 days') as messages_7_days,
              (select count(*) from courseplatform.attempts
               where submitted_at >= now() - interval '30 days') as submissions_30_days,
              (select count(*) from courseplatform.notifications
               where created_at >= now() - interval '30 days') as notifications_30_days
            """
        ).fetchone() or {}
        performance = conn.execute(
            """
            select
              coalesce((select avg(progress_percent) from courseplatform.enrollments
                        where status in ('ACTIVE', 'COMPLETED')), 0) as average_progress,
              coalesce((select 100.0 * count(*) filter (where status = 'COMPLETED') / nullif(count(*), 0)
                        from courseplatform.enrollments where status in ('ACTIVE', 'COMPLETED')), 0) as completion_rate,
              coalesce((select 100.0 * count(*) filter (where status = 'APPROVED') / nullif(count(*), 0)
                        from courseplatform.attempts
                        where status in ('APPROVED', 'FAILED', 'CORRECTION_REQUIRED')), 0) as approval_rate
            """
        ).fetchone() or {}
        operations = conn.execute(
            """
            select
              (select count(*) from courseplatform.notification_deliveries where status = 'FAILED') as failed_deliveries,
              (select count(*) from courseplatform.certificate_requests where status in ('REQUESTED', 'PAYMENT_SUBMITTED')) as pending_certificates,
              (select count(*) from courseplatform.students where status in ('BLOCKED', 'INACTIVE')) as inactive_students,
              (select count(*) from courseplatform.attempts where status = 'TIME_EXCEEDED') as expired_attempts,
              (select count(*) from courseplatform.chat_message_reports where status = 'OPEN') as open_chat_reports
            """
        ).fetchone() or {}
        courses = conn.execute(
            """
            with enrollment_stats as (
              select course_id,
                     count(*) filter (where status in ('ACTIVE', 'COMPLETED')) as student_count,
                     count(*) filter (where status = 'COMPLETED') as completed_count,
                     coalesce(avg(progress_percent) filter (where status in ('ACTIVE', 'COMPLETED')), 0) as average_progress
              from courseplatform.enrollments group by course_id
            ), pending_stats as (
              select l.course_id, count(*) as pending_reviews
              from courseplatform.attempts a
              join courseplatform.lessons l on l.lesson_id = a.lesson_id
              where a.status in ('SUBMITTED', 'UNDER_REVIEW')
              group by l.course_id
            )
            select c.course_id, c.course_code, c.title,
                   coalesce(e.student_count, 0) as student_count,
                   coalesce(e.completed_count, 0) as completed_count,
                   coalesce(e.average_progress, 0) as average_progress,
                   coalesce(p.pending_reviews, 0) as pending_reviews
            from courseplatform.courses c
            left join enrollment_stats e on e.course_id = c.course_id
            left join pending_stats p on p.course_id = c.course_id
            where c.status = 'ACTIVE'
            order by student_count desc, c.title
            limit 10
            """
        ).fetchall()
        activity = conn.execute(
            """
            select day::date as activity_date,
                   (select count(*) from courseplatform.attempts a
                    where a.submitted_at >= day and a.submitted_at < day + interval '1 day') as submissions,
                   (select count(*) from courseplatform.chat_messages m
                    where m.status = 'ACTIVE' and m.created_at >= day and m.created_at < day + interval '1 day') as messages
            from generate_series(current_date - interval '6 days', current_date, interval '1 day') day
            order by day
            """
        ).fetchall()
        conn.commit()
    numeric = lambda row, key: int(row.get(key) or 0)
    return success({
        "summary": {
            "activeStudents": numeric(summary, "active_students"),
            "onlineStudents": numeric(summary, "online_students"),
            "activeCourses": numeric(summary, "active_courses"),
            "enrollments": numeric(summary, "enrollments"),
            "pendingReviews": numeric(summary, "pending_reviews"),
            "issuedCertificates": numeric(summary, "issued_certificates"),
        },
        "engagement": {
            "activeToday": numeric(engagement, "active_today"),
            "active7Days": numeric(engagement, "active_7_days"),
            "active30Days": numeric(engagement, "active_30_days"),
            "messages7Days": numeric(engagement, "messages_7_days"),
            "submissions30Days": numeric(engagement, "submissions_30_days"),
            "notifications30Days": numeric(engagement, "notifications_30_days"),
        },
        "performance": {
            "averageProgress": round(float(performance.get("average_progress") or 0), 1),
            "completionRate": round(float(performance.get("completion_rate") or 0), 1),
            "approvalRate": round(float(performance.get("approval_rate") or 0), 1),
        },
        "operations": {
            "failedDeliveries": numeric(operations, "failed_deliveries"),
            "pendingCertificates": numeric(operations, "pending_certificates"),
            "inactiveStudents": numeric(operations, "inactive_students"),
            "expiredAttempts": numeric(operations, "expired_attempts"),
            "openChatReports": numeric(operations, "open_chat_reports"),
        },
        "courses": [{
            "courseId": row.get("course_id") or "",
            "courseCode": row.get("course_code") or "",
            "title": row.get("title") or "Curso",
            "studentCount": int(row.get("student_count") or 0),
            "completedCount": int(row.get("completed_count") or 0),
            "averageProgress": round(float(row.get("average_progress") or 0), 1),
            "pendingReviews": int(row.get("pending_reviews") or 0),
        } for row in courses],
        "activity": [{
            "date": iso(row.get("activity_date")),
            "submissions": int(row.get("submissions") or 0),
            "messages": int(row.get("messages") or 0),
        } for row in activity],
        "generatedAt": iso(utc_now()),
    })


def admin_list_students_action(payload: dict[str, Any], *, runtime: AdministrationRuntime):
    admin_context = runtime.admin_context
    cursor_page_limit = runtime.cursor_page_limit
    cursor_pagination_result = runtime.cursor_pagination_result
    cursor_scope = runtime.cursor_scope
    decode_list_cursor = runtime.decode_list_cursor
    fetch_all = runtime.fetch_all
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    public_enrollment = runtime.public_enrollment
    public_group_member = runtime.public_group_member
    public_student = runtime.public_student
    str_value = runtime.str_value
    success = runtime.success
    admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    prepare_notification_feature_schema()
    status = (payload.get("status") or "ALL").upper()
    query = str_value(payload.get("query")).lower()
    progress = str_value(payload.get("progress") or "ALL").upper()
    sort = str_value(payload.get("sort") or "name")
    if progress not in {"ALL", "NOT_STARTED", "IN_PROGRESS", "COMPLETED"}:
        raise ApiError("INVALID_STUDENT_FILTER", "O filtro de progresso é inválido.")
    if sort not in {"name", "progressDesc", "progressAsc", "recentLogin"}:
        raise ApiError("INVALID_STUDENT_SORT", "A ordenação de estudantes é inválida.")
    limit = cursor_page_limit(payload)
    scope = cursor_scope("admin-students", status, progress, sort, query)
    sort_type = "text" if sort == "name" else "number" if sort.startswith("progress") else "datetime"
    cursor = decode_list_cursor(
        payload.get("cursor"), "admin-students", scope,
        sort_type=sort_type, allow_null_sort=sort == "recentLogin",
    )
    progress_sql = {
        "ALL": "true",
        "NOT_STARTED": "primary_progress <= 0",
        "IN_PROGRESS": "primary_progress > 0 and primary_progress < 100",
        "COMPLETED": "primary_progress >= 100",
    }[progress]
    cursor_sql = ""
    cursor_params: list[Any] = []
    if sort == "name":
        sort_field = "pagination_sort_text"
        order_sql = "pagination_sort_text, student_id"
        if cursor:
            cursor_value, cursor_id = cursor
            cursor_sql = "where (pagination_sort_text > %s or (pagination_sort_text = %s and student_id > %s))"
            cursor_params.extend((cursor_value, cursor_value, cursor_id))
    elif sort == "progressAsc":
        sort_field = "primary_progress"
        order_sql = "primary_progress, student_id"
        if cursor:
            cursor_value, cursor_id = cursor
            cursor_sql = "where (primary_progress > %s or (primary_progress = %s and student_id > %s))"
            cursor_params.extend((cursor_value, cursor_value, cursor_id))
    elif sort == "progressDesc":
        sort_field = "primary_progress"
        order_sql = "primary_progress desc, student_id desc"
        if cursor:
            cursor_value, cursor_id = cursor
            cursor_sql = "where (primary_progress < %s or (primary_progress = %s and student_id < %s))"
            cursor_params.extend((cursor_value, cursor_value, cursor_id))
    else:
        sort_field = "last_login_at"
        order_sql = "last_login_at desc nulls last, student_id desc"
        if cursor:
            cursor_value, cursor_id = cursor
            if cursor_value is None:
                cursor_sql = "where last_login_at is null and student_id < %s"
                cursor_params.append(cursor_id)
            else:
                cursor_sql = "where (last_login_at < %s or last_login_at is null or (last_login_at = %s and student_id < %s))"
                cursor_params.extend((cursor_value, cursor_value, cursor_id))
    rows = fetch_all(
        f"""
        with student_rows as (
          select s.*,
            (select count(*) from courseplatform.push_subscriptions ps where ps.student_id = s.student_id and ps.enabled) as push_subscription_count,
            coalesce(jsonb_agg(distinct to_jsonb(e)) filter (where e.enrollment_id is not null), '[]') as enrollments,
            coalesce(jsonb_agg(distinct to_jsonb(gm)) filter (where gm.group_member_id is not null), '[]') as memberships,
            coalesce(max(e.progress_percent), 0) as primary_progress,
            lower(coalesce(s.full_name, '')) as pagination_sort_text
          from courseplatform.students s
          left join courseplatform.enrollments e on e.student_id = s.student_id
          left join courseplatform.group_members gm on gm.student_id = s.student_id and gm.status = 'ACTIVE'
          where (%s = 'ALL' or s.status = %s)
            and (%s = '' or lower(coalesce(s.full_name, '') || ' ' || coalesce(s.email, '') || ' ' ||
              coalesce(s.public_student_id, '') || ' ' || coalesce(s.country, '') || ' ' || coalesce(s.organization, '')) like %s)
          group by s.student_id
        ), filtered_students as (
          select * from student_rows where {progress_sql}
        ), numbered_students as (
          select *,
            count(*) over() as total_count,
            count(*) filter (where status = 'ACTIVE') over() as active_count,
            count(*) filter (where status = 'BLOCKED') over() as blocked_count,
            count(*) filter (where primary_progress >= 100) over() as completed_count,
            avg(primary_progress) over() as average_progress
          from filtered_students
        )
        select * from numbered_students
        {cursor_sql}
        order by {order_sql}
        limit %s
        """,
        (status, status, query, f"%{query}%", *cursor_params, limit + 1),
    )
    summary_row = rows[0] if rows else {}
    total = int(summary_row.get("total_count") or 0)
    rows, page_info = cursor_pagination_result(
        rows, limit, "admin-students", scope, sort_field, "student_id"
    )
    page_info["total"] = total
    return success({
        "students": [
            {
                "student": public_student(row),
                "enrollments": [public_enrollment(item) for item in row.get("enrollments", [])],
                "memberships": [public_group_member(item) for item in row.get("memberships", [])],
            }
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "pagination": page_info,
        "summary": {
            "active": int(summary_row.get("active_count") or 0),
            "blocked": int(summary_row.get("blocked_count") or 0),
            "completed": int(summary_row.get("completed_count") or 0),
            "averageProgress": round(float(summary_row.get("average_progress") or 0), 1),
        },
    })


def admin_list_staff_action(payload: dict[str, Any], *, runtime: AdministrationRuntime):
    admin_context = runtime.admin_context
    cursor_page_limit = runtime.cursor_page_limit
    cursor_pagination_result = runtime.cursor_pagination_result
    cursor_scope = runtime.cursor_scope
    decode_list_cursor = runtime.decode_list_cursor
    fetch_all = runtime.fetch_all
    public_admin = runtime.public_admin
    str_value = runtime.str_value
    success = runtime.success
    _, current_admin = admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    status = str_value(payload.get("status") or "ALL").upper()
    role = str_value(payload.get("role") or "ALL").upper()
    query = str_value(payload.get("query")).lower()
    limit = cursor_page_limit(payload)
    scope = cursor_scope("admin-staff", status, role, query)
    cursor = decode_list_cursor(payload.get("cursor"), "admin-staff", scope, sort_type="text")
    cursor_sql = ""
    cursor_params: list[Any] = []
    if cursor:
        cursor_name, cursor_id = cursor
        cursor_sql = "where (pagination_sort_text > %s or (pagination_sort_text = %s and admin_id > %s))"
        cursor_params.extend((cursor_name, cursor_name, cursor_id))
    rows = fetch_all(
        f"""
        with staff_rows as (
          select *, lower(coalesce(full_name, '')) as pagination_sort_text
          from courseplatform.admins
          where (%s = 'ALL' or status = %s)
            and (%s = 'ALL' or role = %s)
            and (%s = '' or lower(coalesce(full_name, '') || ' ' || coalesce(email, '') || ' ' || coalesce(role, '')) like %s)
        ), numbered_staff as (
          select *,
            count(*) over() as total_count,
            count(*) filter (where status = 'ACTIVE') over() as active_count,
            count(*) filter (where role = 'REVIEWER' and status = 'ACTIVE') over() as reviewer_count
          from staff_rows
        )
        select * from numbered_staff
        {cursor_sql}
        order by pagination_sort_text, admin_id
        limit %s
        """,
        (status, status, role, role, query, f"%{query}%", *cursor_params, limit + 1),
    )
    summary_row = rows[0] if rows else {}
    total = int(summary_row.get("total_count") or 0)
    rows, page_info = cursor_pagination_result(
        rows, limit, "admin-staff", scope, "pagination_sort_text", "admin_id"
    )
    page_info["total"] = total
    return success({
        "staff": [public_admin(row) for row in rows],
        "currentAdmin": public_admin(current_admin),
        "pagination": page_info,
        "summary": {
            "active": int(summary_row.get("active_count") or 0),
            "reviewers": int(summary_row.get("reviewer_count") or 0),
        },
    })


def admin_save_staff_action(payload: dict[str, Any], *, runtime: AdministrationRuntime):
    admin_context = runtime.admin_context
    audit = runtime.audit
    connection = runtime.connection
    fetch_one = runtime.fetch_one
    generate_access_code = runtime.generate_access_code
    generate_id = runtime.generate_id
    normalize_email = runtime.normalize_email
    public_admin = runtime.public_admin
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    success = runtime.success
    valid_password = runtime.valid_password
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


def admin_set_staff_status_action(payload: dict[str, Any], *, runtime: AdministrationRuntime):
    admin_context = runtime.admin_context
    audit = runtime.audit
    connection = runtime.connection
    public_admin = runtime.public_admin
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    success = runtime.success
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


def admin_create_student_action(payload: dict[str, Any], *, runtime: AdministrationRuntime):
    admin_context = runtime.admin_context
    audit = runtime.audit
    connection = runtime.connection
    generate_access_code = runtime.generate_access_code
    generate_id = runtime.generate_id
    normalize_email = runtime.normalize_email
    public_student = runtime.public_student
    public_student_id = runtime.public_student_id
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    success = runtime.success
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


def admin_change_student_email_action(payload: dict[str, Any], *, runtime: AdministrationRuntime):
    admin_context = runtime.admin_context
    as_bool = runtime.as_bool
    connection = runtime.connection
    database_api_error = runtime.database_api_error
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    public_student = runtime.public_student
    require_fields = runtime.require_fields
    secure_student_email_update = runtime.secure_student_email_update
    str_value = runtime.str_value
    success = runtime.success
    validated_email_change = runtime.validated_email_change
    verify_password_with_conn = runtime.verify_password_with_conn
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


def admin_set_student_status_action(payload: dict[str, Any], *, runtime: AdministrationRuntime):
    admin_context = runtime.admin_context
    audit = runtime.audit
    connection = runtime.connection
    public_student = runtime.public_student
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    success = runtime.success
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


def admin_reset_student_access_code_action(payload: dict[str, Any], *, runtime: AdministrationRuntime):
    admin_context = runtime.admin_context
    audit = runtime.audit
    connection = runtime.connection
    generate_access_code = runtime.generate_access_code
    public_student = runtime.public_student
    require_fields = runtime.require_fields
    success = runtime.success
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


def credential_restore_item_action(kind: str, row: dict[str, Any], temporary_password: str, *, runtime: AdministrationRuntime) -> dict[str, Any]:
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


def admin_restore_credentials_action(payload: dict[str, Any], *, runtime: AdministrationRuntime):
    admin_context = runtime.admin_context
    as_bool = runtime.as_bool
    audit = runtime.audit
    connection = runtime.connection
    credential_restore_item = runtime.credential_restore_item
    generate_access_code = runtime.generate_access_code
    str_value = runtime.str_value
    success = runtime.success
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


def admin_student_details_action(payload: dict[str, Any], *, runtime: AdministrationRuntime):
    admin_context = runtime.admin_context
    connection = runtime.connection
    ensure_certificate_feature_schema = runtime.ensure_certificate_feature_schema
    iso = runtime.iso
    prepare_assessment_feature_schema = runtime.prepare_assessment_feature_schema
    public_certificate = runtime.public_certificate
    public_certificate_request = runtime.public_certificate_request
    public_enrollment = runtime.public_enrollment
    public_group_member = runtime.public_group_member
    public_progress = runtime.public_progress
    public_student = runtime.public_student
    require_fields = runtime.require_fields
    staff_attempt = runtime.staff_attempt
    success = runtime.success
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
                "attempt": staff_attempt({
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


def admin_upload_brand_logo_action(payload: dict[str, Any], *, runtime: AdministrationRuntime):
    BRAND_LOGO_MAX_BYTES = runtime.BRAND_LOGO_MAX_BYTES
    admin_context = runtime.admin_context
    audit = runtime.audit
    certificate_token = runtime.certificate_token
    connection = runtime.connection
    decode_raster_data_url = runtime.decode_raster_data_url
    get_settings = runtime.get_settings
    persist_media_config = runtime.persist_media_config
    read_media_config = runtime.read_media_config
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    success = runtime.success
    upload_raster_asset_to_storage = runtime.upload_raster_asset_to_storage
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["fileName", "mimeType", "dataUrl"])
    course_id = str_value(payload.get("courseId") or get_settings().default_course_id)
    mime_type, data_url, file_bytes = decode_raster_data_url(
        payload.get("dataUrl"),
        payload.get("mimeType"),
        BRAND_LOGO_MAX_BYTES,
    )
    extension = mimetypes.guess_extension(mime_type) or ".png"
    object_path = f"{course_id}/branding/institutional-logo-{certificate_token(8)}{extension}"
    storage_saved, storage_error = upload_raster_asset_to_storage(file_bytes, mime_type, object_path)

    media = read_media_config(course_id)
    if not isinstance(media, dict):
        media = {"logoUrl": "", "videos": []}
    media["logoUrl"] = data_url
    media.setdefault("videos", [])
    with connection() as conn:
        persist_media_config(conn, media)
        audit(
            conn,
            "ADMIN",
            admin["admin_id"],
            "BRAND_LOGO_UPLOADED",
            "SETTING",
            "MEDIA_CONFIG",
            {
                "fileName": str_value(payload.get("fileName"))[:180],
                "mimeType": mime_type,
                "sizeBytes": len(file_bytes),
                "storageSaved": storage_saved,
                "storagePath": object_path if storage_saved else "",
            },
        )
        conn.commit()

    return success({
        "mediaConfig": media,
        "storageSaved": storage_saved,
        "storagePath": object_path if storage_saved else "",
        "storageError": storage_error,
    })
