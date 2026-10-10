"""Local tools exposed to the attribution agent.

Each function is side-effect scoped:
  - candidate requirements go to agent_workspace/, never requirements_all/
  - run_install defaults to pip --dry-run
  - real installs use a disposable venv
"""

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import batch_runner
import failure_analyzer


ROOT = Path(__file__).resolve().parent
REQ_DIR = ROOT / "requirements_all"
ERROR_DIR = ROOT / "error_all"
MANIFEST_PATH = ROOT / "manifest.json"
WORKSPACE = ROOT / "agent_workspace"

CASE_ID_RE = re.compile(r"^\d{1,4}$")
PACKAGE_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

PYPI_URL = "https://pypi.org/pypi/{package}/json"
USER_AGENT = "codex-agent-tools/1.0"


def normalize_case_id(value):
    text = str(value).strip()
    if not CASE_ID_RE.match(text):
        raise ValueError(f"invalid case_id: {value!r}")
    return f"{int(text):03d}"


def load_manifest():
    if not MANIFEST_PATH.exists():
        return {}
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {entry["case_id"]: entry for entry in payload.get("entries", [])}


def read_case(case_id, max_log_chars=12000):
    case_id = normalize_case_id(case_id)
    req_path = REQ_DIR / f"requirements_{case_id}.txt"
    error_path = ERROR_DIR / f"error_case_{case_id}.txt"
    if not req_path.exists():
        raise FileNotFoundError(f"requirements file not found: {req_path.name}")
    if not error_path.exists():
        raise FileNotFoundError(f"error log not found: {error_path.name}")

    log_text = error_path.read_text(encoding="utf-8", errors="replace")
    meta = dict(load_manifest().get(case_id, {}))
    meta_path = error_path.with_suffix(".meta.json")
    if meta_path.exists():
        run_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta.update(
            {
                "python": run_meta.get("python"),
                "pip": run_meta.get("pip"),
                "run_mode": run_meta.get("run_mode"),
                "returncode": run_meta.get("returncode"),
            }
        )

    return {
        "case_id": case_id,
        "repo": meta.get("repo"),
        "path": meta.get("path"),
        "commit_sha": meta.get("commit_sha"),
        "priority": meta.get("priority"),
        "python": meta.get("python"),
        "pip": meta.get("pip"),
        "run_mode": meta.get("run_mode"),
        "returncode": meta.get("returncode"),
        "requirements": req_path.read_text(encoding="utf-8", errors="replace"),
        "error_log": log_text[-max_log_chars:] if max_log_chars > 0 else log_text,
        "error_log_truncated": len(log_text) > max_log_chars > 0,
    }


def analyze_failure(case_id):
    case_id = normalize_case_id(case_id)
    error_path = ERROR_DIR / f"error_case_{case_id}.txt"
    if not error_path.exists():
        raise FileNotFoundError(f"error log not found: {error_path.name}")
    text = error_path.read_text(encoding="utf-8", errors="replace")
    analysis = failure_analyzer.classify(text)
    return {
        "case_id": case_id,
        "failure_type": analysis["failure_type"],
        "root_cause": analysis["root_cause"],
        "evidence": failure_analyzer.collect_evidence(text),
        "suggestions": analysis["suggestions"],
        "confidence": analysis["confidence"],
        "returncode": analysis["returncode"],
    }


def write_requirements(case_id, content):
    case_id = normalize_case_id(case_id)
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    target = WORKSPACE / f"requirements_{case_id}_candidate.txt"
    target.write_text(content, encoding="utf-8")
    return {
        "case_id": case_id,
        "candidate_file": str(target.relative_to(ROOT)).replace("\\", "/"),
        "lines": len(content.splitlines()),
    }


def run_install(case_id, requirements_text=None, dry_run=True, timeout=60):
    case_id = normalize_case_id(case_id)
    timeout = max(10, min(int(timeout), 120))

    if requirements_text:
        info = write_requirements(case_id, requirements_text)
        req_path = ROOT / info["candidate_file"]
    else:
        req_path = REQ_DIR / f"requirements_{case_id}.txt"
        if not req_path.exists():
            raise FileNotFoundError(f"requirements file not found: {req_path.name}")

    run_mode = "dry-run" if dry_run else "install"
    python_exe = batch_runner.interpreter_for(run_mode, case_id)
    command = batch_runner.build_command(python_exe, req_path, run_mode)

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        result = subprocess.CompletedProcess(
            command,
            returncode=124,
            stdout=exc.stdout or "",
            stderr=(exc.stderr or "") + f"\n[agent] timeout after {timeout}s\n",
        )
        timed_out = True

    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    return {
        "case_id": case_id,
        "requirements_file": str(req_path.relative_to(ROOT)).replace("\\", "/"),
        "dry_run": dry_run,
        "returncode": result.returncode,
        "timed_out": timed_out,
        "log_tail": combined[-4000:],
    }


def pypi_metadata(package, version=None):
    if not PACKAGE_RE.match(package):
        raise ValueError(f"invalid package name: {package!r}")
    request = urllib.request.Request(
        PYPI_URL.format(package=package),
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"package": package, "found": False}
        raise RuntimeError(f"PyPI HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"PyPI connection error: {exc.reason}") from exc

    info = payload.get("info", {})
    releases = payload.get("releases", {})
    result = {
        "package": package,
        "found": True,
        "requires_python": info.get("requires_python"),
        "requires_dist": (info.get("requires_dist") or [])[:30],
        "release_count": len(releases),
        "latest_version": info.get("version"),
    }
    if version:
        files = releases.get(version)
        if files is None:
            result["version_found"] = False
        else:
            result["version_found"] = True
            result["files"] = [item.get("filename") for item in files[:20]]
    return result


TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "read_case",
            "description": "读取一个案例的 requirements、pip 原始日志和运行元数据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {"type": "string", "description": "案例编号，如 000 或 005"},
                    "max_log_chars": {"type": "integer", "description": "日志最多返回多少字符", "default": 12000},
                },
                "required": ["case_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_failure",
            "description": "用确定性规则分析器给案例一个基线判断，可用于交叉验证。",
            "parameters": {
                "type": "object",
                "properties": {"case_id": {"type": "string"}},
                "required": ["case_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_requirements",
            "description": "把修改后的 requirements 内容写入候选文件，供 run_install 验证。",
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {"type": "string"},
                    "content": {"type": "string", "description": "完整的 requirements 文件内容"},
                },
                "required": ["case_id", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_install",
            "description": "对指定 requirements 执行 pip。默认 dry-run，只做解析不安装；可传入修改后的 requirements 验证修复。",
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {"type": "string"},
                    "requirements_text": {"type": "string", "description": "可选，修改后的完整 requirements 内容"},
                    "dry_run": {"type": "boolean", "default": True},
                    "timeout": {"type": "integer", "default": 60},
                },
                "required": ["case_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pypi_metadata",
            "description": "查询 PyPI 元数据，确认某个包或版本的 Requires-Python、依赖和可用文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "package": {"type": "string"},
                    "version": {"type": "string", "description": "可选，指定版本"},
                },
                "required": ["package"],
            },
        },
    },
]


TOOL_FUNCTIONS = {
    "read_case": read_case,
    "analyze_failure": analyze_failure,
    "write_requirements": write_requirements,
    "run_install": run_install,
    "pypi_metadata": pypi_metadata,
}


def execute_tool(name, arguments):
    if name not in TOOL_FUNCTIONS:
        return {"error": f"unknown tool: {name}"}
    try:
        return TOOL_FUNCTIONS[name](**arguments)
    except Exception as exc:  # noqa: BLE001 - return the error to the model
        return {"error": str(exc)}
