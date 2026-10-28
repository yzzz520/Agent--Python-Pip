"""Aggregated evaluation numbers, computed from the database instead of files."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_session
from ..schemas import ApproachStats, StatsOut
from ..services import build_stats

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=StatsOut, summary="Three-way accuracy and cost")
def get_stats(session: Session = Depends(get_session)) -> StatsOut:
    payload = build_stats(session)
    payload["by_approach"] = [ApproachStats(**item) for item in payload["by_approach"]]
    return StatsOut(**payload)
