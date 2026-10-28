"""Ingest the offline artifacts into the relational schema.

The pipeline writes JSON files; this module is the only place that knows their
shape. Every write is an upsert keyed by (case_id) or (case_id, approach), so
``sync`` can be re-run at any time without producing duplicates.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .models import AttributionReport, Case, Label, PipRun, Verification

REPORT_DIRS = {
    "rule": "reports_all",
    "llm": "reports_llm_all",
    "agent": "reports_agent_all",
}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def discover_case_ids() -> list[str]:
    """Union of case ids that have a requirements file or an error log."""

    ids: set[str] = set()
    for pattern in ("requirements_all/requirements_*.txt", "error_all/error_case_*.txt"):
        for path in config.DATA_DIR.glob(pattern):
            suffix = path.stem.rsplit("_", 1)[-1]
            if suffix.isdigit():
                ids.add(suffix.zfill(3))
    return sorted(ids)


def load_manifest() -> dict[str, dict[str, Any]]:
    payload = _read_json(config.DATA_DIR / "manifest.json") or {}
    entries = payload.get("entries") or []
    return {str(entry.get("case_id")): entry for entry in entries if entry.get("case_id")}


def load_labels() -> dict[str, dict[str, Any]]:
    payload = _read_json(config.DATA_DIR / "golden_labels.json") or {}
    labels = payload.get("labels") or {}
    return {str(key): value for key, value in labels.items() if isinstance(value, dict)}


def upsert_report(
    session: Session, case_id: str, approach: str, payload: dict[str, Any] | None
) -> AttributionReport | None:
    """Create or refresh one attribution report row."""

    if not payload:
        return None

    report = session.scalars(
        select(AttributionReport).where(
            AttributionReport.case_id == case_id,
            AttributionReport.approach == approach,
        )
    ).first()
    if report is None:
        report = AttributionReport(case_id=case_id, approach=approach)
        session.add(report)

    report.failure_type = str(payload.get("failure_type") or "unknown")
    report.root_cause = str(payload.get("root_cause") or "")
    report.evidence = list(payload.get("evidence") or [])
    report.suggestions = list(payload.get("suggestions") or [])
    report.confidence = float(payload.get("confidence") or 0.0)
    report.model = payload.get("model")
    report.prompt_version = payload.get("prompt_version")
    report.total_tokens = int(payload.get("total_tokens") or 0)
    report.tool_calls = int(payload.get("tool_calls") or 0)
    report.latency_ms = payload.get("latency_ms")
    report.fix_verified = bool(payload.get("fix_verified") or False)
    report.verification_note = payload.get("verification_note")
    report.trace_path = payload.get("trace_file")
    report.generated_at = payload.get("generated_at")
    return report


def _upsert_case(session: Session, case_id: str, entry: dict[str, Any]) -> Case:
    case = session.get(Case, case_id)
    if case is None:
        case = Case(id=case_id)
        session.add(case)

    req_path = config.DATA_DIR / "requirements_all" / f"requirements_{case_id}.txt"
    err_path = config.DATA_DIR / "error_all" / f"error_case_{case_id}.txt"

    case.repo = entry.get("repo")
    case.path = entry.get("path")
    case.commit_sha = entry.get("commit_sha")
    case.priority = entry.get("priority")
    case.category = entry.get("category")
    case.source_url = entry.get("source_url")
    case.sha256 = entry.get("sha256")
    case.downloaded_at = entry.get("downloaded_at")
    case.requirements_path = config.rel(req_path) if req_path.is_file() else None
    case.requirements_text = _read_text(req_path)
    case.error_log_path = config.rel(err_path) if err_path.is_file() else None
    return case


def _upsert_run(session: Session, case_id: str, meta: dict[str, Any]) -> PipRun | None:
    if not meta:
        return None

    run = session.scalars(
        select(PipRun).where(PipRun.case_id == case_id).order_by(PipRun.id.desc())
    ).first()
    if run is None:
        run = PipRun(case_id=case_id)
        session.add(run)

    run.run_mode = str(meta.get("run_mode") or "dry-run")
    run.python = meta.get("python")
    run.pip_version = meta.get("pip")
    run.returncode = meta.get("returncode")
    run.timed_out = bool(meta.get("timed_out"))
    run.duration_sec = meta.get("duration_sec")
    command = meta.get("command")
    run.command = " ".join(command) if isinstance(command, list) else command
    run.log_path = meta.get("error_file") or config.rel(
        config.DATA_DIR / "error_all" / f"error_case_{case_id}.txt"
    )
    return run


def _upsert_label(
    session: Session, case_id: str, payload: dict[str, Any] | None
) -> Label | None:
    if not payload:
        return None

    label = session.get(Label, case_id)
    if label is None:
        label = Label(case_id=case_id, failure_type="unknown")
        session.add(label)

    label.failure_type = str(payload.get("failure_type") or "unknown")
    label.root_cause_hint = payload.get("root_cause_hint")
    label.acceptable = list(payload.get("acceptable") or [])
    label.ambiguous = bool(payload.get("ambiguous") or False)
    label.note = payload.get("note")
    label.reviewed = bool(payload.get("reviewed") or False)
    label.reviewed_by = payload.get("reviewed_by")
    label.reviewed_at = payload.get("reviewed_at")
    return label


def _upsert_verification(
    session: Session, case_id: str, payload: dict[str, Any] | None
) -> Verification | None:
    if not payload:
        return None

    verification = session.get(Verification, case_id)
    if verification is None:
        verification = Verification(case_id=case_id)
        session.add(verification)

    verification.recovered = bool(payload.get("recovered") or False)
    verification.install_returncode = payload.get("install_returncode")
    verification.pip_check_returncode = payload.get("pip_check_returncode")
    verification.install_duration_sec = payload.get("install_duration_sec")
    verification.fixed_requirements_path = payload.get("fixed_requirements")
    verification.patch_path = payload.get("patch_file")
    verification.install_log_path = payload.get("install_log")
    verification.venv_path = payload.get("venv")
    verification.generated_at = payload.get("generated_at")
    return verification


def ingest_case(
    session: Session,
    case_id: str,
    manifest_entry: dict[str, Any] | None = None,
    label_payload: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Upsert one case and everything attached to it."""

    if manifest_entry is None:
        manifest_entry = load_manifest().get(case_id, {})

    touched = {"runs": 0, "reports": 0, "labels": 0, "verifications": 0}

    _upsert_case(session, case_id, manifest_entry)

    meta = _read_json(config.DATA_DIR / "error_all" / f"error_case_{case_id}.meta.json") or {}
    if _upsert_run(session, case_id, meta) is not None:
        touched["runs"] = 1

    for approach, directory in REPORT_DIRS.items():
        payload = _read_json(config.DATA_DIR / directory / f"report_{case_id}.json")
        if upsert_report(session, case_id, approach, payload) is not None:
            touched["reports"] += 1

    if _upsert_label(session, case_id, label_payload) is not None:
        touched["labels"] = 1

    verification_payload = _read_json(
        config.DATA_DIR / "recovered" / f"case_{case_id}.verification.json"
    )
    if _upsert_verification(session, case_id, verification_payload) is not None:
        touched["verifications"] = 1

    return touched


def sync_all(session: Session) -> dict[str, int]:
    """Full, idempotent sync from disk. Used by the seed script and startup."""

    manifest = load_manifest()
    labels = load_labels()
    counts = {"cases": 0, "runs": 0, "reports": 0, "labels": 0, "verifications": 0}

    for case_id in discover_case_ids():
        touched = ingest_case(
            session,
            case_id,
            manifest_entry=manifest.get(case_id),
            label_payload=labels.get(case_id),
        )
        counts["cases"] += 1
        for key in ("runs", "reports", "labels", "verifications"):
            counts[key] += touched[key]

    session.commit()
    return counts
