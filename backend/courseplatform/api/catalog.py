from typing import Annotated

from fastapi import APIRouter, Path

from .contracts import CourseCatalogData, ERROR_RESPONSES, MediaConfigData, SuccessEnvelope
from .executor import execute_action


router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])
CourseId = Annotated[str, Path(min_length=1, max_length=128)]


@router.get(
    "/courses/{course_id}",
    response_model=SuccessEnvelope[CourseCatalogData],
    responses=ERROR_RESPONSES,
)
async def get_course_catalog(course_id: CourseId):
    return await execute_action("publicCourseConfig", {"courseId": course_id})


@router.get(
    "/courses/{course_id}/media",
    response_model=SuccessEnvelope[MediaConfigData],
    responses=ERROR_RESPONSES,
)
async def get_public_media(course_id: CourseId):
    return await execute_action("publicMediaConfig", {"courseId": course_id})
