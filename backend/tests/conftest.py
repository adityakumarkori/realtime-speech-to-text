from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.config import AppSettings, DatabaseSettings
from app.database import Database
from app.main import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = PROJECT_ROOT / "backend" / "alembic.ini"


def sqlite_url_for(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.as_posix()}"


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app(
        AppSettings(environment="test", log_level="WARNING"),
        DatabaseSettings(),
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def alembic_config_factory() -> Callable[[str | None], Config]:
    def factory(url: str | None) -> Config:
        config = Config(str(ALEMBIC_INI))
        if url is not None:
            config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
        return config

    return factory


@pytest.fixture
def migrated_sqlite_url(
    tmp_path: Path,
    alembic_config_factory: Callable[[str | None], Config],
) -> str:
    url = sqlite_url_for(tmp_path / "transcripts.db")
    command.upgrade(alembic_config_factory(url), "head")
    return url


@pytest.fixture
def sqlite_database(migrated_sqlite_url: str) -> Iterator[Database]:
    database = Database(DatabaseSettings(url=migrated_sqlite_url))
    database.start()
    try:
        yield database
    finally:
        database.dispose()
