import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.config import AppSettings, DatabaseSettings
from app.main import create_app


def make_client(origins: tuple[str, ...] = ()) -> TestClient:
    app = create_app(
        AppSettings(
            environment="test",
            log_level="CRITICAL",
            cors_origins=origins,
        ),
        DatabaseSettings(),
    )
    return TestClient(app)


def test_allowed_origin_receives_cors_header():
    with make_client(("https://frontend.example.test",)) as client:
        response = client.get(
            "/health",
            headers={"Origin": "https://frontend.example.test"},
        )

    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == "https://frontend.example.test"
    )


def test_preflight_allows_history_methods_and_headers():
    with make_client(("https://frontend.example.test",)) as client:
        response = client.options(
            "/api/transcript-segments/segment-1",
            headers={
                "Origin": "https://frontend.example.test",
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert (
        response.headers["access-control-allow-origin"]
        == "https://frontend.example.test"
    )
    assert "PATCH" in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers[
        "access-control-allow-headers"
    ].lower()


def test_unknown_origin_does_not_receive_cors_header():
    with make_client(("https://frontend.example.test",)) as client:
        response = client.get(
            "/health",
            headers={"Origin": "https://unknown.example.test"},
        )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_no_cors_header_without_configuration():
    with make_client() as client:
        response = client.get(
            "/health",
            headers={"Origin": "https://frontend.example.test"},
        )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_responses_include_security_headers():
    with make_client() as client:
        response = client.get("/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["strict-transport-security"] == "max-age=31536000"


def test_api_responses_are_not_cached():
    with make_client() as client:
        response = client.get("/api/transcription-sessions")

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"


def test_websocket_rejects_disallowed_origin():
    with make_client(("https://frontend.example.test",)) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                "/ws/transcribe",
                headers={"Origin": "https://unknown.example.test"},
            ):
                pass

    assert exc_info.value.code == 1008


def test_websocket_allows_configured_origin():
    with make_client(("https://frontend.example.test",)) as client:
        with client.websocket_connect(
            "/ws/transcribe",
            headers={"Origin": "https://frontend.example.test"},
        ) as websocket:
            message = websocket.receive_json()

    assert message["type"] == "error"
    assert message["code"] == "database_unavailable"


def test_websocket_allows_missing_origin():
    with make_client(("https://frontend.example.test",)) as client:
        with client.websocket_connect("/ws/transcribe") as websocket:
            message = websocket.receive_json()

    assert message["type"] == "error"
    assert message["code"] == "database_unavailable"
