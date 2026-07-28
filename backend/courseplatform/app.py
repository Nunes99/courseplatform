from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .actions import ApiError, dispatch, public_error
from .config import get_settings

settings = get_settings()

app = FastAPI(title="CoursePlatform Python API", version=settings.app_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/")
async def get_action(request: Request):
    payload = dict(request.query_params)
    action = payload.get("action", "health")
    try:
        return JSONResponse(dispatch(action, payload))
    except Exception as error:
        return JSONResponse(public_error(error), status_code=400 if isinstance(error, ApiError) else 500)


@app.post("/")
async def post_action(request: Request):
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
