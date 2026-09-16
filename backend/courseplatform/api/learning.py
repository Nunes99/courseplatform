from typing import Annotated

from fastapi import APIRouter, Header, Path, Query

from .contracts import (
    ERROR_RESPONSES,
    LearningDashboardData,
    LessonReadData,
    StudentHomeData,
    SuccessEnvelope,
)
from .executor import execute_action


router = APIRouter(prefix="/api/v1/students/me", tags=["learning"])
SessionToken = Annotated[str, Header(alias="X-Session-Token", min_length=1)]
CourseIdQuery = Annotated[str, Query(alias="courseId", max_length=128)]
EnrollmentIdQuery = Annotated[str, Query(alias="enrollmentId", max_length=128)]
LessonId = Annotated[str, Path(min_length=1, max_length=128)]


def learning_context_payload(
    session_token: str,
    course_id: str = "",
    enrollment_id: str = "",
) -> dict[str, str]:
    return {
        "sessionToken": session_token,
        "courseId": course_id,
        "enrollmentId": enrollment_id,
    }


@router.get(
    "/home",
    response_model=SuccessEnvelope[StudentHomeData],
    responses=ERROR_RESPONSES,
)
async def get_student_home(
    session_token: SessionToken,
    course_id: CourseIdQuery = "",
    enrollment_id: EnrollmentIdQuery = "",
):
    return await execute_action(
        "getStudentHome",
        learning_context_payload(session_token, course_id, enrollment_id),
    )


@router.get(
    "/dashboard",
    response_model=SuccessEnvelope[LearningDashboardData],
    responses=ERROR_RESPONSES,
)
async def get_learning_dashboard(
    session_token: SessionToken,
    course_id: CourseIdQuery = "",
    enrollment_id: EnrollmentIdQuery = "",
):
    return await execute_action(
        "getDashboard",
        learning_context_payload(session_token, course_id, enrollment_id),
    )


@router.get(
    "/lessons/{lesson_id}",
    response_model=SuccessEnvelope[LessonReadData],
    responses=ERROR_RESPONSES,
)
async def get_lesson(
    lesson_id: LessonId,
    session_token: SessionToken,
    enrollment_id: EnrollmentIdQuery = "",
):
    return await execute_action(
        "getLesson",
        {
            "sessionToken": session_token,
            "lessonId": lesson_id,
            "enrollmentId": enrollment_id,
        },
    )
