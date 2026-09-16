from typing import Annotated, Literal

from fastapi import APIRouter, Header, Query

from .contracts import AdminStaffData, AdminStudentsData, ERROR_RESPONSES, SuccessEnvelope
from .executor import execute_action


router = APIRouter(prefix="/api/v1/admin", tags=["administration"])


@router.get(
    "/students",
    response_model=SuccessEnvelope[AdminStudentsData],
    responses=ERROR_RESPONSES,
)
async def list_students(
    admin_token: str = Header(alias="X-Admin-Token", min_length=1),
    query: Annotated[str, Query(max_length=256)] = "",
    status: Literal["ALL", "ACTIVE", "BLOCKED", "INACTIVE"] = "ALL",
    progress: Literal["ALL", "NOT_STARTED", "IN_PROGRESS", "COMPLETED"] = "ALL",
    sort: Literal["name", "progressDesc", "progressAsc", "recentLogin"] = "name",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    cursor: Annotated[str, Query(max_length=1024)] = "",
):
    return await execute_action(
        "adminListStudents",
        {
            "adminToken": admin_token,
            "query": query,
            "status": status,
            "progress": progress,
            "sort": sort,
            "limit": limit,
            "cursor": cursor,
        },
    )


@router.get(
    "/staff",
    response_model=SuccessEnvelope[AdminStaffData],
    responses=ERROR_RESPONSES,
)
async def list_staff(
    admin_token: str = Header(alias="X-Admin-Token", min_length=1),
    query: Annotated[str, Query(max_length=256)] = "",
    status: Literal["ALL", "ACTIVE", "INACTIVE"] = "ALL",
    role: Literal["ALL", "OWNER", "ADMIN", "REVIEWER"] = "ALL",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    cursor: Annotated[str, Query(max_length=1024)] = "",
):
    return await execute_action(
        "adminListStaff",
        {
            "adminToken": admin_token,
            "query": query,
            "status": status,
            "role": role,
            "limit": limit,
            "cursor": cursor,
        },
    )
