import uuid
from datetime import datetime, timedelta, timezone
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import AppSettings, DatabaseSettings
from app.database import Database
from app.live import LiveSummary, LiveTranscriptionRunner
from app.main import create_app
from app.models import Transcript
from poc.transcripts import TranscriptEvent


@pytest.fixture
def history_client(migrated_sqlite_url: str) -> Iterator[TestClient]:
    app = create_app(
        AppSettings(environment="test", log_level="CRITICAL"),
        DatabaseSettings(url=migrated_sqlite_url),
    )
    with TestClient(app) as client:
        yield client


def _add_segment(
    database: Database,
    *,
    session_id: uuid.UUID,
    sequence: int,
    text: str,
    language_code: str | None = None,
    created_at: datetime | None = None,
) -> uuid.UUID:
    with database.session_scope() as session:
        transcript = Transcript(
            session_id=session_id,
            sequence=sequence,
            text=text,
            language_code=language_code,
            **({"created_at": created_at} if created_at is not None else {}),
        )
        session.add(transcript)
        session.flush()
        return transcript.id


def test_list_sessions_returns_metadata_and_orders_by_latest(
    history_client: TestClient,
    sqlite_database: Database,
) -> None:
    first_session = uuid.uuid4()
    second_session = uuid.uuid4()
    base_time = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)

    _add_segment(
        sqlite_database,
        session_id=first_session,
        sequence=0,
        text="Hello from the first session.",
        language_code="en-IN",
        created_at=base_time,
    )
    _add_segment(
        sqlite_database,
        session_id=first_session,
        sequence=1,
        text="नमस्ते।",
        language_code="hi-IN",
        created_at=base_time + timedelta(minutes=1),
    )
    _add_segment(
        sqlite_database,
        session_id=second_session,
        sequence=0,
        text="A later session.",
        created_at=base_time + timedelta(hours=1),
    )

    response = history_client.get("/api/transcription-sessions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["limit"] == 50
    assert payload["offset"] == 0
    assert [item["session_id"] for item in payload["sessions"]] == [
        str(second_session),
        str(first_session),
    ]
    first_summary = payload["sessions"][1]
    assert first_summary["segment_count"] == 2
    assert first_summary["preview"] == "Hello from the first session."
    assert first_summary["language_codes"] == ["en-IN", "hi-IN"]
    assert first_summary["started_at"].startswith("2026-01-01T10:00:00")
    assert first_summary["ended_at"].startswith("2026-01-01T10:01:00")


def test_list_sessions_search_pagination_and_empty_state(
    history_client: TestClient,
    sqlite_database: Database,
) -> None:
    base_time = datetime(2026, 2, 1, 9, 0, tzinfo=timezone.utc)
    session_ids = [uuid.uuid4() for _ in range(3)]
    for index, session_id in enumerate(session_ids):
        _add_segment(
            sqlite_database,
            session_id=session_id,
            sequence=0,
            text=f"Project update number {index}",
            created_at=base_time + timedelta(minutes=index),
        )
    _add_segment(
        sqlite_database,
        session_id=session_ids[1],
        sequence=1,
        text="Unrelated follow-up.",
        created_at=base_time + timedelta(seconds=90),
    )

    search_response = history_client.get(
        "/api/transcription-sessions",
        params={"q": "UPDATE NUMBER 1"},
    )
    assert search_response.status_code == 200
    search_payload = search_response.json()
    assert search_payload["total"] == 1
    assert search_payload["sessions"][0]["session_id"] == str(session_ids[1])
    assert search_payload["sessions"][0]["segment_count"] == 2
    assert (
        search_payload["sessions"][0]["preview"]
        == "Project update number 1"
    )

    page_response = history_client.get(
        "/api/transcription-sessions",
        params={"limit": 1, "offset": 1},
    )
    assert page_response.status_code == 200
    page_payload = page_response.json()
    assert page_payload["total"] == 3
    assert len(page_payload["sessions"]) == 1
    assert page_payload["sessions"][0]["session_id"] == str(session_ids[1])

    empty_response = history_client.get(
        "/api/transcription-sessions",
        params={"q": "no such transcript"},
    )
    assert empty_response.status_code == 200
    assert empty_response.json() == {
        "sessions": [],
        "total": 0,
        "limit": 50,
        "offset": 0,
    }


def test_search_treats_like_wildcards_literally(
    history_client: TestClient,
    sqlite_database: Database,
) -> None:
    session_id = uuid.uuid4()
    _add_segment(
        sqlite_database,
        session_id=session_id,
        sequence=0,
        text="The result was 100% accurate.",
    )
    _add_segment(
        sqlite_database,
        session_id=uuid.uuid4(),
        sequence=0,
        text="A different result.",
    )
    underscore_session = uuid.uuid4()
    _add_segment(
        sqlite_database,
        session_id=underscore_session,
        sequence=0,
        text="snake_case value",
    )
    _add_segment(
        sqlite_database,
        session_id=uuid.uuid4(),
        sequence=0,
        text="snakeXcase value",
    )

    response = history_client.get(
        "/api/transcription-sessions",
        params={"q": "100%"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["sessions"][0]["session_id"] == str(session_id)

    underscore_response = history_client.get(
        "/api/transcription-sessions",
        params={"q": "snake_case"},
    )
    assert underscore_response.status_code == 200
    underscore_payload = underscore_response.json()
    assert underscore_payload["total"] == 1
    assert underscore_payload["sessions"][0]["session_id"] == str(
        underscore_session
    )


def test_get_session_returns_ordered_segments(
    history_client: TestClient,
    sqlite_database: Database,
) -> None:
    session_id = uuid.uuid4()
    segment_ids = {}
    for sequence, text in ((2, "Third"), (0, "First"), (1, "Second")):
        segment_ids[sequence] = _add_segment(
            sqlite_database,
            session_id=session_id,
            sequence=sequence,
            text=text,
            language_code="en-IN",
        )

    response = history_client.get(
        f"/api/transcription-sessions/{session_id}"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == str(session_id)
    assert payload["segment_count"] == 3
    assert [item["sequence"] for item in payload["segments"]] == [0, 1, 2]
    assert [item["text"] for item in payload["segments"]] == [
        "First",
        "Second",
        "Third",
    ]
    assert [item["id"] for item in payload["segments"]] == [
        str(segment_ids[0]),
        str(segment_ids[1]),
        str(segment_ids[2]),
    ]
    assert payload["started_at"] is not None
    assert payload["ended_at"] is not None


def test_get_session_not_found_and_invalid_identifier(
    history_client: TestClient,
) -> None:
    missing = history_client.get(
        f"/api/transcription-sessions/{uuid.uuid4()}"
    )
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Transcription session not found"}

    invalid = history_client.get("/api/transcription-sessions/not-a-uuid")
    assert invalid.status_code == 422


def test_update_transcript_segment(
    history_client: TestClient,
    sqlite_database: Database,
) -> None:
    session_id = uuid.uuid4()
    transcript_id = _add_segment(
        sqlite_database,
        session_id=session_id,
        sequence=0,
        text="Original text.",
    )
    other_id = _add_segment(
        sqlite_database,
        session_id=session_id,
        sequence=1,
        text="Untouched text.",
    )

    response = history_client.patch(
        f"/api/transcript-segments/{transcript_id}",
        json={"text": "  Corrected text.  "},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(transcript_id)
    assert payload["text"] == "Corrected text."
    assert payload["sequence"] == 0

    detail = history_client.get(
        f"/api/transcription-sessions/{session_id}"
    )
    assert detail.status_code == 200
    assert [item["text"] for item in detail.json()["segments"]] == [
        "Corrected text.",
        "Untouched text.",
    ]

    with sqlite_database.session_scope() as session:
        stored = session.get(Transcript, other_id)
        assert stored is not None
        assert stored.text == "Untouched text."


@pytest.mark.parametrize("text", ["", "   ", "\n\t "])
def test_update_transcript_rejects_blank_text(
    history_client: TestClient,
    sqlite_database: Database,
    text: str,
) -> None:
    session_id = uuid.uuid4()
    transcript_id = _add_segment(
        sqlite_database,
        session_id=session_id,
        sequence=0,
        text="Keep this.",
    )

    response = history_client.patch(
        f"/api/transcript-segments/{transcript_id}",
        json={"text": text},
    )

    assert response.status_code == 422
    detail = history_client.get(
        f"/api/transcription-sessions/{session_id}"
    )
    assert detail.status_code == 200
    assert detail.json()["segments"][0]["text"] == "Keep this."


def test_update_transcript_missing_and_invalid_identifier(
    history_client: TestClient,
) -> None:
    missing = history_client.patch(
        f"/api/transcript-segments/{uuid.uuid4()}",
        json={"text": "Updated."},
    )
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Transcript segment not found"}

    invalid = history_client.patch(
        "/api/transcript-segments/not-a-uuid",
        json={"text": "Updated."},
    )
    assert invalid.status_code == 422


def test_delete_session_removes_all_related_segments(
    history_client: TestClient,
    sqlite_database: Database,
) -> None:
    deleted_session = uuid.uuid4()
    kept_session = uuid.uuid4()
    for sequence in range(3):
        _add_segment(
            sqlite_database,
            session_id=deleted_session,
            sequence=sequence,
            text=f"Deleted segment {sequence}.",
        )
    _add_segment(
        sqlite_database,
        session_id=kept_session,
        sequence=0,
        text="Kept segment.",
    )

    response = history_client.delete(
        f"/api/transcription-sessions/{deleted_session}"
    )

    assert response.status_code == 204
    assert response.content == b""

    with sqlite_database.session_scope() as session:
        remaining = session.scalar(
            select(func.count(Transcript.id)).where(
                Transcript.session_id == deleted_session
            )
        )
        assert remaining == 0
        kept = session.scalar(
            select(func.count(Transcript.id)).where(
                Transcript.session_id == kept_session
            )
        )
        assert kept == 1

    assert (
        history_client.get(
            f"/api/transcription-sessions/{deleted_session}"
        ).status_code
        == 404
    )
    assert (
        history_client.get(
            f"/api/transcription-sessions/{kept_session}"
        ).status_code
        == 200
    )

    missing = history_client.delete(
        f"/api/transcription-sessions/{deleted_session}"
    )
    assert missing.status_code == 404
    assert missing.json() == {
        "detail": "Transcription session not found"
    }


def test_history_endpoints_return_503_without_database(
    client: TestClient,
) -> None:
    session_id = uuid.uuid4()
    responses = [
        client.get("/api/transcription-sessions"),
        client.get(f"/api/transcription-sessions/{session_id}"),
        client.patch(
            f"/api/transcript-segments/{uuid.uuid4()}",
            json={"text": "Updated."},
        ),
        client.delete(f"/api/transcription-sessions/{session_id}"),
    ]

    for response in responses:
        assert response.status_code == 503
        assert response.json() == {"detail": "Database unavailable"}
        assert "DATABASE_URL" not in response.text


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"q": "x" * 201},
    ],
)
def test_list_sessions_validates_query_parameters(
    history_client: TestClient,
    params: dict,
) -> None:
    response = history_client.get(
        "/api/transcription-sessions",
        params=params,
    )

    assert response.status_code == 422


def test_live_final_segment_appears_in_history(
    migrated_sqlite_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_transcription(
        *,
        settings,
        chunks,
        language_codes,
        on_ready,
        on_event,
    ):
        await on_ready()
        emitted = False
        async for _chunk in chunks:
            if not emitted:
                await on_event(
                    TranscriptEvent(
                        kind="final",
                        text="Integrated final segment.",
                    )
                )
                emitted = True
        return LiveSummary(
            interim_count=0,
            final_count=1 if emitted else 0,
        )

    monkeypatch.setattr(
        "app.live.run_transcription",
        fake_run_transcription,
    )
    app = create_app(
        AppSettings(environment="test", log_level="CRITICAL"),
        DatabaseSettings(url=migrated_sqlite_url),
    )
    app.state.live_runner = LiveTranscriptionRunner(
        transcript_service=app.state.transcript_service,
        database=app.state.database,
        settings_loader=lambda: object(),
    )

    with TestClient(app) as client:
        with client.websocket_connect(
            "/ws/transcribe?language_codes=en-IN"
        ) as websocket:
            ready = websocket.receive_json()
            assert ready["type"] == "ready"
            session_id = ready["session_id"]

            websocket.send_bytes(b"\x00" * 3200)
            final = websocket.receive_json()
            assert final["type"] == "final"
            assert final["text"] == "Integrated final segment."

            websocket.send_text('{"type":"stop"}')
            completed = websocket.receive_json()
            assert completed["type"] == "completed"
            assert completed["final_count"] == 1

        listed = client.get(
            "/api/transcription-sessions",
            params={"q": "integrated"},
        )
        assert listed.status_code == 200
        payload = listed.json()
        assert payload["total"] == 1
        assert payload["sessions"][0]["session_id"] == session_id
        assert payload["sessions"][0]["preview"] == (
            "Integrated final segment."
        )

        detail = client.get(
            f"/api/transcription-sessions/{session_id}"
        )
        assert detail.status_code == 200
        assert detail.json()["segments"][0]["text"] == (
            "Integrated final segment."
        )
