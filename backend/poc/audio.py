import asyncio
import wave
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path

SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
CHUNK_FRAMES = 1_600
CHUNK_BYTES = CHUNK_FRAMES * SAMPLE_WIDTH_BYTES * CHANNELS
MAX_SESSION_SECONDS = 600
FRAME_BYTES = SAMPLE_RATE * SAMPLE_WIDTH_BYTES * CHANNELS
MIME_TYPE = f"audio/pcm;rate={SAMPLE_RATE}"


class AudioInputError(ValueError):
    pass


@dataclass(frozen=True)
class PcmAudio:
    data: bytes

    @property
    def duration_seconds(self) -> float:
        return len(self.data) / FRAME_BYTES


def load_audio(path: Path) -> PcmAudio:
    source = Path(path).expanduser()
    if not source.is_file():
        raise AudioInputError(f"Audio file not found: {source}")

    suffix = source.suffix.lower()
    if suffix == ".wav":
        data = _read_wav(source)
    elif suffix == ".pcm":
        try:
            data = source.read_bytes()
        except OSError as exc:
            raise AudioInputError(f"Could not read {source}: {exc}") from exc
    else:
        raise AudioInputError(
            f"Unsupported audio format {suffix!r}. Use a 16 kHz mono "
            "PCM16 .wav file or a raw .pcm file."
        )

    if not data:
        raise AudioInputError(f"Audio file is empty: {source}")
    if len(data) % SAMPLE_WIDTH_BYTES != 0:
        raise AudioInputError(
            "Audio byte count is not aligned to 16-bit samples."
        )

    audio = PcmAudio(data=data)
    if audio.duration_seconds > MAX_SESSION_SECONDS:
        raise AudioInputError(
            f"Audio is {audio.duration_seconds:.1f}s long; the Live "
            f"transcription limit is {MAX_SESSION_SECONDS}s per session."
        )
    return audio


def _read_wav(path: Path) -> bytes:
    try:
        with wave.open(str(path), "rb") as wav_file:
            if wav_file.getnchannels() != CHANNELS:
                raise AudioInputError(
                    f"WAV must be mono; found {wav_file.getnchannels()} channels."
                )
            if wav_file.getsampwidth() != SAMPLE_WIDTH_BYTES:
                raise AudioInputError(
                    "WAV must use 16-bit samples; found "
                    f"{wav_file.getsampwidth() * 8}-bit samples."
                )
            if wav_file.getframerate() != SAMPLE_RATE:
                raise AudioInputError(
                    f"WAV must use {SAMPLE_RATE} Hz; found "
                    f"{wav_file.getframerate()} Hz."
                )
            if wav_file.getcomptype() != "NONE":
                raise AudioInputError(
                    "Compressed WAV files are unsupported; use PCM16."
                )
            return wav_file.readframes(wav_file.getnframes())
    except AudioInputError:
        raise
    except (wave.Error, EOFError, OSError) as exc:
        raise AudioInputError(f"Could not read WAV file {path}: {exc}") from exc


def iter_chunks(data: bytes) -> Iterator[bytes]:
    for offset in range(0, len(data), CHUNK_BYTES):
        yield data[offset : offset + CHUNK_BYTES]


async def iter_file_chunks(audio: PcmAudio) -> AsyncIterator[bytes]:
    chunks = iter_chunks(audio.data)
    try:
        current = next(chunks)
    except StopIteration:
        return

    while True:
        try:
            following = next(chunks)
        except StopIteration:
            yield current
            return

        yield current
        await asyncio.sleep(len(current) / FRAME_BYTES)
        current = following


def _load_sounddevice():
    try:
        import sounddevice
    except (ImportError, OSError) as exc:
        raise AudioInputError(
            "Microphone support is unavailable. Install requirements.txt "
            "and verify PortAudio can access an input device."
        ) from exc
    return sounddevice


def list_input_devices() -> list[str]:
    sounddevice = _load_sounddevice()
    try:
        devices = sounddevice.query_devices()
    except Exception as exc:
        raise AudioInputError(f"Could not query audio devices: {exc}") from exc

    result: list[str] = []
    for index, device in enumerate(devices):
        if device["max_input_channels"] < 1:
            continue
        result.append(
            f"{index}: {device['name']} "
            f"({device['max_input_channels']} ch, "
            f"{int(device['default_samplerate'])} Hz)"
        )
    return result


def check_microphone(device: int | str | None = None) -> None:
    sounddevice = _load_sounddevice()
    try:
        sounddevice.check_input_settings(
            device=device,
            channels=CHANNELS,
            dtype="int16",
            samplerate=SAMPLE_RATE,
        )
    except Exception as exc:
        raise AudioInputError(
            f"No usable microphone at {SAMPLE_RATE} Hz mono PCM16: {exc}. "
            "Use --input with a WAV/PCM file or --list-devices."
        ) from exc


async def microphone_chunks(
    max_seconds: float = 30.0,
    device: int | str | None = None,
) -> AsyncIterator[bytes]:
    if max_seconds < 0:
        raise AudioInputError("Microphone duration must not be negative.")
    if max_seconds > MAX_SESSION_SECONDS:
        raise AudioInputError(
            f"Microphone duration exceeds the {MAX_SESSION_SECONDS}s "
            "Live API session limit."
        )

    sounddevice = _load_sounddevice()
    check_microphone(device)

    try:
        stream = sounddevice.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=CHUNK_FRAMES,
            channels=CHANNELS,
            dtype="int16",
            device=device,
        )
    except Exception as exc:
        raise AudioInputError(f"Could not open the microphone: {exc}") from exc

    limit = MAX_SESSION_SECONDS if max_seconds == 0 else max_seconds
    loop = asyncio.get_running_loop()
    started_at = loop.time()

    with stream:
        while loop.time() - started_at < limit:
            try:
                buffer, _overflowed = await asyncio.to_thread(
                    stream.read, CHUNK_FRAMES
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                raise AudioInputError(
                    f"Failed while reading from the microphone: {exc}"
                ) from exc
            yield bytes(buffer)
