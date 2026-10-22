import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import Database
from app.models import Transcript
from app.repositories import TranscriptRepository
from app.services import TranscriptService, TranscriptValidationError


@pytest.fixture
def service(sqlite_database: Database) -> TranscriptService:
    return TranscriptService(sqlite_database)


def test_record_final_segment_persists_normalized_values(service):
    session_id = uuid.uuid4()

    transcript = service.record_final_segment(
        session_id=session_id,
        sequence=0,
        text="  Hello world.  ",
        language_code=" en-IN ",
    )

    assert transcript.id is not None
    assert transcript.session_id == session_id
    assert transcript.sequence == 0
    assert transcript.text == "Hello world."
    assert transcript.language_code == "en-IN"
    assert transcript.created_at is not None


def test_blank_language_code_is_stored_as_null(service):
    transcript = service.record_final_segment(
        session_id=uuid.uuid4(),
        sequence=0,
        text="Hello.",
        language_code="   ",
    )

    assert transcript.language_code is None


def test_segments_are_listed_by_sequence(service):
    session_id = uuid.uuid4()
    for sequence, text in ((2, "Third"), (0, "First"), (1, "Second")):
        service.record_final_segment(
            session_id=session_id,
            sequence=sequence,
            text=text,
        )

    transcripts = service.list_for_session(session_id)

    assert [item.text for item in transcripts] == [
        "First",
        "Second",
        "Third",
    ]
    assert service.list_for_session(uuid.uuid4()) == []


def test_duplicate_session_sequence_is_rejected(service):
    session_id = uuid.uuid4()
    service.record_final_segment(
        session_id=session_id,
        sequence=0,
        text="First.",
    )

    with pytest.raises(IntegrityError):
        service.record_final_segment(
            session_id=session_id,
            sequence=0,
            text="Duplicate.",
        )

    assert len(service.list_for_session(session_id)) == 1


@pytest.mark.parametrize(
    ("text", "sequence", "language_code"),
    [
        ("   ", 0, None),
        ("Hello.", -1, None),
        ("Hello.", 0, "x" * 36),
    ],
)
def test_invalid_segment_is_rejected(
    service,
    text,
    sequence,
    language_code,
):
    with pytest.raises(TranscriptValidationError):
        service.record_final_segment(
            session_id=uuid.uuid4(),
            sequence=sequence,
            text=text,
            language_code=language_code,
        )


@pytest.mark.parametrize(
    ("text", "sequence"),
    [
        ("   ", 0),
        ("Hello.", -1),
    ],
)
def test_database_enforces_transcript_checks(
    sqlite_database,
    text,
    sequence,
):
    with pytest.raises(IntegrityError):
        with sqlite_database.session_scope() as session:
            session.add(
                Transcript(
                    session_id=uuid.uuid4(),
                    sequence=sequence,
                    text=text,
                )
            )


def test_repository_get_and_session_rollback(sqlite_database):
    repository = TranscriptRepository()
    session_id = uuid.uuid4()

    with sqlite_database.session_scope() as session:
        transcript = repository.add(
            session,
            session_id=session_id,
            sequence=0,
            text="Persisted.",
            language_code=None,
        )
        transcript_id = transcript.id

    with sqlite_database.session_scope() as session:
        assert repository.get(session, transcript_id).text == "Persisted."

    with pytest.raises(RuntimeError):
        with sqlite_database.session_scope() as session:
            repository.add(
                session,
                session_id=session_id,
                sequence=1,
                text="Rolled back.",
                language_code=None,
            )
            raise RuntimeError("rollback")

    with sqlite_database.session_scope() as session:
        persisted_text = list(session.scalars(select(Transcript.text)))
        assert persisted_text == ["Persisted."]
