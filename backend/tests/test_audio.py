import asyncio
import wave
from pathlib import Path

import pytest

from poc import audio as audio_module
from poc.audio import (
    CHUNK_BYTES,
    AudioInputError,
    PcmAudio,
    iter_chunks,
    iter_file_chunks,
    load_audio,
)


def _write_wav(
    path: Path,
    frames: bytes,
    *,
    channels: int = 1,
    sample_width: int = 2,
    sample_rate: int = 16_000,
) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(frames)


def test_load_valid_wav(tmp_path):
    path = tmp_path / "sample.wav"
    _write_wav(path, b"\x00" * 3_200)

    audio = load_audio(path)

    assert audio.data == b"\x00" * 3_200
    assert audio.duration_seconds == pytest.approx(0.1)


def test_load_valid_raw_pcm(tmp_path):
    path = tmp_path / "sample.pcm"
    path.write_bytes(b"\x01\x00" * 1_600)

    audio = load_audio(path)

    assert audio.duration_seconds == pytest.approx(0.1)


def test_missing_file_raises(tmp_path):
    with pytest.raises(AudioInputError, match="not found"):
        load_audio(tmp_path / "missing.wav")


def test_unsupported_extension_raises(tmp_path):
    path = tmp_path / "sample.mp3"
    path.write_bytes(b"not audio")
    with pytest.raises(AudioInputError, match="Unsupported audio format"):
        load_audio(path)


def test_empty_file_raises(tmp_path):
    path = tmp_path / "sample.pcm"
    path.write_bytes(b"")
    with pytest.raises(AudioInputError, match="empty"):
        load_audio(path)


def test_odd_pcm_byte_count_raises(tmp_path):
    path = tmp_path / "sample.pcm"
    path.write_bytes(b"\x00\x00\x00")
    with pytest.raises(AudioInputError, match="16-bit"):
        load_audio(path)


def test_stereo_wav_raises(tmp_path):
    path = tmp_path / "sample.wav"
    _write_wav(path, b"\x00" * 3_200, channels=2)
    with pytest.raises(AudioInputError, match="mono"):
        load_audio(path)


def test_wrong_wav_sample_rate_raises(tmp_path):
    path = tmp_path / "sample.wav"
    _write_wav(path, b"\x00" * 3_200, sample_rate=8_000)
    with pytest.raises(AudioInputError, match="16000 Hz"):
        load_audio(path)


def test_wrong_wav_sample_width_raises(tmp_path):
    path = tmp_path / "sample.wav"
    _write_wav(path, b"\x00" * 1_600, sample_width=1)
    with pytest.raises(AudioInputError, match="16-bit"):
        load_audio(path)


def test_invalid_wav_bytes_raise(tmp_path):
    path = tmp_path / "sample.wav"
    path.write_bytes(b"not a wav")
    with pytest.raises(AudioInputError, match="Could not read WAV"):
        load_audio(path)


def test_audio_longer_than_session_limit_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(audio_module, "MAX_SESSION_SECONDS", 0.1)
    path = tmp_path / "sample.pcm"
    path.write_bytes(b"\x00\x00" * 2_000)
    with pytest.raises(AudioInputError, match="Live transcription limit"):
        load_audio(path)


def test_iter_chunks_uses_exact_sizes():
    data = b"x" * (CHUNK_BYTES * 2 + 100)
    chunks = list(iter_chunks(data))
    assert [len(chunk) for chunk in chunks] == [CHUNK_BYTES, CHUNK_BYTES, 100]
    assert b"".join(chunks) == data


def test_iter_file_chunks_preserves_data(monkeypatch):
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(audio_module.asyncio, "sleep", no_sleep)
    data = b"\x00" * (CHUNK_BYTES + 100)
    audio = PcmAudio(data=data)

    async def collect():
        return b"".join([chunk async for chunk in iter_file_chunks(audio)])

    assert asyncio.run(collect()) == data
