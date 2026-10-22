import uuid

from app.database import Database
from app.models import Transcript
from app.repositories import (
    SessionPage,
    TranscriptRepository,
)

MAX_LANGUAGE_CODE_LENGTH = 35


class TranscriptValidationError(ValueError):
    pass


class TranscriptService:
    def __init__(
        self,
        database: Database,
        repository: TranscriptRepository | None = None,
    ) -> None:
        self._database = database
        self._repository = repository or TranscriptRepository()

    def record_final_segment(
        self,
        *,
        session_id: uuid.UUID,
        sequence: int,
        text: str,
        language_code: str | None = None,
    ) -> Transcript:
        normalized_text = text.strip()
        if not normalized_text:
            raise TranscriptValidationError(
                "Transcript text must not be blank."
            )
        if sequence < 0:
            raise TranscriptValidationError(
                "Transcript sequence must be non-negative."
            )

        normalized_language = language_code.strip() if language_code else None
        if normalized_language == "":
            normalized_language = None
        if (
            normalized_language is not None
            and len(normalized_language) > MAX_LANGUAGE_CODE_LENGTH
        ):
            raise TranscriptValidationError(
                "Language code must not exceed 35 characters."
            )

        with self._database.session_scope() as session:
            return self._repository.add(
                session,
                session_id=session_id,
                sequence=sequence,
                text=normalized_text,
                language_code=normalized_language,
            )

    def list_for_session(self, session_id: uuid.UUID) -> list[Transcript]:
        with self._database.session_scope() as session:
            return self._repository.list_for_session(session, session_id)

    def list_sessions(
        self,
        *,
        limit: int = 10,
        offset: int = 0,
        search: str | None = None,
    ) -> SessionPage:
        normalized_search = search.strip() if search else None
        if normalized_search == "":
            normalized_search = None
        with self._database.session_scope() as session:
            return self._repository.list_sessions(
                session,
                limit=limit,
                offset=offset,
                search=normalized_search,
            )

    def update_transcript(
        self,
        transcript_id: uuid.UUID,
        text: str,
    ) -> Transcript | None:
        normalized_text = text.strip()
        if not normalized_text:
            raise TranscriptValidationError(
                "Transcript text must not be blank."
            )

        with self._database.session_scope() as session:
            return self._repository.update_text(
                session,
                transcript_id,
                normalized_text,
            )

    def delete_session(self, session_id: uuid.UUID) -> int:
        with self._database.session_scope() as session:
            return self._repository.delete_session(session, session_id)
