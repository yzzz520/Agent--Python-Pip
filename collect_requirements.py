"""Stage 1: discover and index real requirements sources from GitHub.

Responsibilities (方案 A):
  - Seed requirements_sources.json once from the curated requirements_sources.md.
  - Discover new candidate repositories through the GitHub Search API.
  - Verify candidate requirements paths with raw.githubusercontent.com HEAD checks.
  - Write the machine-readable index and optionally render the Markdown view.

This script never downloads requirements content. Downloading is the job of
download_requirements.py.
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
JSON_PATH = ROOT / "requirements_sources.json"
MD_PATH = ROOT / "requirements_sources.md"

USER_AGENT = "codex-requirements-collector/1.0"
HTTP_TIMEOUT = 60
SEARCH_SLEEP = 2.0
HEAD_SLEEP = 0.2

SEARCH_URL = "https://api.github.com/search/repositories"

CANDIDATE_PATHS = [
    "requirements.txt",
    "requirements/base.txt",
    "requirements/common.txt",
    "requirements/runtime.txt",
    "requirements/requirements.txt",
    "requirements-dev.txt",
    "backend/requirements.txt",
    "api/requirements.txt",
    "python/requirements.txt",
]

DEFAULT_QUERIES = [
    {"query": "topic:llm stars:>1000", "category": "LLM/RAG"},
    {"query": "topic:rag stars:>300", "category": "LLM/RAG"},
    {"query": "topic:diffusion stars:>1000", "category": "生成式图像"},
    {"query": "topic:object-detection stars:>1000", "category": "CV/OCR"},
    {"query": "topic:web-framework language:python stars:>1000", "category": "Web/后端"},
    {"query": "topic:data-science language:python stars:>2000", "category": "数据"},
    {"query": "topic:mlops language:python stars:>500", "category": "训练/ML基建"},
]

# Entries small enough to serve as smoke tests. They are tagged in the index so
# the downloader does not need its own hardcoded target list.
SMOKE_KEYS = {
    ("microsoft/playwright-python", "requirements.txt"),
    ("encode/httpx", "requirements.txt"),
    ("tornadoweb/tornado", "requirements.txt"),
}

CATEGORY_KEYWORDS = [
    ("LLM/RAG", ["llm", "rag", "langchain", "vector", "retriev", "embedding", "transformer", "gpt", "agent"]),
    ("生成式图像", ["diffus", "stable-diffusion", "comfy", "image generation", "sd-scripts", "fooocus"]),
    ("CV/OCR", ["mmcv", "detection", "segmentation", "ocr", "yolo", "opencv", "image", "vision"]),
    ("语音", ["audio", "speech", "whisper", "tts"]),
    ("训练/ML基建", ["torch", "cuda", "deepspeed", "training", "colossal", "ray", "mlflow", "onnx", "tensorflow", "ml基建"]),
    ("Web/后端", ["django", "flask", "fastapi", "web", "http", "tornado", "celery", "erp", "superset", "后端"]),
    ("爬虫/自动化", ["scrapy", "spider", "selenium", "playwright", "automation", "crawler", "爬虫", "自动化"]),
    ("数据", ["pandas", "numpy", "data", "expectations", "数据"]),
]


def http_request(url, method="GET", accept="application/vnd.github+json"):
    request = urllib.request.Request(
        url,
        method=method,
        headers={"User-Agent": USER_AGENT, "Accept": accept},
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        return response.status, response.read()


def guess_category(repo, path, kind, risk):
    haystack = " ".join([repo, path, kind, risk]).lower()
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return category
    return "其它"


def parse_md_entries(md_text):
    entries = []
    notes = []
    in_stats = False

    for raw_line in md_text.splitlines():
        line = raw_line.strip()
        if line.startswith("## 统计"):
            in_stats = True
            continue
        if in_stats:
            if line.startswith("- ") and "合计" not in line and "P0` 共" not in line and "覆盖方向" not in line:
                notes.append(line)
            continue
        if not line.startswith("|") or set(line) <= set("|-: "):
            continue

        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 7:
            continue

        repo_match = re.search(r"\[([^\]]+)\]\(https://github\.com/([^)]+)\)", cells[1])
        path_match = re.search(r"`([^`]+)`", cells[2])
        raw_match = re.search(r"\[raw\]\(([^)]+)\)", " | ".join(cells))
        priority_match = re.search(r"\bP[0-2]\b", " | ".join(cells))
        if not (repo_match and path_match and priority_match):
            continue

        repo = repo_match.group(2)
        path = path_match.group(1)
        kind = cells[3]
        risk = cells[4]
        priority = priority_match.group(0)
        raw_url = raw_match.group(1) if raw_match else (
            f"https://raw.githubusercontent.com/{repo}/HEAD/{path}"
        )

        entries.append(
            {
                "repo": repo,
                "path": path,
                "kind": kind,
                "risk": risk,
                "priority": priority,
                "category": guess_category(repo, path, kind, risk),
                "tags": ["smoke"] if (repo, path) in SMOKE_KEYS else [],
                "curated": True,
                "raw_url": raw_url,
                "verified_at": None,
                "stars": None,
                "default_branch": None,
                "discovery_source": "requirements_sources.md",
            }
        )
    return entries, notes


def load_index():
    if JSON_PATH.exists():
        return json.loads(JSON_PATH.read_text(encoding="utf-8"))
    return None


def save_index(entries, notes, extra=None):
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_index": "requirements_sources.md",
        "notes": notes,
        "entries": entries,
    }
    if extra:
        payload.update(extra)
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def search_repositories(query, per_page):
    params = urllib.parse.urlencode(
        {"q": query, "sort": "stars", "order": "desc", "per_page": per_page}
    )
    url = f"{SEARCH_URL}?{params}"
    try:
        status, body = http_request(url)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"GitHub search {exc.code}: {detail}") from exc
    if status != 200:
        raise RuntimeError(f"GitHub search returned status {status}")
    return json.loads(body.decode("utf-8")).get("items", [])


def head_status(repo, branch, path):
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
    try:
        status, _ = http_request(url, method="HEAD", accept="text/plain")
        return status, url
    except urllib.error.HTTPError as exc:
        return exc.code, url
    except urllib.error.URLError:
        return None, url


def discover(entries, queries, per_query, max_new):
    known = {(entry["repo"], entry["path"]) for entry in entries}
    added = []

    for query_spec in queries:
        query = query_spec["query"]
        category = query_spec["category"]
        print(f"[搜索] {query}")
        try:
            repos = search_repositories(query, per_query)
        except Exception as exc:  # noqa: BLE001 - keep other queries running
            print(f"[跳过] {query} -> {exc}")
            time.sleep(SEARCH_SLEEP)
            continue

        for item in repos:
            repo = item.get("full_name")
            if not repo:
                continue
            branch = item.get("default_branch") or "HEAD"

            for path in CANDIDATE_PATHS:
                status, url = head_status(repo, branch, path)
                time.sleep(HEAD_SLEEP)
                if status != 200:
                    continue
                if (repo, path) in known:
                    break

                stars = item.get("stargazers_count")
                if stars is None:
                    priority = "P2"
                elif stars >= 5000:
                    priority = "P0"
                elif stars >= 1000:
                    priority = "P1"
                else:
                    priority = "P2"

                entry = {
                    "repo": repo,
                    "path": path,
                    "kind": "运行时",
                    "risk": "自动发现 / 未人工复核",
                    "priority": priority,
                    "category": category,
                    "tags": [],
                    "curated": False,
                    "raw_url": url,
                    "verified_at": datetime.now(timezone.utc).isoformat(),
                    "stars": stars,
                    "default_branch": branch,
                    "discovery_source": f"github-search: {query}",
                }
                entries.append(entry)
                known.add((repo, path))
                added.append(entry)
                print(f"[新增] {repo} :: {path} ({priority}, stars={stars})")
                break

            if len(added) >= max_new:
                return added

        time.sleep(SEARCH_SLEEP)

    return added


def parse_source(value):
    """Parse a GitHub URL or owner/repo shorthand into (repo, path, branch)."""
    value = value.strip()
    if value.startswith("https://github.com/"):
        parts = value[len("https://github.com/"):].strip("/").split("/")
        if len(parts) >= 2:
            repo = f"{parts[0]}/{parts[1]}"
            if len(parts) >= 5 and parts[2] == "blob":
                return repo, "/".join(parts[4:]), parts[3]
            if len(parts) == 2:
                return repo, None, None
        raise ValueError("只支持 github.com/{owner}/{repo} 或 /blob/{branch}/{path} 形式")

    if value.startswith("https://raw.githubusercontent.com/"):
        parts = value[len("https://raw.githubusercontent.com/"):].strip("/").split("/")
        if len(parts) >= 4:
            return f"{parts[0]}/{parts[1]}", "/".join(parts[3:]), parts[2]
        raise ValueError("raw 链接格式不完整")

    if re.fullmatch(r"[\w.-]+/[\w.-]+", value):
        return value, None, None

    raise ValueError("无法识别的链接格式")


def add_sources(entries, raw_sources, priority, category, kind, risk, tags):
    known = {(entry["repo"], entry["path"]) for entry in entries}
    added = []

    for raw_source in raw_sources:
        try:
            repo, path, branch = parse_source(raw_source)
        except ValueError as exc:
            print(f"[跳过] {raw_source} -> {exc}")
            continue

        branch = branch or "HEAD"
        candidates = [path] if path else CANDIDATE_PATHS
        hit = None
        for candidate in candidates:
            status, url = head_status(repo, branch, candidate)
            time.sleep(HEAD_SLEEP)
            if status == 200:
                hit = (candidate, url)
                break

        if hit is None:
            print(f"[失败] {raw_source} -> 未找到可用的 requirements 路径")
            continue

        candidate_path, raw_url = hit
        if (repo, candidate_path) in known:
            print(f"[跳过] {repo} :: {candidate_path} 已在索引中")
            continue

        entry_kind = kind or "运行时"
        entry_risk = risk or "人工指定 / 待复核"
        entry = {
            "repo": repo,
            "path": candidate_path,
            "kind": entry_kind,
            "risk": entry_risk,
            "priority": priority or "P1",
            "category": category or guess_category(repo, candidate_path, entry_kind, entry_risk),
            "tags": tags or [],
            "curated": True,
            "raw_url": raw_url,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "stars": None,
            "default_branch": branch,
            "discovery_source": f"manual-add: {raw_source}",
        }
        entries.append(entry)
        known.add((repo, candidate_path))
        added.append(entry)
        print(f"[新增] {repo} :: {candidate_path} ({entry['priority']})")

    return added


def render_md(entries, notes):
    curated = [e for e in entries if e.get("curated", True)]
    auto = [e for e in entries if not e.get("curated", True)]
    ordered = curated + sorted(auto, key=lambda e: -(e.get("stars") or 0))

    lines = [
        "# GitHub requirements 来源索引",
        "",
        "本文件由 `collect_requirements.py` 生成，机器可读版本见 `requirements_sources.json`。",
        "",
        "- 人工条目：来自最初手工核验的 `P0/P1/P2` 清单，`curated=true`。",
        "- 自动条目：来自 GitHub Search API + raw HEAD 校验，`curated=false`，使用前建议人工复核。",
        "- 优先级：`P0` 优先入数据集；`P1` 次之；`P2` 作为补充或负样本。",
        "",
        f"生成时间：`{datetime.now(timezone.utc).isoformat()}`",
        "",
        "| # | 仓库 | 文件 | 类型 | 风险 / 价值标签 | 优先级 | 来源 | 抓取地址 |",
        "|---|------|------|------|------------------|--------|------|----------|",
    ]

    for index, entry in enumerate(ordered, start=1):
        repo = entry["repo"]
        path = entry["path"]
        source = "人工" if entry.get("curated", True) else "自动"
        raw_url = entry["raw_url"]
        lines.append(
            f"| {index} | [{repo}](https://github.com/{repo}) | `{path}` | "
            f"{entry['kind']} | {entry['risk']} | {entry['priority']} | {source} | "
            f"[raw]({raw_url}) |"
        )

    p0 = sum(1 for e in ordered if e["priority"] == "P0")
    p1 = sum(1 for e in ordered if e["priority"] == "P1")
    p2 = sum(1 for e in ordered if e["priority"] == "P2")
    lines.extend(
        [
            "",
            "## 统计",
            "",
            f"- 合计 `{len(ordered)}` 条来源：`curated=true` {len(curated)} 条，`curated=false` {len(auto)} 条。",
            f"- `P0` 共 `{p0}` 条，`P1` 共 `{p1}` 条，`P2` 共 `{p2}` 条。",
        ]
    )
    lines.extend(notes)
    MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Discover and index requirements sources.")
    parser.add_argument("--seed-only", action="store_true", help="migrate requirements_sources.md -> .json and exit")
    parser.add_argument("--discover", action="store_true", help="run GitHub repository discovery")
    parser.add_argument("--render-md", action="store_true", help="regenerate requirements_sources.md from the index")
    parser.add_argument("--per-query", type=int, default=5, help="repositories inspected per search query")
    parser.add_argument("--max-new", type=int, default=10, help="maximum new entries added per run")
    parser.add_argument("--add-url", action="append", default=[], help="manually add a GitHub URL or owner/repo")
    parser.add_argument("--priority", help="priority override for manual additions, e.g. P0")
    parser.add_argument("--category", help="category override for manual additions")
    parser.add_argument("--kind", help="kind override for manual additions")
    parser.add_argument("--risk", help="risk label override for manual additions")
    parser.add_argument("--tag", action="append", default=[], help="tag for manual additions, repeatable")
    args = parser.parse_args()

    index = load_index()
    if index is None:
        if not MD_PATH.exists():
            print(f"[错误] 找不到 {MD_PATH}，无法初始化索引。")
            return 1
        entries, notes = parse_md_entries(MD_PATH.read_text(encoding="utf-8"))
        index = save_index(entries, notes)
        print(f"[初始化] 从 md 迁移 {len(entries)} 条来源到 {JSON_PATH.name}")
    else:
        entries = index.get("entries", [])
        notes = index.get("notes", [])
        print(f"[索引] 读取 {len(entries)} 条来源")

    if args.seed_only:
        print("[完成] seed-only 模式，不执行发现。")
        return 0

    manual_sources = [
        item.strip()
        for group in args.add_url
        for item in group.split(",")
        if item.strip()
    ]
    if manual_sources:
        added = add_sources(
            entries,
            manual_sources,
            priority=args.priority,
            category=args.category,
            kind=args.kind,
            risk=args.risk,
            tags=args.tag,
        )
        print(f"[手动] 本次新增 {len(added)} 条")
        save_index(entries, notes)

    if args.discover:
        added = discover(entries, DEFAULT_QUERIES, args.per_query, args.max_new)
        print(f"[发现] 本次新增 {len(added)} 条")
        save_index(entries, notes)

    if args.render_md:
        render_md(entries, notes)
        print(f"[渲染] 已更新 {MD_PATH.name}")

    print(f"[汇总] 索引中共 {len(entries)} 条来源")
    return 0


if __name__ == "__main__":
    sys.exit(main())
