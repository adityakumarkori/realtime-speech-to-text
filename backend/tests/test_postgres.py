import os
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy import Connection, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, IntegrityError
from sqlalchemy.pool import NullPool

from app.models import Transcript

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def _environment_value(name: str) -> str:
    value = os.environ.get(name)
    if value is None and ENV_FILE.is_file():
        value = dotenv_values(ENV_FILE).get(name)
    return (value or "").strip()


def _postgres_test_url() -> str:
    raw_url = _environment_value("TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("TEST_DATABASE_URL is not set.")

    try:
        test_url = make_url(raw_url)
    except ArgumentError:
        pytest.fail("TEST_DATABASE_URL is not a valid SQLAlchemy URL.")

    if test_url.drivername != "postgresql+psycopg":
        pytest.fail("TEST_DATABASE_URL must use postgresql+psycopg.")

    if "test" not in (test_url.database or "").lower():
        pytest.fail(
            "TEST_DATABASE_URL must target a dedicated test database."
        )

    runtime_url = _environment_value("DATABASE_URL")
    if runtime_url:
        try:
            parsed_runtime_url = make_url(runtime_url)
        except ArgumentError:
            parsed_runtime_url = None
        if parsed_runtime_url is not None and parsed_runtime_url == test_url:
            pytest.fail("TEST_DATABASE_URL must differ from DATABASE_URL.")

    return raw_url


@pytest.fixture
def postgres_schema() -> Iterator[tuple[Connection, str]]:
    engine = create_engine(_postgres_test_url(), poolclass=NullPool)
    schema = f"phase2_test_{uuid.uuid4().hex}"
    connection = None

    try:
        connection = engine.connect()
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.commit()
        connection.execute(text(f'SET search_path TO "{schema}"'))
        connection.commit()
        yield connection, schema
    finally:
        if connection is not None:
            try:
                connection.rollback()
                connection.execute(
                    text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                )
                connection.commit()
            finally:
                connection.close()
        engine.dispose()


@pytest.mark.postgres
def test_postgres_migration_round_trip(
    postgres_schema: tuple[Connection, str],
    alembic_config_factory: Callable[[str | None], Config],
) -> None:
    connection, schema = postgres_schema
    config = alembic_config_factory(None)
    config.attributes["connection"] = connection

    command.upgrade(config, "head")
    if connection.in_transaction():
        connection.commit()

    inspector = inspect(connection)
    assert "transcripts" in inspector.get_table_names(schema=schema)

    unique_constraints = {
        item["name"]
        for item in inspector.get_unique_constraints(
            "transcripts",
            schema=schema,
        )
    }
    assert "uq_transcripts_session_sequence" in unique_constraints

    check_constraints = {
        item["name"]
        for item in inspector.get_check_constraints(
            "transcripts",
            schema=schema,
        )
    }
    assert {
        "ck_transcripts_sequence_non_negative",
        "ck_transcripts_text_not_blank",
    }.issubset(check_constraints)

    indexes = {
        item["name"]
        for item in inspector.get_indexes("transcripts", schema=schema)
    }
    assert "ix_transcripts_session_created_at" in indexes

    insert_statement = Transcript.__table__.insert().values(
        id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        sequence=0,
        text="Hello.",
        language_code="en-IN",
    )
    connection.execute(insert_statement)
    connection.commit()

    row = connection.execute(
        text(
            "SELECT text, language_code, created_at "
            "FROM transcripts"
        )
    ).one()
    assert row.text == "Hello."
    assert row.language_code == "en-IN"
    assert row.created_at is not None

    with pytest.raises(IntegrityError):
        with connection.begin_nested():
            connection.execute(insert_statement)
    connection.rollback()

    command.downgrade(config, "base")
    if connection.in_transaction():
        connection.commit()

    assert "transcripts" not in inspect(connection).get_table_names(
        schema=schema
    )
