"""Tool-using failure attribution agent.

The model receives the case id plus a tool box, decides which tools to call,
observes the results, and may verify a proposed fix by calling run_install
again. The final message must be the same JSON schema as llm_analyzer.py.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import agent_tools
from llm_analyzer import normalize_payload, parse_json_response
from llm_client import LLMClient, LLMConfigError


ROOT = Path(__file__).resolve().parent
DEFAULT_REPORT_DIR = ROOT / "reports_agent_all"
DEFAULT_TRACE_DIR = ROOT / "agent_traces"

SYSTEM_PROMPT = """你是一个依赖安装失败归因 Agent。
你可以调用工具来收集证据、验证假设、修改 requirements 并重新安装验证。
工作方式：
1. 先读取案例，理解 pip 到底报了什么。
2. 如果证据不足，调用工具补充证据（例如查 PyPI 元数据、用规则分析器交叉验证）。
3. 如果提出了修复方案，尽量调用 run_install 验证它是否真的能通过。
4. 验证后给出最终 JSON，字段必须与要求一致。
5. 如果案例的 returncode 是 0，说明本来就没有失败，直接判定 no_failure，不要调用 run_install。
最终回复只输出 JSON，不要输出其他文字。
"""

FINAL_SCHEMA_HINT = """最终必须输出这个 JSON：
{
  "failure_type": "dependency_conflict | python_version_mismatch | no_matching_distribution | build_failure | network_error | missing_referenced_file | invalid_local_reference | no_failure | unknown",
  "root_cause": "一句话中文根因",
  "evidence": ["来自日志的短证据，最多 5 条"],
  "suggestions": ["建议，最多 4 条"],
  "confidence": 0.0,
  "fix_verified": false,
  "verification_note": "如果调用过 run_install，说明验证结果；否则留空"
}
"""


def load_case_ids(value):
    if not value:
        return None
    return {item.strip().lstrip("0") or "0" for item in value.split(",") if item.strip()}


def build_initial_message(case_id):
    return f"""请归因案例 {case_id}。
你可以使用工具收集证据。requirements 和 pip 日志要用工具读取，不要凭空猜测。
如果给出修复方案，请用 run_install 验证修复后的 requirements 是否能通过解析。

{FINAL_SCHEMA_HINT}
"""


def build_initial_message_preloaded(case):
    return f"""请归因案例 {case['case_id']}。案例内容已经附在下面，不需要再调用 read_case。
如果提出修复方案，可以用 run_install 验证；如果 returncode 是 0，直接判定 no_failure。

【元数据】
repo: {case.get('repo')}
path: {case.get('path')}
commit: {case.get('commit_sha')}
python: {case.get('python')}
pip: {case.get('pip')}
returncode: {case.get('returncode')}

【requirements.txt】
{case.get('requirements', '')}

【pip 输出】
{case.get('error_log', '')}

{FINAL_SCHEMA_HINT}
"""


def execute_tool_call(name, arguments, allow_real_install):
    if name == "run_install" and not allow_real_install:
        arguments = dict(arguments)
        arguments["dry_run"] = True
    return agent_tools.execute_tool(name, arguments)


def mock_analysis(case_id):
    case = agent_tools.read_case(case_id)
    rule = agent_tools.analyze_failure(case_id)
    return {
        "failure_type": rule["failure_type"],
        "root_cause": rule["root_cause"],
        "evidence": rule["evidence"][:5],
        "suggestions": rule["suggestions"],
        "confidence": rule["confidence"],
        "fix_verified": False,
        "verification_note": "mock 模式：未调用真实模型",
    }


def main():
    parser = argparse.ArgumentParser(description="Tool-using failure attribution agent.")
    parser.add_argument("--cases", help="comma-separated case ids, e.g. 000,005")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--model")
    parser.add_argument("--max-steps", type=int, default=6)
    parser.add_argument("--max-tokens", type=int, default=2000)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--allow-real-install", action="store_true", help="allow run_install with dry_run=false")
    parser.add_argument("--preload", action="store_true", help="include case content in the first message")
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--trace-dir", type=Path, default=DEFAULT_TRACE_DIR)
    args = parser.parse_args()

    wanted = load_case_ids(args.cases)
    error_files = sorted(
        path
        for path in (ROOT / "error_all").iterdir()
        if path.is_file() and path.name.endswith(".txt")
    )
    if wanted:
        error_files = [
            path
            for path in error_files
            if (path.stem.replace("error_case_", "").lstrip("0") or "0") in wanted
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
    args.trace_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    failures = []

    print(f"[系统] 共 {len(error_files)} 个案例，模型: {model_name}，mock={args.mock}")

    for error_path in error_files:
        case_id = error_path.stem.replace("error_case_", "")
        trace = []
        total_tokens = 0
        final_payload = None
        tool_calls = 0

        if args.mock:
            raw_mock = mock_analysis(case_id)
            final_payload = normalize_payload(raw_mock)
            final_payload["fix_verified"] = bool(raw_mock.get("fix_verified", False))
            final_payload["verification_note"] = str(raw_mock.get("verification_note", ""))
        else:
            if args.preload:
                case_content = agent_tools.read_case(case_id)
                initial_message = build_initial_message_preloaded(case_content)
            else:
                initial_message = build_initial_message(case_id)
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": initial_message},
            ]
            json_retries = 0
            try:
                for step in range(args.max_steps):
                    response = client.chat_with_tools(
                        messages,
                        agent_tools.TOOL_SPECS,
                        temperature=args.temperature,
                        max_tokens=args.max_tokens,
                    )
                    usage = response.get("usage", {})
                    total_tokens += usage.get("total_tokens", 0)
                    calls = response.get("tool_calls", [])
                    messages.append(response["message"])

                    if not calls:
                        try:
                            raw_final = parse_json_response(response["content"])
                        except Exception:
                            if json_retries < 2:
                                json_retries += 1
                                messages.append(
                                    {
                                        "role": "user",
                                        "content": "上一条回复不是合法 JSON。请只输出最终 JSON，不要任何解释或 Markdown。",
                                    }
                                )
                                continue
                            raise
                        final_payload = normalize_payload(raw_final)
                        final_payload["fix_verified"] = bool(raw_final.get("fix_verified", False))
                        final_payload["verification_note"] = str(raw_final.get("verification_note", ""))
                        break

                    for call in calls:
                        tool_calls += 1
                        name = call["function"]["name"]
                        raw_args = call["function"].get("arguments") or "{}"
                        try:
                            arguments = json.loads(raw_args)
                        except json.JSONDecodeError:
                            arguments = {}
                        result = execute_tool_call(name, arguments, args.allow_real_install)
                        trace.append(
                            {
                                "step": step,
                                "tool": name,
                                "arguments": arguments,
                                "result": result,
                            }
                        )
                        print(f"[工具] case={case_id} step={step} {name}")
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.get("id"),
                                "content": json.dumps(result, ensure_ascii=False)[:8000],
                            }
                        )
                else:
                    raise RuntimeError(f"达到最大步数 {args.max_steps} 仍未得到最终 JSON")
            except Exception as exc:  # noqa: BLE001 - keep the batch running
                (args.trace_dir / f"trace_{case_id}.json").write_text(
                    json.dumps(
                        {
                            "case_id": case_id,
                            "model": model_name,
                            "error": str(exc),
                            "tool_calls": tool_calls,
                            "trace": trace,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                failures.append({"case_id": case_id, "error": str(exc)})
                print(f"[失败] case={case_id} -> {exc}")
                continue

        trace_path = args.trace_dir / f"trace_{case_id}.json"
        trace_path.write_text(
            json.dumps(
                {
                    "case_id": case_id,
                    "model": model_name,
                    "tool_calls": tool_calls,
                    "total_tokens": total_tokens,
                    "trace": trace,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        verified = bool(final_payload.get("fix_verified", False))
        verification_note = final_payload.get("verification_note", "")
        for item in trace:
            if item["tool"] != "run_install":
                continue
            if not item["arguments"].get("requirements_text"):
                continue
            if item["result"].get("returncode") == 0:
                verified = True
                if not verification_note:
                    verification_note = "run_install 对修改后的 requirements 解析成功 (returncode=0)"

        record = {
            "case_id": case_id,
            "source_error_file": error_path.name,
            "model": model_name,
            "failure_type": final_payload["failure_type"],
            "root_cause": final_payload["root_cause"],
            "evidence": final_payload["evidence"],
            "suggestions": final_payload["suggestions"],
            "confidence": final_payload["confidence"],
            "fix_verified": verified,
            "verification_note": verification_note,
            "tool_calls": tool_calls,
            "total_tokens": total_tokens,
            "trace_file": str(trace_path.relative_to(ROOT)).replace("\\", "/"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        (args.report_dir / f"report_{case_id}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        summary.append(record)
        print(
            f"[完成] case={case_id} -> {record['failure_type']} "
            f"(confidence={record['confidence']}, tools={tool_calls})"
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
        "mock": args.mock,
        "case_count": len(summary),
        "failure_type_counts": counts,
        "average_confidence": round(
            sum(record["confidence"] for record in summary) / len(summary), 4
        ) if summary else 0.0,
        "total_tool_calls": sum(record["tool_calls"] for record in summary),
        "total_tokens": sum(record["total_tokens"] for record in summary),
        "fix_verified_count": sum(1 for record in summary if record["fix_verified"]),
        "cases": summary,
        "failures": failures,
    }
    (args.report_dir / "summary.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n[汇总] {counts}")
    print(f"[汇总] 工具调用 {summary_payload['total_tool_calls']} 次，tokens {summary_payload['total_tokens']}")
    print(f"[汇总] 写出目录: {args.report_dir}")
    if failures:
        print(f"[汇总] 失败 {len(failures)} 条")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
