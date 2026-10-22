import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Transcript

PREVIEW_LENGTH = 200


@dataclass(frozen=True)
class SessionSummary:
    session_id: uuid.UUID
    started_at: datetime
    ended_at: datetime
    segment_count: int
    preview: str
    language_codes: tuple[str, ...]


@dataclass(frozen=True)
class SessionPage:
    sessions: list[SessionSummary]
    total: int


def _escape_like(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _preview(text: str) -> str:
    if len(text) <= PREVIEW_LENGTH:
        return text
    return f"{text[: PREVIEW_LENGTH - 3]}..."


class TranscriptRepository:
    def add(
        self,
        session: Session,
        *,
        session_id: uuid.UUID,
        sequence: int,
        text: str,
        language_code: str | None,
    ) -> Transcript:
        transcript = Transcript(
            session_id=session_id,
            sequence=sequence,
            text=text,
            language_code=language_code,
        )
        session.add(transcript)
        session.flush()
        return transcript

    def get(
        self,
        session: Session,
        transcript_id: uuid.UUID,
    ) -> Transcript | None:
        return session.get(Transcript, transcript_id)

    def list_for_session(
        self,
        session: Session,
        session_id: uuid.UUID,
    ) -> list[Transcript]:
        statement = (
            select(Transcript)
            .where(Transcript.session_id == session_id)
            .order_by(Transcript.sequence, Transcript.created_at)
        )
        return list(session.scalars(statement))

    def list_sessions(
        self,
        session: Session,
        *,
        limit: int,
        offset: int,
        search: str | None = None,
    ) -> SessionPage:
        filters = []
        if search:
            filters.append(
                Transcript.text.ilike(
                    f"%{_escape_like(search)}%",
                    escape="\\",
                )
            )

        matching_session_ids = select(Transcript.session_id)
        if filters:
            matching_session_ids = matching_session_ids.where(*filters)

        total_statement = select(
            func.count()
        ).select_from(matching_session_ids.distinct().subquery())
        total = int(session.scalar(total_statement) or 0)

        if total == 0:
            return SessionPage(sessions=[], total=0)

        summary_statement = (
            select(
                Transcript.session_id,
                func.min(Transcript.created_at).label("started_at"),
                func.max(Transcript.created_at).label("ended_at"),
                func.count(Transcript.id).label("segment_count"),
            )
            .where(Transcript.session_id.in_(matching_session_ids))
            .group_by(Transcript.session_id)
            .order_by(
                func.max(Transcript.created_at).desc(),
                Transcript.session_id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        rows = session.execute(summary_statement).all()
        session_ids = [row.session_id for row in rows]
        previews, languages = self._metadata_for_sessions(
            session,
            session_ids,
        )

        summaries = [
            SessionSummary(
                session_id=row.session_id,
                started_at=row.started_at,
                ended_at=row.ended_at,
                segment_count=row.segment_count,
                preview=_preview(previews.get(row.session_id, "")),
                language_codes=tuple(languages.get(row.session_id, [])),
            )
            for row in rows
        ]
        return SessionPage(sessions=summaries, total=total)

    def _metadata_for_sessions(
        self,
        session: Session,
        session_ids: list[uuid.UUID],
    ) -> tuple[dict[uuid.UUID, str], dict[uuid.UUID, list[str]]]:
        if not session_ids:
            return {}, {}

        row_number = (
            func.row_number()
            .over(
                partition_by=Transcript.session_id,
                order_by=(Transcript.sequence, Transcript.created_at),
            )
            .label("row_number")
        )
        ranked = (
            select(
                Transcript.session_id.label("session_id"),
                Transcript.text.label("text"),
                row_number,
            )
            .where(Transcript.session_id.in_(session_ids))
            .subquery()
        )
        preview_statement = select(
            ranked.c.session_id,
            ranked.c.text,
        ).where(ranked.c.row_number == 1)
        previews = {
            row.session_id: row.text
            for row in session.execute(preview_statement)
        }

        language_statement = (
            select(Transcript.session_id, Transcript.language_code)
            .where(
                Transcript.session_id.in_(session_ids),
                Transcript.language_code.is_not(None),
            )
            .distinct()
            .order_by(Transcript.session_id, Transcript.language_code)
        )
        languages: dict[uuid.UUID, list[str]] = {}
        for session_id, language_code in session.execute(language_statement):
            languages.setdefault(session_id, []).append(language_code)
        return previews, languages

    def update_text(
        self,
        session: Session,
        transcript_id: uuid.UUID,
        text: str,
    ) -> Transcript | None:
        transcript = self.get(session, transcript_id)
        if transcript is None:
            return None
        transcript.text = text
        session.flush()
        return transcript

    def delete_session(
        self,
        session: Session,
        session_id: uuid.UUID,
    ) -> int:
        result = session.execute(
            delete(Transcript).where(Transcript.session_id == session_id)
        )
        return int(result.rowcount or 0)
