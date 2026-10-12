from typing import Any

from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .. import actions
from ..contracts import ApiError, public_error


AUTHENTICATION_ERRORS = {
    "ADMIN_SESSION_REQUIRED",
    "INVALID_ADMIN_CREDENTIALS",
    "INVALID_ADMIN_SESSION",
    "INVALID_CREDENTIALS",
    "INVALID_SESSION",
    "SESSION_EXPIRED",
    "SESSION_REQUIRED",
    "STUDENT_SESSION_REQUIRED",
    "PLATFORM_SESSION_REQUIRED",
    "INVALID_PLATFORM_CREDENTIALS",
    "INVALID_PLATFORM_SESSION",
    "PLATFORM_SESSION_EXPIRED",
}
AUTHORIZATION_ERRORS = {
    "ADMIN_FORBIDDEN",
    "ADMIN_NOT_ACTIVE",
    "FORBIDDEN",
    "LESSON_LOCKED",
    "PERMISSION_DENIED",
    "ORGANIZATION_ACCESS_DENIED",
    "ORGANIZATION_ACCESS_REVOKED",
    "ORGANIZATION_ACCESS_UNAVAILABLE",
    "SESSION_ORGANIZATION_MISMATCH",
    "STUDENT_NOT_ACTIVE",
    "PLATFORM_ACCESS_REVOKED",
    "PLATFORM_FORBIDDEN",
}
NOT_FOUND_ERRORS = {
    "ADMIN_NOT_FOUND",
    "COURSE_NOT_FOUND",
    "ENROLLMENT_NOT_FOUND",
    "FILE_NOT_FOUND",
    "LESSON_NOT_FOUND",
    "ORGANIZATION_NOT_FOUND",
    "ONBOARDING_REQUEST_NOT_FOUND",
    "STUDENT_NOT_FOUND",
}
CONFLICT_ERRORS = {
    "DUPLICATE_EMAIL",
    "EMAIL_ALREADY_REGISTERED",
    "OFFERING_CAPACITY_REACHED",
    "ORGANIZATION_SLUG_UNAVAILABLE",
    "ONBOARDING_REQUEST_EXISTS",
    "IDEMPOTENCY_KEY_CONFLICT",
}
UNAVAILABLE_ERRORS = {
    "ACCOUNT_VERIFICATION_DELIVERY_FAILED",
    "DATABASE_AUTH_ERROR",
    "DATABASE_MIGRATION_REQUIRED",
    "DATABASE_PERMISSION_ERROR",
    "DATABASE_SCHEMA_ERROR",
    "DATABASE_UNAVAILABLE",
}
RATE_LIMIT_ERRORS = {"ONBOARDING_RATE_LIMITED"}


def action_error_status(error: Exception) -> int:
    if not isinstance(error, ApiError):
        return 500
    if error.code in AUTHENTICATION_ERRORS:
        return 401
    if error.code in AUTHORIZATION_ERRORS:
        return 403
    if error.code in NOT_FOUND_ERRORS:
        return 404
    if error.code in CONFLICT_ERRORS:
        return 409
    if error.code in UNAVAILABLE_ERRORS:
        return 503
    if error.code in RATE_LIMIT_ERRORS:
        return 429
    return 400


async def execute_action(action: str, payload: dict[str, Any]):
    try:
        return await run_in_threadpool(actions.dispatch, action, payload)
    except Exception as error:
        return JSONResponse(public_error(error), status_code=action_error_status(error))
