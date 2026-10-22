# Real-time speech-to-text — Phase 0

Minimal backend proof of concept for streaming microphone or pre-recorded audio
to `gemini-3.5-transcribe-live` through the Gemini Live API. It prints
low-latency interim hypotheses and finalized transcript segments.

Phase 0 is intentionally small: no frontend, FastAPI service, database, auth,
Docker, or long-term storage.

## Verification status

Checked on 2026-10-22 on Windows 11 with Python 3.12.7 and
`google-genai==2.32.0`:

- 39 offline tests pass, including a pinned-SDK contract test, a fake-session
  orchestration test, and CLI device validation.
- A Live API session was established with `gemini-3.5-transcribe-live`.
- The live microphone pipeline succeeded using device 2, the External
  Microphone (Realtek), with synthetic English text-to-speech played through
  the speakers: 28 interim updates, 3 finalized segments, exit code `0`.
- A synthetic English WAV file produced 19 interim updates and 1 finalized
  segment, exit code `0`.
- The default Intel microphone array captured no usable audio; `--device 2` was
  required on this machine.
- **Human-spoken English, Hindi, and Hinglish were not tested.** Hindi and
  Hinglish accuracy remain unverified.
- The documented 10-minute session limit was not exercised.
- Missing API key still produces a clear error with exit code `2`.

Phase 0 is verified for the Live API and microphone pipeline, but not fully
verified for human multilingual use. No audio or transcript content was
written to the repository.

## Requirements

- Python 3.12 (the version tested here)
- A Gemini API key from Google AI Studio
- A microphone, or a 16 kHz mono PCM16 WAV/raw PCM file

## Setup

From `D:\Aditya\Projects\RealTimeTranscriptionApp`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r backend\requirements-dev.txt
Copy-Item backend\.env.example backend\.env
```

Edit `backend/.env` and replace the placeholder:

```dotenv
GEMINI_API_KEY=your_real_key_here
GEMINI_LIVE_MODEL=gemini-3.5-transcribe-live
```

`GEMINI_LIVE_MODEL` is optional and defaults to
`gemini-3.5-transcribe-live`. Never commit `backend/.env`; it is ignored by
Git. The key is read only by the backend process and is never printed.

If PyPI times out, retry the install. On this machine the install succeeded
with a trusted HTTPS mirror for that command only:

```powershell
.\.venv\Scripts\python.exe -m pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple -r backend\requirements.txt -r backend\requirements-dev.txt
```

## Run

List microphone-capable devices:

```powershell
.\.venv\Scripts\python.exe backend\scripts\test_gemini_live.py --list-devices
```

Transcribe the default microphone for 30 seconds with automatic language
detection:

```powershell
.\.venv\Scripts\python.exe backend\scripts\test_gemini_live.py --input mic --seconds 30
```

If the default microphone is silent, select an index printed by
`--list-devices`:

```powershell
.\.venv\Scripts\python.exe backend\scripts\test_gemini_live.py --input mic --device 2 --seconds 30
```

`--device` is valid only with microphone input. Stream until `Ctrl+C` (or the
10-minute session limit):

```powershell
.\.venv\Scripts\python.exe backend\scripts\test_gemini_live.py --seconds 0
```

Bias detection toward Hindi and English (India):

```powershell
.\.venv\Scripts\python.exe backend\scripts\test_gemini_live.py --input mic --language hi-IN,en-IN
```

Use a file:

```powershell
.\.venv\Scripts\python.exe backend\scripts\test_gemini_live.py --input C:\audio\sample.wav
.\.venv\Scripts\python.exe backend\scripts\test_gemini_live.py --input C:\audio\sample.pcm
```

Use `--flush-timeout` to change how long the client waits for finalized
segments after the audio ends (default: 8 seconds). Use `--debug` for an
unexpected-failure traceback.

Expected output shape:

```text
Live session established with gemini-3.5-transcribe-live.
[interim] ...
[final] ...
Interim updates: 12; final segments: 2.
Final 1: ...
Final 2: ...
```

No audio or transcript is written to disk.

## Audio format

- 16,000 Hz sample rate
- Mono
- Signed 16-bit little-endian PCM
- 100 ms chunks: 1,600 frames / 3,200 bytes
- Live MIME type: `audio/pcm;rate=16000`
- Maximum session duration: 600 seconds

A `.wav` file must be uncompressed PCM16, mono, and exactly 16 kHz. Raw
`.pcm` files are assumed to already be in that format. To convert another audio
file with FFmpeg:

```powershell
ffmpeg -i input.mp3 -ar 16000 -ac 1 -c:a pcm_s16le output.wav
```

File streaming is paced in real time to mimic a microphone. The CLI sends an
`audio_stream_end` signal after the input finishes, waits briefly for final
transcripts, then closes the session and microphone stream.

## Configuration

| Variable | Required | Default |
| --- | --- | --- |
| `GEMINI_API_KEY` | Yes | None |
| `GEMINI_LIVE_MODEL` | No | `gemini-3.5-transcribe-live` |

Process environment values take precedence over `backend/.env`. Missing,
blank, and placeholder keys are rejected before any network request.

Use `--language auto` (the default) to omit language hints and let the model
detect language. `--language hi-IN,en-IN` supplies hints for Hindi and English
(India). Hinglish is not a separate language code; mixed-language support
depends on automatic detection and must be tested with representative audio.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The suite covers configuration validation and redaction, WAV/PCM validation,
chunking, transcript event extraction, fake-session orchestration, CLI device
validation, and the installed `google-genai` contract (version, config fields,
response fields, send/receive methods, and async client context management).
Tests do not call the network.

## Limits and cost

Documented Live transcription limits:

- Sessions last at most 10 minutes. Reconnect for longer audio.
- Live streaming does not support speaker diarization or word-level
  timestamps. The model emits utterance-level interim and final text.
- Interim text is speculative and can change; only `input_transcription` is
  authoritative.
- The free tier is listed as free of charge, but free-tier content may be used
  to improve Google products. Actual rate limits and quotas are shown per
  project in AI Studio rather than as fixed public values.
- The pricing page checked on 2026-10-22 lists `$3.50` per 1M audio input
  tokens and `$21` per 1M text output tokens for this model. Token usage and
  the resulting per-minute cost vary with audio and output length; the
  commonly cited estimate is roughly `$0.009` per minute. Confirm current
  pricing before relying on it.

## Troubleshooting

- **`GEMINI_API_KEY is not set` / exit code 2:** Create `backend/.env` from
  `backend/.env.example` and add a real key, or set the environment variable.
- **`No usable microphone at 16000 Hz...`:** Use `--list-devices`, make a
  supported microphone the Windows default, or pass a WAV/PCM file.
- **Default microphone captures silence:** Use `--list-devices` and pass a
  working input with `--device INDEX`. On the verification machine the default
  Intel array was silent and device `2` was used.
- **No finalized transcript / exit code 1:** Check that speech is audible,
  stream for longer, verify credentials and quota, and retry with `--debug`.
- **Install timeouts:** Retry pip. If PyPI remains unreachable, use a trusted
  HTTPS mirror for the install command only.
- **Session ends near 10 minutes:** This is the documented Live API limit, not
  a client bug.

## Official references

- Live transcription:
  https://ai.google.dev/gemini-api/docs/live-api/live-transcribe
- Session management and 10-minute limit:
  https://ai.google.dev/gemini-api/docs/live-api/session-management
- Pricing:
  https://ai.google.dev/gemini-api/docs/pricing
