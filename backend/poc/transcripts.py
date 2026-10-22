from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TranscriptEvent:
    kind: Literal["interim", "final"]
    text: str


def extract_events(server_content) -> list[TranscriptEvent]:
    if server_content is None:
        return []

    events: list[TranscriptEvent] = []
    interim = getattr(server_content, "interim_input_transcription", None)
    if interim is not None:
        text = getattr(interim, "text", None)
        if text and text.strip():
            events.append(TranscriptEvent(kind="interim", text=text))

    final = getattr(server_content, "input_transcription", None)
    if final is not None:
        text = getattr(final, "text", None)
        if text and text.strip():
            events.append(TranscriptEvent(kind="final", text=text))

    return events
