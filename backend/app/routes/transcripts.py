import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services import TranscriptService, TranscriptValidationError

router = APIRouter(prefix="/api", tags=["transcripts"])


class TranscriptSegmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    sequence: int
    text: str
    language_code: str | None
    created_at: datetime


class SessionSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: uuid.UUID
    started_at: datetime
    ended_at: datetime
    segment_count: int
    preview: str
    language_codes: list[str]


class SessionListResponse(BaseModel):
    sessions: list[SessionSummaryResponse]
    total: int
    limit: int
    offset: int


class SessionDetailResponse(BaseModel):
    session_id: uuid.UUID
    started_at: datetime
    ended_at: datetime
    segment_count: int
    segments: list[TranscriptSegmentResponse]


class TranscriptUpdateRequest(BaseModel):
    text: str = Field(min_length=1)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Transcript text must not be blank.")
        return normalized


def _service(request: Request) -> TranscriptService:
    return request.app.state.transcript_service


@router.get(
    "/transcription-sessions",
    response_model=SessionListResponse,
    summary="List transcription sessions",
)
def list_transcription_sessions(
    request: Request,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> SessionListResponse:
    page = _service(request).list_sessions(
        limit=limit,
        offset=offset,
        search=q,
    )
    return SessionListResponse(
        sessions=[
            SessionSummaryResponse.model_validate(item)
            for item in page.sessions
        ],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/transcription-sessions/{session_id}",
    response_model=SessionDetailResponse,
    summary="Get a transcription session",
)
def get_transcription_session(
    request: Request,
    session_id: uuid.UUID,
) -> SessionDetailResponse:
    segments = _service(request).list_for_session(session_id)
    if not segments:
        raise HTTPException(
            status_code=404,
            detail="Transcription session not found",
        )
    return SessionDetailResponse(
        session_id=session_id,
        started_at=min(segment.created_at for segment in segments),
        ended_at=max(segment.created_at for segment in segments),
        segment_count=len(segments),
        segments=[
            TranscriptSegmentResponse.model_validate(segment)
            for segment in segments
        ],
    )


@router.patch(
    "/transcript-segments/{transcript_id}",
    response_model=TranscriptSegmentResponse,
    summary="Update a finalized transcript segment",
)
def update_transcript_segment(
    request: Request,
    transcript_id: uuid.UUID,
    payload: TranscriptUpdateRequest,
) -> TranscriptSegmentResponse:
    try:
        transcript = _service(request).update_transcript(
            transcript_id,
            payload.text,
        )
    except TranscriptValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if transcript is None:
        raise HTTPException(
            status_code=404,
            detail="Transcript segment not found",
        )
    return TranscriptSegmentResponse.model_validate(transcript)


@router.delete(
    "/transcription-sessions/{session_id}",
    status_code=204,
    summary="Delete a transcription session",
)
def delete_transcription_session(
    request: Request,
    session_id: uuid.UUID,
) -> Response:
    deleted = _service(request).delete_session(session_id)
    if deleted == 0:
        raise HTTPException(
            status_code=404,
            detail="Transcription session not found",
        )
    return Response(status_code=204)
