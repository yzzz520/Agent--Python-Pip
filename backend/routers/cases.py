"""Case read endpoints plus the re-run action."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import config
from ..db import get_session
from ..deps import case_id_or_404
from ..jobs import submit_job
from ..models import AttributionReport, Case, Label, PipRun
from ..schemas import (
    CaseDetail,
    CaseListItem,
    JobCreate,
    JobOut,
    LabelOut,
    ReportOut,
    RunOut,
    VerificationOut,
)

router = APIRouter(prefix="/api/cases", tags=["cases"])

APPROACH_ORDER = {"rule": 0, "llm": 1, "agent": 2}


def _latest_run(case: Case) -> PipRun | None:
    return case.runs[-1] if case.runs else None


def _to_list_item(case: Case) -> CaseListItem:
    latest = _latest_run(case)
    return CaseListItem(
        id=case.id,
        repo=case.repo,
        path=case.path,
        priority=case.priority,
        category=case.category,
        returncode=latest.returncode if latest else None,
        failure_types={report.approach: report.failure_type for report in case.reports},
        label=case.label.failure_type if case.label else None,
        reviewed=bool(case.label and case.label.reviewed),
        fix_verified=any(report.fix_verified for report in case.reports),
        recovered=case.verification.recovered if case.verification else None,
    )


def _load_case(session: Session, case_id: str) -> Case:
    cid = case_id_or_404(case_id)
    case = session.scalars(
        select(Case)
        .where(Case.id == cid)
        .options(
            selectinload(Case.reports),
            selectinload(Case.runs),
            selectinload(Case.label),
            selectinload(Case.verification),
        )
    ).first()
    if case is None:
        raise HTTPException(status_code=404, detail=f"case {cid} not found")
    return case


@router.get("", response_model=list[CaseListItem], summary="List cases")
def list_cases(
    failure_type: str | None = Query(
        None, description="Only cases where any approach reported this failure type"
    ),
    priority: str | None = Query(None, description="P0 / P1 / P2"),
    reviewed: bool | None = Query(None, description="Filter by human review status"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> list[CaseListItem]:
    stmt = select(Case).options(
        selectinload(Case.reports),
        selectinload(Case.runs),
        selectinload(Case.label),
        selectinload(Case.verification),
    )

    if failure_type:
        stmt = stmt.where(Case.reports.any(AttributionReport.failure_type == failure_type))
    if priority:
        stmt = stmt.where(Case.priority == priority)
    if reviewed is not None:
        if reviewed:
            stmt = stmt.where(Case.label.has(Label.reviewed.is_(True)))
        else:
            stmt = stmt.where(~Case.label.has(Label.reviewed.is_(True)))

    stmt = stmt.order_by(Case.id).offset(offset).limit(limit)
    return [_to_list_item(case) for case in session.scalars(stmt).all()]


@router.get("/{case_id}", response_model=CaseDetail, summary="Case detail with all three reports")
def get_case(
    case_id: str,
    log_chars: int = Query(4000, ge=0, le=200_000),
    session: Session = Depends(get_session),
) -> CaseDetail:
    case = _load_case(session, case_id)

    log_tail = ""
    if case.error_log_path and log_chars:
        log_path = config.DATA_DIR / case.error_log_path
        if log_path.is_file():
            text = log_path.read_text(encoding="utf-8", errors="replace")
            log_tail = text[-log_chars:]

    reports = sorted(
        case.reports, key=lambda report: APPROACH_ORDER.get(report.approach, 99)
    )
    latest = _latest_run(case)

    return CaseDetail(
        id=case.id,
        repo=case.repo,
        path=case.path,
        commit_sha=case.commit_sha,
        priority=case.priority,
        category=case.category,
        source_url=case.source_url,
        sha256=case.sha256,
        requirements_text=case.requirements_text,
        error_log_tail=log_tail,
        reports=[ReportOut.model_validate(report) for report in reports],
        label=LabelOut.model_validate(case.label) if case.label else None,
        verification=VerificationOut.model_validate(case.verification)
        if case.verification
        else None,
        latest_run=RunOut.model_validate(latest) if latest else None,
    )


@router.get(
    "/{case_id}/log",
    response_class=PlainTextResponse,
    summary="Raw pip log (tail)",
)
def get_case_log(
    case_id: str,
    max_chars: int = Query(20_000, ge=1, le=500_000),
    session: Session = Depends(get_session),
) -> str:
    case = _load_case(session, case_id)
    if not case.error_log_path:
        raise HTTPException(status_code=404, detail="no pip log stored for this case")

    path = config.DATA_DIR / case.error_log_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"log file missing: {case.error_log_path}")
    return path.read_text(encoding="utf-8", errors="replace")[-max_chars:]


@router.get(
    "/{case_id}/patch",
    response_class=PlainTextResponse,
    summary="Verified requirements patch (if any)",
)
def get_case_patch(case_id: str, session: Session = Depends(get_session)) -> str:
    cid = case_id_or_404(case_id)
    path = config.DATA_DIR / "recovered" / f"case_{cid}.patch"
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"no verified patch for case {cid}")
    return path.read_text(encoding="utf-8", errors="replace")


@router.post(
    "/{case_id}/jobs",
    response_model=JobOut,
    status_code=202,
    summary="Queue a re-run (rule analysis or pip dry-run)",
)
def create_case_job(
    case_id: str,
    payload: JobCreate,
    session: Session = Depends(get_session),
) -> JobOut:
    case = _load_case(session, case_id)
    job = submit_job(case.id, payload.kind, payload.timeout)
    return JobOut.model_validate(job)
