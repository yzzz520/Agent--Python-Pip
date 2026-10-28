"""Job polling endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..deps import case_id_or_404
from ..models import Job
from ..schemas import JobOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut], summary="Recent jobs")
def list_jobs(
    case_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[JobOut]:
    stmt = select(Job)
    if case_id:
        stmt = stmt.where(Job.case_id == case_id_or_404(case_id))
    stmt = stmt.order_by(Job.id.desc()).limit(limit)
    return [JobOut.model_validate(job) for job in session.scalars(stmt).all()]


@router.get("/{job_id}", response_model=JobOut, summary="One job")
def get_job(job_id: int, session: Session = Depends(get_session)) -> JobOut:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} not found")
    return JobOut.model_validate(job)
