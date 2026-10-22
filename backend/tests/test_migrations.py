from collections.abc import Callable
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.models import Base


def sqlite_url_for(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.as_posix()}"


def test_sqlite_migration_round_trip(
    tmp_path: Path,
    alembic_config_factory: Callable[[str | None], Config],
) -> None:
    url = sqlite_url_for(tmp_path / "migration.db")
    config = alembic_config_factory(url)

    command.upgrade(config, "head")

    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        assert "transcripts" in inspector.get_table_names()

        columns = {
            column["name"]: column
            for column in inspector.get_columns("transcripts")
        }
        assert set(columns) == {
            "id",
            "session_id",
            "sequence",
            "text",
            "language_code",
            "created_at",
        }
        assert columns["id"]["nullable"] is False
        assert columns["session_id"]["nullable"] is False
        assert columns["sequence"]["nullable"] is False
        assert columns["text"]["nullable"] is False
        assert columns["language_code"]["nullable"] is True
        assert columns["created_at"]["nullable"] is False

        unique_constraints = {
            item["name"]
            for item in inspector.get_unique_constraints("transcripts")
        }
        assert "uq_transcripts_session_sequence" in unique_constraints

        check_constraints = {
            item["name"]
            for item in inspector.get_check_constraints("transcripts")
        }
        assert {
            "ck_transcripts_sequence_non_negative",
            "ck_transcripts_text_not_blank",
        }.issubset(check_constraints)

        indexes = {
            item["name"] for item in inspector.get_indexes("transcripts")
        }
        assert "ix_transcripts_session_created_at" in indexes
    finally:
        engine.dispose()

    command.downgrade(config, "base")

    engine = create_engine(url)
    try:
        assert "transcripts" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_models_match_initial_migration_table_name() -> None:
    assert Base.metadata.tables["transcripts"].name == "transcripts"
