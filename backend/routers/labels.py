"""Golden label management: the human-in-the-loop part of the API."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..deps import case_id_or_404
from ..models import Case, Label
from ..schemas import LabelIn, LabelOut

router = APIRouter(prefix="/api/labels", tags=["labels"])


@router.get("", response_model=list[LabelOut], summary="List every label")
def list_labels(session: Session = Depends(get_session)) -> list[LabelOut]:
    labels = session.scalars(select(Label).order_by(Label.case_id)).all()
    return [LabelOut.model_validate(label) for label in labels]


@router.get("/{case_id}", response_model=LabelOut, summary="One label")
def get_label(case_id: str, session: Session = Depends(get_session)) -> LabelOut:
    label = session.get(Label, case_id_or_404(case_id))
    if label is None:
        raise HTTPException(status_code=404, detail="label not found")
    return LabelOut.model_validate(label)


@router.put("/{case_id}", response_model=LabelOut, summary="Create or update a label")
def put_label(
    case_id: str, payload: LabelIn, session: Session = Depends(get_session)
) -> LabelOut:
    cid = case_id_or_404(case_id)
    if session.get(Case, cid) is None:
        raise HTTPException(status_code=404, detail=f"case {cid} not found")

    label = session.get(Label, cid)
    if label is None:
        label = Label(case_id=cid, failure_type=payload.failure_type)
        session.add(label)

    label.failure_type = payload.failure_type
    label.root_cause_hint = payload.root_cause_hint
    label.acceptable = list(payload.acceptable)
    label.ambiguous = payload.ambiguous
    label.note = payload.note
    label.reviewed = payload.reviewed
    if payload.reviewed:
        label.reviewed_by = payload.reviewed_by
        label.reviewed_at = date.today().isoformat()

    session.commit()
    session.refresh(label)
    return LabelOut.model_validate(label)
