"""SQLAlchemy engine/session wiring.

Deliberately SQLite for the MVP; swapping to PostgreSQL means changing
DATABASE_URL and nothing else, because every query goes through the repository.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    pass


def _engine_kwargs() -> dict:
    url = settings.resolved_database_url
    if url.startswith("sqlite"):
        # FastAPI serves requests from a thread pool; SQLite needs this flag.
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True}


engine = create_engine(settings.resolved_database_url, **_engine_kwargs())
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    from app.db import models  # noqa: F401  (registers mappers)

    Base.metadata.create_all(engine)


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
