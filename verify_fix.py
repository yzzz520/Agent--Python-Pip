"""Install-level verification for an agent-proposed fix.

Unlike run_install(dry_run=True), this performs a real install into a
disposable venv, runs `pip check`, optionally imports a few packages, and
writes the verified patch to recovered/.
"""

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REQ_DIR = ROOT / "requirements_all"
WORKSPACE = ROOT / "agent_workspace"
RECOVERED_DIR = ROOT / "recovered"
VENV_ROOT = ROOT / ".runner_venvs"

CASE_ID_RE = re.compile(r"^\d{1,4}$")

DEFAULT_IMPORTS = {
    "000": ["numpy", "langchain_chroma", "langchain_pinecone", "langchain_google_alloydb_pg"],
}


def normalize_case_id(value):
    text = str(value).strip()
    if not CASE_ID_RE.match(text):
        raise ValueError(f"invalid case id: {value!r}")
    return f"{int(text):03d}"


def venv_python(venv_path):
    scripts = venv_path / ("Scripts" if os.name == "nt" else "bin")
    return scripts / ("python.exe" if os.name == "nt" else "python")


def run_command(command, timeout, cwd=None):
    started = time.perf_counter()
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=cwd,
        )
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        started_result = subprocess.CompletedProcess(
            command,
            returncode=124,
            stdout=exc.stdout or "",
            stderr=(exc.stderr or "") + f"\n[verify] timeout after {timeout}s\n",
        )
        result = started_result
        timed_out = True
    duration = round(time.perf_counter() - started, 2)
    return result, timed_out, duration


def main():
    parser = argparse.ArgumentParser(description="Real install verification for a proposed fix.")
    parser.add_argument("--case", required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--skip-install", action="store_true", help="reuse an existing venv and skip pip install")
    parser.add_argument("--skip-imports", action="store_true")
    parser.add_argument("--imports", help="comma-separated import names override")
    args = parser.parse_args()

    case_id = normalize_case_id(args.case)
    original_path = REQ_DIR / f"requirements_{case_id}.txt"
    candidate_path = args.candidate or WORKSPACE / f"requirements_{case_id}_candidate.txt"
    verification_path = RECOVERED_DIR / f"case_{case_id}.verification.json"
    previous_report = {}
    if args.skip_install and verification_path.exists():
        previous_report = json.loads(verification_path.read_text(encoding="utf-8"))
    if not original_path.exists():
        print(f"[错误] 原始 requirements 不存在: {original_path}")
        return 1
    if not candidate_path.exists():
        print(f"[错误] 候选 requirements 不存在: {candidate_path}")
        return 1

    original_text = original_path.read_text(encoding="utf-8")
    candidate_text = candidate_path.read_text(encoding="utf-8")
    RECOVERED_DIR.mkdir(parents=True, exist_ok=True)

    diff = "\n".join(
        difflib.unified_diff(
            original_text.splitlines(),
            candidate_text.splitlines(),
            fromfile=f"requirements_all/requirements_{case_id}.txt",
            tofile=f"recovered/requirements_{case_id}.fixed.txt",
            lineterm="",
        )
    ) + "\n"
    (RECOVERED_DIR / f"case_{case_id}.patch").write_text(diff, encoding="utf-8")
    (RECOVERED_DIR / f"requirements_{case_id}.fixed.txt").write_text(candidate_text, encoding="utf-8")

    venv_path = VENV_ROOT / f"verify_case_{case_id}"
    if args.skip_install and not venv_path.exists():
        print(f"[错误] --skip-install 需要已存在的 venv: {venv_path}")
        return 1
    if not venv_path.exists():
        print(f"[环境] 创建隔离 venv: {venv_path}")
        result, timed_out, duration = run_command(
            [sys.executable, "-m", "venv", str(venv_path)],
            timeout=180,
        )
        if result.returncode != 0:
            print(f"[错误] venv 创建失败: {result.stderr[-500:]}")
            return 1

    python_exe = venv_python(venv_path)
    if not python_exe.exists():
        print(f"[错误] venv python 不存在: {python_exe}")
        return 1

    install_command = [
        str(python_exe),
        "-m",
        "pip",
        "install",
        "-r",
        str(candidate_path),
        "--disable-pip-version-check",
        "--no-input",
    ]
    if args.skip_install:
        print("[安装] 跳过安装，复用已有 venv")
        install_result = subprocess.CompletedProcess(
            install_command,
            returncode=0,
            stdout="[verify] skipped install, reusing existing venv\n",
            stderr="",
        )
        install_timeout = False
        install_duration = 0.0
        install_log = install_result.stdout
    else:
        print(f"[安装] 真实安装开始（最长 {args.timeout}s）: {candidate_path.name}")
        install_result, install_timeout, install_duration = run_command(install_command, args.timeout)
        install_log = (install_result.stdout or "") + "\n" + (install_result.stderr or "")
        (RECOVERED_DIR / f"case_{case_id}.install.log").write_text(install_log, encoding="utf-8")

    check_result = None
    check_duration = 0.0
    if install_result.returncode == 0:
        print("[检查] pip check ...")
        check_result, _check_timeout, check_duration = run_command(
            [str(python_exe), "-m", "pip", "check"],
            timeout=120,
        )

    imports = []
    if args.imports:
        import_names = [item.strip() for item in args.imports.split(",") if item.strip()]
    else:
        import_names = DEFAULT_IMPORTS.get(case_id, [])
    if install_result.returncode == 0 and import_names and not args.skip_imports:
        code = "import " + ", ".join(import_names) + "; print('import-ok')"
        import_result, _timeout, duration = run_command(
            [str(python_exe), "-c", code],
            timeout=120,
        )
        imports.append(
            {
                "names": import_names,
                "returncode": import_result.returncode,
                "duration_sec": duration,
                "output": ((import_result.stdout or "") + (import_result.stderr or ""))[-1000:],
            }
        )

    install_ok = install_result.returncode == 0 and not install_timeout
    pip_check_ok = check_result is not None and check_result.returncode == 0
    imports_ok = all(item["returncode"] == 0 for item in imports) if imports else None
    recovered = install_ok and pip_check_ok

    report = {
        "case_id": case_id,
        "original_requirements": str(original_path.relative_to(ROOT)).replace("\\", "/"),
        "candidate_requirements": str(candidate_path.relative_to(ROOT)).replace("\\", "/"),
        "fixed_requirements": f"recovered/requirements_{case_id}.fixed.txt",
        "patch_file": f"recovered/case_{case_id}.patch",
        "install_log": f"recovered/case_{case_id}.install.log",
        "venv": str(venv_path.relative_to(ROOT)).replace("\\", "/"),
        "install_returncode": install_result.returncode,
        "install_timed_out": install_timeout,
        "install_duration_sec": install_duration,
        "pip_check_returncode": check_result.returncode if check_result else None,
        "pip_check_output": ((check_result.stdout or "") + (check_result.stderr or ""))[-1000:] if check_result else None,
        "imports": imports,
        "install_verified": install_ok,
        "pip_check_verified": pip_check_ok,
        "imports_verified": imports_ok,
        "recovery_basis": "real install + pip check; import smoke test is informational",
        "recovered": recovered,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if previous_report:
        for key in ("install_returncode", "install_timed_out", "install_duration_sec", "install_log"):
            if key in previous_report:
                report[key] = previous_report[key]
    verification_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[安装] returncode={install_result.returncode}, 耗时 {install_duration}s")
    print(f"[检查] pip check returncode={report['pip_check_returncode']}")
    if imports:
        print(f"[检查] import 冒烟测试 returncode={imports[0]['returncode']}")
    print(f"[结果] recovered={recovered}")
    print(f"[产物] {RECOVERED_DIR}")
    return 0 if recovered else 1


if __name__ == "__main__":
    sys.exit(main())
