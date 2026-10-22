from types import SimpleNamespace

from poc.transcripts import extract_events


def _content(interim=None, final=None):
    return SimpleNamespace(
        interim_input_transcription=interim,
        input_transcription=final,
    )


def test_extract_interim_event():
    content = _content(interim=SimpleNamespace(text="hello"))
    events = extract_events(content)
    assert len(events) == 1
    assert events[0].kind == "interim"
    assert events[0].text == "hello"


def test_extract_final_event():
    content = _content(final=SimpleNamespace(text="hello there"))
    events = extract_events(content)
    assert len(events) == 1
    assert events[0].kind == "final"
    assert events[0].text == "hello there"


def test_extract_both_events_in_order():
    content = _content(
        interim=SimpleNamespace(text="नमस्ते"),
        final=SimpleNamespace(text="नमस्ते, hello"),
    )
    events = extract_events(content)
    assert [(event.kind, event.text) for event in events] == [
        ("interim", "नमस्ते"),
        ("final", "नमस्ते, hello"),
    ]


def test_extract_ignores_missing_and_blank_events():
    assert extract_events(None) == []
    assert extract_events(_content()) == []
    assert extract_events(
        _content(
            interim=SimpleNamespace(text="   "),
            final=SimpleNamespace(text=""),
        )
    ) == []
