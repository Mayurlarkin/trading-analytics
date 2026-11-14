"""Migrations are the source of truth for the schema; keep them in step with the models."""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect

from app.db import Base
from tests.conftest import make_alembic_config, make_sqlite_engine, migrate_to_head


@pytest.fixture
def migrated_sqlite() -> Iterator[Engine]:
    """A fresh in-memory SQLite database, independent of the shared test database."""
    engine = make_sqlite_engine()
    migrate_to_head(engine)
    yield engine
    engine.dispose()


def test_migrations_produce_the_schema_the_models_describe(migrated_sqlite: Engine) -> None:
    with migrated_sqlite.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []


def test_downgrade_to_base_removes_every_table(migrated_sqlite: Engine) -> None:
    config = make_alembic_config()
    with migrated_sqlite.connect() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
        connection.commit()
        assert set(inspect(connection).get_table_names()) <= {"alembic_version"}
