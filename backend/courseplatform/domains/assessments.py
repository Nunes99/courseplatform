import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta, timezone
from typing import Any

from ..contracts import ApiError
from ..storage import StorageError


ACTION_BINDINGS = (
    ("adminListSubmissions", "admin_list_submissions"),
    ("adminListPendingSubmissions", "admin_list_submissions"),
    ("getAttemptStatus", "attempt_status"),
    ("startAttempt", "start_attempt"),
    ("saveAnswer", "save_answer"),
    ("uploadFile", "upload_file"),
    ("deleteUploadedFile", "delete_uploaded_file"),
    ("submitAttempt", "submit_attempt"),
    ("adminGetSubmission", "admin_get_submission"),
    ("adminReviewSubmission", "admin_review_submission"),
    ("adminAuthorizeRetry", "admin_authorize_retry"),
    ("adminUpdateAttempt", "admin_update_attempt"),
)


@dataclass(frozen=True)
class AssessmentRuntime:
    ATTEMPT_STATUSES: Any
    CONTENT_ACCESS_STATUSES: Any
    _private_content_payload: Callable[..., Any]
    admin_context: Callable[..., Any]
    admin_review_submission: Callable[..., Any]
    as_bool: Callable[..., Any]
    assessment_snapshot_from_version_lesson: Callable[..., Any]
    audit: Callable[..., Any]
    connection: Callable[..., Any]
    correction_deadline: Callable[..., Any]
    create_student_notification: Callable[..., Any]
    cursor_page_limit: Callable[..., Any]
    cursor_pagination_result: Callable[..., Any]
    cursor_scope: Callable[..., Any]
    decode_list_cursor: Callable[..., Any]
    dispatch_notification_deliveries: Callable[..., Any]
    editable_attempt: Callable[..., Any]
    expire_attempt_if_needed: Callable[..., Any]
    expire_overdue_attempts: Callable[..., Any]
    feedback_policy: Callable[..., Any]
    feedback_visibility: Callable[..., Any]
    fetch_all: Callable[..., Any]
    fetch_one: Callable[..., Any]
    float_value: Callable[..., Any]
    generate_id: Callable[..., Any]
    get_settings: Callable[..., Any]
    grade_objective_answers: Callable[..., Any]
    int_value: Callable[..., Any]
    iso: Callable[..., Any]
    legacy_progress_status: Callable[..., Any]
    notification_status_label: Callable[..., Any]
    parse_assessment_snapshot: Callable[..., Any]
    parse_datetime: Callable[..., Any]
    prepare_assessment_feature_schema: Callable[..., Any]
    prepare_notification_feature_schema: Callable[..., Any]
    progress_access_status: Callable[..., Any]
    progress_evaluation_status: Callable[..., Any]
    public_file: Callable[..., Any]
    public_lesson: Callable[..., Any]
    public_progress: Callable[..., Any]
    public_review: Callable[..., Any]
    public_student: Callable[..., Any]
    refresh_enrollment_progress: Callable[..., Any]
    require_fields: Callable[..., Any]
    require_latest_attempt: Callable[..., Any]
    selected_option_ids: Callable[..., Any]
    selected_option_storage: Callable[..., Any]
    snapshot_for_attempt_with_conn: Callable[..., Any]
    staff_answer: Callable[..., Any]
    staff_attempt: Callable[..., Any]
    staff_option: Callable[..., Any]
    staff_question: Callable[..., Any]
    start_attempt_with_conn: Callable[..., Any]
    storage_api_error: Callable[..., Any]
    storage_object_path: Callable[..., Any]
    str_value: Callable[..., Any]
    student_answer: Callable[..., Any]
    student_attempt: Callable[..., Any]
    student_context: Callable[..., Any]
    student_review: Callable[..., Any]
    student_snapshot_questions: Callable[..., Any]
    submission_item: Callable[..., Any]
    success: Callable[..., Any]
    upload_private_object: Callable[..., Any]
    utc_now: Callable[..., Any]
    validate_upload: Callable[..., Any]


def attempt_status_action(payload: dict[str, Any], runtime: AssessmentRuntime):
    connection = runtime.connection
    expire_attempt_if_needed = runtime.expire_attempt_if_needed
    feedback_policy = runtime.feedback_policy
    feedback_visibility = runtime.feedback_visibility
    fetch_one = runtime.fetch_one
    prepare_assessment_feature_schema = runtime.prepare_assessment_feature_schema
    public_file = runtime.public_file
    require_fields = runtime.require_fields
    snapshot_for_attempt_with_conn = runtime.snapshot_for_attempt_with_conn
    student_answer = runtime.student_answer
    student_attempt = runtime.student_attempt
    student_context = runtime.student_context
    student_review = runtime.student_review
    student_snapshot_questions = runtime.student_snapshot_questions
    success = runtime.success
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
    with connection() as conn:
        answers = conn.execute(
            "select * from courseplatform.answers where attempt_id = %s order by saved_at",
            (attempt["attempt_id"],),
        ).fetchall()
        files = conn.execute(
            """
            select *
            from courseplatform.files
            where attempt_id = %s and coalesce(status, 'ACTIVE') <> 'DELETED'
            order by uploaded_at
            """,
            (attempt["attempt_id"],),
        ).fetchall()
        latest_review = conn.execute(
            """
            select *
            from courseplatform.reviews
            where attempt_id = %s
            order by reviewed_at desc nulls last
            limit 1
            """,
            (attempt["attempt_id"],),
        ).fetchone()
        snapshot = snapshot_for_attempt_with_conn(conn, attempt)
    reveal_answers, reveal_explanations = feedback_visibility(attempt, snapshot)
    policy = feedback_policy(snapshot.get("feedbackPolicy"))
    return success({
        "attempt": student_attempt(attempt),
        "questions": student_snapshot_questions(attempt, snapshot),
        "answers": [student_answer(row, reveal_answers=reveal_answers) for row in answers],
        "files": [public_file(row) for row in files],
        "latestReview": student_review(latest_review) if attempt.get("submitted_at") or attempt.get("reviewed_at") else None,
        "feedbackPolicy": {
            "releaseMode": policy["releaseMode"],
            "correctAnswersVisible": reveal_answers,
            "explanationsVisible": reveal_explanations,
        },
    })


def start_attempt_action(payload: dict[str, Any], runtime: AssessmentRuntime):
    connection = runtime.connection
    prepare_assessment_feature_schema = runtime.prepare_assessment_feature_schema
    require_fields = runtime.require_fields
    start_attempt_with_conn = runtime.start_attempt_with_conn
    str_value = runtime.str_value
    student_context = runtime.student_context
    _, student = student_context(payload)
    require_fields(payload, ["lessonId"])
    prepare_assessment_feature_schema()
    lesson_id = payload["lessonId"]
    enrollment_id = str_value(payload.get("enrollmentId"))
    with connection() as conn:
        return start_attempt_with_conn(conn, student, lesson_id, enrollment_id)


def start_attempt_with_conn_action(conn, student, lesson_id, enrollment_id: str = "", *, runtime: AssessmentRuntime):
    as_bool = runtime.as_bool
    assessment_snapshot_from_version_lesson = runtime.assessment_snapshot_from_version_lesson
    audit = runtime.audit
    editable_attempt = runtime.editable_attempt
    generate_id = runtime.generate_id
    int_value = runtime.int_value
    iso = runtime.iso
    parse_assessment_snapshot = runtime.parse_assessment_snapshot
    parse_datetime = runtime.parse_datetime
    progress_access_status = runtime.progress_access_status
    progress_evaluation_status = runtime.progress_evaluation_status
    student_attempt = runtime.student_attempt
    success = runtime.success
    utc_now = runtime.utc_now
    # Serialize starts and consume each retry permission only once.
    if enrollment_id:
        progress = conn.execute(
            """
            select p.*, l.exercise_minutes, l.individual_minutes, l.submission_duration_minutes,
                   l.feedback_release_mode, l.show_correct_answers, l.show_explanations
            from courseplatform.lesson_progress p
            join courseplatform.lessons l on l.lesson_id = p.lesson_id
            where p.student_id = %s and p.lesson_id = %s and p.enrollment_id = %s
            for update of p
            """,
            (student["student_id"], lesson_id, enrollment_id),
        ).fetchone()
    else:
        matches = conn.execute(
            """
            select p.*, l.exercise_minutes, l.individual_minutes, l.submission_duration_minutes,
                   l.feedback_release_mode, l.show_correct_answers, l.show_explanations
            from courseplatform.lesson_progress p
            join courseplatform.lessons l on l.lesson_id = p.lesson_id
            where p.student_id = %s and p.lesson_id = %s
            order by p.updated_at desc nulls last
            limit 2
            for update of p
            """,
            (student["student_id"], lesson_id),
        ).fetchall()
        if len(matches) > 1:
            raise ApiError("ENROLLMENT_REQUIRED", "Selecione a matrícula/edição antes de iniciar a atividade.")
        progress = matches[0] if matches else None
    if not progress or progress_access_status(progress) != "AVAILABLE":
        raise ApiError("LESSON_LOCKED", "Este módulo ainda não está disponível.")
    if progress_evaluation_status(progress) not in {"NOT_STARTED", "IN_PROGRESS", "CORRECTION_REQUIRED", "FAILED", "TIME_EXCEEDED"}:
        raise ApiError("ATTEMPT_NOT_AVAILABLE", "Não é possível iniciar uma tentativa neste estado.")

    existing = conn.execute(
        """
        select *
        from courseplatform.attempts
        where progress_id = %s
        order by attempt_number desc, created_at desc
        limit 1
        for update
        """,
        (progress["progress_id"],),
    ).fetchone()
    if existing and existing.get("status") == "IN_PROGRESS":
        editable_attempt(conn, existing["attempt_id"], student["student_id"])
        return success({"attempt": student_attempt(existing)})

    now = utc_now()
    minutes = int_value(progress.get("submission_duration_minutes"))
    if minutes <= 0:
        minutes = int_value(progress.get("exercise_minutes")) + int_value(progress.get("individual_minutes"))
    if minutes <= 0:
        minutes = 180
    deadline = now + timedelta(minutes=minutes)
    is_retry = bool(existing and progress_evaluation_status(progress) != "NOT_STARTED")
    if is_retry:
        if not as_bool(existing.get("retry_authorized")):
            raise ApiError("RETRY_NOT_AUTHORIZED", "A administração precisa de autorizar um novo envio.")
        review = conn.execute(
            """select correction_deadline from courseplatform.reviews
               where attempt_id = %s order by reviewed_at desc nulls last limit 1""",
            (existing["attempt_id"],),
        ).fetchone()
        if review and review.get("correction_deadline"):
            deadline = parse_datetime(review["correction_deadline"])
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
        if deadline <= now:
            raise ApiError("RETRY_DEADLINE_EXPIRED", "O prazo autorizado para o novo envio terminou. Solicite um novo prazo à administração.")
    attempt_number = int_value(progress.get("attempt_count")) + 1
    if existing:
        attempt_number = max(attempt_number, int_value(existing.get("attempt_number")) + 1)
    existing_snapshot = parse_assessment_snapshot((existing or {}).get("assessment_snapshot_json"))
    if is_retry and isinstance(existing_snapshot.get("questions"), list):
        snapshot = existing_snapshot
    else:
        version_row = conn.execute(
            """
            select cv.content_snapshot_json
            from courseplatform.enrollments e
            join courseplatform.course_versions cv on cv.course_version_id = e.course_version_id
            where e.enrollment_id = %s
            """,
            (progress["enrollment_id"],),
        ).fetchone()
        version_snapshot = (version_row or {}).get("content_snapshot_json") or {}
        version_lesson = next(
            (
                item for item in version_snapshot.get("lessons", [])
                if isinstance(item, dict) and item.get("lesson_id") == lesson_id
            ),
            None,
        )
        if not version_lesson:
            raise ApiError("LESSON_VERSION_MISMATCH", "O módulo não pertence à versão desta matrícula.")
        snapshot = assessment_snapshot_from_version_lesson(version_lesson)
    attempt = conn.execute(
        """
        insert into courseplatform.attempts
          (attempt_id, progress_id, student_id, lesson_id, attempt_number, started_at,
           deadline_at, submitted_at, status, score, objective_score, assessment_snapshot_json,
           retry_authorized, created_at, updated_at)
        values (%s, %s, %s, %s, %s, %s, %s, null, 'IN_PROGRESS', null, null, %s, false, %s, %s)
        returning *
        """,
        (
            generate_id("ATT"), progress["progress_id"], student["student_id"], lesson_id,
            attempt_number, now, deadline,
            json.dumps(snapshot, ensure_ascii=True, separators=(",", ":")),
            now, now,
        ),
    ).fetchone()
    if is_retry:
        conn.execute(
            "update courseplatform.attempts set retry_authorized = false, updated_at = %s where attempt_id = %s",
            (now, existing["attempt_id"]),
        )
        conn.execute(
            """insert into courseplatform.answers
               (answer_id, attempt_id, question_id, answer_text, selected_option_id, saved_at)
               select 'ANS-' || %s || '-' || question_id, %s, question_id,
                      answer_text, selected_option_id, %s
               from courseplatform.answers where attempt_id = %s""",
            (attempt["attempt_id"], attempt["attempt_id"], now, existing["attempt_id"]),
        )
    conn.execute(
        """
        update courseplatform.lesson_progress
        set status = 'IN_PROGRESS', evaluation_status = 'IN_PROGRESS',
            content_access_status = coalesce(content_access_status, 'AVAILABLE'),
            started_at = coalesce(started_at, %s),
            attempt_count = %s, submitted_at = null, approved_at = null, score = null, updated_at = %s
        where progress_id = %s
        """,
        (now, attempt_number, now, progress["progress_id"]),
    )
    audit(conn, "STUDENT", student["student_id"], "ATTEMPT_STARTED", "ATTEMPT", attempt["attempt_id"], {
        "previousAttemptId": existing["attempt_id"] if is_retry else None,
        "deadlineAt": iso(deadline),
    })
    conn.commit()
    return success({"attempt": student_attempt(attempt)})


def save_answer_action(payload: dict[str, Any], runtime: AssessmentRuntime):
    connection = runtime.connection
    editable_attempt = runtime.editable_attempt
    generate_id = runtime.generate_id
    prepare_assessment_feature_schema = runtime.prepare_assessment_feature_schema
    require_fields = runtime.require_fields
    selected_option_ids = runtime.selected_option_ids
    selected_option_storage = runtime.selected_option_storage
    snapshot_for_attempt_with_conn = runtime.snapshot_for_attempt_with_conn
    str_value = runtime.str_value
    student_answer = runtime.student_answer
    student_context = runtime.student_context
    success = runtime.success
    _, student = student_context(payload)
    require_fields(payload, ["attemptId", "questionId"])
    prepare_assessment_feature_schema()
    with connection() as conn:
        attempt = editable_attempt(conn, payload["attemptId"], student["student_id"])
        snapshot = snapshot_for_attempt_with_conn(conn, attempt)
        question = next(
            (
                item for item in snapshot.get("questions", [])
                if isinstance(item, dict) and item.get("question_id") == payload["questionId"]
            ),
            None,
        )
        if not question:
            raise ApiError("QUESTION_NOT_FOUND", "Questão não encontrada neste módulo.")
        question_type = str_value(question.get("question_type")).upper()
        selected_options = selected_option_ids(payload.get("selectedOptionId"))
        valid_option_ids = {
            str_value(option.get("option_id"))
            for option in question.get("options", [])
            if isinstance(option, dict)
        }
        if any(option_id not in valid_option_ids for option_id in selected_options):
            raise ApiError("INVALID_ANSWER_OPTION", "A resposta contém uma opção que não pertence a esta questão.")
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
                selected_option_storage(payload.get("selectedOptionId"), question_type),
            ),
        ).fetchone()
        conn.commit()
    return success({"answer": student_answer(answer)})


def upload_file_action(payload: dict[str, Any], runtime: AssessmentRuntime):
    audit = runtime.audit
    connection = runtime.connection
    editable_attempt = runtime.editable_attempt
    generate_id = runtime.generate_id
    get_settings = runtime.get_settings
    prepare_assessment_feature_schema = runtime.prepare_assessment_feature_schema
    public_file = runtime.public_file
    require_fields = runtime.require_fields
    storage_api_error = runtime.storage_api_error
    storage_object_path = runtime.storage_object_path
    student_context = runtime.student_context
    success = runtime.success
    upload_private_object = runtime.upload_private_object
    validate_upload = runtime.validate_upload
    _, student = student_context(payload)
    require_fields(payload, ["attemptId", "fileName"])
    prepare_assessment_feature_schema()
    with connection() as conn:
        attempt = editable_attempt(conn, payload["attemptId"], student["student_id"])
    try:
        upload = validate_upload(
            payload.get("base64Data"),
            payload.get("fileName"),
            payload.get("mimeType"),
            purpose="SUBMISSION",
        )
    except StorageError as error:
        raise storage_api_error(error) from error

    settings = get_settings()
    object_path = storage_object_path("submission", student["student_id"], attempt["attempt_id"], upload)
    upload_key = hashlib.sha256(
        f"{student['student_id']}:{attempt['attempt_id']}:{upload.checksum_sha256}".encode("utf-8")
    ).hexdigest()
    try:
        upload_private_object(settings.supabase_submission_bucket, object_path, upload)
    except StorageError as error:
        raise storage_api_error(error) from error

    with connection() as conn:
        attempt = editable_attempt(conn, payload["attemptId"], student["student_id"])
        row = conn.execute(
            """
            insert into courseplatform.files
              (file_id, attempt_id, student_id, lesson_id, file_name, mime_type,
               size_bytes, drive_file_id, drive_url, storage_bucket, storage_path,
               storage_checksum_sha256, storage_status, storage_upload_key, uploaded_at, status)
            values (%s, %s, %s, %s, %s, %s, %s, '', '', %s, %s, %s, 'READY', %s, now(), 'ACTIVE')
            on conflict (storage_upload_key) where storage_upload_key is not null do update
            set file_name = excluded.file_name,
                mime_type = excluded.mime_type,
                size_bytes = excluded.size_bytes,
                storage_bucket = excluded.storage_bucket,
                storage_path = excluded.storage_path,
                storage_checksum_sha256 = excluded.storage_checksum_sha256,
                storage_status = 'READY',
                uploaded_at = now(),
                status = 'ACTIVE'
            returning *
            """,
            (
                generate_id("FIL"),
                attempt["attempt_id"],
                student["student_id"],
                attempt["lesson_id"],
                upload.file_name,
                upload.mime_type,
                upload.size_bytes,
                settings.supabase_submission_bucket,
                object_path,
                upload.checksum_sha256,
                upload_key,
            ),
        ).fetchone()
        audit(
            conn,
            "STUDENT",
            student["student_id"],
            "SUBMISSION_FILE_UPLOADED",
            "FILE",
            row["file_id"],
            {"attemptId": attempt["attempt_id"], "sizeBytes": upload.size_bytes, "mimeType": upload.mime_type},
        )
        conn.commit()
    return success({"file": public_file(row)})


def delete_uploaded_file_action(payload: dict[str, Any], runtime: AssessmentRuntime):
    connection = runtime.connection
    editable_attempt = runtime.editable_attempt
    prepare_assessment_feature_schema = runtime.prepare_assessment_feature_schema
    public_file = runtime.public_file
    require_fields = runtime.require_fields
    student_context = runtime.student_context
    success = runtime.success
    _, student = student_context(payload)
    require_fields(payload, ["fileId"])
    prepare_assessment_feature_schema()
    with connection() as conn:
        file = conn.execute(
            "select attempt_id from courseplatform.files where file_id = %s and student_id = %s",
            (payload["fileId"], student["student_id"]),
        ).fetchone()
        if not file:
            raise ApiError("FILE_NOT_FOUND", "Ficheiro não encontrado.")
        editable_attempt(conn, file["attempt_id"], student["student_id"])
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


def submit_attempt_action(payload: dict[str, Any], runtime: AssessmentRuntime):
    audit = runtime.audit
    connection = runtime.connection
    editable_attempt = runtime.editable_attempt
    grade_objective_answers = runtime.grade_objective_answers
    prepare_assessment_feature_schema = runtime.prepare_assessment_feature_schema
    require_fields = runtime.require_fields
    snapshot_for_attempt_with_conn = runtime.snapshot_for_attempt_with_conn
    student_attempt = runtime.student_attempt
    student_context = runtime.student_context
    success = runtime.success
    utc_now = runtime.utc_now
    _, student = student_context(payload)
    require_fields(payload, ["attemptId"])
    prepare_assessment_feature_schema()
    now = utc_now()
    status = "UNDER_REVIEW"
    with connection() as conn:
        attempt = editable_attempt(conn, payload["attemptId"], student["student_id"])
        snapshot = snapshot_for_attempt_with_conn(conn, attempt)
        answers = conn.execute(
            "select * from courseplatform.answers where attempt_id = %s for update",
            (attempt["attempt_id"],),
        ).fetchall()
        objective_score, graded_answers = grade_objective_answers(snapshot, answers)
        conn.execute(
            "update courseplatform.answers set submitted_at = %s where attempt_id = %s",
            (now, attempt["attempt_id"]),
        )
        for is_correct, awarded_points, answer_id in graded_answers:
            conn.execute(
                """update courseplatform.answers
                   set is_correct = %s, awarded_points = %s, submitted_at = %s
                   where answer_id = %s and attempt_id = %s""",
                (is_correct, awarded_points, now, answer_id, attempt["attempt_id"]),
            )
        updated = conn.execute(
            """
            update courseplatform.attempts
            set status = %s, submitted_at = %s, objective_score = %s, updated_at = %s
            where attempt_id = %s
            returning *
            """,
            (status, now, objective_score, now, attempt["attempt_id"]),
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
    return success({"attempt": student_attempt(updated)})


def submission_file_download_payload_action(payload: dict[str, Any], runtime: AssessmentRuntime) -> dict[str, Any]:
    _private_content_payload = runtime._private_content_payload
    admin_context = runtime.admin_context
    fetch_one = runtime.fetch_one
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    student_context = runtime.student_context
    require_fields(payload, ["fileId"])
    if str_value(payload.get("adminToken")):
        admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
        row = fetch_one(
            "select * from courseplatform.files where file_id = %s and coalesce(status, 'ACTIVE') <> 'DELETED'",
            (payload["fileId"],),
        )
    else:
        _, student = student_context(payload)
        row = fetch_one(
            """select * from courseplatform.files
               where file_id = %s and student_id = %s and coalesce(status, 'ACTIVE') <> 'DELETED'""",
            (payload["fileId"], student["student_id"]),
        )
    if not row:
        raise ApiError("FILE_NOT_FOUND", "Ficheiro não encontrado.")
    return _private_content_payload(
        row,
        bucket_field="storage_bucket",
        path_field="storage_path",
        checksum_field="storage_checksum_sha256",
        status_field="storage_status",
        legacy_url_field="drive_url",
        file_name_field="file_name",
        mime_type_field="mime_type",
        size_field="size_bytes",
    )


def admin_list_submissions_action(payload: dict[str, Any], runtime: AssessmentRuntime):
    admin_context = runtime.admin_context
    cursor_page_limit = runtime.cursor_page_limit
    cursor_pagination_result = runtime.cursor_pagination_result
    cursor_scope = runtime.cursor_scope
    decode_list_cursor = runtime.decode_list_cursor
    expire_overdue_attempts = runtime.expire_overdue_attempts
    fetch_all = runtime.fetch_all
    submission_item = runtime.submission_item
    success = runtime.success
    admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    expire_overdue_attempts()
    status = (payload.get("status") or "ALL").upper()
    query = (payload.get("query") or "").strip().lower()
    limit = cursor_page_limit(payload)
    scope = cursor_scope("admin-submissions", status, query)
    cursor = decode_list_cursor(payload.get("cursor"), "admin-submissions", scope)
    cursor_sql = ""
    cursor_params: list[Any] = []
    if cursor:
        cursor_at, cursor_id = cursor
        cursor_sql = """
          and (
            coalesce(a.submitted_at, a.started_at, a.created_at) < %s
            or (
              coalesce(a.submitted_at, a.started_at, a.created_at) = %s
              and a.attempt_id < %s
            )
          )
        """
        cursor_params.extend((cursor_at, cursor_at, cursor_id))
    rows = fetch_all(
        f"""
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
          coalesce(fc.file_count, 0) as file_count,
          coalesce(a.submitted_at, a.started_at, a.created_at) as pagination_sort_at
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
          {cursor_sql}
        order by coalesce(a.submitted_at, a.started_at, a.created_at) desc nulls last,
                 a.attempt_id desc
        limit %s
        """,
        (status, status, status, query, f"%{query}%", *cursor_params, limit + 1),
    )
    rows, page_info = cursor_pagination_result(
        rows,
        limit,
        "admin-submissions",
        scope,
        "pagination_sort_at",
        "attempt_id",
    )
    return success({
        "submissions": [submission_item(row) for row in rows],
        "pagination": page_info,
    })


def admin_get_submission_action(payload: dict[str, Any], runtime: AssessmentRuntime):
    admin_context = runtime.admin_context
    connection = runtime.connection
    fetch_all = runtime.fetch_all
    fetch_one = runtime.fetch_one
    prepare_assessment_feature_schema = runtime.prepare_assessment_feature_schema
    public_file = runtime.public_file
    public_lesson = runtime.public_lesson
    public_progress = runtime.public_progress
    public_review = runtime.public_review
    public_student = runtime.public_student
    require_fields = runtime.require_fields
    snapshot_for_attempt_with_conn = runtime.snapshot_for_attempt_with_conn
    staff_answer = runtime.staff_answer
    staff_attempt = runtime.staff_attempt
    staff_option = runtime.staff_option
    staff_question = runtime.staff_question
    success = runtime.success
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
    with connection() as conn:
        snapshot = snapshot_for_attempt_with_conn(conn, attempt)
    questions = [row for row in snapshot.get("questions", []) if isinstance(row, dict)]
    answers = fetch_all("select * from courseplatform.answers where attempt_id = %s", (attempt["attempt_id"],))
    answer_by_question = {row["question_id"]: row for row in answers}
    files = fetch_all(
        "select * from courseplatform.files where attempt_id = %s and coalesce(status, 'ACTIVE') <> 'DELETED' order by uploaded_at",
        (attempt["attempt_id"],),
    )
    reviews = fetch_all("select * from courseplatform.reviews where attempt_id = %s order by reviewed_at desc nulls last", (attempt["attempt_id"],))
    return success({
        "student": public_student(student or {"student_id": attempt["student_id"], "full_name": "Estudante sem cadastro", "email": "", "status": "UNKNOWN"}),
        "lesson": public_lesson(lesson or {"lesson_id": attempt["lesson_id"], "title": attempt["lesson_id"]}),
        "progress": public_progress(progress) if progress else None,
        "attempt": staff_attempt(attempt),
        "answers": [
            {
                "question": {
                    **staff_question(question),
                    "options": [staff_option(option) for option in question.get("options", [])],
                },
                "answer": staff_answer(answer_by_question.get(question["question_id"])) or {
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


def admin_review_submission_action(payload: dict[str, Any], runtime: AssessmentRuntime):
    admin_context = runtime.admin_context
    as_bool = runtime.as_bool
    audit = runtime.audit
    connection = runtime.connection
    correction_deadline = runtime.correction_deadline
    create_student_notification = runtime.create_student_notification
    dispatch_notification_deliveries = runtime.dispatch_notification_deliveries
    fetch_one = runtime.fetch_one
    float_value = runtime.float_value
    generate_id = runtime.generate_id
    iso = runtime.iso
    notification_status_label = runtime.notification_status_label
    prepare_assessment_feature_schema = runtime.prepare_assessment_feature_schema
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    public_review = runtime.public_review
    refresh_enrollment_progress = runtime.refresh_enrollment_progress
    require_fields = runtime.require_fields
    require_latest_attempt = runtime.require_latest_attempt
    staff_attempt = runtime.staff_attempt
    str_value = runtime.str_value
    success = runtime.success
    utc_now = runtime.utc_now
    _, admin = admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    require_fields(payload, ["attemptId", "decision"])
    prepare_assessment_feature_schema()
    prepare_notification_feature_schema()
    decision = str_value(payload.get("decision")).upper()
    if decision not in {"APPROVED", "APPROVED_WITH_NOTES", "CORRECTION_REQUIRED", "FAILED"}:
        raise ApiError("INVALID_DECISION", "Decisão inválida.")
    status = "APPROVED" if decision in {"APPROVED", "APPROVED_WITH_NOTES"} else decision
    authorize_retry = as_bool(payload.get("authorizeRetry", decision == "CORRECTION_REQUIRED"))
    if authorize_retry and decision not in {"CORRECTION_REQUIRED", "FAILED"}:
        raise ApiError("INVALID_RETRY_DECISION", "O reenvio só pode ser autorizado para trabalhos devolvidos ou não aprovados.")
    deadline = correction_deadline(payload) if authorize_retry else None
    if status != "CORRECTION_REQUIRED":
        require_fields(payload, ["score"])
    score = None if payload.get("score") in (None, "") else float_value(payload.get("score"))
    if score is not None and not 0 <= score <= 100:
        raise ApiError("INVALID_SCORE", "A classificação deve estar entre 0 e 100.")
    now = utc_now()
    attempt = fetch_one("select * from courseplatform.attempts where attempt_id = %s", (payload["attemptId"],))
    if not attempt:
        raise ApiError("ATTEMPT_NOT_FOUND", "Tentativa não encontrada.")
    notification_ids: list[str] = []
    with connection() as conn:
        conn.execute("select progress_id from courseplatform.lesson_progress where progress_id = %s for update", (attempt["progress_id"],)).fetchone()
        attempt = conn.execute("select * from courseplatform.attempts where attempt_id = %s for update", (attempt["attempt_id"],)).fetchone()
        require_latest_attempt(conn, attempt)
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
                deadline,
                status == "APPROVED",
                now,
            ),
        ).fetchone()
        updated = conn.execute(
            """
            update courseplatform.attempts
            set status = %s, score = %s, reviewer_id = %s, reviewed_at = %s,
                review_comments = %s, retry_authorized = %s, updated_at = %s
            where attempt_id = %s
            returning *
            """,
            (status, score, admin["admin_id"], now, str_value(payload.get("comments")), authorize_retry, now, attempt["attempt_id"]),
        ).fetchone()
        conn.execute(
            """
            update courseplatform.lesson_progress
            set status = %s, evaluation_status = %s,
                content_access_status = case when %s then 'AVAILABLE' else coalesce(content_access_status, 'AVAILABLE') end,
                approved_at = case when %s = 'APPROVED' then %s else null end,
                score = %s, updated_at = %s
            where progress_id = %s
            """,
            (status, status, authorize_retry, status, now, score, now, attempt.get("progress_id")),
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
        if authorize_retry:
            message = f"{message} Novo envio autorizado até {iso(deadline)}. As respostas anteriores serão preservadas; carregue os documentos corrigidos."
        notification_id = create_student_notification(
            conn,
            attempt["student_id"],
            "REVIEW_FEEDBACK" if comments else "SUBMISSION_STATUS",
            "Avaliação atualizada",
            message,
            admin_id=admin["admin_id"],
            action_url=f"#/lesson/{attempt['lesson_id']}" if authorize_retry else "#/grades",
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
        audit(conn, "ADMIN", admin["admin_id"], "SUBMISSION_REVIEWED", "ATTEMPT", attempt["attempt_id"], {
            "decision": decision, "score": score, "retryAuthorized": authorize_retry, "correctionDeadline": iso(deadline),
        })
        conn.commit()
    dispatch_notification_deliveries(notification_ids)
    return success({"attempt": staff_attempt(updated), "review": public_review(review)})


def admin_authorize_retry_action(payload: dict[str, Any], runtime: AssessmentRuntime):
    admin_context = runtime.admin_context
    admin_review_submission = runtime.admin_review_submission
    as_bool = runtime.as_bool
    audit = runtime.audit
    connection = runtime.connection
    correction_deadline = runtime.correction_deadline
    create_student_notification = runtime.create_student_notification
    dispatch_notification_deliveries = runtime.dispatch_notification_deliveries
    fetch_one = runtime.fetch_one
    prepare_assessment_feature_schema = runtime.prepare_assessment_feature_schema
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    require_fields = runtime.require_fields
    require_latest_attempt = runtime.require_latest_attempt
    staff_attempt = runtime.staff_attempt
    str_value = runtime.str_value
    success = runtime.success
    _, admin = admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    require_fields(payload, ["attemptId"])
    prepare_assessment_feature_schema()
    prepare_notification_feature_schema()
    if as_bool(payload.get("authorized", True)):
        correction_deadline(payload)
        attempt = fetch_one("select * from courseplatform.attempts where attempt_id = %s", (payload["attemptId"],))
        if not attempt:
            raise ApiError("ATTEMPT_NOT_FOUND", "Tentativa não encontrada.")
        return admin_review_submission({
            **payload,
            "decision": "CORRECTION_REQUIRED",
            "score": attempt.get("score"),
            "comments": str_value(payload.get("comments")) or "Trabalho devolvido para correção e novo envio dos documentos.",
            "authorizeRetry": True,
        })
    notification_ids: list[str] = []
    with connection() as conn:
        pending = conn.execute(
            "select * from courseplatform.attempts where attempt_id = %s", (payload["attemptId"],),
        ).fetchone()
        if not pending:
            raise ApiError("ATTEMPT_NOT_FOUND", "Tentativa não encontrada.")
        conn.execute(
            "select progress_id from courseplatform.lesson_progress where progress_id = %s for update",
            (pending["progress_id"],),
        ).fetchone()
        pending = conn.execute(
            "select * from courseplatform.attempts where attempt_id = %s for update", (payload["attemptId"],),
        ).fetchone()
        require_latest_attempt(conn, pending)
        if not as_bool(pending.get("retry_authorized")):
            raise ApiError("RETRY_NOT_PENDING", "Não existe uma autorização de reenvio pendente nesta tentativa.")
        attempt = conn.execute(
            """
            update courseplatform.attempts
            set retry_authorized = false, updated_at = now()
            where attempt_id = %s
            returning *
            """,
            (payload["attemptId"],),
        ).fetchone()
        if not attempt:
            raise ApiError("ATTEMPT_NOT_FOUND", "Tentativa não encontrada.")
        lesson = conn.execute(
            "select title from courseplatform.lessons where lesson_id = %s",
            (attempt["lesson_id"],),
        ).fetchone() or {}
        notification_id = create_student_notification(
            conn,
            attempt["student_id"],
            "SUBMISSION_STATUS",
            "Autorização de reenvio cancelada",
            f"A autorização para iniciar um novo envio em {lesson.get('title') or 'atividade'} foi cancelada.",
            admin_id=admin["admin_id"],
            action_url=f"#/lesson/{attempt['lesson_id']}",
            entity_type="ATTEMPT",
            entity_id=attempt["attempt_id"],
            priority="HIGH",
        )
        if notification_id:
            notification_ids.append(notification_id)
        audit(conn, "ADMIN", admin["admin_id"], "RETRY_REVOKED", "ATTEMPT", attempt["attempt_id"])
        conn.commit()
    dispatch_notification_deliveries(notification_ids)
    return success({"attempt": staff_attempt(attempt)})


def admin_update_attempt_action(payload: dict[str, Any], runtime: AssessmentRuntime):
    ATTEMPT_STATUSES = runtime.ATTEMPT_STATUSES
    CONTENT_ACCESS_STATUSES = runtime.CONTENT_ACCESS_STATUSES
    admin_context = runtime.admin_context
    audit = runtime.audit
    connection = runtime.connection
    create_student_notification = runtime.create_student_notification
    dispatch_notification_deliveries = runtime.dispatch_notification_deliveries
    iso = runtime.iso
    legacy_progress_status = runtime.legacy_progress_status
    notification_status_label = runtime.notification_status_label
    parse_datetime = runtime.parse_datetime
    prepare_assessment_feature_schema = runtime.prepare_assessment_feature_schema
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    progress_access_status = runtime.progress_access_status
    public_progress = runtime.public_progress
    refresh_enrollment_progress = runtime.refresh_enrollment_progress
    require_fields = runtime.require_fields
    staff_attempt = runtime.staff_attempt
    str_value = runtime.str_value
    success = runtime.success
    utc_now = runtime.utc_now
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
    return success({"attempt": staff_attempt(updated), "progress": public_progress(updated_progress) if updated_progress else None})
