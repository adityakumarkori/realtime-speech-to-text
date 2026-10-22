import asyncio
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.live import LiveTranscriptionRunner, LiveSessionError, LiveSummary
from app.services import Transcript, TranscriptService
from poc.config import ConfigurationError
from poc.gemini_live import GeminiLiveError
from poc.transcripts import TranscriptEvent


class FakeTranscriptService:
    def __init__(self):
        self.recorded: list[tuple[uuid.UUID, int, str]] = []
        self.language_codes: list[str | None] = []

    def record_final_segment(
        self, *, session_id: uuid.UUID, sequence: int, text: str, language_code: str | None = None
    ) -> Transcript:
        self.recorded.append((session_id, sequence, text))
        self.language_codes.append(language_code)
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


class FakeTypes:
    @staticmethod
    def LiveConnectConfig(**kwargs):
        return SimpleNamespace(**kwargs)

    @staticmethod
    def AudioTranscriptionConfig(**kwargs):
        return SimpleNamespace(**kwargs)

    @staticmethod
    def Blob(**kwargs):
        return SimpleNamespace(**kwargs)


class FakeSession:
    def __init__(self):
        self.setup_complete = object()
        self.sent_audio: list[bytes] = []
        self.stream_ended = False
        self.audio_end_calls = 0

    async def send_realtime_input(self, *, audio=None, audio_stream_end=None):
        if audio is not None:
            self.sent_audio.append(audio.data)
        if audio_stream_end:
            self.stream_ended = True
            self.audio_end_calls += 1

    async def receive(self):
        interim = SimpleNamespace(
            interim_input_transcription=SimpleNamespace(text="interim text"),
            input_transcription=None,
        )
        yield SimpleNamespace(server_content=interim)

        while not self.stream_ended:
            await asyncio.sleep(0)

        final = SimpleNamespace(
            interim_input_transcription=None,
            input_transcription=SimpleNamespace(text="final text"),
        )
        yield SimpleNamespace(server_content=final)
        while True:
            await asyncio.sleep(0)


class FakeLive:
    def __init__(self):
        self.session = FakeSession()
        self.model = None
        self.config = None

    @asynccontextmanager
    async def connect(self, *, model, config):
        self.model = model
        self.config = config
        yield self.session


class FakeAsyncClient:
    def __init__(self):
        self.live = FakeLive()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeGenai:
    last_client = None

    class Client:
        def __init__(self, *, api_key):
            self.api_key = api_key
            self.aio = FakeAsyncClient()
            FakeGenai.last_client = self


@pytest.fixture
def fake_settings_loader():
    def loader():
        return FakeSettings()

    return loader


@pytest.fixture
def fake_database():
    return FakeDatabase(configured=True)


@pytest.fixture
def fake_transcript_service():
    return FakeTranscriptService()


@pytest.fixture
def runner(fake_database, fake_transcript_service, fake_settings_loader):
    return LiveTranscriptionRunner(
        transcript_service=fake_transcript_service,
        database=fake_database,
        settings_loader=fake_settings_loader,
    )


def _patch_sdk(monkeypatch):
    monkeypatch.setattr("poc.gemini_live._load_sdk", lambda: (FakeGenai, FakeTypes))
    monkeypatch.setattr("poc.gemini_live._print_event", lambda *_args: None)
    monkeypatch.setattr("poc.gemini_live.FINAL_IDLE_SECONDS", 0)


async def test_runner_successful_session(monkeypatch, runner, fake_transcript_service):
    _patch_sdk(monkeypatch)

    session_id = uuid.uuid4()
    language_codes = ["hi-IN", "en-IN"]
    audio_chunks = [b"a" * 3_200, b"b" * 3_200]

    async def chunks():
        for chunk in audio_chunks:
            yield chunk

    ready_called = False
    events: list[TranscriptEvent] = []

    async def on_ready():
        nonlocal ready_called
        ready_called = True

    async def on_event(event: TranscriptEvent):
        events.append(event)

    summary = await runner.run(
        session_id=session_id,
        chunks=chunks(),
        language_codes=language_codes,
        on_ready=on_ready,
        on_event=on_event,
    )

    assert ready_called
    assert len(events) == 2
    assert events[0].kind == "interim"
    assert events[1].kind == "final"
    assert summary.interim_count == 1
    assert summary.final_count == 1
    assert fake_transcript_service.recorded == [(session_id, 0, "final text")]
    assert fake_transcript_service.language_codes == ["hi-IN,en-IN"]


async def test_runner_database_unconfigured_raises_error(
    fake_transcript_service, fake_settings_loader
):
    database = FakeDatabase(configured=False)
    runner = LiveTranscriptionRunner(
        transcript_service=fake_transcript_service,
        database=database,
        settings_loader=fake_settings_loader,
    )

    session_id = uuid.uuid4()

    async def chunks():
        yield b"a" * 3_200

    async def on_ready():
        pass

    async def on_event(event):
        pass

    with pytest.raises(LiveSessionError) as exc_info:
        await runner.run(
            session_id=session_id,
            chunks=chunks(),
            language_codes=[],
            on_ready=on_ready,
            on_event=on_event,
        )

    assert exc_info.value.code == "database_unavailable"
    assert exc_info.value.close_code == 1011
    assert exc_info.value.session_id == session_id


async def test_runner_invalid_configuration_raises_error(
    fake_database, fake_transcript_service
):
    def bad_settings_loader():
        raise ConfigurationError("API key not set")

    runner = LiveTranscriptionRunner(
        transcript_service=fake_transcript_service,
        database=fake_database,
        settings_loader=bad_settings_loader,
    )

    session_id = uuid.uuid4()

    async def chunks():
        yield b"a" * 3_200

    async def on_ready():
        pass

    async def on_event(event):
        pass

    with pytest.raises(LiveSessionError) as exc_info:
        await runner.run(
            session_id=session_id,
            chunks=chunks(),
            language_codes=[],
            on_ready=on_ready,
            on_event=on_event,
        )

    assert exc_info.value.code == "invalid_configuration"
    assert exc_info.value.close_code == 1008
    assert exc_info.value.session_id == session_id


async def test_runner_persistence_error_on_invalid_transcript(
    monkeypatch, runner, fake_transcript_service
):
    _patch_sdk(monkeypatch)

    session_id = uuid.uuid4()

    async def chunks():
        yield b"a" * 3_200

    ready_called = False
    events: list[TranscriptEvent] = []

    async def on_ready():
        nonlocal ready_called
        ready_called = True

    async def on_event(event: TranscriptEvent):
        events.append(event)

    fake_transcript_service.record_final_segment = MagicMock(
        side_effect=Exception("DB error")
    )

    with pytest.raises(LiveSessionError) as exc_info:
        await runner.run(
            session_id=session_id,
            chunks=chunks(),
            language_codes=[],
            on_ready=on_ready,
            on_event=on_event,
        )

    assert exc_info.value.code == "persistence_error"
    assert exc_info.value.close_code == 1011
    assert exc_info.value.session_id == session_id


async def test_runner_sequence_increments_only_after_successful_persistence(
    monkeypatch, fake_database, fake_transcript_service
):
    class MultiFinalSession:
        def __init__(self):
            self.setup_complete = object()
            self.sent_audio: list[bytes] = []
            self.stream_ended = False
            self.audio_end_calls = 0

        async def send_realtime_input(self, *, audio=None, audio_stream_end=None):
            if audio is not None:
                self.sent_audio.append(audio.data)
            if audio_stream_end:
                self.stream_ended = True
                self.audio_end_calls += 1

        async def receive(self):
            for _ in range(3):
                interim = SimpleNamespace(
                    interim_input_transcription=SimpleNamespace(text="interim"),
                    input_transcription=None,
                )
                yield SimpleNamespace(server_content=interim)

            for i in range(3):
                final = SimpleNamespace(
                    interim_input_transcription=None,
                    input_transcription=SimpleNamespace(text=f"final {i}"),
                )
                yield SimpleNamespace(server_content=final)

            while True:
                await asyncio.sleep(0)

    class MultiFinalLive:
        @asynccontextmanager
        async def connect(self, *, model, config):
            session = MultiFinalSession()
            yield session

    class MultiFinalAsyncClient:
        def __init__(self):
            self.live = MultiFinalLive()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class MultiFinalGenai:
        class Client:
            def __init__(self, *, api_key):
                self.api_key = api_key
                self.aio = MultiFinalAsyncClient()

        @staticmethod
        def load_sdk():
            return MultiFinalGenai, FakeTypes

    def multi_final_settings_loader():
        settings = FakeSettings()
        return settings

    monkeypatch.setattr(
        "poc.gemini_live._load_sdk",
        lambda: (MultiFinalGenai, FakeTypes),
    )
    monkeypatch.setattr("poc.gemini_live._print_event", lambda *_args: None)
    monkeypatch.setattr("poc.gemini_live.FINAL_IDLE_SECONDS", 0)

    runner = LiveTranscriptionRunner(
        transcript_service=fake_transcript_service,
        database=fake_database,
        settings_loader=multi_final_settings_loader,
    )

    session_id = uuid.uuid4()

    async def chunks():
        for _ in range(3):
            yield b"a" * 3_200

    events: list[TranscriptEvent] = []

    async def on_ready():
        pass

    async def on_event(event: TranscriptEvent):
        events.append(event)

    summary = await runner.run(
        session_id=session_id,
        chunks=chunks(),
        language_codes=[],
        on_ready=on_ready,
        on_event=on_event,
    )

    assert summary.final_count == 3
    assert [e.text for e in events if e.kind == "final"] == [
        "final 0",
        "final 1",
        "final 2",
    ]
    recorded_sequences = [seq for _, seq, _ in fake_transcript_service.recorded]
    assert recorded_sequences == [0, 1, 2]


async def test_runner_upstream_error_propagates(
    monkeypatch, fake_database, fake_transcript_service, fake_settings_loader
):
    def failing_load_sdk():
        raise GeminiLiveError("upstream failed")

    monkeypatch.setattr("poc.gemini_live._load_sdk", failing_load_sdk)

    runner = LiveTranscriptionRunner(
        transcript_service=fake_transcript_service,
        database=fake_database,
        settings_loader=fake_settings_loader,
    )

    session_id = uuid.uuid4()

    async def chunks():
        yield b"a" * 3_200

    async def on_ready():
        pass

    async def on_event(event):
        pass

    with pytest.raises(LiveSessionError) as exc_info:
        await runner.run(
            session_id=session_id,
            chunks=chunks(),
            language_codes=[],
            on_ready=on_ready,
            on_event=on_event,
        )

    assert exc_info.value.code == "upstream_error"
    assert exc_info.value.close_code == 1011
    assert exc_info.value.session_id == session_id


async def test_runner_cancelled_error_propagates(monkeypatch, runner):
    _patch_sdk(monkeypatch)

    session_id = uuid.uuid4()

    async def chunks():
        yield b"a" * 3_200
        raise asyncio.CancelledError()

    async def on_ready():
        pass

    async def on_event(event):
        pass

    with pytest.raises(asyncio.CancelledError):
        await runner.run(
            session_id=session_id,
            chunks=chunks(),
            language_codes=[],
            on_ready=on_ready,
            on_event=on_event,
        )