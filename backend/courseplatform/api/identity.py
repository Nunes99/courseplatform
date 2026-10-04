import logging

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from ..actions import ACCOUNT_VERIFICATION_DELIVERY_FAILED_MESSAGE
from ..contracts import ApiError, public_error
from ..jobs import (
    ACCOUNT_VERIFICATION_JOB,
    PASSWORD_RESET_JOB,
    enqueue_identity_delivery,
)

from .contracts import (
    AdminLoginRequest,
    AdminSessionData,
    AccountVerificationData,
    AccountVerificationRequest,
    ERROR_RESPONSES,
    LogoutData,
    OrganizationSwitchRequest,
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
logger = logging.getLogger(__name__)


def _request_source(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    if forwarded:
        return forwarded[:256]
    return (request.client.host if request.client else "unknown")[:256]


async def _execute_public_identity_action(
    action: str,
    payload: dict,
    request: Request,
):
    payload["_requestSource"] = _request_source(request)
    result = await execute_action(action, payload)
    if isinstance(result, JSONResponse):
        return result
    reset_delivery = result.pop("_passwordResetDelivery", None)
    verification_delivery = result.pop("_accountVerificationDelivery", None)
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
    return result


@router.post(
    "/registrations",
    response_model=SuccessEnvelope[PublicMessageData],
    responses=ERROR_RESPONSES,
)
async def register_student_account(
    payload: StudentRegistrationRequest,
    request: Request,
):
    return await _execute_public_identity_action(
        "registerStudentAccount",
        payload.action_payload(),
        request,
    )


@router.post(
    "/registrations/verify",
    response_model=SuccessEnvelope[AccountVerificationData],
    responses=ERROR_RESPONSES,
)
async def verify_student_account(
    payload: AccountVerificationRequest,
    request: Request,
):
    return await _execute_public_identity_action(
        "completeStudentAccountVerification",
        payload.action_payload(),
        request,
    )


@router.post(
    "/password-resets",
    response_model=SuccessEnvelope[PublicMessageData],
    responses=ERROR_RESPONSES,
)
async def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
):
    return await _execute_public_identity_action(
        "recoverStudentAccess",
        payload.action_payload(),
        request,
    )


@router.post(
    "/password-resets/complete",
    response_model=SuccessEnvelope[PasswordResetData],
    responses=ERROR_RESPONSES,
)
async def complete_password_reset(
    payload: PasswordResetCompletionRequest,
    request: Request,
):
    return await _execute_public_identity_action(
        "completeStudentPasswordReset",
        payload.action_payload(),
        request,
    )


@router.post(
    "/students/sessions",
    response_model=SuccessEnvelope[StudentSessionData],
    response_model_exclude_none=True,
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
    "/students/sessions/current/organization",
    response_model=SuccessEnvelope[StudentSessionData],
    response_model_exclude_none=True,
    responses=ERROR_RESPONSES,
)
async def switch_student_session_organization(
    payload: OrganizationSwitchRequest,
    request: Request,
    session_token: str = Header(alias="X-Session-Token", min_length=1),
):
    action_payload = payload.action_payload()
    action_payload["sessionToken"] = session_token
    action_payload["userAgent"] = request.headers.get("user-agent", "")[:512]
    return await execute_action("switchStudentOrganization", action_payload)


@router.post(
    "/administrators/sessions",
    response_model=SuccessEnvelope[AdminSessionData],
    response_model_exclude_none=True,
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


@router.post(
    "/administrators/sessions/current/organization",
    response_model=SuccessEnvelope[AdminSessionData],
    response_model_exclude_none=True,
    responses=ERROR_RESPONSES,
)
async def switch_admin_session_organization(
    payload: OrganizationSwitchRequest,
    request: Request,
    admin_token: str = Header(alias="X-Admin-Token", min_length=1),
):
    action_payload = payload.action_payload()
    action_payload["adminToken"] = admin_token
    action_payload["userAgent"] = request.headers.get("user-agent", "")[:512]
    return await execute_action("switchAdminOrganization", action_payload)
