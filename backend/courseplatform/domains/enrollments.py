import json
from dataclasses import dataclass
from datetime import timezone
from typing import Any

from ..contracts import ApiError
from ..reviewer_scopes import admin_from_context, reviewer_scope_predicate


ACTION_BINDINGS = (
    ("getMyCourses", "my_courses"),
    ("adminSaveCourseOffering", "admin_save_course_offering"),
    ("adminEnrollStudentsInOffering", "admin_enroll_students_in_offering"),
    ("adminListCourseReconciliationIssues", "admin_list_course_reconciliation_issues"),
    ("adminListGroups", "admin_list_groups"),
    ("adminSaveGroup", "admin_save_group"),
    ("adminAssignStudentsToGroup", "admin_assign_students_to_group"),
)


@dataclass(frozen=True)
class EnrollmentRuntime:
    admin_context: Any
    audit: Any
    connection: Any
    cursor_page_limit: Any
    cursor_pagination_result: Any
    cursor_scope: Any
    decode_list_cursor: Any
    ensure_offering_enrollment_with_conn: Any
    fetch_all: Any
    generate_id: Any
    initialize_enrollment_progress_with_conn: Any
    int_value: Any
    iso: Any
    parse_datetime: Any
    public_course: Any
    public_course_offering: Any
    public_course_version: Any
    public_enrollment: Any
    public_student: Any
    require_fields: Any
    require_session_token: Any
    resolve_course_offering_with_conn: Any
    str_value: Any
    student_context_with_conn: Any
    student_courses_payload: Any
    student_courses_rows: Any
    student_notification_channel_info: Any
    success: Any


def resolve_course_offering_with_conn_action(conn, course_id: str, offering_id: str = "", *, runtime: EnrollmentRuntime) -> dict[str, Any]:
    if offering_id:
        offering = conn.execute(
            "select * from courseplatform.course_offerings where offering_id = %s and course_id = %s",
            (offering_id, course_id),
        ).fetchone()
        if not offering:
            raise ApiError("OFFERING_NOT_FOUND", "Edição/turma não encontrada para este curso.")
        return offering
    rows = conn.execute(
        """
        select * from courseplatform.course_offerings
        where course_id = %s and status in ('OPEN', 'ACTIVE')
        order by start_date desc nulls last, created_at desc
        limit 2
        """,
        (course_id,),
    ).fetchall()
    if len(rows) == 1:
        return rows[0]
    if len(rows) > 1:
        raise ApiError("OFFERING_REQUIRED", "Selecione a edição/turma do curso.")
    fallback = conn.execute(
        """
        select * from courseplatform.course_offerings
        where course_id = %s and status <> 'ARCHIVED'
        order by start_date desc nulls last, created_at desc
        limit 2
        """,
        (course_id,),
    ).fetchall()
    if len(fallback) == 1:
        return fallback[0]
    if len(fallback) > 1:
        raise ApiError("OFFERING_REQUIRED", "Selecione a edição/turma do curso.")
    raise ApiError("OFFERING_NOT_FOUND", "Este curso ainda não possui uma edição/turma.")


def resolve_student_enrollment_with_conn_action(
    conn,
    student_id: str,
    course_id: str = "",
    enrollment_id: str = "",
    *,
    runtime: EnrollmentRuntime,
) -> dict[str, Any]:
    if enrollment_id:
        enrollment = conn.execute(
            """
            select * from courseplatform.enrollments
            where enrollment_id = %s and student_id = %s
              and (%s = '' or course_id = %s)
            """,
            (enrollment_id, student_id, course_id, course_id),
        ).fetchone()
        if not enrollment:
            raise ApiError("ENROLLMENT_NOT_FOUND", "Matrícula não encontrada.")
        return enrollment
    rows = conn.execute(
        """
        select * from courseplatform.enrollments
        where student_id = %s and (%s = '' or course_id = %s)
          and status in ('ACTIVE', 'COMPLETED')
        order by enrolled_at desc nulls last, updated_at desc nulls last
        limit 2
        """,
        (student_id, course_id, course_id),
    ).fetchall()
    if len(rows) == 1:
        return rows[0]
    if len(rows) > 1:
        raise ApiError("ENROLLMENT_REQUIRED", "Selecione a matrícula/edição do curso.")
    raise ApiError("ENROLLMENT_NOT_FOUND", "Matrícula não encontrada.")


def initialize_enrollment_progress_with_conn_action(conn, enrollment: dict[str, Any], *, runtime: EnrollmentRuntime) -> int:
    generate_id = runtime.generate_id
    int_value = runtime.int_value
    str_value = runtime.str_value
    version = conn.execute(
        """
        select content_snapshot_json
        from courseplatform.course_versions
        where course_version_id = %s
        """,
        (enrollment["course_version_id"],),
    ).fetchone() or {}
    snapshot = version.get("content_snapshot_json") or {}
    lessons = snapshot.get("lessons") if isinstance(snapshot, dict) else []
    if not isinstance(lessons, list):
        return 0
    active_lessons = sorted(
        (
            lesson for lesson in lessons
            if isinstance(lesson, dict)
            and str_value(lesson.get("lesson_id"))
            and str_value(lesson.get("status") or "ACTIVE").upper() == "ACTIVE"
        ),
        key=lambda lesson: (int_value(lesson.get("lesson_number")), str_value(lesson.get("lesson_id"))),
    )
    initialized = 0
    for lesson in active_lessons:
        access_status = "LOCKED" if str_value(lesson.get("prerequisite_lesson_id")) else "AVAILABLE"
        row = conn.execute(
            """
            insert into courseplatform.lesson_progress
              (progress_id, enrollment_id, student_id, lesson_id, status,
               content_access_status, evaluation_status, unlocked_at,
               attempt_count, updated_at)
            values (%s, %s, %s, %s, %s, %s, 'NOT_STARTED',
                    case when %s = 'AVAILABLE' then now() else null end, 0, now())
            on conflict (enrollment_id, lesson_id) do nothing
            returning progress_id
            """,
            (
                generate_id("PRG"),
                enrollment["enrollment_id"],
                enrollment["student_id"],
                lesson["lesson_id"],
                access_status,
                access_status,
                access_status,
            ),
        ).fetchone()
        initialized += 1 if row else 0
    return initialized


def ensure_offering_enrollment_with_conn_action(
    conn,
    student_id: str,
    offering: dict[str, Any],
    group_id: str | None = None,
    *,
    runtime: EnrollmentRuntime,
) -> dict[str, Any]:
    generate_id = runtime.generate_id
    initialize_enrollment_progress_with_conn = runtime.initialize_enrollment_progress_with_conn
    int_value = runtime.int_value
    enrollment = conn.execute(
        """
        select * from courseplatform.enrollments
        where student_id = %s and offering_id = %s
        for update
        """,
        (student_id, offering["offering_id"]),
    ).fetchone()
    if enrollment:
        if group_id and enrollment.get("group_id") != group_id:
            enrollment = conn.execute(
                """
                update courseplatform.enrollments
                set group_id = %s, updated_at = now()
                where enrollment_id = %s
                returning *
                """,
                (group_id, enrollment["enrollment_id"]),
            ).fetchone()
        initialize_enrollment_progress_with_conn(conn, enrollment)
        return enrollment
    capacity = int_value(offering.get("capacity"))
    if capacity:
        current = conn.execute(
            "select count(*) as total from courseplatform.enrollments where offering_id = %s and status <> 'CANCELLED'",
            (offering["offering_id"],),
        ).fetchone() or {}
        if int(current.get("total") or 0) >= capacity:
            raise ApiError("OFFERING_CAPACITY_REACHED", "A edição/turma atingiu a capacidade definida.")
    enrollment = conn.execute(
        """
        insert into courseplatform.enrollments
          (enrollment_id, student_id, course_id, course_version_id, offering_id,
           group_id, status, enrolled_at, progress_percent, updated_at)
        values (%s, %s, %s, %s, %s, %s, 'ACTIVE', now(), 0, now())
        returning *
        """,
        (
            generate_id("ENR"),
            student_id,
            offering["course_id"],
            offering["course_version_id"],
            offering["offering_id"],
            group_id,
        ),
    ).fetchone()
    initialize_enrollment_progress_with_conn(conn, enrollment)
    return enrollment


def student_courses_rows_action(conn, student_id: str, *, runtime: EnrollmentRuntime):
    return conn.execute(
        """
        select
          e.enrollment_id, e.student_id, e.course_id as enrollment_course_id,
          e.course_version_id, e.offering_id,
          e.group_id, e.status as enrollment_status, e.enrolled_at, e.completed_at,
          e.progress_percent, e.final_score, e.certificate_id,
          c.course_id, c.course_code, c.title, c.description, c.total_hours,
          c.passing_score, c.status as course_status, c.created_at, c.updated_at,
          cv.version_number, cv.status as version_status, cv.title as version_title,
          cv.description as version_description, cv.total_hours as version_total_hours,
          cv.passing_score as version_passing_score, cv.published_at,
          o.offering_code, o.name as offering_name, o.start_date as offering_start_date,
          o.end_date as offering_end_date, o.capacity as offering_capacity,
          o.status as offering_status, o.lead_admin_id, o.rules_json, o.calendar_json,
          g.name as group_name, g.start_date, g.end_date,
          coalesce(jsonb_array_length(cv.content_snapshot_json -> 'lessons'), 0) as lesson_count
        from courseplatform.enrollments e
        join courseplatform.courses c on c.course_id = e.course_id
        join courseplatform.course_versions cv on cv.course_version_id = e.course_version_id
        join courseplatform.course_offerings o on o.offering_id = e.offering_id
        left join courseplatform.groups g on g.group_id = e.group_id
        where e.student_id = %s and c.status <> 'DELETED'
        order by coalesce(o.start_date, e.enrolled_at) desc nulls last, c.title
        """,
        (student_id,),
    ).fetchall()


def student_courses_payload_action(rows: list[dict[str, Any]], *, runtime: EnrollmentRuntime):
    iso = runtime.iso
    public_course = runtime.public_course
    public_course_offering = runtime.public_course_offering
    public_course_version = runtime.public_course_version
    public_enrollment = runtime.public_enrollment
    courses = []
    for row in rows:
        enrollment_row = {
            **row,
            "course_id": row.get("enrollment_course_id"),
            "status": row.get("enrollment_status"),
        }
        course_row = {
            **row,
            "title": row.get("version_title") or row.get("title"),
            "description": row.get("version_description") or row.get("description"),
            "total_hours": row.get("version_total_hours"),
            "passing_score": row.get("version_passing_score"),
            "status": row.get("course_status"),
        }
        version_row = {
            **row,
            "status": row.get("version_status"),
            "title": row.get("version_title"),
            "description": row.get("version_description"),
            "total_hours": row.get("version_total_hours"),
            "passing_score": row.get("version_passing_score"),
        }
        offering_row = {
            **row,
            "name": row.get("offering_name"),
            "start_date": row.get("offering_start_date"),
            "end_date": row.get("offering_end_date"),
            "capacity": row.get("offering_capacity"),
            "status": row.get("offering_status"),
        }
        courses.append({
            "course": public_course(course_row),
            "courseVersion": public_course_version(version_row),
            "offering": public_course_offering(offering_row),
            "enrollment": public_enrollment(enrollment_row),
            "group": {
                "name": row.get("group_name"),
                "startDate": iso(row.get("start_date")),
                "endDate": iso(row.get("end_date")),
            } if row.get("group_name") else None,
            "lessonCount": int(row.get("lesson_count") or 0),
        })
    return courses


def my_courses_action(payload: dict[str, Any], *, runtime: EnrollmentRuntime):
    connection = runtime.connection
    public_student = runtime.public_student
    require_session_token = runtime.require_session_token
    student_context_with_conn = runtime.student_context_with_conn
    student_courses_payload = runtime.student_courses_payload
    student_courses_rows = runtime.student_courses_rows
    student_notification_channel_info = runtime.student_notification_channel_info
    success = runtime.success
    require_session_token(payload)
    with connection() as conn:
        _, student = student_context_with_conn(conn, payload)
        rows = student_courses_rows(conn, student["student_id"])
    return success({
        "student": public_student(student),
        "courses": student_courses_payload(rows),
        "notificationChannelInfo": student_notification_channel_info(),
    })


def admin_list_groups_action(payload: dict[str, Any], *, runtime: EnrollmentRuntime):
    admin_context = runtime.admin_context
    cursor_page_limit = runtime.cursor_page_limit
    cursor_pagination_result = runtime.cursor_pagination_result
    cursor_scope = runtime.cursor_scope
    decode_list_cursor = runtime.decode_list_cursor
    fetch_all = runtime.fetch_all
    iso = runtime.iso
    str_value = runtime.str_value
    success = runtime.success
    admin = admin_from_context(admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"}))
    course_id = str_value(payload.get("courseId"))
    status = str_value(payload.get("status") or "ALL").upper()
    query = str_value(payload.get("query")).lower()
    limit = cursor_page_limit(payload)
    scope = cursor_scope("admin-groups", course_id, status, query)
    cursor = decode_list_cursor(payload.get("cursor"), "admin-groups", scope, sort_type="text")
    cursor_sql = ""
    cursor_params: list[Any] = []
    if cursor:
        cursor_name, cursor_id = cursor
        cursor_sql = "where (pagination_sort_text > %s or (pagination_sort_text = %s and group_id > %s))"
        cursor_params.extend((cursor_name, cursor_name, cursor_id))
    reviewer_sql, reviewer_params = reviewer_scope_predicate(
        admin,
        course_expr="g.course_id",
        offering_expr="g.offering_id",
        group_expr="g.group_id",
    )
    rows = fetch_all(
        f"""
        with group_rows as (
          select g.*, count(gm.group_member_id) filter (where gm.status = 'ACTIVE') as member_count,
                 lower(coalesce(g.name, '')) as pagination_sort_text
          from courseplatform.groups g
          left join courseplatform.group_members gm on gm.group_id = g.group_id
          where (%s = '' or g.course_id = %s)
            and (%s = 'ALL' or (%s = 'NON_DELETED' and g.status <> 'DELETED') or g.status = %s)
            and (%s = '' or lower(coalesce(g.name, '') || ' ' || coalesce(g.group_code, '') || ' ' || coalesce(g.group_id, '')) like %s)
            and ({reviewer_sql})
          group by g.group_id
        ), numbered_groups as (
          select *, count(*) over() as total_count from group_rows
        )
        select * from numbered_groups
        {cursor_sql}
        order by pagination_sort_text, group_id
        limit %s
        """,
        (course_id, course_id, status, status, status, query, f"%{query}%", *reviewer_params, *cursor_params, limit + 1),
    )
    total = int(rows[0]["total_count"]) if rows else 0
    rows, page_info = cursor_pagination_result(
        rows, limit, "admin-groups", scope, "pagination_sort_text", "group_id"
    )
    page_info["total"] = total
    return success({
        "groups": [{"group": {
            "groupId": row["group_id"], "groupCode": row.get("group_code"),
            "name": row.get("name"), "courseId": row.get("course_id"),
            "offeringId": row.get("offering_id"), "startDate": iso(row.get("start_date")),
            "endDate": iso(row.get("end_date")), "status": row.get("status"),
            "createdAt": iso(row.get("created_at")), "updatedAt": iso(row.get("updated_at")),
        }, "memberCount": int(row["member_count"] or 0)} for row in rows],
        "pagination": page_info,
    })


def admin_save_course_offering_action(payload: dict[str, Any], *, runtime: EnrollmentRuntime):
    admin_context = runtime.admin_context
    audit = runtime.audit
    connection = runtime.connection
    generate_id = runtime.generate_id
    int_value = runtime.int_value
    parse_datetime = runtime.parse_datetime
    public_course_offering = runtime.public_course_offering
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    success = runtime.success
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["courseId", "courseVersionId", "name"])
    status = str_value(payload.get("status") or "DRAFT").upper()
    if status not in {"DRAFT", "OPEN", "ACTIVE", "COMPLETED", "CANCELLED", "ARCHIVED"}:
        raise ApiError("INVALID_OFFERING_STATUS", "Estado da edição/turma inválido.")
    raw_start_date = payload.get("startDate")
    raw_end_date = payload.get("endDate")
    start_date = parse_datetime(raw_start_date)
    end_date = parse_datetime(raw_end_date)
    if raw_start_date not in (None, "") and start_date is None:
        raise ApiError("INVALID_OFFERING_PERIOD", "A data inicial da edição é inválida.")
    if raw_end_date not in (None, "") and end_date is None:
        raise ApiError("INVALID_OFFERING_PERIOD", "A data final da edição é inválida.")
    if start_date and start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)
    if end_date and end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)
    if start_date and end_date and end_date < start_date:
        raise ApiError("INVALID_OFFERING_PERIOD", "A data final não pode ser anterior à data inicial.")
    capacity = int_value(payload.get("capacity")) if payload.get("capacity") not in (None, "") else None
    if capacity is not None and capacity <= 0:
        raise ApiError("INVALID_OFFERING_CAPACITY", "A capacidade deve ser superior a zero.")
    offering_id = str_value(payload.get("offeringId")) or generate_id("COFF")
    rules = payload.get("rules") if isinstance(payload.get("rules"), dict) else {}
    calendar = payload.get("calendar") if isinstance(payload.get("calendar"), list) else []
    with connection() as conn:
        version = conn.execute(
            """
            select * from courseplatform.course_versions
            where course_version_id = %s and course_id = %s
            """,
            (payload["courseVersionId"], payload["courseId"]),
        ).fetchone()
        if not version:
            raise ApiError("COURSE_VERSION_NOT_FOUND", "Versão do curso não encontrada.")
        if version.get("status") != "PUBLISHED":
            raise ApiError("COURSE_VERSION_NOT_PUBLISHED", "Publique a versão antes de criar uma edição/turma.")
        row = conn.execute(
            """
            insert into courseplatform.course_offerings
              (offering_id, course_id, course_version_id, offering_code, name,
               start_date, end_date, capacity, status, lead_admin_id, rules_json,
               calendar_json, created_by, created_at, updated_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
            on conflict (offering_id) do update
            set course_id = excluded.course_id,
                course_version_id = excluded.course_version_id,
                offering_code = excluded.offering_code,
                name = excluded.name,
                start_date = excluded.start_date,
                end_date = excluded.end_date,
                capacity = excluded.capacity,
                status = excluded.status,
                lead_admin_id = excluded.lead_admin_id,
                rules_json = excluded.rules_json,
                calendar_json = excluded.calendar_json,
                updated_at = now()
            returning *
            """,
            (
                offering_id, payload["courseId"], payload["courseVersionId"],
                str_value(payload.get("offeringCode") or offering_id), str_value(payload.get("name")),
                start_date, end_date, capacity, status,
                str_value(payload.get("leadAdminId")) or None,
                json.dumps(rules, ensure_ascii=True, separators=(",", ":")),
                json.dumps(calendar, ensure_ascii=True, separators=(",", ":")),
                admin["admin_id"],
            ),
        ).fetchone()
        audit(
            conn, "ADMIN", admin["admin_id"], "COURSE_OFFERING_SAVED",
            "COURSE_OFFERING", offering_id,
            {"courseId": row["course_id"], "courseVersionId": row["course_version_id"], "status": status},
        )
        conn.commit()
    return success({"offering": public_course_offering(row)})


def admin_enroll_students_in_offering_action(payload: dict[str, Any], *, runtime: EnrollmentRuntime):
    admin_context = runtime.admin_context
    audit = runtime.audit
    connection = runtime.connection
    ensure_offering_enrollment_with_conn = runtime.ensure_offering_enrollment_with_conn
    generate_id = runtime.generate_id
    public_course_offering = runtime.public_course_offering
    public_enrollment = runtime.public_enrollment
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    success = runtime.success
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["offeringId"])
    student_ids = list(dict.fromkeys(
        str_value(value) for value in (payload.get("studentIds") or []) if str_value(value)
    ))
    if not student_ids:
        raise ApiError("EMPTY_ENROLLMENT_TARGET", "Selecione pelo menos um estudante.")
    group_id = str_value(payload.get("groupId")) or None
    with connection() as conn:
        offering = conn.execute(
            "select * from courseplatform.course_offerings where offering_id = %s for update",
            (payload["offeringId"],),
        ).fetchone()
        if not offering:
            raise ApiError("OFFERING_NOT_FOUND", "Edição/turma não encontrada.")
        if offering.get("status") not in {"OPEN", "ACTIVE"}:
            raise ApiError("OFFERING_NOT_OPEN", "A edição/turma não aceita novas matrículas.")
        if group_id:
            group = conn.execute(
                "select * from courseplatform.groups where group_id = %s and offering_id = %s",
                (group_id, offering["offering_id"]),
            ).fetchone()
            if not group:
                raise ApiError("GROUP_OFFERING_MISMATCH", "O grupo não pertence à edição selecionada.")
        enrollments = []
        for student_id in student_ids:
            student = conn.execute(
                "select student_id from courseplatform.students where student_id = %s and status = 'ACTIVE'",
                (student_id,),
            ).fetchone()
            if not student:
                raise ApiError("STUDENT_NOT_FOUND", "Um dos estudantes selecionados não está ativo.")
            enrollment = ensure_offering_enrollment_with_conn(conn, student_id, offering, group_id)
            enrollments.append(enrollment)
            if group_id:
                conn.execute(
                    """
                    insert into courseplatform.group_members
                      (group_member_id, group_id, student_id, enrollment_id, status, joined_at, updated_at)
                    values (%s, %s, %s, %s, 'ACTIVE', now(), now())
                    on conflict (group_id, student_id) do update
                    set enrollment_id = excluded.enrollment_id, status = 'ACTIVE', updated_at = now()
                    """,
                    (generate_id("GM"), group_id, student_id, enrollment["enrollment_id"]),
                )
        audit(
            conn, "ADMIN", admin["admin_id"], "STUDENTS_ENROLLED_IN_OFFERING",
            "COURSE_OFFERING", offering["offering_id"],
            {"studentCount": len(enrollments), "groupId": group_id},
        )
        conn.commit()
    return success({
        "offering": public_course_offering(offering),
        "enrollments": [public_enrollment(row) for row in enrollments],
    })


def admin_list_course_reconciliation_issues_action(payload: dict[str, Any], *, runtime: EnrollmentRuntime):
    admin_context = runtime.admin_context
    cursor_page_limit = runtime.cursor_page_limit
    cursor_pagination_result = runtime.cursor_pagination_result
    cursor_scope = runtime.cursor_scope
    decode_list_cursor = runtime.decode_list_cursor
    fetch_all = runtime.fetch_all
    iso = runtime.iso
    str_value = runtime.str_value
    success = runtime.success
    admin_context(payload, {"OWNER", "ADMIN"})
    status = str_value(payload.get("status") or "OPEN").upper()
    limit = cursor_page_limit(payload)
    scope = cursor_scope("admin-course-reconciliation", status)
    cursor = decode_list_cursor(payload.get("cursor"), "admin-course-reconciliation", scope)
    cursor_sql = ""
    cursor_params: list[Any] = []
    if cursor:
        cursor_at, cursor_id = cursor
        cursor_sql = """
          and (detected_at > %s or (detected_at = %s and issue_id > %s))
        """
        cursor_params.extend((cursor_at, cursor_at, cursor_id))
    rows = fetch_all(
        f"""
        select *, detected_at as pagination_sort_at
        from courseplatform.migration_reconciliation_issues
        where migration_key = '20260915101047'
          and (%s = 'ALL' or status = %s)
          {cursor_sql}
        order by detected_at, issue_id
        limit %s
        """,
        (status, status, *cursor_params, limit + 1),
    )
    rows, page_info = cursor_pagination_result(
        rows, limit, "admin-course-reconciliation", scope, "pagination_sort_at", "issue_id"
    )
    return success({
        "issues": [
            {
                "issueId": row.get("issue_id"),
                "entityType": row.get("entity_type"),
                "entityId": row.get("entity_id"),
                "issueCode": row.get("issue_code"),
                "details": row.get("details_json") or {},
                "status": row.get("status"),
                "detectedAt": iso(row.get("detected_at")),
            }
            for row in rows
        ],
        "pagination": page_info,
    })


def admin_save_group_action(payload: dict[str, Any], *, runtime: EnrollmentRuntime):
    admin_context = runtime.admin_context
    audit = runtime.audit
    connection = runtime.connection
    ensure_offering_enrollment_with_conn = runtime.ensure_offering_enrollment_with_conn
    generate_id = runtime.generate_id
    iso = runtime.iso
    parse_datetime = runtime.parse_datetime
    require_fields = runtime.require_fields
    resolve_course_offering_with_conn = runtime.resolve_course_offering_with_conn
    str_value = runtime.str_value
    success = runtime.success
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["courseId", "name"])
    group_id = str_value(payload.get("groupId")) or generate_id("GRP")
    student_ids = payload.get("studentIds") if isinstance(payload.get("studentIds"), list) else []
    with connection() as conn:
        existing_group = conn.execute(
            "select * from courseplatform.groups where group_id = %s",
            (group_id,),
        ).fetchone()
        offering = resolve_course_offering_with_conn(
            conn,
            payload["courseId"],
            str_value(payload.get("offeringId")) or str_value((existing_group or {}).get("offering_id")),
        )
        group = conn.execute(
            """
            insert into courseplatform.groups
              (group_id, group_code, name, course_id, offering_id,
               start_date, end_date, status, created_at, updated_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s, now(), now())
            on conflict (group_id) do update
            set group_code = excluded.group_code, name = excluded.name, course_id = excluded.course_id,
                offering_id = excluded.offering_id,
                start_date = excluded.start_date, end_date = excluded.end_date,
                status = excluded.status, updated_at = now()
            returning *
            """,
            (
                group_id,
                str_value(payload.get("groupCode") or group_id),
                str_value(payload.get("name")),
                payload["courseId"],
                offering["offering_id"],
                parse_datetime(payload.get("startDate")),
                parse_datetime(payload.get("endDate")),
                str_value(payload.get("status") or "ACTIVE").upper(),
            ),
        ).fetchone()
        for student_id in student_ids:
            enrollment = ensure_offering_enrollment_with_conn(conn, student_id, offering, group_id)
            conn.execute(
                """
                insert into courseplatform.group_members
                  (group_member_id, group_id, student_id, enrollment_id, status, joined_at, updated_at)
                values (%s, %s, %s, %s, 'ACTIVE', now(), now())
                on conflict (group_id, student_id) do update
                set enrollment_id = excluded.enrollment_id, status = 'ACTIVE', updated_at = now()
                """,
                (generate_id("GM"), group_id, student_id, enrollment["enrollment_id"]),
            )
        audit(conn, "ADMIN", admin["admin_id"], "GROUP_SAVED", "GROUP", group_id, {"studentCount": len(student_ids)})
        conn.commit()
    return success({"group": {"groupId": group["group_id"], "groupCode": group.get("group_code"), "name": group.get("name"), "courseId": group.get("course_id"), "offeringId": group.get("offering_id"), "startDate": iso(group.get("start_date")), "endDate": iso(group.get("end_date")), "status": group.get("status")}})


def admin_assign_students_to_group_action(payload: dict[str, Any], *, runtime: EnrollmentRuntime):
    admin_context = runtime.admin_context
    audit = runtime.audit
    connection = runtime.connection
    ensure_offering_enrollment_with_conn = runtime.ensure_offering_enrollment_with_conn
    generate_id = runtime.generate_id
    require_fields = runtime.require_fields
    success = runtime.success
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["groupId"])
    student_ids = payload.get("studentIds") if isinstance(payload.get("studentIds"), list) else []
    with connection() as conn:
        group = conn.execute(
            """
            select g.*, o.course_version_id, o.status as offering_status,
                   o.capacity, o.rules_json, o.calendar_json
            from courseplatform.groups g
            join courseplatform.course_offerings o on o.offering_id = g.offering_id
            where g.group_id = %s
            """,
            (payload["groupId"],),
        ).fetchone()
        if not group:
            raise ApiError("GROUP_NOT_FOUND", "Grupo não encontrado.")
        offering = {
            **group,
            "offering_id": group["offering_id"],
            "course_id": group["course_id"],
            "status": group.get("offering_status"),
        }
        for student_id in student_ids:
            enrollment = ensure_offering_enrollment_with_conn(
                conn, student_id, offering, group["group_id"]
            )
            conn.execute(
                """
                insert into courseplatform.group_members
                  (group_member_id, group_id, student_id, enrollment_id, status, joined_at, updated_at)
                values (%s, %s, %s, %s, 'ACTIVE', now(), now())
                on conflict (group_id, student_id) do update
                set enrollment_id = excluded.enrollment_id, status = 'ACTIVE', updated_at = now()
                """,
                (generate_id("GM"), payload["groupId"], student_id, enrollment["enrollment_id"]),
            )
        audit(conn, "ADMIN", admin["admin_id"], "GROUP_MEMBERS_ASSIGNED", "GROUP", payload["groupId"], {"studentCount": len(student_ids)})
        conn.commit()
    return success({"studentCount": len(student_ids)})
