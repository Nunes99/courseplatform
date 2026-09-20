from fastapi import APIRouter, BackgroundTasks, Header, Request
from fastapi.responses import JSONResponse

from ..actions import dispatch_student_account_verification, dispatch_student_password_reset

from .contracts import (
    AdminLoginRequest,
    AdminSessionData,
    AccountVerificationData,
    AccountVerificationRequest,
    ERROR_RESPONSES,
    LogoutData,
    PasswordResetCompletionRequest,
    PasswordResetData,
    PasswordResetRequest,
    PublicMessageData,
    StudentRegistrationRequest,
    StudentLoginRequest,
    StudentSessionData,
    SuccessEnvelope,
)
from .executor import execute_action


router = APIRouter(prefix="/api/v1/auth", tags=["identity"])


def _request_source(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    if forwarded:
        return forwarded[:256]
    return (request.client.host if request.client else "unknown")[:256]


async def _execute_public_identity_action(
    action: str,
    payload: dict,
    request: Request,
    background_tasks: BackgroundTasks,
):
    payload["_requestSource"] = _request_source(request)
    result = await execute_action(action, payload)
    if isinstance(result, JSONResponse):
        return result
    reset_delivery = result.pop("_passwordResetDelivery", None)
    verification_delivery = result.pop("_accountVerificationDelivery", None)
    if reset_delivery:
        background_tasks.add_task(
            dispatch_student_password_reset,
            reset_delivery.get("resetId", ""),
            reset_delivery.get("token", ""),
            str(request.base_url).rstrip("/"),
        )
    if verification_delivery:
        background_tasks.add_task(
            dispatch_student_account_verification,
            verification_delivery.get("verificationId", ""),
            verification_delivery.get("token", ""),
            str(request.base_url).rstrip("/"),
        )
    return result


@router.post(
    "/registrations",
    response_model=SuccessEnvelope[PublicMessageData],
    responses=ERROR_RESPONSES,
)
async def register_student_account(
    payload: StudentRegistrationRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    return await _execute_public_identity_action(
        "registerStudentAccount",
        payload.action_payload(),
        request,
        background_tasks,
    )


@router.post(
    "/registrations/verify",
    response_model=SuccessEnvelope[AccountVerificationData],
    responses=ERROR_RESPONSES,
)
async def verify_student_account(
    payload: AccountVerificationRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    return await _execute_public_identity_action(
        "completeStudentAccountVerification",
        payload.action_payload(),
        request,
        background_tasks,
    )


@router.post(
    "/password-resets",
    response_model=SuccessEnvelope[PublicMessageData],
    responses=ERROR_RESPONSES,
)
async def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    return await _execute_public_identity_action(
        "recoverStudentAccess",
        payload.action_payload(),
        request,
        background_tasks,
    )


@router.post(
    "/password-resets/complete",
    response_model=SuccessEnvelope[PasswordResetData],
    responses=ERROR_RESPONSES,
)
async def complete_password_reset(
    payload: PasswordResetCompletionRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    return await _execute_public_identity_action(
        "completeStudentPasswordReset",
        payload.action_payload(),
        request,
        background_tasks,
    )


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
