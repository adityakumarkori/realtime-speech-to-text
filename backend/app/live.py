import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from app.database import Database, DatabaseUnavailableError
from app.services import TranscriptService, TranscriptValidationError
from poc.config import ConfigurationError, load_settings
from poc.gemini_live import GeminiLiveError, run_transcription
from poc.transcripts import TranscriptEvent

logger = logging.getLogger(__name__)


@dataclass
class LiveEvent:
    kind: str
    text: str
    sequence: int | None = None


class LiveSessionError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        close_code: int,
        session_id: uuid.UUID | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.close_code = close_code
        self.session_id = session_id


@dataclass(frozen=True)
class LiveSummary:
    interim_count: int
    final_count: int


class LiveRunner(Protocol):
    async def run(
        self,
        *,
        session_id: uuid.UUID,
        chunks: AsyncIterator[bytes],
        language_codes: list[str],
        on_ready: Callable[[], Awaitable[None]],
        on_event: Callable[[LiveEvent], Awaitable[None]],
    ) -> LiveSummary: ...


class LiveTranscriptionRunner:
    def __init__(
        self,
        transcript_service: TranscriptService,
        database: Database,
        settings_loader=load_settings,
    ) -> None:
        self._transcript_service = transcript_service
        self._database = database
        self._settings_loader = settings_loader

    async def run(
        self,
        *,
        session_id: uuid.UUID,
        chunks: AsyncIterator[bytes],
        language_codes: list[str],
        on_ready: Callable[[], Awaitable[None]],
        on_event: Callable[[LiveEvent], Awaitable[None]],
    ) -> LiveSummary:
        if not self._database.is_configured:
            raise LiveSessionError(
                code="database_unavailable",
                message="Transcript persistence is not configured",
                close_code=1011,
                session_id=session_id,
            )

        try:
            settings = self._settings_loader()
        except ConfigurationError as exc:
            raise LiveSessionError(
                code="invalid_configuration",
                message=str(exc),
                close_code=1008,
                session_id=session_id,
            ) from exc

        sequence = 0
        final_count = 0
        interim_count = 0

        async def handle_event(event: TranscriptEvent) -> None:
            nonlocal sequence, final_count, interim_count
            if event.kind == "interim":
                interim_count += 1
                await on_event(LiveEvent(kind="interim", text=event.text))
            else:
                try:
                    self._transcript_service.record_final_segment(
                        session_id=session_id,
                        sequence=sequence,
                        text=event.text,
                        language_code=None,
                    )
                except TranscriptValidationError as exc:
                    raise LiveSessionError(
                        code="persistence_error",
                        message="Invalid transcript data",
                        close_code=1011,
                        session_id=session_id,
                    ) from exc
                except DatabaseUnavailableError as exc:
                    raise LiveSessionError(
                        code="database_unavailable",
                        message="Transcript persistence became unavailable",
                        close_code=1011,
                        session_id=session_id,
                    ) from exc
                except Exception as exc:
                    logger.error("Unexpected error persisting transcript")
                    raise LiveSessionError(
                        code="persistence_error",
                        message="Failed to persist transcript",
                        close_code=1011,
                        session_id=session_id,
                    ) from exc
                final_count += 1
                await on_event(LiveEvent(kind="final", text=event.text, sequence=sequence))
                sequence += 1

        try:
            result = await run_transcription(
                settings=settings,
                chunks=chunks,
                language_codes=language_codes,
                on_ready=on_ready,
                on_event=handle_event,
            )
            interim_count = result.interim_count
        except GeminiLiveError as exc:
            raise LiveSessionError(
                code="upstream_error",
                message="Transcription service unavailable",
                close_code=1011,
                session_id=session_id,
            ) from exc
        except LiveSessionError:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Unexpected error during transcription")
            raise LiveSessionError(
                code="internal_error",
                message="Internal server error",
                close_code=1011,
                session_id=session_id,
            ) from exc

        return LiveSummary(interim_count=interim_count, final_count=final_count)