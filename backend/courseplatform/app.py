import os
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from .actions import (
    ApiError,
    admin_certificate_pdf_payload,
    certificate_pdf_payload,
    certificate_receipt_download_payload,
    dispatch,
    dispatch_notification_deliveries,
    dispatch_student_password_reset,
    public_error,
    record_certificate_download,
    submission_file_download_payload,
)
from .certificate_pdf import CertificateLayoutError, build_course_certificate_pdf
from .config import get_settings
from .storage import safe_download_name

settings = get_settings()
STATIC_DIRS = [
    Path(__file__).resolve().parents[2] / "public",
    Path(__file__).resolve().parent / "static",
]

app = FastAPI(title="CoursePlatform Python API", version=settings.app_version)

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


async def handle_post_action(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    action = str(payload.get("action") or "")
    if not action:
        return JSONResponse(public_error(ApiError("ACTION_REQUIRED", "O campo action e obrigatorio.")), status_code=400)

    try:
        payload.pop("_requestSource", None)
        if action in {"recoverStudentAccess", "completeStudentPasswordReset"}:
            payload["_requestSource"] = request_source(request)
        result = await run_in_threadpool(dispatch, action, payload)
        notification_ids = result.pop("_backgroundNotificationIds", []) if isinstance(result, dict) else []
        reset_delivery = result.pop("_passwordResetDelivery", None) if isinstance(result, dict) else None
        if notification_ids:
            background_tasks.add_task(dispatch_notification_deliveries, notification_ids)
        if reset_delivery:
            background_tasks.add_task(
                dispatch_student_password_reset,
                reset_delivery.get("resetId", ""),
                reset_delivery.get("token", ""),
                str(request.base_url).rstrip("/"),
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
