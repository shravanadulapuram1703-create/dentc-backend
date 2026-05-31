"""Engine, session factory, and the ``get_db`` FastAPI dependency.

The session is synchronous (psycopg2). Tenancy is enforced at the query level via
``tenant_id`` columns (see :mod:`app.api.deps`), NOT via ``SET search_path`` — the
migrated data lives entirely in the ``public`` schema.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine: Engine = create_engine(
    settings.sqlalchemy_database_uri,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
    echo=settings.DB_ECHO,
    future=True,
)


@event.listens_for(engine, "connect")
def _set_session_timeouts(dbapi_conn, _record) -> None:  # noqa: ANN001
    """Guard against runaway queries / idle-in-transaction locks."""
    with dbapi_conn.cursor() as cur:
        cur.execute(f"SET statement_timeout = {settings.DB_STATEMENT_TIMEOUT_MS}")
        cur.execute("SET idle_in_transaction_session_timeout = 60000")


SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    future=True,
)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
