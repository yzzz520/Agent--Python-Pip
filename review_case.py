"""Show one case for manual golden-label review.

Prints the local requirements, the raw pip log, the key error lines, and the
current label. Model conclusions are hidden unless --show-models is passed, so
the reviewer can form an independent judgement first.
"""

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REQ_DIR = ROOT / "requirements_all"
ERROR_DIR = ROOT / "error_all"
MANIFEST_PATH = ROOT / "manifest.json"
LABEL_PATH = ROOT / "golden_labels.json"

REPORT_DIRS = {
    "rule": ROOT / "reports_all",
    "llm": ROOT / "reports_llm_all",
    "agent": ROOT / "reports_agent_all",
}

KEY_LINE_RE = re.compile(
    r"ERROR:|Cannot install|The conflict is caused by|conflicting dependencies"
    r"|No matching distribution|Could not find a version|ResolutionImpossible"
    r"|Requires-Python|depends on|Ignored the following",
    re.IGNORECASE,
)


def normalize_case_id(value):
    text = str(value).strip()
    if not text.isdigit():
        raise ValueError(f"invalid case id: {value!r}")
    return f"{int(text):03d}"


def load_json(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Review one case for golden labeling.")
    parser.add_argument("--case", required=True)
    parser.add_argument("--raw", action="store_true", help="print the full error log")
    parser.add_argument("--show-models", action="store_true", help="show rule/llm/agent conclusions")
    parser.add_argument("--max-log-chars", type=int, default=6000)
    args = parser.parse_args()

    case_id = normalize_case_id(args.case)
    req_path = REQ_DIR / f"requirements_{case_id}.txt"
    error_path = ERROR_DIR / f"error_case_{case_id}.txt"
    if not req_path.exists():
        print(f"[错误] 找不到 {req_path}")
        return 1
    if not error_path.exists():
        print(f"[错误] 找不到 {error_path}")
        return 1

    manifest = load_json(MANIFEST_PATH)
    meta = next(
        (entry for entry in manifest.get("entries", []) if entry.get("case_id") == case_id),
        {},
    )
    run_meta = load_json(ERROR_DIR / f"error_case_{case_id}.meta.json")
    labels = load_json(LABEL_PATH).get("labels", {})

    print("=" * 72)
    print(f"案例 {case_id} 人工复核")
    print("=" * 72)
    print(f"repo   : {meta.get('repo') or '(本地手写案例，不在 manifest 中)'}")
    print(f"path   : {meta.get('path') or '-'}")
    print(f"commit : {meta.get('commit_sha') or '-'}")
    print(f"优先级 : {meta.get('priority') or '-'}")
    print(f"python : {run_meta.get('python') or '-'}")
    print(f"pip    : {run_meta.get('pip') or '-'}")
    print(f"run_mode / returncode: {run_meta.get('run_mode') or '-'} / {run_meta.get('returncode')}")

    print("\n----- requirements -----")
    print(req_path.read_text(encoding="utf-8", errors="replace").strip())

    log_text = error_path.read_text(encoding="utf-8", errors="replace")
    print("\n----- 运行元数据 -----")
    for line in log_text.splitlines()[:11]:
        print(line)

    print("\n----- 关键错误行 -----")
    key_lines = [line.strip() for line in log_text.splitlines() if KEY_LINE_RE.search(line)]
    if key_lines:
        for line in key_lines[:20]:
            print(f"  {line[:300]}")
    else:
        print("  (没有匹配到关键字，请用 --raw 查看完整日志)")

    print("\n----- pip 日志结尾 -----")
    tail = log_text if args.raw else log_text[-args.max_log_chars:]
    print(tail.strip()[-args.max_log_chars:])

    print("\n----- 当前标签 -----")
    current = labels.get(case_id)
    if current:
        print(json.dumps(current, ensure_ascii=False, indent=2))
        print("提醒：请先自己根据上面的日志判断，再决定是否修改这个标签。")
    else:
        print("(尚无标签，需要新增)")

    if args.show_models:
        print("\n----- 三条轨道的结论 -----")
        for name, directory in REPORT_DIRS.items():
            payload = load_json(directory / f"report_{case_id}.json")
            if not payload:
                print(f"{name:6}: (无报告)")
                continue
            print(
                f"{name:6}: {payload.get('failure_type')} "
                f"(confidence={payload.get('confidence')}) "
                f"| {payload.get('root_cause')}"
            )

    print("\n[下一步] 修改 golden_labels.json 里 case_id=" + case_id + " 的 failure_type 和 root_cause_hint。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
