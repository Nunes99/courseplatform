from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from .actions import ApiError, admin_certificate_pdf_payload, certificate_pdf_payload, dispatch, public_error, record_certificate_download
from .certificate_pdf import build_course_certificate_pdf
from .config import get_settings

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


async def handle_get_action(request: Request):
    payload = dict(request.query_params)
    if request.url.path == "/" and not payload.get("action"):
        return static_file_response("index.html")
    action = payload.get("action", "health")
    try:
        return JSONResponse(dispatch(action, payload))
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
        return JSONResponse(dispatch(action, payload))
    except Exception as error:
        return JSONResponse(public_error(error), status_code=400 if isinstance(error, ApiError) else 500)


for route_path in ("/", "/api", "/api/index"):
    app.add_api_route(route_path, handle_get_action, methods=["GET"])
    app.add_api_route(route_path, handle_post_action, methods=["POST"])


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
        result = admin_certificate_pdf_payload(payload) if admin_token else certificate_pdf_payload(payload)
        pdf_bytes = build_course_certificate_pdf(result["pdfData"], result["model"])
        if not admin_token:
            record_certificate_download(payload)
        certificate_number = result["certificate"].get("certificateNumber") or certificate_id
        filename = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in certificate_number)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
        )
    except Exception as error:
        return JSONResponse(public_error(error), status_code=400 if isinstance(error, ApiError) else 500)


app.add_api_route("/api/certificates/{certificate_id}/pdf", handle_certificate_pdf, methods=["GET"])


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
            return FileResponse(candidate)

    for static_dir in STATIC_DIRS:
        fallback = static_dir.resolve() / "404.html"
        if fallback.is_file():
            return FileResponse(fallback, status_code=404)

    return JSONResponse({"success": False, "error": {"code": "NOT_FOUND", "message": "Recurso não encontrado."}}, status_code=404)


async def handle_static_file(static_path: str):
    return static_file_response(static_path)


app.add_api_route("/{static_path:path}", handle_static_file, methods=["GET"])
