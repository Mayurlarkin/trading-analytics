from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Base class for all ORM models (added in Phase 1)."""


@lru_cache
def get_engine() -> Engine:
    # pool_pre_ping avoids stale-connection errors after the DB restarts.
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a DB session and always closes it."""
    session = _session_factory()()
    try:
        yield session
    finally:
        session.close()
