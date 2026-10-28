"""Relational model for the dataset.

Six tables, one per concept that actually exists in the pipeline:

    cases                 one downloaded requirements file (+ its provenance)
    pip_runs              the pip execution that produced the error log
    attribution_reports   one row per (case, approach); approach in rule/llm/agent
    labels                the human golden label for a case
    verifications         install-level verification of a proposed fix
    jobs                  async re-run requests issued through the API
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    repo: Mapped[Optional[str]] = mapped_column(String(200))
    path: Mapped[Optional[str]] = mapped_column(String(300))
    commit_sha: Mapped[Optional[str]] = mapped_column(String(64))
    priority: Mapped[Optional[str]] = mapped_column(String(8))
    category: Mapped[Optional[str]] = mapped_column(String(64))
    source_url: Mapped[Optional[str]] = mapped_column(String(500))
    sha256: Mapped[Optional[str]] = mapped_column(String(64))
    requirements_path: Mapped[Optional[str]] = mapped_column(String(300))
    requirements_text: Mapped[str] = mapped_column(Text, default="")
    error_log_path: Mapped[Optional[str]] = mapped_column(String(300))
    downloaded_at: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    runs: Mapped[list["PipRun"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="PipRun.id"
    )
    reports: Mapped[list["AttributionReport"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="AttributionReport.approach"
    )
    label: Mapped[Optional["Label"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", uselist=False
    )
    verification: Mapped[Optional["Verification"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", uselist=False
    )
    jobs: Mapped[list["Job"]] = relationship(back_populates="case", cascade="all, delete-orphan")


class PipRun(Base):
    __tablename__ = "pip_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    run_mode: Mapped[str] = mapped_column(String(16), default="dry-run")
    python: Mapped[Optional[str]] = mapped_column(String(300))
    pip_version: Mapped[Optional[str]] = mapped_column(String(200))
    returncode: Mapped[Optional[int]] = mapped_column(Integer)
    timed_out: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_sec: Mapped[Optional[float]] = mapped_column(Float)
    command: Mapped[Optional[str]] = mapped_column(Text)
    log_path: Mapped[Optional[str]] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    case: Mapped["Case"] = relationship(back_populates="runs")


class AttributionReport(Base):
    __tablename__ = "attribution_reports"
    __table_args__ = (
        UniqueConstraint("case_id", "approach", name="uq_report_case_approach"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    approach: Mapped[str] = mapped_column(String(16), index=True)
    failure_type: Mapped[str] = mapped_column(String(64), default="unknown")
    root_cause: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    suggestions: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    model: Mapped[Optional[str]] = mapped_column(String(100))
    prompt_version: Mapped[Optional[str]] = mapped_column(String(64))
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    fix_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_note: Mapped[Optional[str]] = mapped_column(Text)
    trace_path: Mapped[Optional[str]] = mapped_column(String(300))
    generated_at: Mapped[Optional[str]] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    case: Mapped["Case"] = relationship(back_populates="reports")


class Label(Base):
    __tablename__ = "labels"

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True
    )
    failure_type: Mapped[str] = mapped_column(String(64))
    root_cause_hint: Mapped[Optional[str]] = mapped_column(Text)
    acceptable: Mapped[list] = mapped_column(JSON, default=list)
    ambiguous: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[Optional[str]] = mapped_column(Text)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(64))
    reviewed_at: Mapped[Optional[str]] = mapped_column(String(32))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    case: Mapped["Case"] = relationship(back_populates="label")


class Verification(Base):
    __tablename__ = "verifications"

    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True
    )
    recovered: Mapped[bool] = mapped_column(Boolean, default=False)
    install_returncode: Mapped[Optional[int]] = mapped_column(Integer)
    pip_check_returncode: Mapped[Optional[int]] = mapped_column(Integer)
    install_duration_sec: Mapped[Optional[float]] = mapped_column(Float)
    fixed_requirements_path: Mapped[Optional[str]] = mapped_column(String(300))
    patch_path: Mapped[Optional[str]] = mapped_column(String(300))
    install_log_path: Mapped[Optional[str]] = mapped_column(String(300))
    venv_path: Mapped[Optional[str]] = mapped_column(String(300))
    generated_at: Mapped[Optional[str]] = mapped_column(String(64))

    case: Mapped["Case"] = relationship(back_populates="verification")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    timeout_sec: Mapped[int] = mapped_column(Integer, default=120)
    error: Mapped[Optional[str]] = mapped_column(Text)
    result: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    case: Mapped["Case"] = relationship(back_populates="jobs")
