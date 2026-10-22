import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Transcript


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
