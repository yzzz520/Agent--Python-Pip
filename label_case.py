"""Add or update one golden label safely.

Examples:
  python label_case.py --status
  python label_case.py --case 009 --failure-type no_failure --root-cause "pip 解析成功" --reviewed
  python label_case.py --case 005 --failure-type no_matching_distribution --acceptable no_matching_distribution,python_version_mismatch --reviewed
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LABEL_PATH = ROOT / "golden_labels.json"

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


def normalize_case_id(value):
    text = str(value).strip()
    if not text.isdigit():
        raise ValueError(f"invalid case id: {value!r}")
    return f"{int(text):03d}"


def load_labels():
    if not LABEL_PATH.exists():
        raise FileNotFoundError(f"missing {LABEL_PATH.name}")
    return json.loads(LABEL_PATH.read_text(encoding="utf-8"))


def save_labels(payload):
    LABEL_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Add or update one golden label.")
    parser.add_argument("--case", help="case id, e.g. 009")
    parser.add_argument("--failure-type", choices=sorted(ALLOWED_TYPES))
    parser.add_argument("--root-cause")
    parser.add_argument("--acceptable", help="comma-separated acceptable failure types")
    parser.add_argument("--ambiguous", action="store_true")
    parser.add_argument("--note")
    parser.add_argument("--reviewed", action="store_true")
    parser.add_argument("--unreview", action="store_true", help="remove the reviewed flag")
    parser.add_argument("--reviewed-by", default="me")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--status", action="store_true", help="print review progress and exit")
    args = parser.parse_args()

    payload = load_labels()
    labels = payload.setdefault("labels", {})

    if args.status:
        print(f"标签总数: {len(labels)}")
        for case_id in sorted(labels):
            entry = labels[case_id]
            mark = "已复核" if entry.get("reviewed") else "未复核"
            print(f"  {case_id}: {entry.get('failure_type')} [{mark}]")
        reviewed = sum(1 for entry in labels.values() if entry.get("reviewed"))
        print(f"进度: {reviewed}/{len(labels)}")
        return 0

    if not args.case:
        print("[错误] 需要 --case，或者使用 --status 查看进度。")
        return 1

    if args.unreview:
        case_id = normalize_case_id(args.case)
        if case_id not in labels:
            print(f"[错误] 标签里没有案例 {case_id}。")
            return 1
        entry = labels[case_id]
        entry.pop("reviewed", None)
        entry.pop("reviewed_by", None)
        entry.pop("reviewed_at", None)
        reviewed = sum(1 for item in labels.values() if item.get("reviewed"))
        payload["reviewed_count"] = reviewed
        payload["total_labels"] = len(labels)
        print(f"[撤销复核] case={case_id}")
        print(f"[进度] 已复核 {reviewed}/{len(labels)}")
        if args.dry_run:
            print("[完成] dry-run，未写入文件。")
            return 0
        save_labels(payload)
        print(f"[完成] 已更新 {LABEL_PATH.name}")
        return 0

    if not args.failure_type:
        print("[错误] 需要 --failure-type。")
        return 1
    if not args.root_cause:
        print("[错误] 需要 --root-cause。")
        return 1

    case_id = normalize_case_id(args.case)
    entry = dict(labels.get(case_id, {}))
    entry["failure_type"] = args.failure_type
    entry["root_cause_hint"] = args.root_cause

    if args.acceptable:
        acceptable = [item.strip() for item in args.acceptable.split(",") if item.strip()]
        invalid = [item for item in acceptable if item not in ALLOWED_TYPES]
        if invalid:
            print(f"[错误] acceptable 里有非法类型: {', '.join(invalid)}")
            return 1
        entry["acceptable"] = acceptable
    if args.ambiguous:
        entry["ambiguous"] = True
    if args.note:
        entry["note"] = args.note
    if args.reviewed:
        entry["reviewed"] = True
        entry["reviewed_by"] = args.reviewed_by
        entry["reviewed_at"] = date.today().isoformat()

    labels[case_id] = entry
    reviewed = sum(1 for item in labels.values() if item.get("reviewed"))
    payload["reviewed_count"] = reviewed
    payload["total_labels"] = len(labels)

    print(f"[写入] case={case_id}")
    print(json.dumps(entry, ensure_ascii=False, indent=2))
    print(f"[进度] 已复核 {reviewed}/{len(labels)}")

    if args.dry_run:
        print("[完成] dry-run，未写入文件。")
        return 0

    save_labels(payload)
    print(f"[完成] 已更新 {LABEL_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
