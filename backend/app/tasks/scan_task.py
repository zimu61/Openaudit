import asyncio
import logging

from celery import Celery
from datetime import datetime, timezone

from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "openaudit",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_concurrency=2,
    broker_connection_retry_on_startup=True,
    task_routes={
        "app.tasks.scan_task.run_scan_task": {"queue": "scans"},
    },
)


async def _mark_scan_failed(project_id: str, scan_id: str, error: str):
    """Fallback: update DB to mark scan/project as failed when task crashes."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.models.scan import Scan
    from app.models.project import Project

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as db:
            result = await db.execute(select(Scan).where(Scan.id == scan_id))
            scan = result.scalar_one_or_none()
            if scan and scan.status not in ("completed", "failed"):
                scan.status = "failed"
                scan.error_message = error[:2000]
                scan.completed_at = datetime.now(timezone.utc)

            result = await db.execute(select(Project).where(Project.id == project_id))
            project = result.scalar_one_or_none()
            if project and project.status == "scanning":
                project.status = "failed"

            await db.commit()
    finally:
        await engine.dispose()


@celery_app.task(name="app.tasks.scan_task.run_scan_task", bind=True, max_retries=0)
def run_scan_task(self, project_id: str, scan_id: str):
    """Celery task that bridges to async scan service."""
    logger.info(f"Starting scan task: project={project_id}, scan={scan_id}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        from app.services.scan_service import ScanService

        service = ScanService()
        loop.run_until_complete(service.run_scan(project_id, scan_id))
        logger.info(f"Scan task completed: scan={scan_id}")
    except Exception as e:
        logger.exception(f"Scan task failed: {e}")
        try:
            loop.run_until_complete(_mark_scan_failed(project_id, scan_id, str(e)))
        except Exception:
            logger.exception("Failed to update scan status after task error")
    finally:
        loop.close()
