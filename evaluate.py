"""Compare rule / LLM / Agent attribution against golden labels."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RULE_DIR = ROOT / "reports_all"
LLM_DIR = ROOT / "reports_llm_all"
AGENT_DIR = ROOT / "reports_agent_all"
DEFAULT_LABELS = ROOT / "golden_labels.json"
DEFAULT_OUT = ROOT / "evaluation"

APPROACHES = {
    "rule": RULE_DIR,
    "llm": LLM_DIR,
    "agent": AGENT_DIR,
}


def load_json(path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def is_match(label, failure_type):
    if failure_type == label["failure_type"]:
        return True
    return failure_type in label.get("acceptable", [])


def collect(case_ids, labels):
    rows = []
    for case_id in case_ids:
        label = labels.get(case_id)
        if not label:
            continue
        row = {"case_id": case_id, "golden": label["failure_type"], "approaches": {}}
        for name, directory in APPROACHES.items():
            payload = load_json(directory / f"report_{case_id}.json")
            if payload is None:
                row["approaches"][name] = {"available": False}
                continue
            failure_type = payload.get("failure_type")
            row["approaches"][name] = {
                "available": True,
                "failure_type": failure_type,
                "confidence": payload.get("confidence"),
                "correct": is_match(label, failure_type),
                "strict_correct": failure_type == label["failure_type"],
                "total_tokens": payload.get("total_tokens", 0),
                "fix_verified": payload.get("fix_verified"),
                "tool_calls": payload.get("tool_calls"),
            }
        rows.append(row)
    return rows


def summarize(rows):
    summary = {}
    for name in APPROACHES:
        available = [row for row in rows if row["approaches"][name]["available"]]
        correct = [row for row in available if row["approaches"][name]["correct"]]
        strict_correct = [row for row in available if row["approaches"][name]["strict_correct"]]
        summary[name] = {
            "evaluated": len(available),
            "correct": len(correct),
            "accuracy": round(len(correct) / len(available), 4) if available else None,
            "strict_correct": len(strict_correct),
            "strict_accuracy": round(len(strict_correct) / len(available), 4) if available else None,
            "average_confidence": round(
                sum(row["approaches"][name]["confidence"] or 0 for row in available) / len(available), 4
            ) if available else None,
            "total_tokens": sum(row["approaches"][name]["total_tokens"] or 0 for row in available),
            "fix_verified": sum(1 for row in available if row["approaches"][name].get("fix_verified")),
            "total_tool_calls": sum(row["approaches"][name].get("tool_calls") or 0 for row in available),
        }
    return summary


def render_markdown(rows, summary, labels_meta):
    lines = [
        "# 规则 / LLM / Agent 三方对比",
        "",
        f"- 生成时间：`{datetime.now(timezone.utc).isoformat()}`",
        f"- 标签来源：`{labels_meta.get('source')}`，需要人工复核：`{labels_meta.get('needs_human_review')}`",
        "",
        "## 逐案例结果",
        "",
        "| 案例 | Golden | Rule | LLM | Agent | Agent 验证修复 |",
        "|------|--------|------|-----|-------|----------------|",
    ]
    for row in rows:
        cells = [row["case_id"], row["golden"]]
        for name in ("rule", "llm", "agent"):
            item = row["approaches"][name]
            if not item["available"]:
                cells.append("-")
            else:
                mark = "OK" if item["correct"] else "X"
                cells.append(f"{item['failure_type']} ({mark})")
        agent = row["approaches"]["agent"]
        cells.append(str(agent.get("fix_verified")) if agent["available"] else "-")
        lines.append("| " + " | ".join(cells) + " |")

    lines.extend(
        [
            "",
            "## 汇总",
            "",
            "| 方案 | 已评测 | 正确 | 严格准确率 | 平均置信度 | tokens | 验证修复数 | 工具调用 |",
            "|------|--------|------|------------|------------|--------|------------|----------|",
        ]
    )
    for name, item in summary.items():
        lines.append(
            f"| {name} | {item['evaluated']} | {item['strict_correct']}/{item['evaluated']} | {item['strict_accuracy']} | "
            f"{item['average_confidence']} | {item['total_tokens']} | "
            f"{item['fix_verified']} | {item['total_tool_calls']} |"
        )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Evaluate attribution approaches against golden labels.")
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--cases", help="comma-separated case ids")
    args = parser.parse_args()

    label_payload = load_json(args.labels)
    if not label_payload:
        print(f"[错误] 找不到标签文件: {args.labels}")
        return 1
    labels = label_payload.get("labels", {})

    if args.cases:
        case_ids = [item.strip().zfill(3) for item in args.cases.split(",") if item.strip()]
    else:
        case_ids = sorted(labels)

    rows = collect(case_ids, labels)
    summary = summarize(rows)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "labels_source": str(args.labels.relative_to(ROOT)).replace("\\", "/"),
        "needs_human_review": label_payload.get("needs_human_review"),
        "rows": rows,
        "summary": summary,
    }
    (args.out_dir / "comparison.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown = render_markdown(rows, summary, label_payload)
    (args.out_dir / "comparison.md").write_text(markdown, encoding="utf-8")

    print(markdown)
    print(f"[完成] 结果已写入 {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
