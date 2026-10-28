"""In-process job worker.

FastAPI's BackgroundTasks would block the response until the pip run finishes;
a small thread pool plus a ``jobs`` row keeps the API responsive and lets the
client poll ``GET /api/jobs/{id}``.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import Job
from .services import execute_job

logger = logging.getLogger("pipattr.jobs")

# Two workers is enough for a demo dataset and keeps SQLite write contention low.
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pipattr-job")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def submit_job(case_id: str, kind: str, timeout: int = 120) -> Job:
    """Persist a queued job and hand it to the pool. Returns the stored row."""

    with SessionLocal() as session:
        job = Job(case_id=case_id, kind=kind, status="queued", timeout_sec=timeout)
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

    _executor.submit(_run_job, job_id)

    with SessionLocal() as session:
        stored = session.get(Job, job_id)
        if stored is None:  # pragma: no cover - only if the row was deleted
            raise RuntimeError(f"job {job_id} disappeared right after insert")
        return stored


def _finish(
    session: Session,
    job_id: int,
    *,
    status: str,
    error: str | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    job = session.get(Job, job_id)
    if job is None:  # pragma: no cover
        return
    job.status = status
    job.error = error
    job.result = result
    job.finished_at = _now()
    session.commit()


def _run_job(job_id: int) -> None:
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        if job is None:  # pragma: no cover
            return

        job.status = "running"
        job.started_at = _now()
        session.commit()

        try:
            result = execute_job(
                session, job.case_id, job.kind, timeout=job.timeout_sec or 120
            )
        except Exception as exc:  # noqa: BLE001 - job failures are data, not crashes
            logger.exception("job %s failed", job_id)
            session.rollback()
            _finish(session, job_id, status="failed", error=str(exc)[:2000])
            return

        _finish(session, job_id, status="succeeded", result=result)
