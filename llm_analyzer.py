"""LLM-based failure attribution.

Reads error_all/error_case_*.txt plus the matching requirements file, asks an
OpenAI-compatible chat model for a structured JSON attribution, validates the
response, and writes reports to reports_llm_all/.

This is the LLM baseline that will later be compared against:
  - failure_analyzer.py (rule baseline)
  - agent_analyzer.py  (tool-using agent, future work)
"""

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from llm_client import LLMClient, LLMConfigError


ROOT = Path(__file__).resolve().parent
ERROR_DIR = ROOT / "error_all"
REQ_DIR = ROOT / "requirements_all"
RULE_REPORT_DIR = ROOT / "reports_all"
DEFAULT_REPORT_DIR = ROOT / "reports_llm_all"
DEFAULT_CACHE_DIR = ROOT / "llm_cache"
MANIFEST_PATH = ROOT / "manifest.json"
DEFAULT_PROMPT_PATH = ROOT / "prompts" / "attribution_v2.md"

ALLOWED_TYPES = {
    "dependency_conflict",
    "python_version_mismatch",
    "no_matching_distribution",
    "build_failure",
    "network_error",
    "missing_referenced_file",
    "invalid_local_reference",
    "no_failure",
    "unknown",
}

EVIDENCE_MAX_CHARS = 240


def load_manifest():
    if not MANIFEST_PATH.exists():
        return {}
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {entry["case_id"]: entry for entry in payload.get("entries", [])}


def load_case_ids(value):
    if not value:
        return None
    return {item.strip().lstrip("0") or "0" for item in value.split(",") if item.strip()}


def truncate_text(text, max_chars):
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    head = max_chars // 3
    tail = max_chars - head
    return (
        text[:head] + "\n[... 中间内容已截断，以下为日志尾部 ...]\n" + text[-tail:],
        True,
    )


def build_prompt(template, case_id, meta, requirements, error_log):
    replacements = {
        "<<CASE_ID>>": case_id,
        "<<REPO>>": str(meta.get("repo") or "local"),
        "<<PATH>>": str(meta.get("path") or "requirements"),
        "<<COMMIT>>": str(meta.get("commit_sha") or ""),
        "<<PYTHON>>": str(meta.get("python") or ""),
        "<<PIP>>": str(meta.get("pip") or ""),
        "<<RUN_MODE>>": str(meta.get("run_mode") or ""),
        "<<RETURNCODE>>": str(meta.get("returncode") if meta.get("returncode") is not None else ""),
        "<<REQUIREMENTS>>": requirements,
        "<<ERROR_LOG>>": error_log,
    }
    prompt = template
    for token, value in replacements.items():
        prompt = prompt.replace(token, value)
    return prompt


def parse_json_response(text):
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("response does not contain a JSON object")
    return json.loads(cleaned[start:end + 1])


def normalize_payload(payload):
    failure_type = str(payload.get("failure_type", "unknown")).strip()
    if failure_type not in ALLOWED_TYPES:
        failure_type = "unknown"

    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = min(max(confidence, 0.0), 1.0)

    evidence = [str(item).strip() for item in payload.get("evidence", []) if str(item).strip()]
    evidence = [
        (item[:EVIDENCE_MAX_CHARS] + "...") if len(item) > EVIDENCE_MAX_CHARS else item
        for item in evidence
    ]
    suggestions = [str(item).strip() for item in payload.get("suggestions", []) if str(item).strip()]
    root_cause = str(payload.get("root_cause", "")).strip() or "模型未给出根因"

    return {
        "failure_type": failure_type,
        "root_cause": root_cause,
        "evidence": evidence[:8],
        "suggestions": suggestions[:4],
        "confidence": confidence,
    }


def split_evidence(evidence, haystack):
    verified, unverified = [], []
    for line in evidence:
        if line and line in haystack:
            verified.append(line)
        else:
            unverified.append(line)
    return verified, unverified


def mock_payload(case_id):
    rule_path = RULE_REPORT_DIR / f"report_{case_id}.json"
    if rule_path.exists():
        payload = json.loads(rule_path.read_text(encoding="utf-8"))
        return {
            "content": json.dumps(
                {
                    "failure_type": payload.get("failure_type", "unknown"),
                    "root_cause": payload.get("root_cause", "mock"),
                    "evidence": payload.get("evidence", []),
                    "suggestions": payload.get("suggestions", []),
                    "confidence": payload.get("confidence", 0.0),
                },
                ensure_ascii=False,
            ),
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "latency_ms": 0,
            "model": "mock",
        }
    return {
        "content": json.dumps(
            {
                "failure_type": "unknown",
                "root_cause": "mock 模式：没有调用真实模型",
                "evidence": [],
                "suggestions": [],
                "confidence": 0.0,
            },
            ensure_ascii=False,
        ),
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "latency_ms": 0,
        "model": "mock",
    }


def cache_key(model, temperature, max_tokens, prompt):
    raw = f"{model}|{temperature}|{max_tokens}|{prompt}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def render_text_report(case_id, meta, analysis, verification, model):
    lines = [
        "=" * 70,
        f"【LLM 归因报告】 - 案例: {case_id}",
        "=" * 70,
        "",
        "0. 来源信息：",
        f"   - repo   : {meta.get('repo')}",
        f"   - path   : {meta.get('path')}",
        f"   - commit : {meta.get('commit_sha')}",
        f"   - model  : {model}",
        "",
        "1. 失败类型：",
        f"   - {analysis['failure_type']} (confidence={analysis['confidence']})",
        "",
        "2. 根因分析：",
        f"   {analysis['root_cause']}",
        "",
        "3. 证据行：",
    ]
    if analysis["evidence"]:
        lines.extend(f"   - {line}" for line in analysis["evidence"])
    else:
        lines.append("   - 无")
    lines.extend(
        [
            f"   - 其中可在原始日志中逐字验证: {len(verification['verified'])}",
            f"   - 未验证: {len(verification['unverified'])}",
            "",
            "4. 修复建议：",
        ]
    )
    if analysis["suggestions"]:
        lines.extend(f"   - {item}" for item in analysis["suggestions"])
    else:
        lines.append("   - 无")
    lines.append("=" * 70)
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="LLM-based failure attribution.")
    parser.add_argument("--cases", help="comma-separated case ids, e.g. 000,005,007")
    parser.add_argument("--limit", type=int, help="maximum number of cases")
    parser.add_argument("--model", help="override LLM_MODEL")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=2500)
    parser.add_argument("--max-log-chars", type=int, default=16000)
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT_PATH)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--mock", action="store_true", help="do not call the API")
    args = parser.parse_args()

    if not args.prompt.exists():
        print(f"[错误] Prompt 模板不存在: {args.prompt}")
        return 1
    prompt_template = args.prompt.read_text(encoding="utf-8")
    prompt_version = args.prompt.stem

    manifest = load_manifest()
    wanted = load_case_ids(args.cases)
    error_files = sorted(p for p in ERROR_DIR.iterdir() if p.is_file() and p.name.endswith(".txt"))
    if wanted:
        error_files = [
            p
            for p in error_files
            if (p.stem.replace("error_case_", "").lstrip("0") or "0") in wanted
        ]
    if args.limit is not None:
        error_files = error_files[:args.limit]
    if not error_files:
        print("[系统] 没有匹配的案例。")
        return 0

    client = None
    model_name = args.model or "from-env"
    if not args.mock:
        try:
            client = LLMClient(model=args.model)
            model_name = client.model
        except LLMConfigError as exc:
            print(f"[错误] {exc}")
            return 1

    args.report_dir.mkdir(parents=True, exist_ok=True)
    if not args.no_cache:
        args.cache_dir.mkdir(parents=True, exist_ok=True)

    print(f"[系统] 共 {len(error_files)} 个案例，模型: {model_name}，mock={args.mock}")
    summary = []
    failures = []

    for error_path in error_files:
        case_id = error_path.stem.replace("error_case_", "")
        meta = dict(manifest.get(case_id, {}))
        run_meta_path = error_path.with_suffix(".meta.json")
        if run_meta_path.exists():
            run_meta = json.loads(run_meta_path.read_text(encoding="utf-8"))
            meta.update(
                {
                    "python": run_meta.get("python"),
                    "pip": run_meta.get("pip"),
                    "run_mode": run_meta.get("run_mode"),
                    "returncode": run_meta.get("returncode"),
                }
            )
        else:
            match = re.search(r"^returncode\s*:\s*(-?\d+)", error_path.read_text(encoding="utf-8", errors="replace"), re.MULTILINE)
            meta["returncode"] = int(match.group(1)) if match else None

        req_path = REQ_DIR / f"requirements_{case_id}.txt"
        requirements = req_path.read_text(encoding="utf-8", errors="replace") if req_path.exists() else "(missing requirements file)"
        error_log, truncated = truncate_text(
            error_path.read_text(encoding="utf-8", errors="replace"),
            args.max_log_chars,
        )

        prompt = build_prompt(prompt_template, case_id, meta, requirements, error_log)
        payload = None
        response = None
        cached = False
        last_error = None
        error_dir = args.report_dir / "errors"
        error_dir.mkdir(parents=True, exist_ok=True)

        for attempt in range(2):
            max_tokens = args.max_tokens * (attempt + 1)
            key = cache_key(model_name, args.temperature, max_tokens, prompt)
            cache_path = args.cache_dir / f"{key}.json"
            try:
                if args.mock:
                    response = mock_payload(case_id)
                    cached = False
                elif not args.no_cache and cache_path.exists():
                    response = json.loads(cache_path.read_text(encoding="utf-8"))
                    cached = True
                else:
                    response = client.chat(
                        [
                            {
                                "role": "system",
                                "content": "你是 Python 依赖安装失败归因专家。只输出 JSON，evidence 每条不超过 200 字符。",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        temperature=args.temperature,
                        max_tokens=max_tokens,
                    )
                    cached = False
                    if not args.no_cache:
                        cache_path.write_text(
                            json.dumps(response, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )

                payload = normalize_payload(parse_json_response(response["content"]))
                last_error = None
                break
            except Exception as exc:  # noqa: BLE001 - retry once, then record
                last_error = exc
                raw_content = (response or {}).get("content") or ""
                if raw_content:
                    (error_dir / f"case_{case_id}_attempt{attempt + 1}_raw.txt").write_text(
                        raw_content,
                        encoding="utf-8",
                    )
                if args.mock or attempt == 1:
                    break
                print(f"[重试] case={case_id} 解析失败，加倍输出预算重试: {exc}")

        if payload is None:
            failures.append({"case_id": case_id, "error": str(last_error)})
            print(f"[失败] case={case_id} -> {last_error}")
            continue

        verification = {
            "verified": split_evidence(payload["evidence"], error_log)[0],
            "unverified": split_evidence(payload["evidence"], error_log)[1],
        }
        usage = response.get("usage", {})
        record = {
            "case_id": case_id,
            "source_error_file": error_path.name,
            "repo": meta.get("repo"),
            "path": meta.get("path"),
            "commit_sha": meta.get("commit_sha"),
            "priority": meta.get("priority"),
            "model": response.get("model", model_name),
            "prompt_version": prompt_version,
            "failure_type": payload["failure_type"],
            "root_cause": payload["root_cause"],
            "evidence": payload["evidence"],
            "suggestions": payload["suggestions"],
            "confidence": payload["confidence"],
            "evidence_verified": verification["verified"],
            "evidence_unverified": verification["unverified"],
            "returncode": meta.get("returncode"),
            "log_truncated": truncated,
            "latency_ms": response.get("latency_ms", 0),
            "finish_reason": response.get("finish_reason"),
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "cached": cached,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "raw_response": response.get("content", ""),
        }

        report_json = args.report_dir / f"report_{case_id}.json"
        report_txt = args.report_dir / f"report_{case_id}.txt"
        report_json.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        report_txt.write_text(
            render_text_report(case_id, meta, payload, verification, record["model"]),
            encoding="utf-8",
        )

        summary.append(record)
        cache_tag = " cached" if cached else ""
        print(
            f"[完成] case={case_id} -> {payload['failure_type']} "
            f"(confidence={payload['confidence']}){cache_tag}"
        )
        if not args.mock:
            time.sleep(1)

    counts = {}
    for record in summary:
        counts[record["failure_type"]] = counts.get(record["failure_type"], 0) + 1
    counts = dict(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0])))

    summary_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": model_name,
        "prompt_version": prompt_version,
        "mock": args.mock,
        "case_count": len(summary),
        "failure_type_counts": counts,
        "average_confidence": round(
            sum(record["confidence"] for record in summary) / len(summary), 4
        ) if summary else 0.0,
        "total_tokens": sum(record["total_tokens"] for record in summary),
        "average_latency_ms": round(
            sum(record["latency_ms"] for record in summary) / len(summary)
        ) if summary else 0,
        "cases": [
            {
                "case_id": record["case_id"],
                "failure_type": record["failure_type"],
                "confidence": record["confidence"],
                "total_tokens": record["total_tokens"],
                "latency_ms": record["latency_ms"],
                "cached": record["cached"],
            }
            for record in summary
        ],
        "failures": failures,
    }
    (args.report_dir / "summary.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n[汇总] {counts}")
    print(f"[汇总] 平均置信度: {summary_payload['average_confidence']}")
    print(f"[汇总] 总 tokens: {summary_payload['total_tokens']}")
    print(f"[汇总] 写出目录: {args.report_dir}")
    if failures:
        print(f"[汇总] 失败 {len(failures)} 条")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
