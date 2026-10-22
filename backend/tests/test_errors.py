from fastapi.testclient import TestClient

from app.config import AppSettings
from app.main import create_app


def test_not_found_uses_detail_shape(client):
    response = client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_unhandled_exception_returns_generic_detail():
    app = create_app(
        AppSettings(environment="test", log_level="CRITICAL")
    )

    @app.get("/boom")
    async def boom():
        raise RuntimeError("sensitive internal detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "sensitive internal detail" not in response.text
