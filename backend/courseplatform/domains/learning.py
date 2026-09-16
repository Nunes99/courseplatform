from dataclasses import dataclass
from typing import Any

from ..contracts import ApiError


ACTION_BINDINGS = (
    ("getDashboard", "dashboard"),
    ("getStudentHome", "student_home"),
    ("getLesson", "get_lesson"),
    ("adminSetLessonAccess", "admin_set_lesson_access"),
    ("adminManageLessonProgress", "admin_manage_lesson_progress"),
)


@dataclass(frozen=True)
class LearningRuntime:
    ATTEMPT_STATUSES: Any
    CONTENT_ACCESS_STATUSES: Any
    EVALUATION_STATUSES: Any
    admin_context: Any
    as_bool: Any
    audit: Any
    connection: Any
    create_student_notification: Any
    dashboard_payload: Any
    dispatch_notification_deliveries: Any
    ensure_offering_enrollment_with_conn: Any
    feedback_release_mode: Any
    fetch_all: Any
    generate_id: Any
    get_settings: Any
    int_value: Any
    iso: Any
    legacy_progress_status: Any
    notification_status_label: Any
    prepare_assessment_feature_schema: Any
    prepare_notification_feature_schema: Any
    progress_access_status: Any
    progress_evaluation_status: Any
    public_content: Any
    public_course: Any
    public_course_offering: Any
    public_course_version: Any
    public_enrollment: Any
    public_lesson: Any
    public_progress: Any
    public_student: Any
    read_media_config_with_conn: Any
    refresh_enrollment_progress: Any
    require_fields: Any
    require_session_token: Any
    resolve_course_offering_with_conn: Any
    resolve_student_enrollment_with_conn: Any
    str_value: Any
    student_attempt: Any
    student_context: Any
    student_context_with_conn: Any
    student_courses_payload: Any
    student_courses_rows: Any
    student_option: Any
    student_question: Any
    student_visible_media: Any
    success: Any


def progress_access_status_action(row: dict[str, Any] | None, *, runtime: LearningRuntime) -> str:
    CONTENT_ACCESS_STATUSES = runtime.CONTENT_ACCESS_STATUSES
    str_value = runtime.str_value
    source = row or {}
    explicit = str_value(source.get("content_access_status")).upper()
    if explicit in CONTENT_ACCESS_STATUSES:
        return explicit
    return "LOCKED" if str_value(source.get("status")).upper() == "LOCKED" else "AVAILABLE"


def progress_evaluation_status_action(row: dict[str, Any] | None, *, runtime: LearningRuntime) -> str:
    EVALUATION_STATUSES = runtime.EVALUATION_STATUSES
    str_value = runtime.str_value
    source = row or {}
    explicit = str_value(source.get("evaluation_status")).upper()
    if explicit in EVALUATION_STATUSES:
        return explicit
    legacy = str_value(source.get("status")).upper()
    return legacy if legacy in EVALUATION_STATUSES else "NOT_STARTED"


def legacy_progress_status_action(access_status: str, evaluation_status: str, *, runtime: LearningRuntime) -> str:
    return evaluation_status if evaluation_status != "NOT_STARTED" else access_status


def public_lesson_action(row: dict[str, Any] | None, *, runtime: LearningRuntime):
    as_bool = runtime.as_bool
    feedback_release_mode = runtime.feedback_release_mode
    int_value = runtime.int_value
    iso = runtime.iso
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
        "feedbackReleaseMode": feedback_release_mode(row.get("feedback_release_mode")),
        "showCorrectAnswers": as_bool(row.get("show_correct_answers")),
        "showExplanations": as_bool(row.get("show_explanations")),
        "prerequisiteLessonId": row.get("prerequisite_lesson_id"),
        "status": row.get("status"),
        "createdAt": iso(row.get("created_at")),
        "updatedAt": iso(row.get("updated_at")),
    }


def public_content_action(row: dict[str, Any] | None, *, runtime: LearningRuntime):
    as_bool = runtime.as_bool
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


def public_progress_action(row: dict[str, Any] | None, *, runtime: LearningRuntime):
    iso = runtime.iso
    legacy_progress_status = runtime.legacy_progress_status
    progress_access_status = runtime.progress_access_status
    progress_evaluation_status = runtime.progress_evaluation_status
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


def student_question_action(row: dict[str, Any] | None, *, reveal_answers: bool=False, reveal_explanations: bool=False, runtime: LearningRuntime):
    as_bool = runtime.as_bool
    if not row:
        return None
    result = {
        "questionId": row["question_id"],
        "lessonId": row.get("lesson_id"),
        "questionOrder": int(row.get("question_order") or 0),
        "questionType": row.get("question_type"),
        "prompt": row.get("prompt"),
        "isRequired": as_bool(row.get("is_required")),
        "status": row.get("status"),
    }
    if reveal_answers:
        result["correctAnswer"] = row.get("correct_answer")
    if reveal_explanations:
        result["explanation"] = row.get("explanation")
    return result


def student_option_action(row: dict[str, Any] | None, *, reveal_answers: bool=False, runtime: LearningRuntime):
    as_bool = runtime.as_bool
    if not row:
        return None
    result = {
        "optionId": row["option_id"],
        "questionId": row.get("question_id"),
        "optionOrder": int(row.get("option_order") or 0),
        "optionLabel": row.get("option_label"),
        "optionText": row.get("option_text"),
    }
    if reveal_answers:
        result["isCorrect"] = as_bool(row.get("is_correct"))
    return result


def sync_enrollment_completion_action(conn, enrollment: dict[str, Any] | None, completed: bool, final_score: float | None=None, *, runtime: LearningRuntime):
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


def refresh_enrollment_progress_action(conn, progress_id: str | None, *, runtime: LearningRuntime):
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


def dashboard_payload_action(conn, student: dict[str, Any], course_id: str='', enrollment_id: str='', *, runtime: LearningRuntime):
    public_course = runtime.public_course
    public_course_offering = runtime.public_course_offering
    public_course_version = runtime.public_course_version
    public_enrollment = runtime.public_enrollment
    public_lesson = runtime.public_lesson
    public_progress = runtime.public_progress
    public_student = runtime.public_student
    resolve_student_enrollment_with_conn = runtime.resolve_student_enrollment_with_conn
    str_value = runtime.str_value
    student_attempt = runtime.student_attempt
    enrollment = resolve_student_enrollment_with_conn(
        conn, student["student_id"], course_id, enrollment_id
    )
    course = conn.execute(
        "select * from courseplatform.courses where course_id = %s",
        (enrollment["course_id"],),
    ).fetchone()
    version = conn.execute(
        "select * from courseplatform.course_versions where course_version_id = %s",
        (enrollment["course_version_id"],),
    ).fetchone()
    offering = conn.execute(
        "select * from courseplatform.course_offerings where offering_id = %s",
        (enrollment["offering_id"],),
    ).fetchone()
    if not course or not version or not offering:
        raise ApiError("ENROLLMENT_STRUCTURE_INVALID", "A matrícula não está ligada a uma edição válida.")
    snapshot = version.get("content_snapshot_json") or {}
    snapshot_lessons = snapshot.get("lessons") if isinstance(snapshot, dict) else []
    if not isinstance(snapshot_lessons, list):
        snapshot_lessons = []
    lesson_ids = [str_value(item.get("lesson_id")) for item in snapshot_lessons if isinstance(item, dict)]
    progress_rows = []
    if lesson_ids:
        progress_rows = conn.execute(
            """
            select p.*,
                   a.attempt_id, a.attempt_number, a.started_at as attempt_started_at,
                   a.deadline_at, a.submitted_at as attempt_submitted_at,
                   a.status as attempt_status, a.score as attempt_score,
                   a.reviewed_at, a.review_comments, a.retry_authorized
            from courseplatform.lesson_progress p
            left join lateral (
              select * from courseplatform.attempts a
              where a.progress_id = p.progress_id
              order by coalesce(a.started_at, a.created_at) desc nulls last
              limit 1
            ) a on true
            where p.enrollment_id = %s and p.lesson_id = any(%s)
            """,
            (enrollment["enrollment_id"], lesson_ids),
        ).fetchall()
    progress_by_lesson = {row["lesson_id"]: row for row in progress_rows}
    version_course = {
        **course,
        "title": version.get("title") or course.get("title"),
        "description": version.get("description") or course.get("description"),
        "total_hours": version.get("total_hours"),
        "passing_score": version.get("passing_score"),
    }
    return {
        "student": public_student(student),
        "course": public_course(version_course),
        "courseVersion": public_course_version(version),
        "offering": public_course_offering(offering),
        "enrollment": public_enrollment(enrollment),
        "lessons": [
            {
                "lesson": public_lesson(lesson),
                "progress": public_progress({
                    "progress_id": progress_by_lesson.get(lesson.get("lesson_id"), {}).get("progress_id"),
                    "lesson_id": lesson.get("lesson_id"),
                    "status": progress_by_lesson.get(lesson.get("lesson_id"), {}).get("status") or "LOCKED",
                    "content_access_status": progress_by_lesson.get(lesson.get("lesson_id"), {}).get("content_access_status"),
                    "evaluation_status": progress_by_lesson.get(lesson.get("lesson_id"), {}).get("evaluation_status"),
                    "score": progress_by_lesson.get(lesson.get("lesson_id"), {}).get("score"),
                    "attempt_count": progress_by_lesson.get(lesson.get("lesson_id"), {}).get("attempt_count"),
                    "unlocked_at": progress_by_lesson.get(lesson.get("lesson_id"), {}).get("unlocked_at"),
                    "started_at": progress_by_lesson.get(lesson.get("lesson_id"), {}).get("started_at"),
                    "submitted_at": progress_by_lesson.get(lesson.get("lesson_id"), {}).get("submitted_at"),
                    "approved_at": progress_by_lesson.get(lesson.get("lesson_id"), {}).get("approved_at"),
                }),
                "activeAttempt": student_attempt({
                    "attempt_id": progress_by_lesson.get(lesson.get("lesson_id"), {}).get("attempt_id"),
                    "progress_id": progress_by_lesson.get(lesson.get("lesson_id"), {}).get("progress_id"),
                    "lesson_id": lesson.get("lesson_id"),
                    "attempt_number": progress_by_lesson.get(lesson.get("lesson_id"), {}).get("attempt_number"),
                    "started_at": progress_by_lesson.get(lesson.get("lesson_id"), {}).get("attempt_started_at"),
                    "deadline_at": progress_by_lesson.get(lesson.get("lesson_id"), {}).get("deadline_at"),
                    "submitted_at": progress_by_lesson.get(lesson.get("lesson_id"), {}).get("attempt_submitted_at"),
                    "status": progress_by_lesson.get(lesson.get("lesson_id"), {}).get("attempt_status"),
                    "score": progress_by_lesson.get(lesson.get("lesson_id"), {}).get("attempt_score"),
                    "reviewed_at": progress_by_lesson.get(lesson.get("lesson_id"), {}).get("reviewed_at"),
                    "review_comments": progress_by_lesson.get(lesson.get("lesson_id"), {}).get("review_comments"),
                    "retry_authorized": progress_by_lesson.get(lesson.get("lesson_id"), {}).get("retry_authorized"),
                }) if progress_by_lesson.get(lesson.get("lesson_id"), {}).get("attempt_id") else None,
            }
            for lesson in snapshot_lessons
            if isinstance(lesson, dict) and str_value(lesson.get("status") or "ACTIVE").upper() == "ACTIVE"
        ],
    }


def student_home_action(payload: dict[str, Any], *, runtime: LearningRuntime):
    connection = runtime.connection
    dashboard_payload = runtime.dashboard_payload
    get_settings = runtime.get_settings
    prepare_assessment_feature_schema = runtime.prepare_assessment_feature_schema
    public_student = runtime.public_student
    read_media_config_with_conn = runtime.read_media_config_with_conn
    require_session_token = runtime.require_session_token
    str_value = runtime.str_value
    student_context_with_conn = runtime.student_context_with_conn
    student_courses_payload = runtime.student_courses_payload
    student_courses_rows = runtime.student_courses_rows
    student_visible_media = runtime.student_visible_media
    success = runtime.success
    require_session_token(payload)
    prepare_assessment_feature_schema()
    with connection() as conn:
        _, student = student_context_with_conn(conn, payload)
        course_rows = student_courses_rows(conn, student["student_id"])
        courses = student_courses_payload(course_rows)
        requested_enrollment_id = str_value(payload.get("enrollmentId"))
        requested_course_id = payload.get("courseId") or get_settings().default_course_id
        selected_entry = next(
            (item for item in courses if item.get("enrollment", {}).get("enrollmentId") == requested_enrollment_id),
            None,
        )
        if not selected_entry:
            selected_entry = next(
                (item for item in courses if item.get("course", {}).get("courseId") == requested_course_id),
                courses[0] if courses else None,
            )
        selected_enrollment_id = selected_entry.get("enrollment", {}).get("enrollmentId") if selected_entry else ""
        selected_course_id = selected_entry.get("course", {}).get("courseId") if selected_entry else requested_course_id
        dashboard_data = dashboard_payload(conn, student, selected_course_id, selected_enrollment_id)
        media = read_media_config_with_conn(conn, selected_course_id)
    return success({
        "student": public_student(student),
        "courses": courses,
        "selectedCourseId": selected_course_id,
        "selectedEnrollmentId": selected_enrollment_id,
        "dashboard": dashboard_data,
        "mediaConfig": student_visible_media(media, student),
    })


def dashboard_action(payload: dict[str, Any], *, runtime: LearningRuntime):
    connection = runtime.connection
    dashboard_payload = runtime.dashboard_payload
    get_settings = runtime.get_settings
    prepare_assessment_feature_schema = runtime.prepare_assessment_feature_schema
    str_value = runtime.str_value
    student_context = runtime.student_context
    success = runtime.success
    _, student = student_context(payload)
    course_id = payload.get("courseId") or get_settings().default_course_id
    enrollment_id = str_value(payload.get("enrollmentId"))
    prepare_assessment_feature_schema()
    with connection() as conn:
        return success(dashboard_payload(conn, student, course_id, enrollment_id))


def get_lesson_action(payload: dict[str, Any], *, runtime: LearningRuntime):
    connection = runtime.connection
    prepare_assessment_feature_schema = runtime.prepare_assessment_feature_schema
    progress_access_status = runtime.progress_access_status
    public_content = runtime.public_content
    public_course_version = runtime.public_course_version
    public_enrollment = runtime.public_enrollment
    public_lesson = runtime.public_lesson
    public_progress = runtime.public_progress
    require_fields = runtime.require_fields
    resolve_student_enrollment_with_conn = runtime.resolve_student_enrollment_with_conn
    str_value = runtime.str_value
    student_context = runtime.student_context
    student_option = runtime.student_option
    student_question = runtime.student_question
    success = runtime.success
    _, student = student_context(payload)
    require_fields(payload, ["lessonId"])
    prepare_assessment_feature_schema()
    lesson_id = payload["lessonId"]
    enrollment_id = str_value(payload.get("enrollmentId"))
    with connection() as conn:
        live_lesson = conn.execute(
            "select course_id from courseplatform.lessons where lesson_id = %s",
            (lesson_id,),
        ).fetchone()
        course_id = live_lesson.get("course_id") if live_lesson else ""
        enrollment = resolve_student_enrollment_with_conn(
            conn, student["student_id"], course_id, enrollment_id
        )
        version = conn.execute(
            "select * from courseplatform.course_versions where course_version_id = %s",
            (enrollment["course_version_id"],),
        ).fetchone()
        snapshot = (version or {}).get("content_snapshot_json") or {}
        snapshot_lessons = snapshot.get("lessons") if isinstance(snapshot, dict) else []
        lesson = next(
            (
                item for item in snapshot_lessons
                if isinstance(item, dict) and item.get("lesson_id") == lesson_id
            ),
            None,
        )
        if not lesson:
            raise ApiError("LESSON_NOT_FOUND", "Módulo não encontrado nesta edição do curso.")
        progress = conn.execute(
            """
            select * from courseplatform.lesson_progress
            where enrollment_id = %s and lesson_id = %s
            """,
            (enrollment["enrollment_id"], lesson_id),
        ).fetchone()
    if not progress or progress_access_status(progress) != "AVAILABLE":
        raise ApiError("LESSON_LOCKED", "Este módulo ainda não está disponível para leitura.")
    content = [
        row for row in (lesson.get("content") or [])
        if isinstance(row, dict) and str_value(row.get("status") or "ACTIVE").upper() == "ACTIVE"
    ]
    questions = [
        row for row in (lesson.get("questions") or [])
        if isinstance(row, dict) and str_value(row.get("status") or "ACTIVE").upper() == "ACTIVE"
    ]
    return success({
        "lesson": public_lesson(lesson),
        "enrollment": public_enrollment(enrollment),
        "courseVersion": public_course_version(version),
        "progress": public_progress(progress or {
            "progress_id": "",
            "lesson_id": lesson_id,
            "status": "LOCKED",
            "attempt_count": 0,
        }),
        "content": [public_content(row) for row in content],
        "questions": [
            {
                **student_question(question),
                "options": [student_option(option) for option in question.get("options", [])],
            }
            for question in questions
        ],
    })


def admin_set_lesson_access_action(payload: dict[str, Any], *, runtime: LearningRuntime):
    CONTENT_ACCESS_STATUSES = runtime.CONTENT_ACCESS_STATUSES
    admin_context = runtime.admin_context
    audit = runtime.audit
    connection = runtime.connection
    create_student_notification = runtime.create_student_notification
    dispatch_notification_deliveries = runtime.dispatch_notification_deliveries
    ensure_offering_enrollment_with_conn = runtime.ensure_offering_enrollment_with_conn
    fetch_all = runtime.fetch_all
    generate_id = runtime.generate_id
    notification_status_label = runtime.notification_status_label
    prepare_assessment_feature_schema = runtime.prepare_assessment_feature_schema
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    progress_access_status = runtime.progress_access_status
    resolve_course_offering_with_conn = runtime.resolve_course_offering_with_conn
    str_value = runtime.str_value
    success = runtime.success
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    prepare_assessment_feature_schema()
    prepare_notification_feature_schema()
    status = str_value(payload.get("status") or "AVAILABLE").upper()
    if status not in CONTENT_ACCESS_STATUSES:
        raise ApiError("INVALID_STATUS", "Estado de acesso inválido.")
    lesson_ids = payload.get("lessonIds") if isinstance(payload.get("lessonIds"), list) else []
    student_ids = set(payload.get("studentIds") if isinstance(payload.get("studentIds"), list) else [])
    group_ids = payload.get("groupIds") if isinstance(payload.get("groupIds"), list) else []
    offering_id = str_value(payload.get("offeringId"))
    if group_ids:
        rows = fetch_all(
            """
            select gm.student_id, g.offering_id
            from courseplatform.group_members gm
            join courseplatform.groups g on g.group_id = gm.group_id
            where gm.group_id = any(%s) and gm.status = 'ACTIVE'
            """,
            (group_ids,),
        )
        student_ids.update(row["student_id"] for row in rows)
        offering_ids = {row.get("offering_id") for row in rows if row.get("offering_id")}
        if offering_id and offering_ids and offering_ids != {offering_id}:
            raise ApiError("GROUP_OFFERING_MISMATCH", "Os grupos não pertencem à edição selecionada.")
        if not offering_id and len(offering_ids) == 1:
            offering_id = next(iter(offering_ids))
        if len(offering_ids) > 1:
            raise ApiError("OFFERING_REQUIRED", "Selecione grupos de uma única edição/turma.")
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
                offering = resolve_course_offering_with_conn(
                    conn, lesson["course_id"], offering_id
                )
                enrollment = ensure_offering_enrollment_with_conn(
                    conn, student_id, offering
                )
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


def admin_manage_lesson_progress_action(payload: dict[str, Any], *, runtime: LearningRuntime):
    ATTEMPT_STATUSES = runtime.ATTEMPT_STATUSES
    CONTENT_ACCESS_STATUSES = runtime.CONTENT_ACCESS_STATUSES
    EVALUATION_STATUSES = runtime.EVALUATION_STATUSES
    admin_context = runtime.admin_context
    audit = runtime.audit
    connection = runtime.connection
    create_student_notification = runtime.create_student_notification
    dispatch_notification_deliveries = runtime.dispatch_notification_deliveries
    ensure_offering_enrollment_with_conn = runtime.ensure_offering_enrollment_with_conn
    generate_id = runtime.generate_id
    int_value = runtime.int_value
    legacy_progress_status = runtime.legacy_progress_status
    notification_status_label = runtime.notification_status_label
    prepare_assessment_feature_schema = runtime.prepare_assessment_feature_schema
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    progress_access_status = runtime.progress_access_status
    progress_evaluation_status = runtime.progress_evaluation_status
    refresh_enrollment_progress = runtime.refresh_enrollment_progress
    resolve_course_offering_with_conn = runtime.resolve_course_offering_with_conn
    str_value = runtime.str_value
    success = runtime.success
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    prepare_assessment_feature_schema()
    prepare_notification_feature_schema()
    lesson_ids = payload.get("lessonIds") if isinstance(payload.get("lessonIds"), list) else []
    student_ids = set(payload.get("studentIds") if isinstance(payload.get("studentIds"), list) else [])
    group_ids = payload.get("groupIds") if isinstance(payload.get("groupIds"), list) else []
    offering_id = str_value(payload.get("offeringId"))
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
                """
                select gm.student_id, g.offering_id
                from courseplatform.group_members gm
                join courseplatform.groups g on g.group_id = gm.group_id
                where gm.group_id = any(%s) and gm.status = 'ACTIVE'
                """,
                (group_ids,),
            ).fetchall()
            student_ids.update(row["student_id"] for row in rows)
            offering_ids = {row.get("offering_id") for row in rows if row.get("offering_id")}
            if offering_id and offering_ids and offering_ids != {offering_id}:
                raise ApiError("GROUP_OFFERING_MISMATCH", "Os grupos não pertencem à edição selecionada.")
            if not offering_id and len(offering_ids) == 1:
                offering_id = next(iter(offering_ids))
            if len(offering_ids) > 1:
                raise ApiError("OFFERING_REQUIRED", "Selecione grupos de uma única edição/turma.")
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
                offering = resolve_course_offering_with_conn(
                    conn, lesson["course_id"], offering_id
                )
                enrollment = ensure_offering_enrollment_with_conn(
                    conn, student_id, offering
                )
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
