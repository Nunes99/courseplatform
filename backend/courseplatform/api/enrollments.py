from fastapi import APIRouter, Header

from .contracts import ERROR_RESPONSES, StudentCoursesData, SuccessEnvelope
from .executor import execute_action


router = APIRouter(prefix="/api/v1/students", tags=["enrollments"])


@router.get(
    "/me/courses",
    response_model=SuccessEnvelope[StudentCoursesData],
    responses=ERROR_RESPONSES,
)
async def list_my_courses(
    session_token: str = Header(alias="X-Session-Token", min_length=1),
):
    return await execute_action("getMyCourses", {"sessionToken": session_token})
