"""Response / request models. Pydantic v2, exposed in the OpenAPI schema."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _none_to_list(value: object) -> object:
    """JSON columns may be NULL in hand-edited rows; never fail validation on it."""

    return [] if value is None else value


StrList = Annotated[list[str], BeforeValidator(_none_to_list)]


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    approach: str
    failure_type: str
    root_cause: str = ""
    evidence: StrList = Field(default_factory=list)
    suggestions: StrList = Field(default_factory=list)
    confidence: float = 0.0
    model: str | None = None
    prompt_version: str | None = None
    total_tokens: int = 0
    tool_calls: int = 0
    latency_ms: int | None = None
    fix_verified: bool = False
    verification_note: str | None = None
    trace_path: str | None = None
    generated_at: str | None = None


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_mode: str
    returncode: int | None = None
    timed_out: bool = False
    duration_sec: float | None = None
    python: str | None = None
    pip_version: str | None = None
    log_path: str | None = None


class LabelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    case_id: str
    failure_type: str
    root_cause_hint: str | None = None
    acceptable: StrList = Field(default_factory=list)
    ambiguous: bool = False
    note: str | None = None
    reviewed: bool = False
    reviewed_by: str | None = None
    reviewed_at: str | None = None


class VerificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    case_id: str
    recovered: bool = False
    install_returncode: int | None = None
    pip_check_returncode: int | None = None
    install_duration_sec: float | None = None
    fixed_requirements_path: str | None = None
    patch_path: str | None = None
    install_log_path: str | None = None
    venv_path: str | None = None
    generated_at: str | None = None


class CaseListItem(BaseModel):
    id: str
    repo: str | None = None
    path: str | None = None
    priority: str | None = None
    category: str | None = None
    returncode: int | None = None
    failure_types: dict[str, str | None] = Field(default_factory=dict)
    label: str | None = None
    reviewed: bool = False
    fix_verified: bool = False
    recovered: bool | None = None


class CaseDetail(BaseModel):
    id: str
    repo: str | None = None
    path: str | None = None
    commit_sha: str | None = None
    priority: str | None = None
    category: str | None = None
    source_url: str | None = None
    sha256: str | None = None
    requirements_text: str = ""
    error_log_tail: str = ""
    reports: list[ReportOut] = Field(default_factory=list)
    label: LabelOut | None = None
    verification: VerificationOut | None = None
    latest_run: RunOut | None = None


class LabelIn(BaseModel):
    failure_type: str
    root_cause_hint: str | None = None
    acceptable: list[str] = Field(default_factory=list)
    ambiguous: bool = False
    note: str | None = None
    reviewed: bool = True
    reviewed_by: str = "manual"


class JobCreate(BaseModel):
    kind: Literal["rule", "pip"] = "rule"
    timeout: int = Field(default=120, ge=10, le=600)


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: str
    kind: str
    status: str
    timeout_sec: int = 120
    error: str | None = None
    result: dict | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ApproachStats(BaseModel):
    approach: str
    label: str
    evaluated: int
    strict_correct: int
    lenient_correct: int
    strict_accuracy: float | None = None
    lenient_accuracy: float | None = None
    average_confidence: float | None = None
    total_tokens: int = 0
    total_tool_calls: int = 0
    fix_verified: int = 0


class StatsOut(BaseModel):
    case_count: int
    labeled_count: int
    reviewed_count: int
    by_approach: list[ApproachStats]
    dataset_failure_type_counts: dict[str, int]
    label_failure_type_counts: dict[str, int]
