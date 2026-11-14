import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Account
from app.services.accounts import create_account

API_ROOT = Path(__file__).resolve().parents[1]

# Unset: tests run on in-memory SQLite (fast, no setup).
# Set (e.g. in CI): the same tests run against a real MySQL.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def make_alembic_config() -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "migrations"))
    return config


def make_sqlite_engine() -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):  # type: ignore[no-untyped-def]
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


def migrate_to_head(engine: Engine) -> None:
    config = make_alembic_config()
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        connection.commit()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """A database whose schema is built by the real Alembic migrations."""
    if TEST_DATABASE_URL:
        db_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
        Base.metadata.drop_all(db_engine)
        with db_engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    else:
        db_engine = make_sqlite_engine()
    migrate_to_head(db_engine)
    yield db_engine
    db_engine.dispose()


@pytest.fixture(autouse=True)
def _empty_tables_after_each_test(engine: Engine) -> Iterator[None]:
    yield
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db() -> Iterator[Session]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def account_and_key(db_session: Session) -> tuple[Account, str]:
    return create_account(db_session, email="trader@example.com", label="Test", is_demo=True)


@pytest.fixture
def auth_headers(account_and_key: tuple[Account, str]) -> dict[str, str]:
    return {"X-API-Key": account_and_key[1]}


@pytest.fixture
def trade_payload() -> Callable[..., dict]:
    """Factory for a valid trade dict; override any field by keyword."""

    def build(**overrides: object) -> dict:
        trade = {
            "ticket": 1001,
            "symbol": "US30",
            "direction": "buy",
            "volume": "1.00",
            "open_time": "2026-11-02T14:30:00+00:00",
            "close_time": "2026-11-02T15:45:00+00:00",
            "open_price": "42000.50",
            "close_price": "42100.25",
            "sl": "41900.00",
            "tp": "42200.00",
            "commission": "-3.50",
            "swap": "0",
            "profit": "99.75",
            "strategy_tag": "ict-sweep",
        }
        trade.update(overrides)
        return trade

    return build
