from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import AppSettings
from app.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app(
        AppSettings(environment="test", log_level="WARNING")
    )
    with TestClient(app) as test_client:
        yield test_client
