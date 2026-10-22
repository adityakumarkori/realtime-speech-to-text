import inspect
from importlib.metadata import version

from google import genai
from google.genai import types
from google.genai.client import AsyncClient
from google.genai.live import AsyncLive, AsyncSession

from poc.gemini_live import _build_config


def test_pinned_google_genai_version():
    assert version("google-genai") == "2.32.0"


def test_transcription_config_fields():
    fields = types.AudioTranscriptionConfig.model_fields
    assert "language_codes" in fields
    assert "mode" in fields

    config = _build_config(types, ["hi-IN", "en-IN"])
    assert config.response_modalities == ["TEXT"]
    assert config.input_audio_transcription is not None
    assert config.input_audio_transcription.language_codes == ["hi-IN", "en-IN"]
    assert config.input_audio_transcription.mode is not None


def test_server_content_transcription_fields():
    fields = types.LiveServerContent.model_fields
    assert "interim_input_transcription" in fields
    assert "input_transcription" in fields


def test_realtime_audio_send_fields():
    fields = types.Blob.model_fields
    assert "data" in fields
    assert "mime_type" in fields

    blob = types.Blob(data=b"\x00\x00", mime_type="audio/pcm;rate=16000")
    assert blob.data == b"\x00\x00"

    parameters = inspect.signature(AsyncSession.send_realtime_input).parameters
    assert "audio" in parameters
    assert "audio_stream_end" in parameters


def test_live_session_api_is_available():
    assert hasattr(AsyncLive, "connect")
    assert hasattr(AsyncSession, "receive")
    assert hasattr(AsyncSession, "send_realtime_input")
    assert "setup_complete" in inspect.signature(AsyncSession.__init__).parameters
    assert hasattr(genai.Client, "aio")
    assert hasattr(AsyncClient, "__aenter__")
    assert hasattr(AsyncClient, "__aexit__")
