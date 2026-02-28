"""Celery worker entry point.

Start with:
    celery -A celery_worker worker --loglevel=info -Q scans
"""

from app.tasks.scan_task import celery_app

if __name__ == "__main__":
    celery_app.start()
