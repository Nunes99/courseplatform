from fastapi import APIRouter

from .administration import router as administration_router
from .enrollments import router as enrollments_router
from .identity import router as identity_router


router = APIRouter()
router.include_router(identity_router)
router.include_router(enrollments_router)
router.include_router(administration_router)
