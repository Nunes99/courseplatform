import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..contracts import ApiError
from ..reviewer_scopes import admin_from_context, reviewer_scope_predicate
from ..storage import StorageError


ACTION_BINDINGS = (
    ("submitProfessionalCertificatePayment", "submit_professional_certificate_payment"),
    ("adminListCertificateRequests", "admin_list_certificate_requests"),
    ("adminReviewCertificateRequest", "admin_review_certificate_request"),
    ("adminDeleteCertificateRequest", "admin_delete_certificate_request"),
)


@dataclass(frozen=True)
class FinancialRuntime:
    _private_content_payload: Callable[..., Any]
    admin_context: Callable[..., Any]
    approve_participation_request: Callable[..., Any]
    as_bool: Callable[..., Any]
    audit: Callable[..., Any]
    certificate_content_summary: Callable[..., Any]
    certificate_number: Callable[..., Any]
    certificate_template_snapshot: Callable[..., Any]
    certificate_verification_code: Callable[..., Any]
    connection: Callable[..., Any]
    cursor_page_limit: Callable[..., Any]
    cursor_pagination_result: Callable[..., Any]
    cursor_scope: Callable[..., Any]
    decode_list_cursor: Callable[..., Any]
    ensure_certificate_feature_schema: Callable[..., Any]
    ensure_simple_certificate: Callable[..., Any]
    fetch_one: Callable[..., Any]
    generate_id: Callable[..., Any]
    get_settings: Callable[..., Any]
    public_certificate: Callable[..., Any]
    public_certificate_request: Callable[..., Any]
    require_fields: Callable[..., Any]
    resolve_student_enrollment_with_conn: Callable[..., Any]
    storage_api_error: Callable[..., Any]
    storage_object_path: Callable[..., Any]
    str_value: Callable[..., Any]
    student_context: Callable[..., Any]
    success: Callable[..., Any]
    upload_private_object: Callable[..., Any]
    validate_upload: Callable[..., Any]


def submit_professional_certificate_payment_action(payload: dict[str, Any], runtime: FinancialRuntime):
    audit = runtime.audit
    connection = runtime.connection
    ensure_certificate_feature_schema = runtime.ensure_certificate_feature_schema
    fetch_one = runtime.fetch_one
    get_settings = runtime.get_settings
    public_certificate_request = runtime.public_certificate_request
    require_fields = runtime.require_fields
    storage_api_error = runtime.storage_api_error
    storage_object_path = runtime.storage_object_path
    student_context = runtime.student_context
    success = runtime.success
    upload_private_object = runtime.upload_private_object
    validate_upload = runtime.validate_upload
    _, student = student_context(payload)
    require_fields(payload, ["requestId", "receiptFileName"])
    request = fetch_one(
        """
        select * from courseplatform.certificate_requests
        where request_id = %s and student_id = %s
          and request_type = 'PROFESSIONAL'
          and status in ('REQUESTED', 'PAYMENT_SUBMITTED')
          and certificate_id is null
        """,
        (payload["requestId"], student["student_id"]),
    )
    if not request:
        raise ApiError("CERTIFICATE_REQUEST_NOT_FOUND", "Pedido de certificado não encontrado.")
    try:
        upload = validate_upload(
            payload.get("receiptBase64"),
            payload.get("receiptFileName"),
            payload.get("receiptMimeType"),
            purpose="PAYMENT_RECEIPT",
        )
    except StorageError as error:
        raise storage_api_error(error) from error
    settings = get_settings()
    object_path = storage_object_path("payment-receipt", student["student_id"], request["request_id"], upload)
    try:
        upload_private_object(settings.supabase_payment_receipt_bucket, object_path, upload)
    except StorageError as error:
        raise storage_api_error(error) from error

    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        request = conn.execute(
            """
            update courseplatform.certificate_requests
            set status = 'PAYMENT_SUBMITTED',
                payment_receipt_name = %s,
                payment_receipt_url = '',
                payment_receipt_mime_type = %s,
                payment_receipt_bucket = %s,
                payment_receipt_path = %s,
                payment_receipt_checksum_sha256 = %s,
                payment_receipt_size_bytes = %s,
                payment_receipt_storage_status = 'READY',
                submitted_at = now(),
                updated_at = now()
            where request_id = %s and student_id = %s
              and request_type = 'PROFESSIONAL'
              and status in ('REQUESTED', 'PAYMENT_SUBMITTED')
              and certificate_id is null
            returning *
            """,
            (
                upload.file_name,
                upload.mime_type,
                settings.supabase_payment_receipt_bucket,
                object_path,
                upload.checksum_sha256,
                upload.size_bytes,
                payload["requestId"],
                student["student_id"],
            ),
        ).fetchone()
        if request:
            audit(
                conn,
                "STUDENT",
                student["student_id"],
                "PAYMENT_RECEIPT_UPLOADED",
                "CERTIFICATE_REQUEST",
                request["request_id"],
                {"sizeBytes": upload.size_bytes, "mimeType": upload.mime_type},
            )
        conn.commit()
    if not request:
        raise ApiError("CERTIFICATE_REQUEST_NOT_FOUND", "Pedido de certificado não encontrado.")
    return success({"request": public_certificate_request(request)})


def admin_list_certificate_requests_action(payload: dict[str, Any], runtime: FinancialRuntime):
    admin_context = runtime.admin_context
    as_bool = runtime.as_bool
    connection = runtime.connection
    cursor_page_limit = runtime.cursor_page_limit
    cursor_pagination_result = runtime.cursor_pagination_result
    cursor_scope = runtime.cursor_scope
    decode_list_cursor = runtime.decode_list_cursor
    ensure_certificate_feature_schema = runtime.ensure_certificate_feature_schema
    public_certificate_request = runtime.public_certificate_request
    success = runtime.success
    admin = admin_from_context(admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"}))
    status = (payload.get("status") or "ALL").upper()
    query = (payload.get("query") or "").strip().lower()
    survey_only = as_bool(payload.get("surveyOnly"))
    limit = cursor_page_limit(payload)
    scope = cursor_scope("admin-certificate-requests", status, query, survey_only)
    cursor = decode_list_cursor(payload.get("cursor"), "admin-certificate-requests", scope)
    cursor_sql = ""
    cursor_params: list[Any] = []
    if cursor:
        cursor_at, cursor_id = cursor
        cursor_sql = """
              and (
                coalesce(cr.submitted_at, cr.updated_at, cr.created_at) < %s
                or (
                  coalesce(cr.submitted_at, cr.updated_at, cr.created_at) = %s
                  and cr.request_id < %s
                )
              )
        """
        cursor_params.extend((cursor_at, cursor_at, cursor_id))
    reviewer_sql, reviewer_params = reviewer_scope_predicate(
        admin,
        course_expr="cr.course_id",
        offering_expr="e.offering_id",
        group_expr="e.group_id",
    )
    with connection() as conn:
        ensure_certificate_feature_schema(conn)
        rows = conn.execute(
            f"""
            select cr.*, s.full_name, s.email, c.title,
                   cert.certificate_number, cert.verification_code, cert.issue_date,
                   cert.final_score, cert.certificate_type, cert.content_summary,
                   coalesce(cr.submitted_at, cr.updated_at, cr.created_at) as pagination_sort_at
            from courseplatform.certificate_requests cr
            join courseplatform.students s on s.student_id = cr.student_id
            join courseplatform.courses c on c.course_id = cr.course_id
            left join courseplatform.certificates cert on cert.certificate_id = cr.certificate_id
            left join courseplatform.enrollments e on e.enrollment_id = cr.enrollment_id
            where (%s = 'ALL' or cr.status = %s)
              and (%s = false or coalesce(cr.survey_answers_json, '{{}}'::jsonb) <> '{{}}'::jsonb)
              and (
                %s = ''
                or lower(coalesce(s.full_name, '') || ' ' || coalesce(s.email, '') || ' ' ||
                  coalesce(c.title, '') || ' ' || coalesce(cr.request_id, '')) like %s
              )
              and ({reviewer_sql})
              {cursor_sql}
            order by coalesce(cr.submitted_at, cr.updated_at, cr.created_at) desc,
                     cr.request_id desc
            limit %s
            """,
            (status, status, survey_only, query, f"%{query}%", *reviewer_params, *cursor_params, limit + 1),
        ).fetchall()
        conn.commit()
    rows, page_info = cursor_pagination_result(
        rows,
        limit,
        "admin-certificate-requests",
        scope,
        "pagination_sort_at",
        "request_id",
    )
    return success({
        "requests": [public_certificate_request(row) for row in rows],
        "pagination": page_info,
    })


def admin_review_certificate_request_action(payload: dict[str, Any], runtime: FinancialRuntime):
    admin_context = runtime.admin_context
    approve_participation_request = runtime.approve_participation_request
    audit = runtime.audit
    certificate_content_summary = runtime.certificate_content_summary
    certificate_number = runtime.certificate_number
    certificate_template_snapshot = runtime.certificate_template_snapshot
    certificate_verification_code = runtime.certificate_verification_code
    connection = runtime.connection
    ensure_certificate_feature_schema = runtime.ensure_certificate_feature_schema
    generate_id = runtime.generate_id
    public_certificate = runtime.public_certificate
    public_certificate_request = runtime.public_certificate_request
    require_fields = runtime.require_fields
    resolve_student_enrollment_with_conn = runtime.resolve_student_enrollment_with_conn
    str_value = runtime.str_value
    success = runtime.success
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
        if decision == "APPROVED" and request.get("request_type") == "PARTICIPATION":
            certificate = approve_participation_request(conn, request, admin)
            request = conn.execute(
                """
                update courseplatform.certificate_requests
                set status = 'APPROVED', certificate_id = %s, reviewed_by = %s,
                    reviewed_at = now(), admin_notes = %s, updated_at = now()
                where request_id = %s returning *
                """, (certificate["certificate_id"], admin["admin_id"], str_value(payload.get("adminNotes")), request["request_id"]),
            ).fetchone()
        elif decision == "APPROVED":
            student = conn.execute("select * from courseplatform.students where student_id = %s", (request["student_id"],)).fetchone()
            course = conn.execute("select * from courseplatform.courses where course_id = %s", (request["course_id"],)).fetchone()
            enrollment = resolve_student_enrollment_with_conn(
                conn,
                request["student_id"],
                request["course_id"],
                str_value(request.get("enrollment_id")),
            )
            version = conn.execute(
                "select * from courseplatform.course_versions where course_version_id = %s",
                (enrollment["course_version_id"],),
            ).fetchone()
            certificate = conn.execute(
                """
                insert into courseplatform.certificates
                  (certificate_id, student_id, course_id, enrollment_id, offering_id,
                   course_version_id, certificate_number, verification_code,
                   issue_date, final_score, drive_file_id, drive_url, status, certificate_type,
                   recognition_level, content_summary, template_snapshot_json, professional_request_id,
                   download_count, max_downloads, payment_status, approved_by, approved_at)
                values (%s, %s, %s, %s, %s, %s, %s, %s, now(), %s,
                  '', '', 'ISSUED', 'PROFESSIONAL', 'CONTENT_DETAILED', %s, %s, %s, 0, 5,
                  'CONFIRMED', %s, now())
                returning *
                """,
                (
                    generate_id("CERT"),
                    request["student_id"],
                    request["course_id"],
                    enrollment["enrollment_id"],
                    enrollment["offering_id"],
                    enrollment["course_version_id"],
                    certificate_number(),
                    certificate_verification_code(),
                    enrollment.get("final_score"),
                    certificate_content_summary(conn, request["course_id"], version),
                    json.dumps(certificate_template_snapshot(conn, request["course_id"], "PROFESSIONAL", version)),
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


def admin_delete_certificate_request_action(payload: dict[str, Any], runtime: FinancialRuntime):
    admin_context = runtime.admin_context
    audit = runtime.audit
    connection = runtime.connection
    ensure_certificate_feature_schema = runtime.ensure_certificate_feature_schema
    public_certificate_request = runtime.public_certificate_request
    require_fields = runtime.require_fields
    success = runtime.success
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


def certificate_receipt_download_payload_action(payload: dict[str, Any], runtime: FinancialRuntime) -> dict[str, Any]:
    _private_content_payload = runtime._private_content_payload
    admin_context = runtime.admin_context
    fetch_one = runtime.fetch_one
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    student_context = runtime.student_context
    require_fields(payload, ["requestId"])
    if str_value(payload.get("adminToken")):
        admin_context(payload, {"OWNER", "ADMIN"})
        row = fetch_one(
            "select * from courseplatform.certificate_requests where request_id = %s",
            (payload["requestId"],),
        )
    else:
        _, student = student_context(payload)
        row = fetch_one(
            "select * from courseplatform.certificate_requests where request_id = %s and student_id = %s",
            (payload["requestId"], student["student_id"]),
        )
    if not row or not (row.get("payment_receipt_path") or row.get("payment_receipt_url")):
        raise ApiError("PAYMENT_RECEIPT_NOT_FOUND", "Comprovativo de pagamento não encontrado.")
    return _private_content_payload(
        row,
        bucket_field="payment_receipt_bucket",
        path_field="payment_receipt_path",
        checksum_field="payment_receipt_checksum_sha256",
        status_field="payment_receipt_storage_status",
        legacy_url_field="payment_receipt_url",
        file_name_field="payment_receipt_name",
        mime_type_field="payment_receipt_mime_type",
        size_field="payment_receipt_size_bytes",
    )


def approve_participation_request_action(conn, request, admin, runtime: FinancialRuntime):
    audit = runtime.audit
    ensure_simple_certificate = runtime.ensure_simple_certificate
    str_value = runtime.str_value
    student = conn.execute("select * from courseplatform.students where student_id = %s", (request["student_id"],)).fetchone()
    cert, _, _, completed = ensure_simple_certificate(
        conn, student, request["course_id"], str_value(request.get("enrollment_id"))
    )
    if not completed:
        raise ApiError("COURSE_NOT_COMPLETED", "O estudante ainda não concluiu este curso.")
    if not cert:
        raise ApiError("PARTICIPATION_DISABLED", "Ative o certificado de participação na configuração do curso antes de aprovar o pedido.")
    updated = conn.execute(
        """
        update courseplatform.certificates
        set status = 'ISSUED', approved_by = %s, approved_at = now(),
            download_count = 0, status_note = 'Pedido de participação aprovado.',
            status_updated_by = %s, status_updated_at = now()
        where certificate_id = %s returning *
        """, (admin["admin_id"], admin["admin_id"], cert["certificate_id"]),
    ).fetchone()
    audit(conn, "ADMIN", admin["admin_id"], "PARTICIPATION_APPROVED", "CERTIFICATE", cert["certificate_id"],
          {"requestId": request["request_id"], "previousDownloadCount": cert.get("download_count")})
    return updated
