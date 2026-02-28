import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.project import Project
from app.models.scan import Scan, Finding
from app.schemas.scan import ScanResponse, FindingResponse, FindingListResponse
from app.services.report_service import ReportService

router = APIRouter()


@router.post("/{scan_id}", response_model=ScanResponse, include_in_schema=False)
async def _placeholder(scan_id: uuid.UUID):
    """Placeholder - scan creation is under /api/projects/{id}/scan"""
    raise HTTPException(status_code=404)


@router.get("/{scan_id}", response_model=ScanResponse)
async def get_scan(scan_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = result.scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan


@router.get("/{scan_id}/findings", response_model=FindingListResponse)
async def get_findings(
    scan_id: uuid.UUID,
    skip: int = 0,
    limit: int = 50,
    severity: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    # Verify scan exists
    scan_result = await db.execute(select(Scan).where(Scan.id == scan_id))
    if not scan_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Scan not found")

    query = select(Finding).where(Finding.scan_id == scan_id)
    count_query = select(func.count(Finding.id)).where(Finding.scan_id == scan_id)

    if severity:
        query = query.where(Finding.severity == severity)
        count_query = count_query.where(Finding.severity == severity)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    result = await db.execute(
        query.order_by(Finding.created_at.desc()).offset(skip).limit(limit)
    )
    findings = result.scalars().all()
    return FindingListResponse(findings=findings, total=total)


@router.get("/{scan_id}/report")
async def download_report(scan_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    # Verify scan exists and is completed
    result = await db.execute(select(Scan).where(Scan.id == scan_id))
    scan = result.scalar_one_or_none()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    if scan.status != "completed":
        raise HTTPException(
            status_code=400, detail="Report is only available for completed scans"
        )

    buf, filename = await ReportService.generate_scan_report(db, scan_id)
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
