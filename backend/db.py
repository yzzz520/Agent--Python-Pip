"""Database engine, session factory and declarative base."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from . import config


class Base(DeclarativeBase):
    """Declarative base shared by every model."""


config.ensure_dirs()

# SQLite is enough for a single-process demo service; check_same_thread=False
# lets the job worker thread reuse the same engine.
engine = create_engine(
    f"sqlite:///{config.DB_PATH.as_posix()}",
    connect_args={"check_same_thread": False},
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """Create missing tables. Safe to call on every process start."""

    from . import models  # noqa: F401  (import registers the mappings)

    Base.metadata.create_all(bind=engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""

    with SessionLocal() as session:
        yield session
