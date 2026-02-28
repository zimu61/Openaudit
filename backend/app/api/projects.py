import uuid
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.project import Project
from app.models.scan import Scan
from app.schemas.project import ProjectResponse, ProjectListResponse
from app.schemas.scan import ScanResponse, ScanListResponse
from app.services.file_service import FileService

router = APIRouter()
file_service = FileService()


@router.post("/upload", response_model=ProjectResponse)
async def upload_project(
    file: UploadFile = File(...),
    name: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    valid_extensions = (".zip", ".tar.gz", ".tgz")
    if not any(file.filename.lower().endswith(ext) for ext in valid_extensions):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Accepted: {', '.join(valid_extensions)}",
        )

    # Save and extract
    upload_path, extracted_path, file_count = await file_service.save_and_extract(
        file, settings.UPLOAD_DIR, settings.WORKSPACE_DIR
    )

    project_name = name or Path(file.filename).stem
    project = Project(
        name=project_name,
        original_filename=file.filename,
        upload_path=str(extracted_path),
        file_count=file_count,
        status="uploaded",
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    total_result = await db.execute(select(func.count(Project.id)))
    total = total_result.scalar_one()

    result = await db.execute(
        select(Project).order_by(Project.created_at.desc()).offset(skip).limit(limit)
    )
    projects = result.scalars().all()
    return ProjectListResponse(projects=projects, total=total)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/{project_id}/scans", response_model=ScanListResponse)
async def list_project_scans(
    project_id: uuid.UUID,
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    # Verify project exists
    proj_result = await db.execute(select(Project).where(Project.id == project_id))
    if not proj_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    total_result = await db.execute(
        select(func.count(Scan.id)).where(Scan.project_id == project_id)
    )
    total = total_result.scalar_one()

    result = await db.execute(
        select(Scan)
        .where(Scan.project_id == project_id)
        .order_by(Scan.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    scans = result.scalars().all()
    return ScanListResponse(scans=scans, total=total)


@router.delete("/{project_id}")
async def delete_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Clean up files
    if project.upload_path and Path(project.upload_path).exists():
        shutil.rmtree(project.upload_path, ignore_errors=True)

    await db.delete(project)
    await db.commit()
    return {"detail": "Project deleted"}


@router.post("/{project_id}/scan", response_model=ScanResponse)
async def start_scan(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == "scanning":
        # Check if there's actually a running scan, not a stale status
        active_result = await db.execute(
            select(Scan).where(
                Scan.project_id == project.id,
                Scan.status.notin_(["completed", "failed"]),
            )
        )
        active_scan = active_result.scalar_one_or_none()
        if active_scan:
            raise HTTPException(status_code=409, detail="A scan is already running")
        # Stale status from a previously crashed scan — allow re-scan
        project.status = "uploaded"

    scan = Scan(project_id=project.id, status="pending", progress=0)
    db.add(scan)
    project.status = "scanning"
    await db.commit()
    await db.refresh(scan)

    # Dispatch Celery task
    from app.tasks.scan_task import run_scan_task

    run_scan_task.delay(str(project.id), str(scan.id))

    return scan
