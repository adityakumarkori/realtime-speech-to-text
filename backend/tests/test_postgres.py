import os
import uuid
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy import Connection, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.models import Transcript
from app.repositories import TranscriptRepository

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

@pytest.mark.postgres
def test_postgres_history_queries(
    postgres_schema: tuple[Connection, str],
    alembic_config_factory: Callable[[str | None], Config],
) -> None:
    connection, _schema = postgres_schema
    config = alembic_config_factory(None)
    config.attributes["connection"] = connection

    command.upgrade(config, "head")
    if connection.in_transaction():
        connection.commit()

    first_session = uuid.uuid4()
    second_session = uuid.uuid4()
    base_time = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
    first_segment = Transcript(
        session_id=first_session,
        sequence=0,
        text="Project kickoff.",
        language_code="en-IN",
        created_at=base_time,
    )
    second_segment = Transcript(
        session_id=first_session,
        sequence=1,
        text="Follow-up notes.",
        language_code="hi-IN",
        created_at=base_time + timedelta(minutes=1),
    )
    other_segment = Transcript(
        session_id=second_session,
        sequence=0,
        text="Another session.",
        created_at=base_time + timedelta(hours=1),
    )

    repository = TranscriptRepository()
    with Session(bind=connection) as session:
        session.add_all([first_segment, second_segment, other_segment])
        session.commit()

        page = repository.list_sessions(
            session,
            limit=10,
            offset=0,
            search="PROJECT",
        )
        assert page.total == 1
        summary = page.sessions[0]
        assert summary.session_id == first_session
        assert summary.segment_count == 2
        assert summary.preview == "Project kickoff."
        assert summary.language_codes == ("en-IN", "hi-IN")
        assert summary.started_at == base_time
        assert summary.ended_at == base_time + timedelta(minutes=1)

        updated = repository.update_text(
            session,
            first_segment.id,
            "Project kickoff edited.",
        )
        session.commit()
        assert updated is not None
        assert updated.text == "Project kickoff edited."

        assert repository.delete_session(session, first_session) == 2
        session.commit()
        assert repository.list_for_session(session, first_session) == []
        assert (
            repository.list_for_session(session, second_session)[0].text
            == "Another session."
        )
