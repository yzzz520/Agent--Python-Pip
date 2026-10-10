"""Stage 2: download requirements files pinned to commit SHAs.

Flow:
  1. Read requirements_sources.json produced by collect_requirements.py.
  2. Resolve the default branch commit SHA (GitHub API, with git ls-remote fallback).
  3. Download the requirements file at that SHA.
  4. Download referenced companion files (-r / -c) into a per-case support dir
     and rewrite the top-level references to those local copies.
  5. Comment out local editable references (-e .) and record them.

Every downloaded file is recorded in manifest.json together with the resolved
commit SHA, so the test input stays reproducible even after the default branch
moves.
"""

import argparse
import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INDEX_PATH = ROOT / "requirements_sources.json"
REQ_DIR = ROOT / "requirements_all"
SUPPORT_DIRNAME = "support"
MANIFEST_PATH = ROOT / "manifest.json"

API_COMMIT_URL = "https://api.github.com/repos/{repo}/commits/HEAD"
RAW_URL = "https://raw.githubusercontent.com/{repo}/{sha}/{path}"
BLOB_URL = "https://github.com/{repo}/blob/{sha}/{path}"

USER_AGENT = "codex-requirements-downloader/1.0"
HTTP_TIMEOUT = 60
GIT_TIMEOUT = 60

MAX_COMPANIONS = 25
MAX_COMPANION_DEPTH = 5

REF_RE = re.compile(
    r"^(?P<indent>\s*)(?P<opt>-r|--requirement|-c|--constraint)(?P<sep>\s+|=)(?P<ref>\S+)(?P<rest>.*)$",
    re.IGNORECASE,
)
EDITABLE_RE = re.compile(
    r"^(?P<indent>\s*)(?P<opt>-e|--editable)(?P<sep>\s+|=)(?P<ref>\S+)(?P<rest>.*)$",
    re.IGNORECASE,
)
URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")

API_DISABLED = False


def http_get(url, accept="application/vnd.github+json"):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": accept},
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        return response.read()


def load_index(path):
    if not path.exists():
        raise RuntimeError(
            f"找不到索引文件 {path.name}。先运行: python collect_requirements.py --seed-only"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("entries", [])


def load_manifest():
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"generated_at": None, "source_index": INDEX_PATH.name, "entries": []}


def split_filter(value):
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def select_entries(entries, args, manifest_entries):
    priorities = {p.upper() for p in split_filter(args.priority)}
    repos = split_filter(args.repo)
    paths = split_filter(args.path)
    tags = set(split_filter(args.tag))
    ids = {value.strip().lstrip("0") or "0" for value in split_filter(args.ids)}

    id_to_key = {
        (entry["case_id"].lstrip("0") or "0"): (entry["repo"], entry["path"])
        for entry in manifest_entries
    }
    wanted_keys = {id_to_key[case_id] for case_id in ids if case_id in id_to_key}

    selected = []
    for entry in entries:
        if priorities and entry.get("priority", "").upper() not in priorities:
            continue
        if repos and not any(repo.lower() in entry["repo"].lower() for repo in repos):
            continue
        if paths and not any(path.lower() in entry["path"].lower() for path in paths):
            continue
        if tags and not tags.intersection(entry.get("tags", [])):
            continue
        if ids and (entry["repo"], entry["path"]) not in wanted_keys:
            continue
        selected.append(entry)

    if args.offset:
        selected = selected[args.offset:]
    if args.limit is not None:
        selected = selected[:args.limit]
    return selected


def resolve_commit_sha_api(repo):
    url = API_COMMIT_URL.format(repo=repo)
    try:
        payload = json.loads(http_get(url).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"GitHub API {exc.code}: {detail}") from exc
    sha = payload.get("sha")
    if not sha:
        raise RuntimeError("GitHub API returned no commit sha")
    return sha


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


def resolve_commit_sha(repo, git_only=False):
    global API_DISABLED
    if not git_only and not API_DISABLED:
        try:
            return resolve_commit_sha_api(repo), "github-api"
        except RuntimeError as exc:
            message = str(exc)
            if "403" in message:
                API_DISABLED = True
                print("[提示] GitHub API 触发限流，后续改用 git ls-remote。")
            else:
                print(f"[提示] API 解析失败，改用 git ls-remote: {message}")
    return resolve_commit_sha_git(repo), "git-ls-remote"


def download_raw(repo, sha, path):
    url = RAW_URL.format(repo=repo, sha=sha, path=path)
    try:
        return url, http_get(url, accept="text/plain")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"raw download {exc.code} for {url}: {detail}") from exc


def is_local_reference(ref):
    ref = ref.strip()
    return (
        ref.startswith(".")
        or ref.startswith("/")
        or ref.startswith("~")
        or bool(re.match(r"^[A-Za-z]:[/\\]", ref))
    )


def normalize_repo_path(base_dir, ref):
    ref = ref.strip().replace("\\", "/")
    if URL_RE.match(ref) or ref.startswith("git+"):
        return None, "url"
    if ref.startswith("/") or ref.startswith("~") or re.match(r"^[A-Za-z]:/", ref):
        return None, "absolute"

    candidate = posixpath.normpath(posixpath.join(base_dir, ref))
    if candidate in (".", ""):
        return None, "local-directory"
    if candidate == ".." or candidate.startswith("../"):
        return None, "escapes-repo-root"
    return candidate, None


def extract_references(text, base_dir):
    references = []
    for line in text.splitlines():
        match = REF_RE.match(line)
        if not match:
            continue
        repo_path, _reason = normalize_repo_path(base_dir, match.group("ref"))
        if repo_path:
            references.append(repo_path)
    return references


def rewrite_main_file(entry, content, case_id):
    """Return rewritten text, companion paths, removed local refs."""
    text = content.decode("utf-8", errors="replace")
    base_dir = posixpath.dirname(entry["path"])
    support_prefix = f"{SUPPORT_DIRNAME}/case_{case_id}"

    rewritten_lines = []
    companion_paths = []
    removed_local = []

    for line in text.splitlines():
        ref_match = REF_RE.match(line)
        if ref_match:
            repo_path, _reason = normalize_repo_path(base_dir, ref_match.group("ref"))
            if repo_path:
                local_ref = f"{support_prefix}/{repo_path}"
                rewritten_lines.append(
                    f"{ref_match.group('indent')}{ref_match.group('opt')}"
                    f"{ref_match.group('sep')}{local_ref}{ref_match.group('rest')}"
                )
                companion_paths.append(repo_path)
                continue

        editable_match = EDITABLE_RE.match(line)
        if editable_match and is_local_reference(editable_match.group("ref")):
            removed_local.append(line.strip())
            rewritten_lines.append(f"# [collector] skipped local editable reference: {line.strip()}")
            continue

        stripped = line.strip()
        if (
            stripped
            and not stripped.startswith("#")
            and not stripped.startswith("-")
            and is_local_reference(stripped.split()[0])
        ):
            removed_local.append(stripped)
            rewritten_lines.append(f"# [collector] skipped local path reference: {stripped}")
            continue

        rewritten_lines.append(line)

    rewritten_text = "\n".join(rewritten_lines)
    if text.endswith("\n"):
        rewritten_text += "\n"
    return rewritten_text, companion_paths, removed_local


def download_companions(repo, sha, case_id, initial_paths):
    support_root = REQ_DIR / SUPPORT_DIRNAME / f"case_{case_id}"
    downloaded = []
    missing = []
    seen = set()
    queue = deque((path, 1) for path in initial_paths)

    while queue:
        repo_path, depth = queue.popleft()
        if repo_path in seen:
            continue
        seen.add(repo_path)

        if depth > MAX_COMPANION_DEPTH or len(downloaded) >= MAX_COMPANIONS:
            missing.append({"repo_path": repo_path, "error": "depth or file limit reached"})
            continue

        try:
            _url, data = download_raw(repo, sha, repo_path)
        except Exception as exc:  # noqa: BLE001 - record and keep going
            missing.append({"repo_path": repo_path, "error": str(exc)})
            continue

        local_path = support_root / repo_path
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(data)

        downloaded.append(
            {
                "repo_path": repo_path,
                "local_path": str(local_path.relative_to(ROOT)).replace("\\", "/"),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )

        nested_text = data.decode("utf-8", errors="replace")
        for nested in extract_references(nested_text, posixpath.dirname(repo_path)):
            queue.append((nested, depth + 1))

    return downloaded, missing


def next_case_number(entries):
    used = {int(entry["case_id"]) for entry in entries if entry.get("case_id", "").isdigit()}
    return max(used, default=0) + 1


def main():
    parser = argparse.ArgumentParser(description="Download requirements files pinned to commit SHAs.")
    parser.add_argument("--json", type=Path, default=INDEX_PATH, help="path to requirements_sources.json")
    parser.add_argument("--priority", help="comma-separated priorities, e.g. P0,P1")
    parser.add_argument("--repo", help="comma-separated repo substrings, e.g. vllm,deepspeed")
    parser.add_argument("--path", help="comma-separated path substrings, e.g. requirements/common")
    parser.add_argument("--tag", help="comma-separated tags, e.g. smoke")
    parser.add_argument("--ids", help="comma-separated case ids already recorded in manifest.json")
    parser.add_argument("--limit", type=int, help="maximum number of entries to download")
    parser.add_argument("--offset", type=int, default=0, help="skip the first N selected entries")
    parser.add_argument("--git-only", action="store_true", help="skip the GitHub API and use git ls-remote")
    parser.add_argument("--list", action="store_true", help="print the selection and exit")
    args = parser.parse_args()

    try:
        entries = load_index(args.json)
    except Exception as exc:  # noqa: BLE001
        print(f"[错误] {exc}")
        return 1

    manifest = load_manifest()
    manifest_entries = manifest.get("entries", [])
    selected = select_entries(entries, args, manifest_entries)

    if not selected:
        print("[系统] 没有匹配的来源。")
        return 0

    if args.list:
        print(f"[筛选] 共选中 {len(selected)} 条：")
        for entry in selected:
            print(
                f"  - {entry['priority']} {entry['repo']} :: {entry['path']} "
                f"(tags={','.join(entry.get('tags', []))})"
            )
        return 0

    REQ_DIR.mkdir(parents=True, exist_ok=True)
    by_key = {(e["repo"], e["path"]): e for e in manifest_entries}

    print(f"[系统] 准备下载 {len(selected)} 个来源，输出目录: {REQ_DIR}")
    failures = []
    for index, entry in enumerate(selected, start=1):
        repo = entry["repo"]
        path = entry["path"]
        key = (repo, path)
        print(f"\n[{index}/{len(selected)}] {repo} :: {path}")

        try:
            sha, sha_source = resolve_commit_sha(repo, git_only=args.git_only)
            raw_url, content = download_raw(repo, sha, path)
        except Exception as exc:  # noqa: BLE001 - keep the batch running
            failures.append({"repo": repo, "path": path, "error": str(exc)})
            print(f"[失败] {repo} :: {path} -> {exc}")
            continue

        existing = by_key.get(key)
        case_id = existing["case_id"] if existing else f"{next_case_number(manifest_entries):03d}"

        rewritten_text, companion_paths, removed_local = rewrite_main_file(entry, content, case_id)
        companions, missing_companions = download_companions(repo, sha, case_id, companion_paths)

        filename = f"requirements_{case_id}.txt"
        file_path = REQ_DIR / filename
        rewritten_bytes = rewritten_text.encode("utf-8")
        if rewritten_bytes == content:
            file_path.write_bytes(content)
            rewritten = False
        else:
            file_path.write_bytes(rewritten_bytes)
            rewritten = True

        record = {
            "case_id": case_id,
            "requirements_file": str(file_path.relative_to(ROOT)).replace("\\", "/"),
            "repo": repo,
            "path": path,
            "commit_sha": sha,
            "sha_source": sha_source,
            "raw_url": raw_url,
            "source_url": BLOB_URL.format(repo=repo, sha=sha, path=path),
            "priority": entry.get("priority"),
            "category": entry.get("category"),
            "tags": entry.get("tags", []),
            "curated": entry.get("curated", True),
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "bytes": len(rewritten_bytes),
            "source_bytes": len(content),
            "sha256": hashlib.sha256(rewritten_bytes).hexdigest(),
            "source_sha256": hashlib.sha256(content).hexdigest(),
            "rewritten": rewritten,
            "removed_local_references": removed_local,
            "companions": companions,
            "missing_companions": missing_companions,
        }

        if existing:
            existing.update(record)
        else:
            manifest_entries.append(record)
            by_key[key] = record

        suffix = ""
        if companions:
            suffix += f" companions={len(companions)}"
        if removed_local:
            suffix += f" removed_local={len(removed_local)}"
        if missing_companions:
            suffix += f" missing_companions={len(missing_companions)}"
        print(f"[完成] case={case_id} sha={sha[:10]} bytes={len(rewritten_bytes)}{suffix}")
        time.sleep(1)

    manifest["entries"] = manifest_entries
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n[系统] 完成。manifest: {MANIFEST_PATH}")
    print(f"[系统] 成功 {len(selected) - len(failures)} 个，失败 {len(failures)} 个。")
    for failure in failures:
        print(f"  - 失败: {failure['repo']} :: {failure['path']} -> {failure['error']}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
