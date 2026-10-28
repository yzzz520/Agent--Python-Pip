"""Pytest bootstrap.

Environment variables must be set *before* ``backend`` is imported, because the
engine and the DB path are resolved at import time.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="pipattr-tests-"))
os.environ["PIPATTR_DB"] = str(_TMP / "test.db")
os.environ["PIPATTR_AUTOSEED"] = "0"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    from backend.db import SessionLocal, init_db
    from backend.ingest import sync_all
    from backend.main import app

    init_db()
    with SessionLocal() as session:
        counts = sync_all(session)
    assert counts["cases"] > 0, "no case artifacts found; run the dataset pipeline first"

    with TestClient(app) as test_client:
        yield test_client
