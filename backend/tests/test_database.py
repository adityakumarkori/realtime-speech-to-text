import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import AppSettings, DatabaseSettings
from app.database import Database, DatabaseUnavailableError
from app.main import create_app


def sqlite_url_for(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.as_posix()}"


def test_unconfigured_database_is_disabled(caplog):
    database = Database(DatabaseSettings())

    with caplog.at_level(logging.WARNING):
        database.start()

    assert database.is_configured is False
    assert "DATABASE_URL is not set" in caplog.text
    with pytest.raises(DatabaseUnavailableError):
        with database.session_scope():
            pass


def test_database_start_and_dispose_are_idempotent(tmp_path):
    database = Database(
        DatabaseSettings(url=sqlite_url_for(tmp_path / "database.db"))
    )

    database.start()
    database.start()
    assert database.is_configured is True

    database.dispose()
    database.dispose()
    assert database.is_configured is False


def test_app_starts_degraded_without_database(caplog):
    app = create_app(
        AppSettings(environment="test", log_level="WARNING"),
        DatabaseSettings(),
    )

    with caplog.at_level(logging.WARNING):
        with TestClient(app) as client:
            response = client.get("/health")
            assert app.state.database.is_configured is False

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "transcript persistence is disabled" in caplog.text


def test_app_manages_configured_database_lifecycle(tmp_path):
    app = create_app(
        AppSettings(environment="test", log_level="WARNING"),
        DatabaseSettings(url=sqlite_url_for(tmp_path / "lifecycle.db")),
    )

    with TestClient(app) as client:
        assert app.state.database.is_configured is True
        assert client.get("/health").status_code == 200

    assert app.state.database.is_configured is False
