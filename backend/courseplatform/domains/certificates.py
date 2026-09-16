import json
import mimetypes
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..contracts import ApiError


ACTION_BINDINGS = (
    ("verifyCertificate", "verify_certificate"),
    ("getMyCertifications", "my_certifications"),
    ("requestProfessionalCertificate", "request_professional_certificate"),
    ("requestParticipationCertificate", "request_participation_certificate"),
    ("recordCertificateDownload", "record_certificate_download"),
    ("getMyCertificate", "my_certificate"),
    ("adminListCertificates", "admin_list_certificates"),
    ("adminSetCertificateStatus", "admin_set_certificate_status"),
    ("adminRefreshCertificateFormat", "admin_refresh_certificate_format"),
    ("adminDeleteCertificate", "admin_delete_certificate"),
    ("adminGetCertificateSettings", "admin_get_certificate_settings"),
    ("adminSaveCertificateSettings", "admin_save_certificate_settings"),
    ("adminListCertificateSurveys", "admin_list_certificate_surveys"),
    ("adminSaveCertificateSurvey", "admin_save_certificate_survey"),
    ("adminUploadCertificateAsset", "admin_upload_certificate_asset"),
)


@dataclass(frozen=True)
class CertificateRuntime:
    admin_context: Callable[..., Any]
    as_bool: Callable[..., Any]
    audit: Callable[..., Any]
    certificate_content_summary: Callable[..., Any]
    certificate_document_payload: Callable[..., Any]
    certificate_download_access: Callable[..., Any]
    certificate_number: Callable[..., Any]
    certificate_settings_payload: Callable[..., Any]
    certificate_template_snapshot: Callable[..., Any]
    certificate_token: Callable[..., Any]
    certificate_verification_code: Callable[..., Any]
    connection: Callable[..., Any]
    course_completion_snapshot: Callable[..., Any]
    cursor_page_limit: Callable[..., Any]
    cursor_pagination_result: Callable[..., Any]
    cursor_scope: Callable[..., Any]
    decode_list_cursor: Callable[..., Any]
    decode_raster_data_url: Callable[..., Any]
    default_certificate_profile: Callable[..., Any]
    ensure_certificate_feature_schema: Callable[..., Any]
    ensure_simple_certificate: Callable[..., Any]
    fetch_one: Callable[..., Any]
    generate_id: Callable[..., Any]
    get_settings: Callable[..., Any]
    iso: Callable[..., Any]
    normalize_certificate_profile: Callable[..., Any]
    normalize_participation_policy: Callable[..., Any]
    normalize_survey_questions: Callable[..., Any]
    participation_policy: Callable[..., Any]
    public_certificate: Callable[..., Any]
    public_certificate_request: Callable[..., Any]
    public_course: Callable[..., Any]
    public_enrollment: Callable[..., Any]
    public_student: Callable[..., Any]
    require_certificate_download_access: Callable[..., Any]
    require_fields: Callable[..., Any]
    str_value: Callable[..., Any]
    student_certificate_payload: Callable[..., Any]
    student_context: Callable[..., Any]
    success: Callable[..., Any]
    sync_enrollment_completion: Callable[..., Any]
    upload_raster_asset_to_storage: Callable[..., Any]


def my_certificate_action(payload: dict[str, Any], runtime: CertificateRuntime):
    connection = runtime.connection
    ensure_simple_certificate = runtime.ensure_simple_certificate
    get_settings = runtime.get_settings
    participation_policy = runtime.participation_policy
    str_value = runtime.str_value
    student_certificate_payload = runtime.student_certificate_payload
    student_context = runtime.student_context
    success = runtime.success
    _, student = student_context(payload)
    course_id = payload.get("courseId") or get_settings().default_course_id
    enrollment_id = str_value(payload.get("enrollmentId"))
    with connection() as conn:
        cert, _, _, _ = ensure_simple_certificate(conn, student, course_id, enrollment_id)
        policy = participation_policy(conn, course_id)
        conn.commit()
    return success({"certificate": student_certificate_payload(cert, policy)})


def my_certifications_action(payload: dict[str, Any], runtime: CertificateRuntime):
    certificate_settings_payload = runtime.certificate_settings_payload
    connection = runtime.connection
    ensure_simple_certificate = runtime.ensure_simple_certificate
    get_settings = runtime.get_settings
    normalize_participation_policy = runtime.normalize_participation_policy
    public_certificate_request = runtime.public_certificate_request
    public_course = runtime.public_course
    public_enrollment = runtime.public_enrollment
    public_student = runtime.public_student
    str_value = runtime.str_value
    student_certificate_payload = runtime.student_certificate_payload
    student_context = runtime.student_context
    success = runtime.success
    _, student = student_context(payload)
    course_id = payload.get("courseId") or get_settings().default_course_id
    enrollment_id = str_value(payload.get("enrollmentId"))
    with connection() as conn:
        simple_cert, enrollment, course, completed = ensure_simple_certificate(
            conn, student, course_id, enrollment_id
        )
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
            where cert.student_id = %s and cert.course_id = %s and cert.enrollment_id = %s
              and coalesce(cert.status, 'ISSUED') <> 'DELETED'
            order by cert.issue_date desc nulls last
            """,
            (student["student_id"], course_id, enrollment["enrollment_id"]),
        ).fetchall()
        requests = conn.execute(
            """
            select cr.*, s.full_name, s.email, c.title
            from courseplatform.certificate_requests cr
            join courseplatform.students s on s.student_id = cr.student_id
            join courseplatform.courses c on c.course_id = cr.course_id
            where cr.student_id = %s and cr.course_id = %s and cr.enrollment_id = %s
            order by coalesce(cr.updated_at, cr.created_at) desc
            """,
            (student["student_id"], course_id, enrollment["enrollment_id"]),
        ).fetchall()
        policy = normalize_participation_policy(((settings_row or {}).get("certificate_profile_json") or {}).get("participation"))
        conn.commit()
    return success({
        "student": public_student(student),
        "course": public_course(course),
        "enrollment": public_enrollment(enrollment),
        "completed": completed,
        "simpleCertificate": student_certificate_payload(simple_cert, policy),
        "certificates": [item for row in certificates if (item := student_certificate_payload(row, policy))],
        "requests": [public_certificate_request(row) for row in requests],
        "settings": certificate_settings_payload(settings_row, course),
    })


def request_professional_certificate_action(payload: dict[str, Any], runtime: CertificateRuntime):
    certificate_settings_payload = runtime.certificate_settings_payload
    connection = runtime.connection
    ensure_simple_certificate = runtime.ensure_simple_certificate
    generate_id = runtime.generate_id
    get_settings = runtime.get_settings
    public_certificate_request = runtime.public_certificate_request
    str_value = runtime.str_value
    student_context = runtime.student_context
    success = runtime.success
    _, student = student_context(payload)
    course_id = payload.get("courseId") or get_settings().default_course_id
    enrollment_id = str_value(payload.get("enrollmentId"))
    survey_answers = payload.get("surveyAnswers") if isinstance(payload.get("surveyAnswers"), dict) else {}
    with connection() as conn:
        _, enrollment, _, completed = ensure_simple_certificate(
            conn, student, course_id, enrollment_id
        )
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
            where cr.student_id = %s and cr.course_id = %s and cr.enrollment_id = %s
              and cr.request_type = 'PROFESSIONAL'
              and cr.status in ('REQUESTED', 'PAYMENT_SUBMITTED', 'APPROVED')
              and not (cr.status = 'APPROVED' and coalesce(cert.status, 'ISSUED') in ('BLOCKED', 'DELETED'))
            order by created_at desc
            limit 1
            """,
            (student["student_id"], course_id, enrollment["enrollment_id"]),
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
                  (request_id, student_id, course_id, enrollment_id, offering_id,
                   course_version_id, request_type, status,
                   survey_answers_json, created_at, updated_at)
                values (%s, %s, %s, %s, %s, %s, 'PROFESSIONAL', %s, %s, now(), now())
                returning *
                """,
                (
                    generate_id("CREQ"), student["student_id"], course_id,
                    enrollment["enrollment_id"], enrollment["offering_id"],
                    enrollment["course_version_id"], initial_status,
                    json.dumps(survey_answers),
                ),
            ).fetchone()
        conn.commit()
    return success({"request": public_certificate_request(request)})


def request_participation_certificate_action(payload: dict[str, Any], runtime: CertificateRuntime):
    audit = runtime.audit
    certificate_download_access = runtime.certificate_download_access
    connection = runtime.connection
    ensure_simple_certificate = runtime.ensure_simple_certificate
    generate_id = runtime.generate_id
    get_settings = runtime.get_settings
    participation_policy = runtime.participation_policy
    public_certificate_request = runtime.public_certificate_request
    str_value = runtime.str_value
    student_context = runtime.student_context
    success = runtime.success
    _, student = student_context(payload)
    course_id = payload.get("courseId") or get_settings().default_course_id
    enrollment_id = str_value(payload.get("enrollmentId"))
    with connection() as conn:
        cert, enrollment, _, completed = ensure_simple_certificate(
            conn, student, course_id, enrollment_id
        )
        if not completed:
            raise ApiError("COURSE_NOT_COMPLETED", "Conclua o curso antes de solicitar o certificado.")
        policy = participation_policy(conn, course_id)
        if not policy["enabled"]:
            raise ApiError("PARTICIPATION_DISABLED", "Este curso não disponibiliza certificado de participação.")
        access = certificate_download_access(cert, policy)
        if access["allowed"]:
            raise ApiError("CERTIFICATE_ALREADY_AVAILABLE", "O certificado já está disponível para download.")
        request = conn.execute(
            """
            select * from courseplatform.certificate_requests
            where student_id = %s and course_id = %s and enrollment_id = %s
              and request_type = 'PARTICIPATION'
              and status = 'PAYMENT_SUBMITTED'
            order by created_at desc limit 1
            """, (student["student_id"], course_id, enrollment["enrollment_id"]),
        ).fetchone()
        if not request:
            request = conn.execute(
                """
                insert into courseplatform.certificate_requests
                  (request_id, student_id, course_id, enrollment_id, offering_id,
                   course_version_id, request_type, status, created_at, updated_at)
                values (%s, %s, %s, %s, %s, %s, 'PARTICIPATION', 'PAYMENT_SUBMITTED', now(), now())
                returning *
                """, (
                    generate_id("CREQ"), student["student_id"], course_id,
                    enrollment["enrollment_id"], enrollment["offering_id"],
                    enrollment["course_version_id"],
                ),
            ).fetchone()
            audit(conn, "STUDENT", student["student_id"], "PARTICIPATION_REQUESTED", "CERTIFICATE_REQUEST", request["request_id"])
        conn.commit()
    return success({"request": public_certificate_request(request)})


def record_certificate_download_action(payload: dict[str, Any], runtime: CertificateRuntime):
    certificate_template_snapshot = runtime.certificate_template_snapshot
    connection = runtime.connection
    ensure_certificate_feature_schema = runtime.ensure_certificate_feature_schema
    public_certificate = runtime.public_certificate
    require_certificate_download_access = runtime.require_certificate_download_access
    require_fields = runtime.require_fields
    student_context = runtime.student_context
    success = runtime.success
    _, student = student_context(payload)
    require_fields(payload, ["certificateId"])
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        cert = conn.execute(
            "select * from courseplatform.certificates where certificate_id = %s and student_id = %s for update",
            (payload["certificateId"], student["student_id"]),
        ).fetchone()
        if not cert:
            raise ApiError("CERTIFICATE_NOT_FOUND", "Certificado não encontrado.")
        require_certificate_download_access(conn, cert)
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


def admin_list_certificates_action(payload: dict[str, Any], runtime: CertificateRuntime):
    admin_context = runtime.admin_context
    certificate_download_access = runtime.certificate_download_access
    connection = runtime.connection
    cursor_page_limit = runtime.cursor_page_limit
    cursor_pagination_result = runtime.cursor_pagination_result
    cursor_scope = runtime.cursor_scope
    decode_list_cursor = runtime.decode_list_cursor
    ensure_certificate_feature_schema = runtime.ensure_certificate_feature_schema
    public_certificate = runtime.public_certificate
    str_value = runtime.str_value
    success = runtime.success
    admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    status = (payload.get("status") or "ACTIVE").upper()
    query = str_value(payload.get("query")).lower()
    limit = cursor_page_limit(payload)
    scope = cursor_scope("admin-certificates", status, query)
    cursor = decode_list_cursor(
        payload.get("cursor"),
        "admin-certificates",
        scope,
        allow_null_sort=True,
    )
    cursor_sql = ""
    cursor_params: list[Any] = []
    if cursor:
        cursor_at, cursor_id = cursor
        if cursor_at is None:
            cursor_sql = "and cert.issue_date is null and cert.certificate_id < %s"
            cursor_params.append(cursor_id)
        else:
            cursor_sql = """
              and (
                cert.issue_date < %s
                or cert.issue_date is null
                or (cert.issue_date = %s and cert.certificate_id < %s)
              )
            """
            cursor_params.extend((cursor_at, cursor_at, cursor_id))
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        rows = conn.execute(
            f"""
            select cert.*, s.full_name as student_name, s.email, c.title as course_title,
                   cs.certificate_profile_json as course_certificate_profile
            from courseplatform.certificates cert
            join courseplatform.students s on s.student_id = cert.student_id
            join courseplatform.courses c on c.course_id = cert.course_id
            left join courseplatform.certificate_settings cs on cs.course_id = cert.course_id
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
              {cursor_sql}
            order by cert.issue_date desc nulls last, cert.certificate_id desc
            limit %s
            """,
            (status, status, status, query, f"%{query}%", *cursor_params, limit + 1),
        ).fetchall()
        conn.commit()
    rows, page_info = cursor_pagination_result(
        rows,
        limit,
        "admin-certificates",
        scope,
        "issue_date",
        "certificate_id",
    )
    return success({"certificates": [
        {**public_certificate(row), "downloadAccess": certificate_download_access(
            row, (row.get("course_certificate_profile") or {}).get("participation"),
        )} for row in rows
    ], "pagination": page_info})


def admin_set_certificate_status_action(payload: dict[str, Any], runtime: CertificateRuntime):
    admin_context = runtime.admin_context
    as_bool = runtime.as_bool
    audit = runtime.audit
    connection = runtime.connection
    ensure_certificate_feature_schema = runtime.ensure_certificate_feature_schema
    participation_policy = runtime.participation_policy
    public_certificate = runtime.public_certificate
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    success = runtime.success
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["certificateId", "status"])
    status = str_value(payload.get("status")).upper()
    if status not in {"ISSUED", "BLOCKED"}:
        raise ApiError("INVALID_CERTIFICATE_STATUS", "Estado de certificado inválido.")
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        current = conn.execute(
            "select * from courseplatform.certificates where certificate_id = %s for update",
            (payload["certificateId"],),
        ).fetchone()
        if not current:
            raise ApiError("CERTIFICATE_NOT_FOUND", "Certificado não encontrado.")
        if status == "ISSUED" and (current.get("certificate_type") or "SIMPLE") == "SIMPLE":
            if not participation_policy(conn, current["course_id"])["enabled"]:
                raise ApiError("PARTICIPATION_DISABLED", "Ative o certificado de participação na configuração do curso antes de o disponibilizar.")
        reset_downloads = as_bool(payload.get("resetDownloads")) and status == "ISSUED"
        certificate = conn.execute(
            """
            update courseplatform.certificates
            set status = %s,
                status_note = %s,
                status_updated_by = %s,
                status_updated_at = now(),
                approved_by = case when %s = 'ISSUED' then %s else approved_by end,
                approved_at = case when %s = 'ISSUED' then now() else approved_at end,
                download_count = case when %s then 0 else download_count end
            where certificate_id = %s
            returning *
            """,
            (status, str_value(payload.get("statusNote")), admin["admin_id"], status, admin["admin_id"],
             status, reset_downloads, payload["certificateId"]),
        ).fetchone()
        if not certificate:
            raise ApiError("CERTIFICATE_NOT_FOUND", "Certificado não encontrado.")
        audit(conn, "ADMIN", admin["admin_id"], "CERTIFICATE_STATUS_CHANGED", "CERTIFICATE", certificate["certificate_id"],
              {"status": status, "resetDownloads": reset_downloads, "previousDownloadCount": current.get("download_count")})
        conn.commit()
    return success({"certificate": public_certificate(certificate)})


def admin_refresh_certificate_format_action(payload: dict[str, Any], runtime: CertificateRuntime):
    admin_context = runtime.admin_context
    audit = runtime.audit
    certificate_content_summary = runtime.certificate_content_summary
    certificate_template_snapshot = runtime.certificate_template_snapshot
    connection = runtime.connection
    ensure_certificate_feature_schema = runtime.ensure_certificate_feature_schema
    public_certificate = runtime.public_certificate
    str_value = runtime.str_value
    success = runtime.success
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


def admin_delete_certificate_action(payload: dict[str, Any], runtime: CertificateRuntime):
    admin_context = runtime.admin_context
    audit = runtime.audit
    connection = runtime.connection
    ensure_certificate_feature_schema = runtime.ensure_certificate_feature_schema
    public_certificate = runtime.public_certificate
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    success = runtime.success
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


def admin_get_certificate_settings_action(payload: dict[str, Any], runtime: CertificateRuntime):
    admin_context = runtime.admin_context
    certificate_settings_payload = runtime.certificate_settings_payload
    connection = runtime.connection
    ensure_certificate_feature_schema = runtime.ensure_certificate_feature_schema
    get_settings = runtime.get_settings
    public_course = runtime.public_course
    success = runtime.success
    admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    course_id = payload.get("courseId") or get_settings().default_course_id
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        course = conn.execute("select * from courseplatform.courses where course_id = %s", (course_id,)).fetchone()
        row = conn.execute("select * from courseplatform.certificate_settings where course_id = %s", (course_id,)).fetchone()
        conn.commit()
    return success({"settings": certificate_settings_payload(row, course), "course": public_course(course)})


def admin_save_certificate_settings_action(payload: dict[str, Any], runtime: CertificateRuntime):
    admin_context = runtime.admin_context
    audit = runtime.audit
    certificate_settings_payload = runtime.certificate_settings_payload
    connection = runtime.connection
    ensure_certificate_feature_schema = runtime.ensure_certificate_feature_schema
    get_settings = runtime.get_settings
    normalize_certificate_profile = runtime.normalize_certificate_profile
    normalize_survey_questions = runtime.normalize_survey_questions
    public_course = runtime.public_course
    str_value = runtime.str_value
    success = runtime.success
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    course_id = payload.get("courseId") or get_settings().default_course_id
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        course = conn.execute("select * from courseplatform.courses where course_id = %s", (course_id,)).fetchone()
        current = conn.execute("select * from courseplatform.certificate_settings where course_id = %s", (course_id,)).fetchone()
        current_payload = certificate_settings_payload(current, course)
        survey_questions = normalize_survey_questions(payload.get("surveyQuestions")) if isinstance(payload.get("surveyQuestions"), list) else current_payload.get("surveyQuestions", [])
        profile_source = {**current_payload.get("certificateProfile", {}), **(payload.get("certificateProfile") or {})}
        profile = normalize_certificate_profile(profile_source, course)
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


def admin_list_certificate_surveys_action(payload: dict[str, Any], runtime: CertificateRuntime):
    admin_context = runtime.admin_context
    certificate_settings_payload = runtime.certificate_settings_payload
    connection = runtime.connection
    cursor_page_limit = runtime.cursor_page_limit
    cursor_pagination_result = runtime.cursor_pagination_result
    cursor_scope = runtime.cursor_scope
    decode_list_cursor = runtime.decode_list_cursor
    ensure_certificate_feature_schema = runtime.ensure_certificate_feature_schema
    iso = runtime.iso
    public_course = runtime.public_course
    str_value = runtime.str_value
    success = runtime.success
    admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    query = str_value(payload.get("query")).lower()
    limit = cursor_page_limit(payload)
    scope = cursor_scope("admin-certificate-surveys", query)
    cursor = decode_list_cursor(payload.get("cursor"), "admin-certificate-surveys", scope, sort_type="text")
    cursor_sql = ""
    cursor_params: list[Any] = []
    if cursor:
        cursor_title, cursor_id = cursor
        cursor_sql = "and (lower(coalesce(c.title, '')) > %s or (lower(coalesce(c.title, '')) = %s and c.course_id > %s))"
        cursor_params.extend((cursor_title, cursor_title, cursor_id))
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        rows = conn.execute(
            f"""
            with survey_rows as (
              select c.*, cs.survey_questions_json, cs.congratulations_message, cs.updated_at,
                     lower(coalesce(c.title, '')) as pagination_sort_text
              from courseplatform.courses c
              left join courseplatform.certificate_settings cs on cs.course_id = c.course_id
              where coalesce(c.status, 'ACTIVE') <> 'DELETED'
                and (%s = '' or lower(coalesce(c.title, '') || ' ' || coalesce(c.course_code, '') || ' ' || coalesce(c.course_id, '')) like %s)
            ), numbered_surveys as (
              select *, count(*) over() as total_count from survey_rows
            )
            select * from numbered_surveys c
            where true {cursor_sql}
            order by pagination_sort_text, course_id
            limit %s
            """,
            (query, f"%{query}%", *cursor_params, limit + 1),
        ).fetchall()
        conn.commit()
    total = int(rows[0]["total_count"]) if rows else 0
    rows, page_info = cursor_pagination_result(
        rows, limit, "admin-certificate-surveys", scope, "pagination_sort_text", "course_id"
    )
    page_info["total"] = total
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
    return success({"surveys": surveys, "pagination": page_info})


def admin_save_certificate_survey_action(payload: dict[str, Any], runtime: CertificateRuntime):
    admin_context = runtime.admin_context
    audit = runtime.audit
    certificate_settings_payload = runtime.certificate_settings_payload
    connection = runtime.connection
    ensure_certificate_feature_schema = runtime.ensure_certificate_feature_schema
    get_settings = runtime.get_settings
    normalize_certificate_profile = runtime.normalize_certificate_profile
    normalize_survey_questions = runtime.normalize_survey_questions
    public_course = runtime.public_course
    str_value = runtime.str_value
    success = runtime.success
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


def admin_upload_certificate_asset_action(payload: dict[str, Any], runtime: CertificateRuntime):
    admin_context = runtime.admin_context
    certificate_token = runtime.certificate_token
    decode_raster_data_url = runtime.decode_raster_data_url
    default_certificate_profile = runtime.default_certificate_profile
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    success = runtime.success
    upload_raster_asset_to_storage = runtime.upload_raster_asset_to_storage
    admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["courseId", "assetKey", "fileName", "mimeType", "dataUrl"])
    course_id = str_value(payload.get("courseId"))
    asset_key = str_value(payload.get("assetKey"))
    allowed_keys = set(default_certificate_profile().get("assets", {}).keys())
    if asset_key not in allowed_keys:
        raise ApiError("INVALID_ASSET_KEY", "Tipo de elemento gráfico inválido.")
    mime_type, data_url, file_bytes = decode_raster_data_url(
        payload.get("dataUrl"),
        payload.get("mimeType"),
        3 * 1024 * 1024,
    )

    extension = mimetypes.guess_extension(mime_type) or ".png"
    object_path = f"{course_id}/{asset_key}-{certificate_token(8)}{extension}"
    storage_saved, storage_error = upload_raster_asset_to_storage(file_bytes, mime_type, object_path)

    return success({
        "assetKey": asset_key,
        "assetUrl": data_url,
        "storagePath": object_path if storage_saved else "",
        "storageSaved": storage_saved,
        "storageError": storage_error,
    })


def verify_certificate_action(payload: dict[str, Any], runtime: CertificateRuntime):
    fetch_one = runtime.fetch_one
    iso = runtime.iso
    success = runtime.success
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


def certificate_pdf_payload_action(payload: dict[str, Any], runtime: CertificateRuntime):
    certificate_document_payload = runtime.certificate_document_payload
    certificate_template_snapshot = runtime.certificate_template_snapshot
    connection = runtime.connection
    ensure_certificate_feature_schema = runtime.ensure_certificate_feature_schema
    require_certificate_download_access = runtime.require_certificate_download_access
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    student_context = runtime.student_context
    _, student = student_context(payload)
    require_fields(payload, ["certificateId"])
    verification_base_url = str_value(payload.get("verificationBaseUrl")) or "verify.html"
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        cert = conn.execute(
            """
            select cert.*, c.title as course_title, c.total_hours as course_hours,
                   s.full_name as student_name,
                   e.final_score as enrollment_score
            from courseplatform.certificates cert
            join courseplatform.courses c on c.course_id = cert.course_id
            join courseplatform.students s on s.student_id = cert.student_id
            left join courseplatform.enrollments e
              on e.enrollment_id = cert.enrollment_id
            where cert.certificate_id = %s and cert.student_id = %s
            """,
            (payload["certificateId"], student["student_id"]),
        ).fetchone()
        if not cert:
            raise ApiError("CERTIFICATE_NOT_FOUND", "Certificado não encontrado.")
        require_certificate_download_access(conn, cert)
        version = conn.execute(
            "select * from courseplatform.course_versions where course_version_id = %s",
            (cert.get("course_version_id"),),
        ).fetchone() if cert.get("course_version_id") else None
        snapshot = cert.get("template_snapshot_json") or certificate_template_snapshot(
            conn, cert.get("course_id"), cert.get("certificate_type"), version
        )
        conn.commit()
    return certificate_document_payload(cert, snapshot, verification_base_url)


def admin_certificate_pdf_payload_action(payload: dict[str, Any], runtime: CertificateRuntime):
    admin_context = runtime.admin_context
    certificate_document_payload = runtime.certificate_document_payload
    certificate_template_snapshot = runtime.certificate_template_snapshot
    connection = runtime.connection
    ensure_certificate_feature_schema = runtime.ensure_certificate_feature_schema
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    require_fields(payload, ["certificateId"])
    verification_base_url = str_value(payload.get("verificationBaseUrl")) or "verify.html"
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        cert = conn.execute(
            """
            select cert.*, c.title as course_title, c.total_hours as course_hours,
                   s.full_name as student_name,
                   e.final_score as enrollment_score
            from courseplatform.certificates cert
            join courseplatform.courses c on c.course_id = cert.course_id
            join courseplatform.students s on s.student_id = cert.student_id
            left join courseplatform.enrollments e
              on e.enrollment_id = cert.enrollment_id
            where cert.certificate_id = %s
            """,
            (payload["certificateId"],),
        ).fetchone()
        snapshot = cert.get("template_snapshot_json") if cert else None
        if cert and not snapshot:
            version = conn.execute(
                "select * from courseplatform.course_versions where course_version_id = %s",
                (cert.get("course_version_id"),),
            ).fetchone() if cert.get("course_version_id") else None
            snapshot = certificate_template_snapshot(
                conn, cert.get("course_id"), cert.get("certificate_type"), version
            )
        conn.commit()
    if not cert:
        raise ApiError("CERTIFICATE_NOT_FOUND", "Certificado não encontrado.")
    if cert.get("status") == "DELETED":
        raise ApiError("CERTIFICATE_NOT_FOUND", "Certificado não encontrado.")
    return certificate_document_payload(cert, snapshot, verification_base_url)


def ensure_simple_certificate_action(
    conn,
    student: dict[str, Any],
    course_id: str,
    enrollment_id: str = "",
    *,
    runtime: CertificateRuntime,
):
    certificate_content_summary = runtime.certificate_content_summary
    certificate_number = runtime.certificate_number
    certificate_template_snapshot = runtime.certificate_template_snapshot
    certificate_verification_code = runtime.certificate_verification_code
    course_completion_snapshot = runtime.course_completion_snapshot
    ensure_certificate_feature_schema = runtime.ensure_certificate_feature_schema
    generate_id = runtime.generate_id
    participation_policy = runtime.participation_policy
    sync_enrollment_completion = runtime.sync_enrollment_completion
    ensure_certificate_feature_schema(conn)
    # Serialize issuance and participation requests for this enrollment.
    conn.execute(
        """
        select enrollment_id from courseplatform.enrollments
        where student_id = %s and course_id = %s
          and (%s = '' or enrollment_id = %s)
        for update
        """,
        (student["student_id"], course_id, enrollment_id, enrollment_id),
    ).fetchone()
    enrollment, course, version, _, _, completed = course_completion_snapshot(
        conn, student["student_id"], course_id, enrollment_id
    )
    enrollment = sync_enrollment_completion(conn, enrollment, completed, (enrollment or {}).get("final_score"))
    if not completed:
        return None, enrollment, course, False
    if not participation_policy(conn, course_id)["enabled"]:
        return None, enrollment, course, True
    existing = conn.execute(
        """
        select cert.*, c.title as course_title, s.full_name as student_name
        from courseplatform.certificates cert
        join courseplatform.courses c on c.course_id = cert.course_id
        join courseplatform.students s on s.student_id = cert.student_id
        where cert.student_id = %s and cert.course_id = %s and cert.enrollment_id = %s
          and coalesce(cert.certificate_type, 'SIMPLE') = 'SIMPLE'
        order by cert.issue_date desc nulls last
        limit 1
        """,
        (student["student_id"], course_id, enrollment["enrollment_id"]),
    ).fetchone()
    if existing:
        return existing, enrollment, course, True
    cert = conn.execute(
        """
        insert into courseplatform.certificates
          (certificate_id, student_id, course_id, enrollment_id, offering_id, course_version_id,
           certificate_number, verification_code,
           issue_date, final_score, drive_file_id, drive_url, status, certificate_type,
           recognition_level, content_summary, template_snapshot_json, max_downloads, payment_status)
        values (%s, %s, %s, %s, %s, %s, %s, %s, now(), %s, '', '', 'ISSUED', 'SIMPLE',
                'PARTICIPATION', %s, %s, null, 'NOT_REQUIRED')
        returning *
        """,
        (
            generate_id("CERT"),
            student["student_id"],
            course_id,
            enrollment["enrollment_id"],
            enrollment["offering_id"],
            enrollment["course_version_id"],
            certificate_number(),
            certificate_verification_code(),
            (enrollment or {}).get("final_score"),
            certificate_content_summary(conn, course_id, version),
            json.dumps(certificate_template_snapshot(conn, course_id, "SIMPLE", version)),
        ),
    ).fetchone()
    return {**cert, "course_title": (course or {}).get("title"), "student_name": student.get("full_name")}, enrollment, course, True
