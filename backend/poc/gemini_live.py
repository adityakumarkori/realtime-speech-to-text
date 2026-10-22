import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass

from .audio import MIME_TYPE
from .config import Settings
from .transcripts import TranscriptEvent, extract_events

DEFAULT_FLUSH_TIMEOUT_SECONDS = 8.0
FINAL_IDLE_SECONDS = 1.0


class GeminiLiveError(RuntimeError):
    pass


@dataclass(frozen=True)
class TranscriptionResult:
    interim_count: int
    final_transcripts: tuple[str, ...]


class _SessionState:
    def __init__(self) -> None:
        self.interim_count = 0
        self.final_transcripts: list[str] = []
        self.last_event_at = 0.0
        self.error: Exception | None = None


def _load_sdk():
    try:
        from google import genai
        from google.genai import types
    except (ImportError, OSError) as exc:
        raise GeminiLiveError(
            "google-genai is unavailable. Install backend/requirements.txt "
            "before running live transcription."
        ) from exc
    return genai, types


def _build_config(types, language_codes: Sequence[str]):
    return types.LiveConnectConfig(
        response_modalities=["TEXT"],
        input_audio_transcription=types.AudioTranscriptionConfig(
            language_codes=list(language_codes),
            mode="VERBATIM",
        ),
    )


def _print_event(kind: str, text: str) -> None:
    print(f"[{kind}] {text}", flush=True)


async def _receive_loop(
    session,
    state: _SessionState,
    on_event: Callable[[TranscriptEvent], Awaitable[None]] | None = None,
) -> None:
    try:
        while True:
            async for response in session.receive():
                content = response.server_content
                if content is None:
                    continue
                for event in extract_events(content):
                    state.last_event_at = asyncio.get_running_loop().time()
                    if on_event is not None:
                        await on_event(event)
                    if event.kind == "interim":
                        state.interim_count += 1
                    else:
                        state.final_transcripts.append(event.text)
                    if on_event is None:
                        _print_event(event.kind, event.text)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        state.error = exc


async def _drain_final_transcripts(
    state: _SessionState,
    timeout: float,
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if state.error is not None:
            return
        if (
            state.final_transcripts
            and loop.time() - state.last_event_at >= FINAL_IDLE_SECONDS
        ):
            return
        await asyncio.sleep(0.1)


async def run_transcription(
    settings: Settings,
    chunks: AsyncIterator[bytes],
    language_codes: Sequence[str] = (),
    flush_timeout: float = DEFAULT_FLUSH_TIMEOUT_SECONDS,
    on_ready: Callable[[], Awaitable[None]] | None = None,
    on_event: Callable[[TranscriptEvent], Awaitable[None]] | None = None,
) -> TranscriptionResult:
    if flush_timeout < 0:
        raise ValueError("flush_timeout must not be negative.")

    genai, types = _load_sdk()
    config = _build_config(types, language_codes)
    state = _SessionState()
    client = genai.Client(api_key=settings.api_key)

    async with client.aio as async_client:
        async with async_client.live.connect(
            model=settings.model,
            config=config,
        ) as session:
            if session.setup_complete is None:
                raise GeminiLiveError(
                    "The Live API session did not return setup_complete."
                )

            if on_ready is None and on_event is None:
                print(
                    f"Live session established with {settings.model}.",
                    flush=True,
                )
            if on_ready is not None:
                await on_ready()

            receive_task = asyncio.create_task(
                _receive_loop(session, state, on_event=on_event)
            )

            try:
                async for chunk in chunks:
                    if state.error is not None:
                        raise state.error
                    await session.send_realtime_input(
                        audio=types.Blob(data=chunk, mime_type=MIME_TYPE)
                    )

                await session.send_realtime_input(audio_stream_end=True)
                if state.error is not None:
                    if on_event is None and not state.final_transcripts:
                        raise state.error
                    elif on_event is not None:
                        raise state.error

                await _drain_final_transcripts(state, flush_timeout)
                if state.error is not None:
                    if on_event is None and not state.final_transcripts:
                        raise state.error
                    elif on_event is not None:
                        raise state.error
            finally:
                receive_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await receive_task

    return TranscriptionResult(
        interim_count=state.interim_count,
        final_transcripts=tuple(state.final_transcripts),
    )
