"""Database bootstrap and session management.

Defaults to a local SQLite database under ``data/core/evolution.db`` but can
be overridden via the ``DATABASE_URL`` environment variable.

This module is intentionally light so it can be swapped out for Postgres or
another backend without touching pipeline/job code.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.ingestion.schemas import Base


def get_database_url() -> str:
    """Return the database URL.

    Priority:
    1. ``DATABASE_URL`` env var
    2. fallback to local SQLite file in ``data/core/evolution.db``
    """

    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url

    # Ensure directory exists for SQLite file
    base_dir = os.path.join(os.getcwd(), "data", "core")
    os.makedirs(base_dir, exist_ok=True)
    return f"sqlite:///{os.path.join(base_dir, 'evolution.db')}"


ENGINE = create_engine(
    get_database_url(),
    future=True,
)

SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False, class_=Session)


def init_db() -> None:
    """Create all tables defined on the SQLAlchemy Base.

    This is safe to call multiple times.
    """

    Base.metadata.create_all(bind=ENGINE)


@contextmanager
def get_session() -> Iterator[Session]:
    """Provide a transactional session scope.

    Usage::

        with get_session() as session:
            ...
    """

    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:  # pragma: no cover - standard rollback pattern
        session.rollback()
        raise
    finally:
        session.close()

