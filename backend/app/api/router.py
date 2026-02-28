from fastapi import APIRouter

from app.api.projects import router as projects_router
from app.api.scans import router as scans_router

api_router = APIRouter()
api_router.include_router(projects_router, prefix="/projects", tags=["projects"])
api_router.include_router(scans_router, prefix="/scans", tags=["scans"])
