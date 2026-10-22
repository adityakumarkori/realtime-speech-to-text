import asyncio
import logging
import uuid
from dataclasses import asdict, dataclass
from typing import AsyncIterator

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState

from app.live import LiveEvent, LiveRunner, LiveSessionError
from poc.audio import CHUNK_BYTES, FRAME_BYTES, MAX_SESSION_SECONDS
from poc.config import ConfigurationError
from poc.config import parse_language_codes as parse_poc_language_codes

router = APIRouter()

logger = logging.getLogger(__name__)

RECOMMENDED_FRAME_BYTES = CHUNK_BYTES
MAX_FRAME_BYTES = FRAME_BYTES


@dataclass
class AudioConfig:
    encoding: str = "pcm_s16le"
    sample_rate_hz: int = 16_000
    channels: int = 1
    recommended_frame_bytes: int = RECOMMENDED_FRAME_BYTES
    max_frame_bytes: int = MAX_FRAME_BYTES
    max_session_seconds: float = MAX_SESSION_SECONDS


@dataclass
class AudioStreamState:
    completion_reason: str = "client_stop"


@dataclass
class ReadyMessage:
    type: str = "ready"
    session_id: str = ""
    audio: dict | None = None


@dataclass
class InterimMessage:
    type: str = "interim"
    session_id: str = ""
    text: str = ""


@dataclass
class FinalMessage:
    type: str = "final"
    session_id: str = ""
    sequence: int = 0
    text: str = ""


@dataclass
class CompletedMessage:
    type: str = "completed"
    session_id: str = ""
    final_count: int = 0
    reason: str = ""


class TranscriptionProtocolError(Exception):
    def __init__(self, code: str, message: str, close_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.close_code = close_code


def parse_language_codes(value: str | None) -> list[str]:
    try:
        return parse_poc_language_codes(value or "")
    except ConfigurationError as exc:
        raise TranscriptionProtocolError(
            code="invalid_configuration",
            message=str(exc),
            close_code=1008,
        ) from exc


async def validate_audio_frame(data: bytes) -> None:
    if not data:
        raise TranscriptionProtocolError(
            code="invalid_audio",
            message="Empty audio frame",
            close_code=1007,
        )
    if len(data) % 2 != 0:
        raise TranscriptionProtocolError(
            code="invalid_audio",
            message="Audio frame length must be even (16-bit PCM)",
            close_code=1007,
        )
    if len(data) > MAX_FRAME_BYTES:
        raise TranscriptionProtocolError(
            code="invalid_audio",
            message=f"Audio frame exceeds maximum size of {MAX_FRAME_BYTES} bytes",
            close_code=1009,
        )


async def audio_chunk_generator(
    websocket: WebSocket,
    max_duration_seconds: float,
    state: AudioStreamState,
) -> AsyncIterator[bytes]:
    start_time = asyncio.get_running_loop().time()
    try:
        while True:
            elapsed = asyncio.get_running_loop().time() - start_time
            remaining = max_duration_seconds - elapsed
            if remaining <= 0:
                state.completion_reason = "max_duration"
                logger.info("Session duration limit reached")
                break

            try:
                message = await asyncio.wait_for(
                    websocket.receive(), timeout=remaining
                )
            except asyncio.TimeoutError:
                state.completion_reason = "max_duration"
                logger.info("Session duration limit reached")
                break

            if message["type"] == "websocket.disconnect":
                logger.info("Client disconnected")
                raise WebSocketDisconnect(code=1000)

            if "bytes" in message and message["bytes"] is not None:
                data = message["bytes"]
                await validate_audio_frame(data)
                yield data
            elif "text" in message and message["text"] is not None:
                text = message["text"].strip()
                if text == '{"type":"stop"}':
                    state.completion_reason = "client_stop"
                    logger.info("Client requested stop")
                    break
                raise TranscriptionProtocolError(
                    code="invalid_message",
                    message='Unsupported text message; send {"type":"stop"} to finish.',
                    close_code=1003,
                )
            else:
                raise TranscriptionProtocolError(
                    code="invalid_message",
                    message="Unsupported message type",
                    close_code=1003,
                )
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected during audio streaming")
        raise
    except TranscriptionProtocolError:
        raise
    except Exception as exc:
        logger.error("Unexpected error in audio chunk generator")
        raise TranscriptionProtocolError(
            code="internal_error",
            message="Internal server error",
            close_code=1011,
        ) from exc


async def send_json_safe(websocket: WebSocket, message: dict) -> bool:
    try:
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_json(message)
            return True
    except (RuntimeError, WebSocketDisconnect):
        pass
    return False


@router.websocket("/ws/transcribe")
async def websocket_transcribe(
    websocket: WebSocket,
    language_codes: str = Query(default="auto", alias="language_codes"),
) -> None:
    allowed_origins = websocket.app.state.settings.cors_origins
    origin = websocket.headers.get("origin")
    if allowed_origins and origin is not None and origin not in allowed_origins:
        logger.warning("Rejected WebSocket connection from an unknown origin")
        await websocket.close(code=1008)
        return

    await websocket.accept()
    session_id = uuid.uuid4()
    session_id_str = str(session_id)

    language_codes_list: list[str]
    try:
        language_codes_list = parse_language_codes(language_codes)
    except TranscriptionProtocolError as exc:
        await send_json_safe(
            websocket,
            {
                "type": "error",
                "session_id": session_id_str,
                "code": exc.code,
                "message": exc.message,
            },
        )
        await websocket.close(code=exc.close_code)
        return

    client_connected = True

    async def emit_event(event_dict: dict) -> None:
        nonlocal client_connected
        if not client_connected:
            return
        sent = await send_json_safe(websocket, event_dict)
        if not sent:
            client_connected = False

    async def on_ready() -> None:
        audio_config = asdict(
            AudioConfig(max_session_seconds=MAX_SESSION_SECONDS)
        )
        ready = ReadyMessage(
            session_id=session_id_str,
            audio=audio_config,
        )
        await emit_event(ready.__dict__)

    async def on_event(event: LiveEvent) -> None:
        nonlocal client_connected
        if event.kind == "interim":
            msg = InterimMessage(
                session_id=session_id_str,
                text=event.text,
            )
            await emit_event(msg.__dict__)
        else:
            msg = FinalMessage(
                session_id=session_id_str,
                sequence=event.sequence,
                text=event.text,
            )
            await emit_event(msg.__dict__)

    runner: LiveRunner = websocket.app.state.live_runner
    stream_state = AudioStreamState()

    close_code = 1000
    try:
        chunks = audio_chunk_generator(
            websocket, MAX_SESSION_SECONDS, stream_state
        )

        summary = await runner.run(
            session_id=session_id,
            chunks=chunks,
            language_codes=language_codes_list,
            on_ready=on_ready,
            on_event=on_event,
        )

        completed = CompletedMessage(
            session_id=session_id_str,
            final_count=summary.final_count,
            reason=stream_state.completion_reason,
        )
        await emit_event(completed.__dict__)

    except WebSocketDisconnect:
        logger.info(f"Session {session_id_str}: client disconnected")
        close_code = 1000
    except TranscriptionProtocolError as exc:
        logger.warning(f"Session {session_id_str}: protocol error {exc.code}")
        await send_json_safe(
            websocket,
            {
                "type": "error",
                "session_id": session_id_str,
                "code": exc.code,
                "message": exc.message,
            },
        )
        close_code = exc.close_code
    except LiveSessionError as exc:
        logger.warning(f"Session {session_id_str}: live session error {exc.code}")
        session_id_for_error = (
            str(exc.session_id) if exc.session_id is not None else session_id_str
        )
        await send_json_safe(
            websocket,
            {
                "type": "error",
                "session_id": session_id_for_error,
                "code": exc.code,
                "message": exc.message,
            },
        )
        close_code = exc.close_code
    except asyncio.CancelledError:
        logger.info(f"Session {session_id_str}: cancelled")
        close_code = 1011
        raise
    except Exception:
        logger.error("Session %s: unexpected error", session_id_str)
        await send_json_safe(
            websocket,
            {
                "type": "error",
                "session_id": session_id_str,
                "code": "internal_error",
                "message": "Internal server error",
            },
        )
        close_code = 1011
    finally:
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close(code=close_code)
        except RuntimeError:
            pass