"""Runtime configuration.

Every path comes from an environment variable so the same code runs locally,
inside Docker, and in tests without edits:

    PIPATTR_DATA_DIR   root of the dataset (default: repository root)
    PIPATTR_DB         sqlite file path (default: <data dir>/backend/data/pipattr.db)
    PIPATTR_AUTOSEED   "1" (default) seeds an empty database on startup
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# The offline scripts live at the repository root; make them importable no
# matter which directory uvicorn is started from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = Path(os.environ.get("PIPATTR_DATA_DIR", str(PROJECT_ROOT))).resolve()
DB_PATH = Path(
    os.environ.get("PIPATTR_DB", str(DATA_DIR / "backend" / "data" / "pipattr.db"))
).resolve()
AUTOSEED = os.environ.get("PIPATTR_AUTOSEED", "1") == "1"

CASE_ID_RE = re.compile(r"^\d{1,4}$")


def normalize_case_id(value: str) -> str:
    """Normalize ``8`` / ``008`` / ``0008`` to ``008``.

    Raises:
        ValueError: when the value is not purely numeric.
    """

    text = str(value).strip()
    if not CASE_ID_RE.match(text):
        raise ValueError(f"invalid case id: {value!r}")
    return f"{int(text):03d}"


def ensure_dirs() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def rel(path: Path) -> str:
    """Store paths relative to the data root so the database stays portable."""

    try:
        return path.relative_to(DATA_DIR).as_posix()
    except ValueError:
        return str(path)
