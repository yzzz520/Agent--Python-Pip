"""Business logic: statistics aggregation and job execution.

The heavy lifting is delegated to the existing offline modules
(``failure_analyzer``, ``batch_runner``) which are imported lazily so that the
service can start even when those scripts are absent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .models import AttributionReport, Case, Label

APPROACH_LABELS = {
    "rule": "规则基线",
    "llm": "单步 LLM",
    "agent": "工具调用 Agent",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _accuracy(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def build_stats(session: Session) -> dict[str, Any]:
    """Compare every approach against the golden labels."""

    cases = session.scalars(select(Case)).all()
    labels = session.scalars(select(Label)).all()
    label_map = {label.case_id: label for label in labels}

    reports = session.scalars(select(AttributionReport)).all()
    report_map = {(report.case_id, report.approach): report for report in reports}

    by_approach: list[dict[str, Any]] = []
    for approach in ("rule", "llm", "agent"):
        evaluated = strict = lenient = 0
        confidence_sum = 0.0
        tokens = tool_calls = fixes = 0

        for case_id, label in label_map.items():
            report = report_map.get((case_id, approach))
            if report is None:
                continue

            evaluated += 1
            confidence_sum += report.confidence or 0.0
            tokens += report.total_tokens or 0
            tool_calls += report.tool_calls or 0
            if report.fix_verified:
                fixes += 1

            if report.failure_type == label.failure_type:
                strict += 1
                lenient += 1
            elif report.failure_type in (label.acceptable or []):
                lenient += 1

        by_approach.append(
            {
                "approach": approach,
                "label": APPROACH_LABELS[approach],
                "evaluated": evaluated,
                "strict_correct": strict,
                "lenient_correct": lenient,
                "strict_accuracy": _accuracy(strict, evaluated),
                "lenient_accuracy": _accuracy(lenient, evaluated),
                "average_confidence": round(confidence_sum / evaluated, 4) if evaluated else None,
                "total_tokens": tokens,
                "total_tool_calls": tool_calls,
                "fix_verified": fixes,
            }
        )

    dataset_counts: dict[str, int] = {}
    for report in reports:
        if report.approach != "rule":
            continue
        dataset_counts[report.failure_type] = dataset_counts.get(report.failure_type, 0) + 1

    label_counts: dict[str, int] = {}
    for label in labels:
        label_counts[label.failure_type] = label_counts.get(label.failure_type, 0) + 1

    return {
        "case_count": len(cases),
        "labeled_count": len(labels),
        "reviewed_count": sum(1 for label in labels if label.reviewed),
        "by_approach": by_approach,
        "dataset_failure_type_counts": dict(sorted(dataset_counts.items())),
        "label_failure_type_counts": dict(sorted(label_counts.items())),
    }


def execute_job(session: Session, case_id: str, kind: str, timeout: int = 120) -> dict[str, Any]:
    """Dispatch a re-run request. Called from the worker thread."""

    if kind == "rule":
        return rerun_rule(session, case_id)
    if kind == "pip":
        return rerun_pip(session, case_id, timeout=timeout)
    raise ValueError(f"unknown job kind: {kind!r}")


def rerun_rule(session: Session, case_id: str) -> dict[str, Any]:
    """Re-classify the stored error log with the deterministic rule baseline."""

    import failure_analyzer  # repository-root module

    from .ingest import upsert_report

    log_path = config.DATA_DIR / "error_all" / f"error_case_{case_id}.txt"
    if not log_path.is_file():
        raise FileNotFoundError(f"error log not found: {log_path.name}")

    text = log_path.read_text(encoding="utf-8", errors="replace")
    analysis = failure_analyzer.classify(text)
    evidence = failure_analyzer.collect_evidence(text)[:5]

    upsert_report(
        session,
        case_id,
        "rule",
        {
            "failure_type": analysis["failure_type"],
            "root_cause": analysis["root_cause"],
            "evidence": evidence,
            "suggestions": analysis["suggestions"],
            "confidence": analysis["confidence"],
            "model": "rule-baseline",
            "generated_at": _now().isoformat(),
        },
    )
    session.commit()
    return {
        "approach": "rule",
        "failure_type": analysis["failure_type"],
        "returncode": analysis["returncode"],
        "evidence_count": len(evidence),
    }


def rerun_pip(session: Session, case_id: str, timeout: int = 120) -> dict[str, Any]:
    """Re-execute pip (dry-run) through the batch runner and re-ingest."""

    import batch_runner  # repository-root module

    from .ingest import ingest_case

    req_path = config.DATA_DIR / "requirements_all" / f"requirements_{case_id}.txt"
    if not req_path.is_file():
        raise FileNotFoundError(f"requirements file not found: {req_path.name}")

    _case_id, returncode, timed_out, duration = batch_runner.run_one(
        req_path, case_id, "dry-run", timeout
    )
    ingest_case(session, case_id)
    session.commit()

    return {
        "approach": "pip",
        "returncode": returncode,
        "timed_out": timed_out,
        "duration_sec": round(duration, 2),
        "run_mode": "dry-run",
    }
