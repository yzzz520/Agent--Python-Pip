"""Rule-based failure attribution baseline.

Reads every error_all/error_case_*.txt and writes both a human-readable report
and a structured JSON report. This is the deterministic baseline that a later
LLM analyzer can be compared against.
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ERROR_DIR = ROOT / "error_all"
REPORT_DIR = ROOT / "reports_all"
MANIFEST_PATH = ROOT / "manifest.json"
SUMMARY_PATH = REPORT_DIR / "summary.json"

MAX_EVIDENCE = 12

RETURNCODE_RE = re.compile(r"^returncode\s*:\s*(-?\d+)", re.MULTILINE)
TIMEOUT_RE = re.compile(r"timeout after \d+s", re.IGNORECASE)

PATTERNS = [
    (
        "invalid_local_reference",
        re.compile(
            r"does not appear to be a Python project"
            r"|Neither 'setup\.py' nor 'pyproject\.toml' found"
            r"|is not installable",
            re.IGNORECASE,
        ),
    ),
    (
        "missing_referenced_file",
        re.compile(r"Could not open (?:requirements|constraints?) file:?\s*(.*)", re.IGNORECASE),
    ),
    (
        "python_version_mismatch",
        re.compile(
            r"Ignored the following versions that require a different python version"
            r"|Requires-Python",
            re.IGNORECASE,
        ),
    ),
    (
        "dependency_conflict",
        re.compile(
            r"ResolutionImpossible"
            r"|The conflict is caused by"
            r"|because these package versions have conflicting dependencies"
            r"|depends on .+",
            re.IGNORECASE,
        ),
    ),
    (
        "no_matching_distribution",
        re.compile(
            r"No matching distribution found for (.+)"
            r"|Could not find a version that satisfies the requirement (.+)",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "build_failure",
        re.compile(
            r"Failed building wheel"
            r"|error: subprocess-exited-with-error"
            r"|Building wheel for"
            r"|Microsoft Visual C\+\+"
            r"|fatal error C\d+",
            re.IGNORECASE,
        ),
    ),
    (
        "network_error",
        re.compile(
            r"Read timed out"
            r"|Temporary failure in name resolution"
            r"|SSLError"
            r"|ProxyError"
            r"|Max retries exceeded"
            r"|Cannot connect"
            r"|Could not fetch URL",
            re.IGNORECASE,
        ),
    ),
]

EVIDENCE_PATTERNS = [
    re.compile(r"The user requested .+", re.IGNORECASE),
    re.compile(r".+ depends on .+"),
    re.compile(r".+ requires .+"),
    re.compile(r"Could not open (?:requirements|constraints?) file:?.+", re.IGNORECASE),
    re.compile(r"No matching distribution found for .+", re.IGNORECASE),
    re.compile(r"Could not find a version that satisfies the requirement .+", re.IGNORECASE),
    re.compile(r"Requires-Python .+", re.IGNORECASE),
    re.compile(r"ERROR: .+"),
]


def load_manifest():
    if not MANIFEST_PATH.exists():
        return {}
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {entry["case_id"]: entry for entry in data.get("entries", [])}


def collect_evidence(text):
    evidence = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or len(line) > 400:
            continue
        for pattern in EVIDENCE_PATTERNS:
            if pattern.search(line):
                if line not in evidence:
                    evidence.append(line)
                break
        if len(evidence) >= MAX_EVIDENCE:
            break
    return evidence


def classify(text):
    returncode_match = RETURNCODE_RE.search(text)
    returncode = int(returncode_match.group(1)) if returncode_match else None

    if TIMEOUT_RE.search(text) or returncode == 124:
        return {
            "failure_type": "timeout",
            "root_cause": "pip 在超时时间内未完成解析或下载。",
            "suggestions": ["提高超时时间后重试。", "检查是否存在体积很大的 wheel 或缓慢的镜像源。"],
            "confidence": 0.9,
            "returncode": returncode,
        }

    if returncode == 0:
        return {
            "failure_type": "no_failure",
            "root_cause": "pip 返回码为 0，本次解析未失败。",
            "suggestions": [],
            "confidence": 0.95,
            "returncode": returncode,
        }

    for failure_type, pattern in PATTERNS:
        match = pattern.search(text)
        if not match:
            continue

        if failure_type == "missing_referenced_file":
            target = (match.group(1) or "").strip()
            root_cause = f"requirements 文件引用了未随案例一起下载的伴随文件：{target or '未知'}"
            suggestions = [
                "在采集阶段同时下载被 -r / -c 引用的伴随文件，并保持相对路径。",
                "或把这些约束内联进单个 requirements 文件。",
            ]
            confidence = 0.95
        elif failure_type == "invalid_local_reference":
            root_cause = "requirements 文件包含 -e / 本地路径引用，但对应的项目文件不在执行目录中。"
            suggestions = [
                "为这类案例额外下载项目本体，或把该行替换为对应的 GitHub 依赖地址。",
                "采集阶段过滤掉只适用于仓库内开发环境的 -e . 行。",
            ]
            confidence = 0.9
        elif failure_type == "python_version_mismatch":
            root_cause = "部分依赖的 Requires-Python 与当前解释器版本不匹配。"
            suggestions = [
                "切换到满足 Requires-Python 的解释器版本。",
                "或选择支持当前 Python 版本的另一组依赖版本。",
            ]
            confidence = 0.9
        elif failure_type == "dependency_conflict":
            root_cause = "pip 解析器发现依赖版本约束互相冲突。"
            suggestions = [
                "放宽或删除冲突包上的版本约束，重新解析。",
                "若冲突不可调和，移除其中一个包或使用兼容版本组合。",
            ]
            confidence = 0.88
        elif failure_type == "no_matching_distribution":
            target = (match.group(1) or match.group(2) or "").strip()
            root_cause = f"目标分发不存在或没有适配当前 Python / 平台的 wheel：{target or '未知包'}"
            suggestions = [
                "确认该包在 PyPI 上是否存在，以及是否支持当前 Python 与平台。",
                "改用有 wheel 的版本，或更换解释器 / 平台。",
            ]
            confidence = 0.85
        elif failure_type == "build_failure":
            root_cause = "依赖需要本地编译，但构建过程失败。"
            suggestions = [
                "安装对应的编译工具链（如 MSVC Build Tools）。",
                "优先选择提供预编译 wheel 的版本或平台。",
            ]
            confidence = 0.85
        else:  # network_error
            root_cause = "访问包索引或下载依赖时出现网络错误。"
            suggestions = ["检查网络、代理与索引源配置后重试。"]
            confidence = 0.8

        return {
            "failure_type": failure_type,
            "root_cause": root_cause,
            "suggestions": suggestions,
            "confidence": confidence,
            "returncode": returncode,
        }

    return {
        "failure_type": "unknown",
        "root_cause": "规则基线未匹配到已知失败模式，需要人工查看原始日志。",
        "suggestions": ["查看 error_all 中对应日志的 STDERR 段。"],
        "confidence": 0.3,
        "returncode": returncode,
    }


def render_text_report(case_id, error_name, meta, analysis, evidence):
    lines = [
        "=" * 70,
        f"【失败归因分析报告】 - 案例: {case_id} - 源文件: {error_name}",
        "=" * 70,
    ]
    if meta:
        lines.extend(
            [
                "",
                "0. 来源信息：",
                f"   - repo        : {meta.get('repo')}",
                f"   - path        : {meta.get('path')}",
                f"   - commit      : {meta.get('commit_sha')}",
                f"   - priority    : {meta.get('priority')}",
            ]
        )

    lines.extend(
        [
            "",
            "1. 失败类型：",
            f"   - {analysis['failure_type']} (confidence={analysis['confidence']})",
            f"   - pip returncode: {analysis['returncode']}",
            "",
            "2. 根因分析：",
            f"   {analysis['root_cause']}",
            "",
            "3. 证据行：",
        ]
    )
    if evidence:
        lines.extend(f"   - {line}" for line in evidence)
    else:
        lines.append("   - 未提取到结构化证据行，请查看原始 STDERR。")

    lines.extend(["", "4. 修复建议："])
    if analysis["suggestions"]:
        lines.extend(f"   - {item}" for item in analysis["suggestions"])
    else:
        lines.append("   - 无需修复。")

    lines.append("=" * 70)
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Analyze error logs and write reports.")
    parser.add_argument("--cases", help="comma-separated case ids, e.g. 006,007,008")
    args = parser.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()

    error_files = sorted(p for p in ERROR_DIR.iterdir() if p.is_file() and p.name.endswith(".txt"))
    if args.cases:
        wanted = {
            value.strip().lstrip("0") or "0"
            for value in args.cases.split(",")
            if value.strip()
        }
        error_files = [
            p
            for p in error_files
            if (p.stem.replace("error_case_", "").lstrip("0") or "0") in wanted
        ]
    if not error_files:
        print(f"[系统] 警告：在 {ERROR_DIR} 中没有找到报错文件。")
        return 0

    print(f"[系统] 共发现 {len(error_files)} 个报错文件，开始批量归因分析...\n")
    summary = []

    for error_path in error_files:
        text = error_path.read_text(encoding="utf-8", errors="replace")
        case_id = error_path.stem.replace("error_case_", "")
        analysis = classify(text)
        evidence = collect_evidence(text)
        meta = manifest.get(case_id)

        report_id = error_path.name.replace("error_case_", "report_")
        report_txt = report_id
        report_json = Path(report_id).with_suffix(".json").name

        (REPORT_DIR / report_txt).write_text(
            render_text_report(case_id, error_path.name, meta, analysis, evidence),
            encoding="utf-8",
        )

        payload = {
            "case_id": case_id,
            "source_error_file": error_path.name,
            "repo": meta.get("repo") if meta else None,
            "path": meta.get("path") if meta else None,
            "commit_sha": meta.get("commit_sha") if meta else None,
            "priority": meta.get("priority") if meta else None,
            "failure_type": analysis["failure_type"],
            "root_cause": analysis["root_cause"],
            "evidence": evidence,
            "suggestions": analysis["suggestions"],
            "confidence": analysis["confidence"],
            "returncode": analysis["returncode"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        (REPORT_DIR / report_json).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        summary.append(
            {
                "case_id": case_id,
                "failure_type": analysis["failure_type"],
                "confidence": analysis["confidence"],
                "returncode": analysis["returncode"],
                "repo": meta.get("repo") if meta else None,
                "priority": meta.get("priority") if meta else None,
                "report": report_json,
            }
        )
        print(f"[完成] {error_path.name} -> {report_txt} / {report_json} :: {analysis['failure_type']}")

    report_files = sorted(
        path for path in REPORT_DIR.glob("report_*.json") if path.name != SUMMARY_PATH.name
    )
    all_cases = []
    for report_file in report_files:
        payload = json.loads(report_file.read_text(encoding="utf-8"))
        all_cases.append(
            {
                "case_id": payload.get("case_id"),
                "failure_type": payload.get("failure_type"),
                "confidence": payload.get("confidence"),
                "returncode": payload.get("returncode"),
                "repo": payload.get("repo"),
                "priority": payload.get("priority"),
                "report": report_file.name,
            }
        )

    failure_counts = {}
    confidence_by_type = {}
    for item in all_cases:
        failure_type = item["failure_type"]
        failure_counts[failure_type] = failure_counts.get(failure_type, 0) + 1
        confidence_by_type.setdefault(failure_type, []).append(item["confidence"])

    failure_counts = dict(sorted(failure_counts.items(), key=lambda pair: (-pair[1], pair[0])))
    average_confidence_by_type = {
        failure_type: round(sum(values) / len(values), 4)
        for failure_type, values in confidence_by_type.items()
    }
    average_confidence = round(
        sum(item["confidence"] for item in all_cases) / len(all_cases),
        4,
    ) if all_cases else 0.0

    summary_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "all_reports",
        "cases_filter": [value.strip() for value in args.cases.split(",") if value.strip()] if args.cases else [],
        "analyzed_this_run": [item["case_id"] for item in summary],
        "case_count": len(all_cases),
        "failure_type_counts": failure_counts,
        "average_confidence": average_confidence,
        "average_confidence_by_type": average_confidence_by_type,
        "cases": all_cases,
    }
    SUMMARY_PATH.write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n[汇总]")
    for item in summary:
        print(
            f"  - case {item['case_id']}: {item['failure_type']} "
            f"(confidence={item['confidence']}) -> {item['report']}"
        )

    print(f"\n[统计] 失败类型分布: {failure_counts}")
    print(f"[统计] 平均置信度: {average_confidence}")
    print(f"[统计] 汇总已写入: {SUMMARY_PATH.relative_to(ROOT)}")

    print("\n[系统] 批量归因分析全部完成！")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
