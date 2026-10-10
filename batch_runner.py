"""Batch requirement executor.

Runs pip for every requirements_*.txt in requirements_all and stores the raw
output in error_all. The runner always uses the interpreter that launched it
("sys.executable -m pip") so the resolved Python version is the one we intend.

By default pip runs in --dry-run mode: the real resolver runs and reports
conflicts / missing distributions, but nothing is installed. Pass --install to
perform real installs into disposable virtual environments.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"


ROOT = Path(__file__).resolve().parent
REQ_DIR = ROOT / "requirements_all"
ERR_DIR = ROOT / "error_all"
VENV_DIR = ROOT / ".runner_venvs"

DEFAULT_TIMEOUT = 300
REQ_PATTERN = re.compile(r"^requirements_(\d+)\.txt$", re.IGNORECASE)


def format_case_id(raw_id):
    """Normalize a numeric case id to three digits: 1 -> 001, 000 -> 000."""
    digits = re.sub(r"\D", "", str(raw_id))
    if not digits:
        raise ValueError(f"case id must contain digits: {raw_id!r}")
    return f"{int(digits):03d}"


def pip_version(python_exe):
    result = subprocess.run(
        [python_exe, "-m", "pip", "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return (result.stdout or result.stderr).strip()


def interpreter_for(run_mode, case_id):
    """Return the interpreter used for pip.

    dry-run keeps the current interpreter; real installs get a disposable venv
    so the base environment is never polluted.
    """
    if run_mode == "dry-run":
        return sys.executable

    VENV_DIR.mkdir(parents=True, exist_ok=True)
    venv_path = VENV_DIR / f"case_{case_id}"
    if not venv_path.exists():
        print(f"[环境] 创建隔离 venv: {venv_path}")
        subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)

    scripts = venv_path / ("Scripts" if os.name == "nt" else "bin")
    python_exe = scripts / ("python.exe" if os.name == "nt" else "python")
    if not python_exe.exists():
        raise RuntimeError(f"venv python not found: {python_exe}")
    return str(python_exe)


def build_command(python_exe, req_path, run_mode):
    command = [
        python_exe,
        "-m",
        "pip",
        "install",
        "-r",
        str(req_path),
        "--disable-pip-version-check",
        "--no-input",
    ]
    if run_mode == "dry-run":
        command.append("--dry-run")
    return command


def render_log(command, python_exe, pip_info, result, duration, run_mode):
    stdout = result.stdout if result.stdout is not None else ""
    stderr = result.stderr if result.stderr is not None else ""
    return "\n".join(
        [
            "=" * 70,
            "PIP RUN METADATA",
            "=" * 70,
            f"timestamp_utc : {datetime.now(timezone.utc).isoformat()}",
            f"run_mode      : {run_mode}",
            f"python        : {python_exe}",
            f"pip           : {pip_info}",
            f"returncode    : {result.returncode}",
            f"duration_sec  : {duration:.2f}",
            f"command       : {' '.join(command)}",
            "=" * 70,
            "STDOUT",
            "=" * 70,
            stdout,
            "=" * 70,
            "STDERR",
            "=" * 70,
            stderr,
            "",
        ]
    )


def run_one(req_path, case_id, run_mode, timeout):
    err_path = ERR_DIR / f"error_case_{case_id}.txt"
    meta_path = ERR_DIR / f"error_case_{case_id}.meta.json"

    print(f"[执行] {req_path.name} ...")
    started = time.perf_counter()
    python_exe = interpreter_for(run_mode, case_id)
    command = build_command(python_exe, req_path, run_mode)
    pip_info = pip_version(python_exe)

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
            stderr=(exc.stderr or "") + f"\n[runner] timeout after {timeout}s\n",
        )
        timed_out = True

    duration = time.perf_counter() - started
    log_text = render_log(command, python_exe, pip_info, result, duration, run_mode)
    err_path.write_text(log_text, encoding="utf-8")

    meta = {
        "case_id": case_id,
        "requirements_file": str(req_path.relative_to(ROOT)).replace("\\", "/"),
        "error_file": str(err_path.relative_to(ROOT)).replace("\\", "/"),
        "run_mode": run_mode,
        "python": python_exe,
        "pip": pip_info,
        "returncode": result.returncode,
        "timed_out": timed_out,
        "duration_sec": round(duration, 2),
        "command": command,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    status = "超时" if timed_out else ("有报错" if result.returncode else "无报错")
    print(f"[完成] {err_path.name} -> returncode={result.returncode} ({status}), {duration:.1f}s")
    return case_id, result.returncode, timed_out, duration


def main():
    parser = argparse.ArgumentParser(description="Run pip for all captured requirements files.")
    parser.add_argument(
        "--install",
        action="store_true",
        help="perform real installs in disposable venvs (default: pip --dry-run)",
    )
    parser.add_argument("--cases", help="comma-separated case ids, e.g. 006,007,008")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="per-case timeout in seconds")
    parser.add_argument("--jobs", type=int, default=1, help="parallel cases; dry-run is safe to parallelize")
    args = parser.parse_args()

    run_mode = "install" if args.install else "dry-run"
    ERR_DIR.mkdir(parents=True, exist_ok=True)

    candidates = sorted(
        p
        for p in REQ_DIR.iterdir()
        if p.is_file() and p.name.lower().startswith("requirements_") and p.suffix.lower() == ".txt"
    )

    req_files = []
    skipped = []
    seen_ids = {}
    for candidate in candidates:
        match = REQ_PATTERN.match(candidate.name)
        if not match:
            skipped.append(candidate.name)
            continue
        case_id = format_case_id(match.group(1))
        if case_id in seen_ids:
            print(
                f"[错误] 案例编号冲突：{candidate.name} 与 {seen_ids[case_id]} "
                f"都会格式化为 {case_id}，请先重命名其中一个文件。"
            )
            return 1
        seen_ids[case_id] = candidate.name
        req_files.append((candidate, case_id))

    if skipped:
        print(f"[警告] 跳过不符合 requirements_NNN.txt 命名的文件: {', '.join(skipped)}")

    if args.cases:
        wanted = set()
        for value in args.cases.split(","):
            value = value.strip()
            if not value:
                continue
            try:
                wanted.add(format_case_id(value))
            except ValueError:
                print(f"[警告] 忽略无法识别的案例编号: {value}")
        req_files = [
            (path, case_id)
            for path, case_id in req_files
            if case_id in wanted
        ]
    if not req_files:
        print(f"[系统] 警告：在 {REQ_DIR} 中没有找到符合条件的 requirements 文件。")
        return 0

    jobs = max(1, args.jobs)
    print(
        f"[系统] 共发现 {len(req_files)} 个依赖文件，模式: {run_mode}，"
        f"超时: {args.timeout}s，并发: {jobs}\n"
    )

    if jobs == 1:
        for req_path, case_id in req_files:
            run_one(req_path, case_id, run_mode, args.timeout)
            time.sleep(1)
    else:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = {
                pool.submit(run_one, req_path, case_id, run_mode, args.timeout): case_id
                for req_path, case_id in req_files
            }
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:  # noqa: BLE001 - keep other cases running
                    print(f"[异常] case={futures[future]} -> {exc}")

    print("\n[系统] 批量执行完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
