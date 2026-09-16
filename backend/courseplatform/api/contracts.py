from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


DataT = TypeVar("DataT")


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    def action_payload(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)


class SuccessEnvelope(BaseModel, Generic[DataT]):
    success: Literal[True] = True
    data: DataT


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorEnvelope(BaseModel):
    success: Literal[False] = False
    error: ErrorBody


ERROR_RESPONSES = {
    400: {"model": ErrorEnvelope, "description": "Pedido inválido."},
    401: {"model": ErrorEnvelope, "description": "Sessão ou credenciais inválidas."},
    403: {"model": ErrorEnvelope, "description": "Operação não autorizada."},
    404: {"model": ErrorEnvelope, "description": "Recurso não encontrado."},
    409: {"model": ErrorEnvelope, "description": "Conflito com o estado atual."},
    503: {"model": ErrorEnvelope, "description": "Dependência indisponível."},
}


class StudentLoginRequest(StrictRequest):
    email: str = Field(min_length=3, max_length=320)
    access_code: str = Field(alias="accessCode", min_length=1, max_length=256)
    course_id: str | None = Field(default=None, alias="courseId", max_length=128)


class AdminLoginRequest(StrictRequest):
    email: str = Field(min_length=3, max_length=320)
    admin_key: str = Field(alias="adminKey", min_length=1, max_length=256)


class StudentSessionData(BaseModel):
    sessionToken: str
    expiresAt: str | None = None
    student: dict[str, Any]


class AdminSessionData(BaseModel):
    adminToken: str
    expiresAt: str | None = None
    admin: dict[str, Any]


class LogoutData(BaseModel):
    loggedOut: bool


class StudentCoursesData(BaseModel):
    student: dict[str, Any]
    courses: list[dict[str, Any]]
    notificationChannelInfo: dict[str, Any]


class CursorPageInfo(BaseModel):
    limit: int
    returned: int
    hasMore: bool
    nextCursor: str
    total: int | None = None


class AdminStudentsData(BaseModel):
    students: list[dict[str, Any]]
    total: int
    limit: int
    pagination: CursorPageInfo
    summary: dict[str, Any]


class AdminStaffData(BaseModel):
    staff: list[dict[str, Any]]
    currentAdmin: dict[str, Any]
    pagination: CursorPageInfo
    summary: dict[str, Any]


class CourseCatalogData(BaseModel):
    course: dict[str, Any] | None = None
    lessons: list[dict[str, Any]]


class MediaConfigData(BaseModel):
    mediaConfig: dict[str, Any]


class LearningDashboardData(BaseModel):
    student: dict[str, Any]
    course: dict[str, Any]
    courseVersion: dict[str, Any]
    offering: dict[str, Any]
    enrollment: dict[str, Any]
    lessons: list[dict[str, Any]]


class StudentHomeData(BaseModel):
    student: dict[str, Any]
    courses: list[dict[str, Any]]
    selectedCourseId: str
    selectedEnrollmentId: str
    dashboard: dict[str, Any]
    mediaConfig: dict[str, Any]


class LessonReadData(BaseModel):
    lesson: dict[str, Any]
    enrollment: dict[str, Any]
    courseVersion: dict[str, Any]
    progress: dict[str, Any]
    content: list[dict[str, Any]]
    questions: list[dict[str, Any]]


class AttemptStatusData(BaseModel):
    attempt: dict[str, Any]
    questions: list[dict[str, Any]]
    answers: list[dict[str, Any]]
    files: list[dict[str, Any]]
    latestReview: dict[str, Any] | None = None
    feedbackPolicy: dict[str, Any]
