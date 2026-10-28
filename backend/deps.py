"""Shared FastAPI helpers."""

from __future__ import annotations

from fastapi import HTTPException

from . import config


def case_id_or_404(value: str) -> str:
    """Normalize a case id from the URL, mapping malformed ids to 404."""

    try:
        return config.normalize_case_id(value)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
