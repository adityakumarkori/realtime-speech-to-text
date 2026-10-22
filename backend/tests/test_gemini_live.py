import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from poc import gemini_live
from poc.config import Settings


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


def test_run_transcription_sends_audio_and_collects_transcripts(monkeypatch):
    monkeypatch.setattr(gemini_live, "_load_sdk", lambda: (FakeGenai, FakeTypes))
    monkeypatch.setattr(gemini_live, "_print_event", lambda *_args: None)
    monkeypatch.setattr(gemini_live, "FINAL_IDLE_SECONDS", 0)

    audio_chunks = [b"a" * 3_200, b"b" * 3_200]

    async def chunks():
        for chunk in audio_chunks:
            yield chunk

    result = asyncio.run(
        gemini_live.run_transcription(
            settings=Settings(api_key="test-key", model="test-model"),
            chunks=chunks(),
            language_codes=["hi-IN", "en-IN"],
            flush_timeout=1.0,
        )
    )

    client = FakeGenai.last_client
    assert client is not None
    assert client.api_key == "test-key"
    assert client.aio.live.model == "test-model"
    assert client.aio.live.config.input_audio_transcription.language_codes == [
        "hi-IN",
        "en-IN",
    ]
    assert client.aio.live.session.sent_audio == audio_chunks
    assert client.aio.live.session.audio_end_calls == 1
    assert result.interim_count == 1
    assert result.final_transcripts == ("final text",)
