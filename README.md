# Real-time speech-to-text

Minimal backend for streaming microphone or pre-recorded audio to
`gemini-3.5-transcribe-live` through the Gemini Live API. The Phase 0 CLI prints
low-latency interim hypotheses and finalized transcript segments. Phase 1 adds a
FastAPI service foundation with configuration, logging, error handling, and a
health endpoint. Phase 2 adds PostgreSQL transcript persistence with SQLAlchemy
and Alembic migrations.

The project has no frontend, authentication, Docker setup, Gemini HTTP/WebSocket
endpoints, or public transcript API. Finalized segments can be persisted
through an internal service layer; the Phase 0 CLI does not write to the
database.

## Verification status

Checked on 2026-10-22 on Windows 11 with Python 3.12.7,
`google-genai==2.32.0`, `fastapi==0.159.1`, `sqlalchemy==2.1.6`,
`psycopg==3.3.6`, and `alembic==1.20.1`:

- 79 tests pass, covering the Phase 0 pipeline, a pinned-SDK contract test, a
  fake-session orchestration test, CLI device validation, and Phase 1 app
  configuration, health, and error behavior.
- Phase 2 tests cover database configuration, degraded startup, transcript
  persistence and constraints, SQLite migration upgrade/downgrade, and a
  PostgreSQL migration/constraint round-trip against a local PostgreSQL 17
  test database.
- A Live API session was established with `gemini-3.5-transcribe-live`.
- Manual live-microphone verification produced 46 interim updates and 3
  finalized segments while speaking English, Hindi, and Hinglish. This is a
  manual functional check, not a formal accuracy benchmark.
- Earlier synthetic English diagnostics produced 28 interim updates and 3
  finalized segments through speaker playback, and 19 interim updates and 1
  finalized segment from a WAV file.
- The default Intel microphone array captured no usable audio; a working input
  selected with `--device` was required on this machine.
- `GET /health` returns HTTP 200 with `{"status":"ok"}` without contacting
  Gemini, requiring an API key, or requiring a database URL.
- The documented 10-minute session limit was not exercised.
- Missing API key still produces a clear error with exit code `2` in the CLI.

Phase 0 is functional for English, Hindi, and Hinglish microphone input. No
formal word-error-rate or multilingual accuracy benchmark has been run. No
audio or transcript content was written to the repository.

## Requirements

- Python 3.12 (the version tested here)
- A Gemini API key from Google AI Studio
- A microphone, or a 16 kHz mono PCM16 WAV/raw PCM file
- PostgreSQL 17 for transcript persistence and migrations; the FastAPI app
  still starts without a database URL, but persistence is disabled

## Setup

From `D:\Aditya\Projects\RealTimeTranscriptionApp`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r backend\requirements-dev.txt
Copy-Item backend\.env.example backend\.env
```

Edit `backend/.env` and replace the Gemini placeholder. Uncomment and set
`DATABASE_URL` to enable transcript persistence:

```dotenv
APP_ENV=development
LOG_LEVEL=INFO
GEMINI_API_KEY=your_real_key_here
GEMINI_LIVE_MODEL=gemini-3.5-transcribe-live
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/realtime_transcription
# TEST_DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/realtime_transcription_test
```

`APP_ENV`, `LOG_LEVEL`, `GEMINI_LIVE_MODEL`, and `DATABASE_URL` are optional.
Never commit `backend/.env`; it is ignored by Git. The Gemini key is read only by
the Phase 0 CLI through `backend/poc/config.py`; the FastAPI app does not use or
require it. Database URLs are redacted and never printed. Secrets are never
printed.

If PyPI times out, retry the install. On this machine the install succeeded
with a trusted HTTPS mirror for that command only:

```powershell
.\.venv\Scripts\python.exe -m pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple -r backend\requirements.txt -r backend\requirements-dev.txt
```

## FastAPI service (Phases 1-2)

The application exposes only `GET /health`; it does not import the Phase 0 POC,
contact Gemini, expose Gemini HTTP/WebSocket endpoints, or expose public
transcript routes. Final transcript segments can be persisted through the
internal `TranscriptService`, which uses one row per finalized segment.

If `DATABASE_URL` is missing or blank, the app starts with a warning and
transcript persistence disabled. If it is present, the database engine is
created during application startup and disposed during shutdown. The health
endpoint never connects to the database.

Start the service from the project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

From `backend`, use `python -m uvicorn app.main:app --reload`. From
`backend/app`, use `python -m uvicorn app.main:app --app-dir .. --reload`. Do not
use `main:app` from `backend/app`, because that directory is not the package
root.

In another shell, verify the endpoint:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

Stop the server with `Ctrl+C`. Interactive API documentation is available at
`http://127.0.0.1:8000/docs` while it is running. The health check does not
contact Gemini, require `GEMINI_API_KEY`, or require `DATABASE_URL`.

The application package is organized as:

```text
backend/app/
  config.py        app and redacted database configuration
  database.py      engine, sessions, and transaction scope
  models.py        transcript table model
  repositories.py  transcript data access
  services.py      final-segment validation and persistence
  logging_config.py idempotent console logging setup
  errors.py        {"detail": "..."} error responses
  main.py          create_app(), lifespan, and the ASGI app
  routes/health.py GET /health
```

Unhandled errors return HTTP 500 with a generic
`{"detail":"Internal server error"}` response. Missing database configuration
returns HTTP 503 if a database-backed operation reaches a request. The server
logs the HTTP method and path, but not request bodies, credentials, database
URLs, or transcript content.

## Database migrations

Alembic is the schema source of truth. The initial migration creates the
`transcripts` table with UUID identifiers, sequence ordering, language codes,
timestamps, uniqueness, and check constraints. The application does not call
`create_all()` or run migrations automatically at startup.

Set `DATABASE_URL` first, then run:

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini upgrade head
```

To inspect or roll back:

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini current
.\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini downgrade base
```

`TEST_DATABASE_URL` is separate and is used only by PostgreSQL tests. It must
name a dedicated disposable test database and must differ from `DATABASE_URL`.
PostgreSQL tests create and drop a randomly named schema; they do not modify the
`public` schema. If `TEST_DATABASE_URL` is unset, those tests are skipped.

## Phase 0 CLI

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

No audio or transcript is written to disk by the Phase 0 CLI. The CLI is not
connected to the Phase 2 persistence service.

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

| Variable | Used by | Required | Default |
| --- | --- | --- | --- |
| `APP_ENV` | FastAPI app | No | `development` |
| `LOG_LEVEL` | FastAPI app | No | `INFO` |
| `DATABASE_URL` | FastAPI app and Alembic | No for app; yes for migrations | None |
| `TEST_DATABASE_URL` | PostgreSQL tests | No; yes to run them | None |
| `GEMINI_API_KEY` | Phase 0 CLI | Yes for the CLI | None |
| `GEMINI_LIVE_MODEL` | Phase 0 CLI | No | `gemini-3.5-transcribe-live` |

`APP_ENV` accepts `development`, `test`, or `production` and is normalized to
lowercase. `LOG_LEVEL` accepts `CRITICAL`, `ERROR`, `WARNING`, `INFO`, or
`DEBUG` and is normalized to uppercase. Invalid values stop startup with a
clear configuration error.

`DATABASE_URL` must use the installed psycopg driver, for example
`postgresql+psycopg://user:password@host:5432/database`. A missing or blank
value starts the app with persistence disabled. An invalid or placeholder value
stops startup without printing the URL.

`TEST_DATABASE_URL` is test-only. It must point to a dedicated disposable
database whose name contains `test`, and it must differ from `DATABASE_URL`.
The PostgreSQL tests use temporary schemas and remove only those schemas.

Process environment values take precedence over `backend/.env` for the FastAPI
app, Alembic, tests, and the CLI. Missing, blank, and placeholder Gemini keys are
rejected by the CLI before any network request. The FastAPI app does not require
any Gemini setting.

Use `--language auto` (the default) to omit language hints and let the model
detect language. `--language hi-IN,en-IN` supplies hints for Hindi and English
(India). Hinglish is not a separate language code; mixed-language support
depends on automatic detection and must be tested with representative audio.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The suite covers Phase 0 configuration validation and redaction, WAV/PCM
validation, chunking, transcript event extraction, fake-session orchestration,
CLI device validation, and the installed `google-genai` contract. It also covers
Phase 1 app configuration, `/health`, and HTTP/error responses, plus Phase 2
database configuration, degraded startup, persistence, constraints, and SQLite
migration upgrades and downgrades. Tests do not call Gemini or other external
network services.

To run the optional PostgreSQL integration test, set a separate disposable test
database:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://user:password@localhost:5432/realtime_transcription_test"
.\.venv\Scripts\python.exe -m pytest
```

The PostgreSQL test is skipped when `TEST_DATABASE_URL` is not set.

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

- **`DATABASE_URL is not set; transcript persistence is disabled`:** This is
  expected without a database. Set `DATABASE_URL` and run the Alembic upgrade.
- **`DATABASE_URL must be set to run database migrations`:** Set the URL before
  running Alembic. The application itself can start without it.
- **PostgreSQL test is skipped:** Set `TEST_DATABASE_URL` to a dedicated
  disposable test database. Do not point it at a production database.
- **Database connection or migration failure:** Verify PostgreSQL is running,
  the URL uses `postgresql+psycopg://`, the database exists, and migrations have
  been applied.
- **`ModuleNotFoundError: No module named 'app'`:** Start Uvicorn from the
  project root or `backend`, not from `backend/app` with `main:app`.
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
