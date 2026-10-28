"""ASGI entry point: ``uvicorn backend.main:app --reload``."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select

from . import __version__, config
from .db import SessionLocal, init_db
from .models import AttributionReport, Case
from .routers import cases, jobs, labels, stats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("pipattr")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()

    if config.AUTOSEED:
        with SessionLocal() as session:
            case_count = session.scalar(select(func.count()).select_from(Case)) or 0
            if case_count == 0:
                from .ingest import sync_all

                logger.info("empty database, ingesting %s", config.DATA_DIR)
                counts = sync_all(session)
                logger.info("ingested %s", counts)

    yield


app = FastAPI(
    title="Pip Failure Attribution API",
    version=__version__,
    description=(
        "Backend for the pip/requirements failure attribution dataset: "
        "cases, three attribution approaches (rule / single-step LLM / tool-using agent), "
        "golden labels, install-level verifications and asynchronous re-runs."
    ),
    lifespan=lifespan,
)

# The service is read-mostly and runs behind its own origin; widen this once a
# real frontend is deployed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cases.router)
app.include_router(labels.router)
app.include_router(stats.router)
app.include_router(jobs.router)


@app.get("/", tags=["ops"], summary="Service index")
def index() -> dict[str, object]:
    return {
        "service": "pip-failure-attribution-api",
        "version": __version__,
        "docs": "/docs",
        "endpoints": [
            "/api/cases",
            "/api/cases/{case_id}",
            "/api/cases/{case_id}/log",
            "/api/cases/{case_id}/patch",
            "/api/cases/{case_id}/jobs",
            "/api/jobs",
            "/api/jobs/{job_id}",
            "/api/labels",
            "/api/labels/{case_id}",
            "/api/stats",
            "/healthz",
        ],
    }


@app.get("/healthz", tags=["ops"], summary="Liveness plus row counts")
def healthz() -> dict[str, object]:
    with SessionLocal() as session:
        case_count = session.scalar(select(func.count()).select_from(Case)) or 0
        report_count = (
            session.scalar(select(func.count()).select_from(AttributionReport)) or 0
        )
    return {
        "status": "ok",
        "cases": case_count,
        "reports": report_count,
        "data_dir": str(config.DATA_DIR),
        "db": str(config.DB_PATH),
    }
