import uuid
from datetime import datetime

from pydantic import BaseModel


class ScanCreate(BaseModel):
    pass  # No extra fields needed; scan is created from project


class ScanResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    progress: int
    current_step: str | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class FindingResponse(BaseModel):
    id: uuid.UUID
    scan_id: uuid.UUID
    source_node_id: int | None
    source_code: str | None
    source_location: str | None
    flow_description: str | None
    flow_code_snippets: dict | None
    vulnerability_type: str | None
    severity: str | None
    ai_analysis: str | None
    confidence: float | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FindingListResponse(BaseModel):
    findings: list[FindingResponse]
    total: int


class ScanListResponse(BaseModel):
    scans: list[ScanResponse]
    total: int


class ScanProgressMessage(BaseModel):
    scan_id: uuid.UUID
    status: str
    progress: int
    current_step: str | None
    message: str | None = None
