import uuid
from datetime import datetime

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str | None = None  # If not provided, derived from filename


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    original_filename: str
    upload_path: str
    language: str | None
    file_count: int
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]
    total: int
