import argparse
import asyncio
import math
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from poc.audio import (
    MAX_SESSION_SECONDS,
    AudioInputError,
    check_microphone,
    iter_file_chunks,
    list_input_devices,
    load_audio,
    microphone_chunks,
)
from poc.config import (
    ConfigurationError,
    load_settings,
    parse_language_codes,
)
from poc.gemini_live import (
    DEFAULT_FLUSH_TIMEOUT_SECONDS,
    GeminiLiveError,
    run_transcription,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Stream microphone, WAV, or PCM audio to gemini-3.5-transcribe-live "
            "and print interim and final transcripts."
        )
    )
    parser.add_argument(
        "--input",
        default="mic",
        metavar="SOURCE",
        help="'mic', a 16 kHz mono PCM16 .wav file, or a raw .pcm file.",
    )
    parser.add_argument(
        "--device",
        type=int,
        default=None,
        metavar="INDEX",
        help="Microphone device index from --list-devices (microphone only).",
    )
    parser.add_argument(
        "--language",
        default="auto",
        help=(
            "auto or comma-separated BCP-47 codes, for example "
            "hi-IN,en-IN. Auto-detection is recommended for Hinglish."
        ),
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=30.0,
        help="Microphone duration; 0 streams until Ctrl+C. Maximum 600.",
    )
    parser.add_argument(
        "--flush-timeout",
        type=float,
        default=DEFAULT_FLUSH_TIMEOUT_SECONDS,
        help="Seconds to wait for final transcripts after audio ends.",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List microphone-capable audio devices and exit.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print a traceback for unexpected failures.",
    )
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    if not math.isfinite(args.seconds) or args.seconds < 0:
        raise ConfigurationError("--seconds must be zero or a positive number.")
    if args.seconds > MAX_SESSION_SECONDS:
        raise ConfigurationError(
            f"--seconds cannot exceed the {MAX_SESSION_SECONDS}s session limit."
        )
    if not math.isfinite(args.flush_timeout) or args.flush_timeout < 0:
        raise ConfigurationError(
            "--flush-timeout must be zero or a positive number."
        )
    if args.device is not None and args.device < 0:
        raise ConfigurationError("--device must be zero or a positive integer.")
    if args.device is not None and args.input.lower() != "mic":
        raise ConfigurationError("--device is only valid with --input mic.")


async def _run(args: argparse.Namespace) -> int:
    if args.list_devices:
        devices = list_input_devices()
        if not devices:
            print("No microphone-capable audio devices were found.")
            return 1
        for device in devices:
            print(device)
        return 0

    _validate_args(args)
    settings = load_settings()
    language_codes = parse_language_codes(args.language)

    if args.input.lower() == "mic":
        check_microphone(args.device)
        device_note = (
            f" on device {args.device}" if args.device is not None else ""
        )
        print(
            f"Speak into the microphone{device_note}. "
            f"Streaming for {args.seconds or MAX_SESSION_SECONDS:.0f}s.",
            flush=True,
        )
        chunks = microphone_chunks(
            max_seconds=args.seconds,
            device=args.device,
        )
    else:
        audio = load_audio(Path(args.input))
        print(
            f"Streaming {audio.duration_seconds:.1f}s from {args.input}.",
            flush=True,
        )
        chunks = iter_file_chunks(audio)

    result = await run_transcription(
        settings=settings,
        chunks=chunks,
        language_codes=language_codes,
        flush_timeout=args.flush_timeout,
    )

    print(
        f"Interim updates: {result.interim_count}; "
        f"final segments: {len(result.final_transcripts)}."
    )
    for index, transcript in enumerate(result.final_transcripts, start=1):
        print(f"Final {index}: {transcript}")

    if not result.final_transcripts:
        print(
            "No finalized transcript was received. Check microphone input, "
            "audio content, credentials, and quota.",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("\nInterrupted; closing audio and Live API resources.", file=sys.stderr)
        return 130
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except AudioInputError as exc:
        print(f"Audio input error: {exc}", file=sys.stderr)
        return 2
    except GeminiLiveError as exc:
        print(f"Gemini Live error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Transcription failed: {exc}", file=sys.stderr)
        if args.debug:
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
