"""Repair manifest.json for local requirements files without re-downloading.

Use case: a download run was interrupted before it wrote manifest.json, so some
requirements_XXX.txt files exist on disk but have no manifest record. This
script reconstructs those records from:
  - requirements_sources.json (repo / path / priority / category)
  - git ls-remote (commit SHA; no file content download)
  - the local file (sha256, bytes, rewritten markers)
  - requirements_all/support/case_XXX (companion files)
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INDEX_PATH = ROOT / "requirements_sources.json"
MANIFEST_PATH = ROOT / "manifest.json"
REQ_DIR = ROOT / "requirements_all"
SUPPORT_DIRNAME = "support"

GIT_TIMEOUT = 30
API_TIMEOUT = 30
API_COMMIT_URL = "https://api.github.com/repos/{repo}/commits/HEAD"
USER_AGENT = "codex-manifest-repair/1.0"

REF_RE = re.compile(
    r"^(?P<indent>\s*)(?P<opt>-r|--requirement|-c|--constraint)(?P<sep>\s+|=)(?P<ref>\S+)(?P<rest>.*)$",
    re.IGNORECASE,
)
REMOVED_RE = re.compile(
    r"^#\s*\[collector\]\s+skipped\s+(?:local editable reference|local path reference):\s*(.+)$"
)


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_commit_sha_git(repo):
    git = shutil.which("git")
    if not git:
        raise RuntimeError("git not found in PATH")
    result = subprocess.run(
        [git, "ls-remote", f"https://github.com/{repo}.git", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=GIT_TIMEOUT,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[:200]
        raise RuntimeError(f"git ls-remote failed: {detail}")
    output = result.stdout.strip()
    if not output:
        raise RuntimeError("git ls-remote returned no HEAD")
    return output.split()[0]


def resolve_commit_sha_api(repo):
    request = urllib.request.Request(
        API_COMMIT_URL.format(repo=repo),
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=API_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"GitHub API {exc.code}: {detail}") from exc
    sha = payload.get("sha")
    if not sha:
        raise RuntimeError("GitHub API returned no commit sha")
    return sha


def resolve_commit_sha(repo):
    errors = []
    for _attempt in range(2):
        try:
            return resolve_commit_sha_git(repo), "git-ls-remote(repair)"
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
            time.sleep(1)
    try:
        return resolve_commit_sha_api(repo), "github-api(repair)"
    except Exception as exc:  # noqa: BLE001
        errors.append(str(exc))
    raise RuntimeError("; ".join(errors))


def simulate_mapping(index_entries, manifest_entries):
    """Reproduce the case-id assignment the interrupted download run used."""
    known = {(entry["repo"], entry["path"]) for entry in manifest_entries}
    next_id = max(
        (int(entry["case_id"]) for entry in manifest_entries if str(entry["case_id"]).isdigit()),
        default=0,
    ) + 1

    mapping = {}
    for entry in index_entries:
        key = (entry["repo"], entry["path"])
        if key in known:
            continue
        mapping[f"{next_id:03d}"] = entry
        next_id += 1
    return mapping


def scan_companions(case_id):
    support_root = REQ_DIR / SUPPORT_DIRNAME / f"case_{case_id}"
    if not support_root.exists():
        return []

    companions = []
    for path in sorted(support_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(support_root).as_posix()
        companions.append(
            {
                "repo_path": relative,
                "local_path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return companions


def detect_removed_local_references(text):
    removed = []
    for line in text.splitlines():
        match = REMOVED_RE.match(line.strip())
        if match:
            removed.append(match.group(1))
    return removed


def detect_missing_companions(text, case_id):
    prefix = f"{SUPPORT_DIRNAME}/case_{case_id}/"
    missing = []
    for line in text.splitlines():
        match = REF_RE.match(line)
        if not match:
            continue
        ref = match.group("ref")
        if not ref.startswith(prefix):
            continue
        relative = ref[len(prefix):]
        if not (REQ_DIR / prefix / relative).exists():
            missing.append({"repo_path": relative, "error": "referenced local companion is missing"})
    return missing


def main():
    parser = argparse.ArgumentParser(description="Repair manifest.json from local files.")
    parser.add_argument("--dry-run", action="store_true", help="print what would change, do not write")
    parser.add_argument(
        "--refresh-missing-sha",
        action="store_true",
        help="only fill commit_sha for existing manifest entries that still miss it",
    )
    args = parser.parse_args()

    index_entries = load_json(INDEX_PATH).get("entries", [])
    manifest = load_json(MANIFEST_PATH)
    manifest_entries = manifest.get("entries", [])
    existing_ids = {entry["case_id"] for entry in manifest_entries}

    if args.refresh_missing_sha:
        targets = [entry for entry in manifest_entries if not entry.get("commit_sha")]
        print(f"[刷新] 需要补 commit SHA 的条目: {len(targets)}")
        updated = 0
        for entry in targets:
            try:
                sha, sha_source = resolve_commit_sha(entry["repo"])
            except Exception as exc:  # noqa: BLE001
                entry["sha_error"] = str(exc)
                print(f"[失败] case={entry['case_id']} {entry['repo']} -> {exc}")
                continue
            entry["commit_sha"] = sha
            entry["sha_source"] = sha_source
            entry["sha_error"] = None
            entry["raw_url"] = (
                f"https://raw.githubusercontent.com/{entry['repo']}/{sha}/{entry['path']}"
            )
            entry["source_url"] = f"https://github.com/{entry['repo']}/blob/{sha}/{entry['path']}"
            updated += 1
            print(f"[修复] case={entry['case_id']} {entry['repo']} sha={sha[:10]} ({sha_source})")

        if args.dry_run:
            print(f"[完成] dry-run 模式，未写入 manifest，可修复 {updated} 条。")
            return 0

        manifest["entries"] = manifest_entries
        manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
        MANIFEST_PATH.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[完成] 已补 {updated} 条 commit SHA，manifest 共 {len(manifest_entries)} 条。")
        return 0

    mapping = simulate_mapping(index_entries, manifest_entries)
    max_local_case = max(
        (
            int(case_id)
            for case_id in mapping
            if (REQ_DIR / f"requirements_{case_id}.txt").exists()
        ),
        default=0,
    )

    repaired = []
    for case_id in sorted(mapping, key=int):
        if int(case_id) > max_local_case:
            break
        if case_id in existing_ids:
            continue

        req_path = REQ_DIR / f"requirements_{case_id}.txt"
        if not req_path.exists():
            print(f"[警告] case={case_id} 在 manifest 中缺失，但本地文件也不存在，跳过。")
            continue

        entry = mapping[case_id]
        try:
            sha = resolve_commit_sha_git(entry["repo"])
            sha_error = None
        except Exception as exc:  # noqa: BLE001
            sha = None
            sha_error = str(exc)

        text = req_path.read_text(encoding="utf-8", errors="replace")
        data = req_path.read_bytes()
        rewritten = f"{SUPPORT_DIRNAME}/case_{case_id}/" in text or "[collector] skipped" in text
        companions = scan_companions(case_id)
        removed = detect_removed_local_references(text)
        missing = detect_missing_companions(text, case_id)

        record = {
            "case_id": case_id,
            "requirements_file": str(req_path.relative_to(ROOT)).replace("\\", "/"),
            "repo": entry["repo"],
            "path": entry["path"],
            "commit_sha": sha,
            "sha_source": "git-ls-remote(repair)" if sha else None,
            "sha_error": sha_error,
            "raw_url": (
                f"https://raw.githubusercontent.com/{entry['repo']}/{sha}/{entry['path']}"
                if sha
                else None
            ),
            "source_url": (
                f"https://github.com/{entry['repo']}/blob/{sha}/{entry['path']}"
                if sha
                else None
            ),
            "priority": entry.get("priority"),
            "category": entry.get("category"),
            "tags": entry.get("tags", []),
            "curated": entry.get("curated", True),
            "downloaded_at": datetime.fromtimestamp(req_path.stat().st_mtime, tz=timezone.utc).isoformat(),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "source_bytes": len(data) if not rewritten else None,
            "source_sha256": hashlib.sha256(data).hexdigest() if not rewritten else None,
            "rewritten": rewritten,
            "removed_local_references": removed,
            "companions": companions,
            "missing_companions": missing,
            "repaired": True,
            "repair_note": "record reconstructed from local files; source hash unavailable when rewritten",
        }
        if sha_error:
            record["repair_note"] += f"; sha resolution failed: {sha_error}"

        repaired.append(record)
        print(
            f"[修复] case={case_id} {entry['repo']} :: {entry['path']} "
            f"sha={sha[:10] if sha else 'N/A'} companions={len(companions)} "
            f"removed_local={len(removed)}"
        )

    print("\n[一致性检查] 已有 manifest 条目 vs 本地文件：")
    issues = []
    for entry in sorted(manifest_entries, key=lambda item: int(item["case_id"]) if str(item["case_id"]).isdigit() else 0):
        req_path = ROOT / entry.get("requirements_file", "")
        if not req_path.exists():
            issues.append(f"case={entry['case_id']} 本地文件不存在")
            continue
        current = sha256_file(req_path)
        if entry.get("sha256") and entry["sha256"] != current:
            issues.append(f"case={entry['case_id']} sha256 不匹配")
    if issues:
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("  - 已有条目全部一致")

    print(f"\n[汇总] 本次可补录 {len(repaired)} 条，已有 {len(manifest_entries)} 条。")
    if args.dry_run:
        print("[完成] dry-run 模式，未写入 manifest。")
        return 0

    merged = manifest_entries + repaired
    merged.sort(key=lambda item: int(item["case_id"]) if str(item["case_id"]).isdigit() else 0)
    manifest["entries"] = merged
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    manifest["repair"] = {
        "repaired_at": datetime.now(timezone.utc).isoformat(),
        "repaired_count": len(repaired),
        "script": "repair_manifest.py",
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[完成] manifest 已更新: {MANIFEST_PATH}，当前共 {len(merged)} 条。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
