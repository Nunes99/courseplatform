import re
from typing import Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import Field, field_validator
from starlette.concurrency import run_in_threadpool

from ..contracts import ApiError, public_error
from ..domains import platform as platform_domain
from ..security import hash_secret
from .contracts import ERROR_RESPONSES, StrictRequest, SuccessEnvelope
from .executor import action_error_status


router = APIRouter(prefix="/api/v1/platform", tags=["platform"])


class PlatformLoginRequest(StrictRequest):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class OnboardingRequest(StrictRequest):
    idempotency_key: str = Field(alias="idempotencyKey", min_length=16, max_length=128)
    requested_slug: str = Field(alias="requestedSlug", min_length=3, max_length=80)
    display_name: str = Field(alias="displayName", min_length=2, max_length=160)
    legal_name: str | None = Field(default=None, alias="legalName", max_length=200)
    contact_name: str = Field(alias="contactName", min_length=2, max_length=160)
    contact_email: str = Field(alias="contactEmail", min_length=3, max_length=320)
    contact_phone: str | None = Field(default=None, alias="contactPhone", max_length=40)
    country_code: str | None = Field(default=None, alias="countryCode", max_length=3)
    website_url: str | None = Field(default=None, alias="websiteUrl", max_length=500)
    plan_code: Literal["STANDARD"] = Field(default="STANDARD", alias="planCode")
    requested_features: dict[str, Any] = Field(default_factory=dict, alias="requestedFeatures")
    applicant_notes: str | None = Field(default=None, alias="applicantNotes", max_length=2000)

    @field_validator("contact_email")
    @classmethod
    def validate_contact_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("Email institucional inválido.")
        return normalized

    @field_validator("website_url")
    @classmethod
    def validate_website_url(cls, value: str | None) -> str | None:
        if not value:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("O website deve usar HTTP ou HTTPS.")
        return value

    @field_validator("country_code")
    @classmethod
    def validate_country_code(cls, value: str | None) -> str | None:
        if not value:
            return None
        normalized = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{2,3}", normalized):
            raise ValueError("Código de país inválido.")
        return normalized


class OnboardingReviewRequest(StrictRequest):
    status: Literal[
        "SUBMITTED",
        "UNDER_REVIEW",
        "NEEDS_INFORMATION",
        "READY_FOR_PROVISIONING",
        "REJECTED",
        "CANCELLED",
    ]
    review_notes: str | None = Field(default=None, alias="reviewNotes", max_length=4000)


def _payload(model: StrictRequest) -> dict[str, Any]:
    return model.model_dump(by_alias=True, exclude_none=True)


async def _execute(operation, *args):
    try:
        return await run_in_threadpool(operation, *args)
    except Exception as error:
        return JSONResponse(public_error(error), status_code=action_error_status(error))


@router.post("/auth/sessions", responses=ERROR_RESPONSES)
async def create_session(payload: PlatformLoginRequest, request: Request):
    data = _payload(payload)
    data["userAgent"] = (request.headers.get("user-agent") or "")[:512]
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    data["ipHash"] = hash_secret(f"platform-session:{forwarded}") if forwarded else ""
    return await _execute(platform_domain.create_platform_session, data)


@router.get("/auth/sessions/current", responses=ERROR_RESPONSES)
async def current_session(
    platform_token: str = Header(alias="X-Platform-Token", min_length=1),
):
    return await _execute(platform_domain.current_platform_session, platform_token)


@router.delete("/auth/sessions/current", responses=ERROR_RESPONSES)
async def delete_session(
    platform_token: str = Header(alias="X-Platform-Token", min_length=1),
):
    return await _execute(platform_domain.delete_platform_session, platform_token)


@router.post(
    "/onboarding-requests",
    response_model=SuccessEnvelope[dict[str, Any]],
    responses=ERROR_RESPONSES,
)
async def submit_onboarding(payload: OnboardingRequest):
    return await _execute(platform_domain.submit_onboarding_request, _payload(payload))


@router.get("/dashboard", responses=ERROR_RESPONSES)
async def dashboard(
    platform_token: str = Header(alias="X-Platform-Token", min_length=1),
):
    return await _execute(platform_domain.platform_dashboard, platform_token)


@router.patch("/onboarding-requests/{request_id}", responses=ERROR_RESPONSES)
async def review_onboarding(
    request_id: str,
    payload: OnboardingReviewRequest,
    platform_token: str = Header(alias="X-Platform-Token", min_length=1),
):
    if not request_id or len(request_id) > 128:
        return JSONResponse(
            public_error(ApiError("INVALID_REQUEST_ID", "Identificador inválido.")),
            status_code=400,
        )
    return await _execute(
        platform_domain.update_onboarding_request,
        platform_token,
        request_id,
        _payload(payload),
    )
