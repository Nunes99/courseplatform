import logging
import os
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from .actions import (
    ACCOUNT_VERIFICATION_DELIVERY_FAILED_MESSAGE,
    ApiError,
    admin_certificate_pdf_payload,
    certificate_pdf_payload,
    certificate_receipt_download_payload,
    dispatch,
    public_error,
    record_certificate_download,
    submission_file_download_payload,
)
from .certificate_pdf import CertificateLayoutError, build_course_certificate_pdf
from .config import get_settings
from .jobs import (
    ACCOUNT_VERIFICATION_JOB,
    PASSWORD_RESET_JOB,
    enqueue_identity_delivery,
    operational_metrics,
    run_operational_cycle,
    runner_authorized,
)
from .observability import (
    configure_logging,
    monotonic_milliseconds,
    normalized_request_id,
    request_id_context,
)
from .api.router import router as typed_api_router
from .storage import safe_download_name

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)
STATIC_DIRS = [
    Path(__file__).resolve().parents[2] / "public",
    Path(__file__).resolve().parent / "static",
]

app = FastAPI(title="CoursePlatform Python API", version=settings.app_version)


@app.middleware("http")
async def structured_request_logging(request: Request, call_next):
    request_id = normalized_request_id(request.headers.get("x-request-id"))
    token = request_id_context.set(request_id)
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "HTTP request completed.",
            extra={
                "event": "http_request_completed",
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": monotonic_milliseconds(started_at),
            },
        )
        return response
    except Exception as error:
        logger.exception(
            "HTTP request failed.",
            extra={
                "event": "http_request_failed",
                "method": request.method,
                "path": request.url.path,
                "duration_ms": monotonic_milliseconds(started_at),
                "error_type": error.__class__.__name__,
            },
        )
        raise
    finally:
        request_id_context.reset(token)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def request_source(request: Request) -> str:
    direct_host = request.client.host if request.client else "unknown"
    if os.getenv("VERCEL"):
        forwarded = (request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
        if forwarded:
            return forwarded[:256]
    return direct_host[:256]


async def handle_get_action(request: Request):
    payload = dict(request.query_params)
    if request.url.path == "/" and not payload.get("action"):
        return static_file_response("index.html")
    action = payload.get("action", "health")
    if action == "healthDiagnostics":
        return JSONResponse(
            public_error(ApiError("METHOD_NOT_ALLOWED", "Use o endpoint protegido de diagnóstico.")),
            status_code=405,
        )
    try:
        return JSONResponse(await run_in_threadpool(dispatch, action, payload))
    except Exception as error:
        return JSONResponse(public_error(error), status_code=400 if isinstance(error, ApiError) else 500)


async def handle_post_action(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    action = str(payload.get("action") or "")
    if not action:
        return JSONResponse(public_error(ApiError("ACTION_REQUIRED", "O campo action e obrigatorio.")), status_code=400)

    try:
        payload.pop("_requestSource", None)
        if action in {
            "registerStudentAccount",
            "completeStudentAccountVerification",
            "recoverStudentAccess",
            "completeStudentPasswordReset",
        }:
            payload["_requestSource"] = request_source(request)
        result = await run_in_threadpool(dispatch, action, payload)
        if isinstance(result, dict):
            result.pop("_backgroundNotificationIds", None)
        reset_delivery = result.pop("_passwordResetDelivery", None) if isinstance(result, dict) else None
        verification_delivery = result.pop("_accountVerificationDelivery", None) if isinstance(result, dict) else None
        if reset_delivery:
            try:
                await run_in_threadpool(
                    enqueue_identity_delivery, PASSWORD_RESET_JOB, reset_delivery
                )
            except Exception as error:
                logger.error(
                    "Password reset delivery could not be queued.",
                    extra={"event": "identity_job_enqueue_failed", "job_type": PASSWORD_RESET_JOB,
                           "error_type": error.__class__.__name__},
                )
        if verification_delivery:
            try:
                await run_in_threadpool(
                    enqueue_identity_delivery, ACCOUNT_VERIFICATION_JOB, verification_delivery
                )
            except Exception as error:
                logger.error(
                    "Account verification delivery could not be queued.",
                    extra={"event": "identity_job_enqueue_failed",
                           "job_type": ACCOUNT_VERIFICATION_JOB,
                           "error_type": error.__class__.__name__},
                )
                return JSONResponse(
                    public_error(ApiError(
                        "ACCOUNT_VERIFICATION_DELIVERY_FAILED",
                        ACCOUNT_VERIFICATION_DELIVERY_FAILED_MESSAGE,
                    )),
                    status_code=503,
                )
        return JSONResponse(result)
    except Exception as error:
        return JSONResponse(public_error(error), status_code=400 if isinstance(error, ApiError) else 500)


for route_path in ("/", "/api", "/api/index"):
    app.add_api_route(route_path, handle_get_action, methods=["GET"])
    app.add_api_route(route_path, handle_post_action, methods=["POST"])


async def handle_liveness():
    return JSONResponse({"status": "ok"})


async def handle_readiness():
    result = await run_in_threadpool(dispatch, "health", {})
    ready = result.get("data", {}).get("status") == "ready"
    return JSONResponse({"status": "ready" if ready else "not_ready"}, status_code=200 if ready else 503)


async def handle_health_diagnostics(request: Request):
    admin_token = request.headers.get("x-admin-token") or ""
    if not admin_token:
        return JSONResponse(
            public_error(ApiError("ADMIN_SESSION_REQUIRED", "É necessária uma sessão administrativa.")),
            status_code=401,
        )
    try:
        return JSONResponse(
            await run_in_threadpool(dispatch, "healthDiagnostics", {"adminToken": admin_token})
        )
    except Exception as error:
        return JSONResponse(public_error(error), status_code=403 if isinstance(error, ApiError) else 500)


app.add_api_route("/health/live", handle_liveness, methods=["GET"])
app.add_api_route("/health/ready", handle_readiness, methods=["GET"])
app.add_api_route("/health/diagnostics", handle_health_diagnostics, methods=["GET"])


def _runner_is_authorized(request: Request) -> bool:
    return runner_authorized(
        request.headers.get("authorization") or "",
        request.headers.get("x-job-runner-secret") or "",
    )


async def handle_operational_jobs(request: Request):
    if not _runner_is_authorized(request):
        return JSONResponse({"detail": "Not authorized."}, status_code=401)
    result = await run_in_threadpool(run_operational_cycle)
    return JSONResponse({"status": "processed", "result": result})


async def handle_operational_metrics(request: Request):
    if not _runner_is_authorized(request):
        return JSONResponse({"detail": "Not authorized."}, status_code=401)
    return JSONResponse({"status": "ok", "metrics": await run_in_threadpool(operational_metrics)})


app.add_api_route("/api/internal/jobs/run", handle_operational_jobs, methods=["POST"])
app.add_api_route("/health/metrics", handle_operational_metrics, methods=["GET"])


async def handle_certificate_pdf(certificate_id: str, request: Request):
    verification_base_url = f"{str(request.base_url).rstrip('/')}/verify.html"
    admin_token = request.query_params.get("adminToken") or request.headers.get("x-admin-token") or ""
    payload = {
        "certificateId": certificate_id,
        "sessionToken": request.query_params.get("sessionToken") or request.headers.get("x-session-token") or "",
        "adminToken": admin_token,
        "verificationBaseUrl": verification_base_url,
    }
    try:
        payload_builder = admin_certificate_pdf_payload if admin_token else certificate_pdf_payload
        result = await run_in_threadpool(payload_builder, payload)
        pdf_bytes = await run_in_threadpool(
            build_course_certificate_pdf,
            result["pdfData"],
            result["model"],
        )
        if not admin_token:
            await run_in_threadpool(record_certificate_download, payload)
        certificate_number = result["certificate"].get("certificateNumber") or certificate_id
        filename = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in certificate_number)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
        )
    except CertificateLayoutError as error:
        return JSONResponse(public_error(ApiError("CERTIFICATE_LAYOUT_INVALID", str(error))), status_code=400)
    except Exception as error:
        return JSONResponse(public_error(error), status_code=400 if isinstance(error, ApiError) else 500)


app.add_api_route("/api/certificates/{certificate_id}/pdf", handle_certificate_pdf, methods=["GET"])


def private_content_response(result: dict, force_download: bool = False):
    if result.get("redirectUrl"):
        return RedirectResponse(
            result["redirectUrl"],
            status_code=307,
            headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
        )
    disposition = "attachment" if force_download else "inline"
    filename = safe_download_name(result.get("fileName"))
    return Response(
        content=result.get("content") or b"",
        media_type=result.get("mimeType") or "application/octet-stream",
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def private_content_error_status(error: Exception) -> int:
    if not isinstance(error, ApiError):
        return 500
    if error.code in {
        "SESSION_REQUIRED",
        "INVALID_SESSION",
        "SESSION_EXPIRED",
        "ADMIN_SESSION_REQUIRED",
        "INVALID_ADMIN_SESSION",
        "STUDENT_SESSION_REQUIRED",
    }:
        return 401
    if error.code in {"FILE_NOT_FOUND", "PAYMENT_RECEIPT_NOT_FOUND"}:
        return 404
    if error.code in {
        "ADMIN_FORBIDDEN", "PERMISSION_DENIED", "FORBIDDEN", "ADMIN_NOT_ACTIVE", "STUDENT_NOT_ACTIVE"
    }:
        return 403
    return 400


async def handle_submission_file(file_id: str, request: Request):
    payload = {
        "fileId": file_id,
        "sessionToken": request.headers.get("x-session-token") or "",
        "adminToken": request.headers.get("x-admin-token") or "",
    }
    try:
        result = await run_in_threadpool(submission_file_download_payload, payload)
        return private_content_response(result, request.query_params.get("download") == "1")
    except Exception as error:
        return JSONResponse(public_error(error), status_code=private_content_error_status(error))


async def handle_certificate_receipt(request_id: str, request: Request):
    payload = {
        "requestId": request_id,
        "sessionToken": request.headers.get("x-session-token") or "",
        "adminToken": request.headers.get("x-admin-token") or "",
    }
    try:
        result = await run_in_threadpool(certificate_receipt_download_payload, payload)
        return private_content_response(result, request.query_params.get("download") == "1")
    except Exception as error:
        return JSONResponse(public_error(error), status_code=private_content_error_status(error))


app.add_api_route("/api/files/{file_id}/content", handle_submission_file, methods=["GET"])
app.add_api_route(
    "/api/certificate-requests/{request_id}/receipt",
    handle_certificate_receipt,
    methods=["GET"],
)

app.include_router(typed_api_router)


def static_file_response(raw_path: str):
    path = (raw_path or "index.html").lstrip("/")
    aliases = {
        "admin": "admin.html",
        "verify": "verify.html",
        "connection-test": "connection-test.html",
    }
    path = aliases.get(path, path)
    for static_dir in STATIC_DIRS:
        static_root = static_dir.resolve()
        candidate = (static_root / path).resolve()
        if str(candidate).startswith(str(static_root)) and candidate.is_file():
            media_type = {".mjs": "text/javascript", ".ttf": "font/ttf"}.get(candidate.suffix.lower())
            return FileResponse(candidate, media_type=media_type)

    for static_dir in STATIC_DIRS:
        fallback = static_dir.resolve() / "404.html"
        if fallback.is_file():
            return FileResponse(fallback, status_code=404)

    return JSONResponse({"success": False, "error": {"code": "NOT_FOUND", "message": "Recurso não encontrado."}}, status_code=404)


async def handle_static_file(static_path: str):
    return static_file_response(static_path)


app.add_api_route("/{static_path:path}", handle_static_file, methods=["GET"])
