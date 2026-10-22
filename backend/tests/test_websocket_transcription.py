import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.config import AppSettings, DatabaseSettings
from app.live import (
    LiveEvent,
    LiveSessionError,
    LiveSummary,
    LiveTranscriptionRunner,
)
from app.main import create_app
from app.routes import transcription as transcription_module
from app.services import Transcript
from poc.transcripts import TranscriptEvent


class FakeTranscriptService:
    def __init__(self):
        self.recorded: list[tuple[uuid.UUID, int, str]] = []

    def record_final_segment(
        self,
        *,
        session_id: uuid.UUID,
        sequence: int,
        text: str,
        language_code: str | None = None,
    ) -> Transcript:
        self.recorded.append((session_id, sequence, text))
        return Transcript(
            id=len(self.recorded),
            session_id=session_id,
            sequence=sequence,
            text=text,
            language_code=language_code,
            created_at=None,
        )


class FakeDatabase:
    def __init__(self, configured: bool = True):
        self._configured = configured

    @property
    def is_configured(self) -> bool:
        return self._configured


class FakeSettings:
    def __init__(self, api_key: str = "test-key", model: str = "test-model"):
        self.api_key = api_key
        self.model = model


class FakeRunner:
    def __init__(
        self,
        should_fail: bool = False,
        fail_code: str = "upstream_error",
        fail_before_events: bool = False,
    ):
        self.should_fail = should_fail
        self.fail_code = fail_code
        self.fail_before_events = fail_before_events
        self.run_called = False
        self.language_codes: list[str] | None = None

    async def run(
        self,
        *,
        session_id,
        chunks,
        language_codes,
        on_ready,
        on_event,
    ) -> LiveSummary:
        self.run_called = True
        self.language_codes = list(language_codes)
        await on_ready()

        if self.fail_before_events:
            raise LiveSessionError(
                code=self.fail_code,
                message="Test failure",
                close_code=1011,
                session_id=session_id,
            )

        emitted = False
        async for _ in chunks:
            if not emitted:
                await on_event(LiveEvent(kind="interim", text="interim text"))
                await on_event(
                    LiveEvent(kind="final", text="final text", sequence=0)
                )
                emitted = True

        if self.should_fail:
            raise LiveSessionError(
                code=self.fail_code,
                message="Test failure",
                close_code=1011,
                session_id=session_id,
            )

        return LiveSummary(
            interim_count=1 if emitted else 0,
            final_count=1 if emitted else 0,
        )


@pytest.fixture
def client_factory():
    clients: list[TestClient] = []

    def create(runner: FakeRunner | LiveTranscriptionRunner) -> TestClient:
        app = create_app(
            settings=AppSettings(),
            database_settings=DatabaseSettings(),
            live_runner=runner,
        )
        client = TestClient(app)
        clients.append(client)
        return client

    yield create

    for client in clients:
        client.close()


@pytest.fixture
def fake_runner() -> FakeRunner:
    return FakeRunner()


@pytest.fixture
def client(client_factory, fake_runner) -> TestClient:
    return client_factory(fake_runner)


def assert_close_code(ws, expected: int) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        ws.receive_json()
    assert exc_info.value.code == expected


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_websocket_ready_then_interim_final_completed(client, fake_runner):
    with client.websocket_connect("/ws/transcribe") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"
        assert "session_id" in ready
        assert ready["audio"]["encoding"] == "pcm_s16le"
        assert ready["audio"]["sample_rate_hz"] == 16000

        ws.send_bytes(b"\x00" * 3200)

        interim = ws.receive_json()
        assert interim["type"] == "interim"
        assert interim["text"] == "interim text"

        final = ws.receive_json()
        assert final["type"] == "final"
        assert final["sequence"] == 0
        assert final["text"] == "final text"

        ws.send_text('{"type":"stop"}')

        completed = ws.receive_json()
        assert completed["type"] == "completed"
        assert completed["final_count"] == 1
        assert completed["reason"] == "client_stop"
        assert_close_code(ws, 1000)


def test_websocket_invalid_audio_empty_frame(client_factory):
    client = client_factory(FakeRunner())

    with client.websocket_connect("/ws/transcribe") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"

        ws.send_bytes(b"")

        error = ws.receive_json()
        assert error["type"] == "error"
        assert error["code"] == "invalid_audio"
        assert error["message"] == "Empty audio frame"
        assert_close_code(ws, 1007)


def test_websocket_invalid_audio_odd_length(client_factory):
    client = client_factory(FakeRunner())

    with client.websocket_connect("/ws/transcribe") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"

        ws.send_bytes(b"\x00" * 3201)

        error = ws.receive_json()
        assert error["type"] == "error"
        assert error["code"] == "invalid_audio"
        assert "even" in error["message"].lower()
        assert_close_code(ws, 1007)


def test_websocket_invalid_audio_oversized(client_factory):
    client = client_factory(FakeRunner())

    with client.websocket_connect("/ws/transcribe") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"

        ws.send_bytes(b"\x00" * 32002)

        error = ws.receive_json()
        assert error["type"] == "error"
        assert error["code"] == "invalid_audio"
        assert "exceeds maximum size" in error["message"]
        assert_close_code(ws, 1009)


def test_websocket_invalid_text_message(client_factory):
    client = client_factory(FakeRunner())

    with client.websocket_connect("/ws/transcribe") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"

        ws.send_text('{"type":"unknown"}')

        error = ws.receive_json()
        assert error["type"] == "error"
        assert error["code"] == "invalid_message"
        assert "unknown" not in error["message"]
        assert_close_code(ws, 1003)


def test_websocket_invalid_language_codes(client):
    with client.websocket_connect(
        "/ws/transcribe?language_codes=invalid code"
    ) as ws:
        error = ws.receive_json()
        assert error["type"] == "error"
        assert error["code"] == "invalid_configuration"
        assert "Invalid language code" in error["message"]
        assert_close_code(ws, 1008)


def test_websocket_database_unavailable_error(client_factory):
    runner = LiveTranscriptionRunner(
        transcript_service=FakeTranscriptService(),
        database=FakeDatabase(configured=False),
        settings_loader=FakeSettings,
    )
    client = client_factory(runner)

    with client.websocket_connect("/ws/transcribe") as ws:
        error = ws.receive_json()
        assert error["type"] == "error"
        assert error["code"] == "database_unavailable"
        assert isinstance(error["session_id"], str)
        assert_close_code(ws, 1011)


def test_websocket_upstream_error_propagates(client_factory):
    client = client_factory(
        FakeRunner(
            should_fail=True,
            fail_code="upstream_error",
            fail_before_events=True,
        )
    )

    with client.websocket_connect("/ws/transcribe") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"

        error = ws.receive_json()
        assert error["type"] == "error"
        assert error["code"] == "upstream_error"
        assert isinstance(error["session_id"], str)
        assert_close_code(ws, 1011)


def test_websocket_persistence_error_propagates(client_factory):
    client = client_factory(
        FakeRunner(
            should_fail=True,
            fail_code="persistence_error",
            fail_before_events=True,
        )
    )

    with client.websocket_connect("/ws/transcribe") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"

        error = ws.receive_json()
        assert error["type"] == "error"
        assert error["code"] == "persistence_error"
        assert isinstance(error["session_id"], str)
        assert_close_code(ws, 1011)


def test_websocket_disconnect_cleanup(client, fake_runner):
    with client.websocket_connect("/ws/transcribe") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"

        ws.close()

    assert fake_runner.run_called


def test_websocket_stop_message(client):
    with client.websocket_connect("/ws/transcribe") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"

        ws.send_bytes(b"\x00" * 3200)

        interim = ws.receive_json()
        assert interim["type"] == "interim"

        final = ws.receive_json()
        assert final["type"] == "final"

        ws.send_text('{"type":"stop"}')

        completed = ws.receive_json()
        assert completed["type"] == "completed"
        assert completed["reason"] == "client_stop"


def test_websocket_language_codes_query(client_factory):
    runner = FakeRunner()
    client = client_factory(runner)

    with client.websocket_connect(
        "/ws/transcribe?language_codes=hi-IN,en-IN"
    ) as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"

        ws.send_bytes(b"\x00" * 3200)

        interim = ws.receive_json()
        assert interim["type"] == "interim"

        final = ws.receive_json()
        assert final["type"] == "final"

        ws.send_text('{"type":"stop"}')

        completed = ws.receive_json()
        assert completed["type"] == "completed"
        assert runner.language_codes == ["hi-IN", "en-IN"]


def test_websocket_persists_final_segment(client_factory, monkeypatch):
    service = FakeTranscriptService()
    runner = LiveTranscriptionRunner(
        transcript_service=service,
        database=FakeDatabase(),
        settings_loader=FakeSettings,
    )

    async def fake_run_transcription(
        *, settings, chunks, language_codes, on_ready, on_event
    ):
        await on_ready()
        async for _ in chunks:
            pass
        await on_event(TranscriptEvent(kind="final", text="persisted text"))
        return SimpleNamespace(interim_count=0)

    monkeypatch.setattr("app.live.run_transcription", fake_run_transcription)
    client = client_factory(runner)

    with client.websocket_connect("/ws/transcribe") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"
        session_id = uuid.UUID(ready["session_id"])

        ws.send_bytes(b"\x00" * 3200)
        ws.send_text('{"type":"stop"}')

        final = ws.receive_json()
        assert final["type"] == "final"
        assert final["sequence"] == 0
        assert final["text"] == "persisted text"

        completed = ws.receive_json()
        assert completed["type"] == "completed"
        assert completed["final_count"] == 1

    assert service.recorded == [(session_id, 0, "persisted text")]


def test_websocket_max_duration_completes(client, monkeypatch):
    monkeypatch.setattr(transcription_module, "MAX_SESSION_SECONDS", 0.05)

    with client.websocket_connect("/ws/transcribe") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"

        completed = ws.receive_json()
        assert completed["type"] == "completed"
        assert completed["reason"] == "max_duration"
        assert completed["final_count"] == 0
