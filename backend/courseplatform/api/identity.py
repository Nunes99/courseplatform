from fastapi import APIRouter, Header, Request

from .contracts import (
    AdminLoginRequest,
    AdminSessionData,
    ERROR_RESPONSES,
    LogoutData,
    StudentLoginRequest,
    StudentSessionData,
    SuccessEnvelope,
)
from .executor import execute_action


router = APIRouter(prefix="/api/v1/auth", tags=["identity"])


@router.post(
    "/students/sessions",
    response_model=SuccessEnvelope[StudentSessionData],
    responses=ERROR_RESPONSES,
)
async def create_student_session(payload: StudentLoginRequest, request: Request):
    action_payload = payload.action_payload()
    action_payload["userAgent"] = request.headers.get("user-agent", "")[:512]
    return await execute_action("login", action_payload)


@router.delete(
    "/students/sessions/current",
    response_model=SuccessEnvelope[LogoutData],
    responses=ERROR_RESPONSES,
)
async def delete_student_session(
    session_token: str = Header(alias="X-Session-Token", min_length=1),
):
    return await execute_action("logout", {"sessionToken": session_token})


@router.post(
    "/administrators/sessions",
    response_model=SuccessEnvelope[AdminSessionData],
    responses=ERROR_RESPONSES,
)
async def create_admin_session(payload: AdminLoginRequest, request: Request):
    action_payload = payload.action_payload()
    action_payload["userAgent"] = request.headers.get("user-agent", "")[:512]
    return await execute_action("adminLogin", action_payload)


@router.delete(
    "/administrators/sessions/current",
    response_model=SuccessEnvelope[LogoutData],
    responses=ERROR_RESPONSES,
)
async def delete_admin_session(
    admin_token: str = Header(alias="X-Admin-Token", min_length=1),
):
    return await execute_action("adminLogout", {"adminToken": admin_token})
