from typing import Annotated

from fastapi import APIRouter, Header, Path

from .contracts import AttemptStatusData, ERROR_RESPONSES, SuccessEnvelope
from .executor import execute_action


router = APIRouter(prefix="/api/v1/students/me/attempts", tags=["assessments"])
SessionToken = Annotated[str, Header(alias="X-Session-Token", min_length=1)]
AttemptId = Annotated[str, Path(min_length=1, max_length=128)]


@router.get(
    "/{attempt_id}",
    response_model=SuccessEnvelope[AttemptStatusData],
    responses=ERROR_RESPONSES,
)
async def get_attempt_status(
    attempt_id: AttemptId,
    session_token: SessionToken,
):
    return await execute_action(
        "getAttemptStatus",
        {
            "sessionToken": session_token,
            "attemptId": attempt_id,
        },
    )
