"""CLI: load every artifact on disk into the database.

Usage:
    python -m backend.seed

Re-running is safe: every row is upserted by key.
"""

from __future__ import annotations

import json

from .db import SessionLocal, init_db
from .ingest import sync_all


def main() -> int:
    init_db()
    with SessionLocal() as session:
        counts = sync_all(session)
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
