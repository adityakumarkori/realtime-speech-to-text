# Real-time speech-to-text

Minimal backend for streaming microphone or pre-recorded audio to
`gemini-3.5-transcribe-live` through the Gemini Live API. The Phase 0 CLI prints
low-latency interim hypotheses and finalized transcript segments. Phase 1 adds a
FastAPI service foundation with configuration, logging, error handling, and a
health endpoint. Phase 2 adds PostgreSQL transcript persistence with SQLAlchemy
and Alembic migrations. Phase 3 adds an unauthenticated, local-development
WebSocket endpoint that streams browser audio frames to Gemini Live and persists
only finalized transcript segments. Phase 4 adds a React and TypeScript
frontend that captures microphone audio, streams PCM16 frames over that
WebSocket, displays interim captions, and shows persisted final segments.
Phase 5 adds a database-backed REST history API and a dashboard for listing,
searching, viewing, editing, and deleting finalized transcription sessions.

The project has no authentication or Docker setup. The Phase 0 CLI and the
WebSocket endpoint both use Gemini Live. The WebSocket endpoint persists final
segments; the dashboard reads, edits, and deletes them through the REST API.
The Phase 0 CLI does not write to the database. The REST API is intended for
local development and must not be exposed to untrusted networks.

## Verification status

Checked on 2026-10-22 on Windows 11 with Python 3.12.7,
`google-genai==2.32.0`, `fastapi==0.159.1`, `sqlalchemy==2.1.6`,
`psycopg==3.3.6`, `alembic==1.20.1`, `websockets==16.1.1`, Node.js 24.14.0,
npm 11.9.0, React 19.3.1, Vite 8.3.5, TypeScript 6.0.3, and Vitest 4.1.12:

- 125 backend tests pass, covering the Phase 0 pipeline, a pinned-SDK contract
  test, a fake-session orchestration test, CLI device validation, Phase 1 app
  configuration, health, and error behavior, Phase 2 persistence and
  migrations, Phase 3 WebSocket streaming, and the Phase 5 history API.
  Language selection is persisted per finalized segment, including bilingual
  hints.
- Phase 2 tests cover database configuration, degraded startup, transcript
  persistence and constraints, SQLite migration upgrade/downgrade, and a
  PostgreSQL migration/constraint round-trip against a local PostgreSQL 17
  test database.
- Phase 3 tests cover optional Gemini callbacks, final-only persistence and
  sequence ordering, WebSocket readiness and framing, audio validation,
  protocol errors, missing configuration, database failures, client stop,
  shortened session timeout, and disconnect cleanup. They use fake Gemini
  sessions and do not call the Gemini API or other external services.
- Phase 5 backend tests cover session metadata and ordering, case-insensitive
  search with literal `%`/`_` handling, pagination and empty results, ordered
  session detail, edit normalization and blank rejection, 404/422 responses,
  deletion of all segments in a session, query validation, and the
  database-unavailable 503 response. An app-level fake-upstream WebSocket test
  confirms that a live final segment and its selected language code are
  persisted and returned by the history endpoints. When `TEST_DATABASE_URL` is
  configured, an additional PostgreSQL
  test exercises session summaries, search, editing, and deletion against a
  temporary schema; otherwise it is skipped.
- 54 frontend Vitest tests pass, covering PCM16 conversion and clipping,
  resampling from 8 kHz, 32 kHz, 44.1 kHz, and 48 kHz, exact frame construction,
  partial and multi-frame buffering, WebSocket message parsing, malformed
  messages, URL construction, session transitions, final ordering, errors,
  the history API client, and dashboard list/detail/search/edit/delete,
  in-app confirmation cancel/confirm, and completion-refresh flows.
- `npm run build` completes with TypeScript checks and a production Vite build.
- The Vite development server returned the page with HTTP 200. `GET /health`
  returned `{"status":"ok"}` both directly and through the Vite `/health` proxy.
  `GET /api/transcription-sessions` returned HTTP 200 both directly and through
  the Vite `/api` proxy. A WebSocket handshake through the Vite `/ws` proxy
  reached the FastAPI app and returned the expected `database_unavailable` error
  when persistence was deliberately disabled for that earlier check. No Gemini
  request was made.
- The full live path (browser microphone → Gemini Live → PostgreSQL → UI) was
  not exercised in this session. It requires an interactive microphone and a
  configured application `DATABASE_URL`; the automated environment did not have
  an interactive microphone. The history dashboard was tested with jsdom and
  mocked API responses, not in a live browser against new microphone audio.
- A security check confirmed `backend/.env` is ignored and untracked, no real
  credentials or database URLs are committed, and PostgreSQL tests leave no
  temporary schemas behind.
- A Live API session was established with `gemini-3.5-transcribe-live` from the
  Phase 0 CLI.
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
- The real 600-second WebSocket limit was not exercised end to end; the timeout
  path is automated with a shortened limit. The WebSocket endpoint was verified
  with automated fake-session tests, not a manual browser session.
- Missing API key still produces a clear error with exit code `2` in the CLI and
  an `invalid_configuration` WebSocket error in the FastAPI app.
- Automated verification did not send audio or transcript content to disk or
  logs. No audio or transcript content was written to the repository.

Phase 0 is functional for English, Hindi, and Hinglish microphone input. No
formal word-error-rate or multilingual accuracy benchmark has been run. No
audio or transcript content was written to the repository.

## Requirements

- Python 3.12 (the version tested here)
- Node.js 20.19 or newer and npm (tested with Node.js 24.14.0 and npm 11.9.0)
- A Gemini API key from Google AI Studio for CLI or WebSocket transcription
- A microphone, or a 16 kHz mono PCM16 WAV/raw PCM file
- PostgreSQL 17 for transcript persistence, WebSocket streaming, and migrations;
  the FastAPI app and `/health` still start without a database URL
- The pinned `websockets` package, installed from `backend/requirements.txt`, for
  the WebSocket transport

## Setup

From `D:\Aditya\Projects\RealTimeTranscriptionApp`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r backend\requirements-dev.txt
Copy-Item backend\.env.example backend\.env
npm --prefix frontend install
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
Never commit `backend/.env`; it is ignored by Git. The Gemini key is read only
on the server for the Phase 0 CLI and Phase 3 WebSocket endpoint. The FastAPI app
starts without a Gemini key, but `/ws/transcribe` returns an
`invalid_configuration` error if the key is missing when a session starts.
Database URLs are redacted and never printed. Secrets and transcript content are
never logged.

If PyPI times out, retry the install. On this machine the install succeeded
with a trusted HTTPS mirror for that command only:

```powershell
.\.venv\Scripts\python.exe -m pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple -r backend\requirements.txt -r backend\requirements-dev.txt
```

## FastAPI service (Phases 1-5)

The application exposes `GET /health`, the local-development WebSocket endpoint
`/ws/transcribe`, and unauthenticated REST endpoints under `/api` for reading,
editing, and deleting finalized transcription history. Final transcript
segments are persisted through `TranscriptService`, which uses one row per
finalized segment. There is no separate session table; a session is the group
of finalized segments that share a `session_id`.

If `DATABASE_URL` is missing or blank, the app starts with a warning, but
`/ws/transcribe` rejects new sessions with `database_unavailable` because final
segments cannot be persisted. If it is present, the database engine is created
during application startup and disposed during shutdown. The health endpoint
never connects to the database or Gemini.

Start the service from the project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

From `backend`, use `python -m uvicorn app.main:app --reload`. From
`backend/app`, use `uvicorn main:app --reload` or
`python -m uvicorn app.main:app --app-dir .. --reload`.

In another shell, verify the endpoint:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

Stop the server with `Ctrl+C`. Interactive API documentation is available at
`http://127.0.0.1:8000/docs` while it is running. It lists `GET /health` and the
`/api` history routes; WebSocket routes are not part of OpenAPI. The health
check does not contact Gemini, require `GEMINI_API_KEY`, or require
`DATABASE_URL`.

### WebSocket transcription endpoint

Connect to the local-development endpoint:

```text
ws://127.0.0.1:8000/ws/transcribe?language_codes=auto
```

`language_codes` is optional and defaults to `auto`, which lets Gemini detect
the language. It may instead be a comma-separated list of BCP-47 hints such as
`hi-IN,en-IN`. The selected hints are saved as each finalized segment's
`language_code`; bilingual selections are stored comma-separated, while `auto`
leaves the field empty. After the connection is accepted, the server checks
database and Gemini configuration, then sends:

```json
{
  "type": "ready",
  "session_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
  "audio": {
    "encoding": "pcm_s16le",
    "sample_rate_hz": 16000,
    "channels": 1,
    "recommended_frame_bytes": 3200,
    "max_frame_bytes": 32000,
    "max_session_seconds": 600
  }
}
```

Send raw binary PCM16 little-endian, mono, 16 kHz audio frames. Frames must have
an even byte length and must not exceed 32,000 bytes; 3,200-byte frames (100 ms)
are recommended. Send the exact text frame `{"type":"stop"}` to finish normally.
The server emits interim and final JSON events:

```json
{"type":"interim","session_id":"...","text":"partial hypothesis"}
{"type":"final","session_id":"...","sequence":0,"text":"committed segment"}
```

Only final segments are persisted, and the final event is emitted only after the
database commit succeeds. `sequence` starts at `0` for each session and
increases after each successfully persisted final segment. When the stream ends
normally, the server sends:

```json
{"type":"completed","session_id":"...","final_count":1,"reason":"client_stop"}
```

`reason` is `client_stop` after a stop frame or `max_duration` when the
600-second session limit is reached. Errors use the same envelope:

```json
{"type":"error","session_id":"...","code":"invalid_audio","message":"..."}
```

Error codes include `invalid_configuration`, `database_unavailable`,
`invalid_message`, `invalid_audio`, `upstream_error`, `persistence_error`, and
`internal_error`. Normal completion closes with 1000; invalid configuration uses
1008, invalid messages 1003, invalid audio 1007 or 1009, and server-side
database/upstream/persistence failures 1011. The endpoint is unauthenticated and
is intended only for local development; bind it to `127.0.0.1` and do not expose
it to untrusted networks. Audio and transcript content are not logged.

## Transcription history API (Phase 5)

These unauthenticated endpoints are intended for local development. They require
a configured `DATABASE_URL`; otherwise they return HTTP 503 with
`{"detail":"Database unavailable"}`. Missing sessions or segments return HTTP
404, invalid UUIDs and invalid query or body values return HTTP 422, and
unexpected failures return the generic HTTP 500 response.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/transcription-sessions` | List sessions, newest first |
| `GET` | `/api/transcription-sessions/{session_id}` | Read one session and its segments |
| `PATCH` | `/api/transcript-segments/{transcript_id}` | Edit one finalized segment |
| `DELETE` | `/api/transcription-sessions/{session_id}` | Delete a session and all its segments |

The list endpoint accepts these query parameters:

- `q`: optional case-insensitive substring search over finalized segment text.
  `%` and `_` are treated as literal characters. The search selects matching
  sessions; each summary still describes the whole session.
- `limit`: page size from 1 to 100, default 10.
- `offset`: non-negative row offset, default 0.

A list response contains `sessions`, `total` (distinct matching sessions),
`limit`, and `offset`. Each session summary contains `session_id`, `started_at`,
`ended_at`, `segment_count`, a text `preview` of at most 200 characters, and
`language_codes`:

```json
{
  "sessions": [
    {
      "session_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
      "started_at": "2026-10-22T10:00:00+00:00",
      "ended_at": "2026-10-22T10:01:00+00:00",
      "segment_count": 3,
      "preview": "The first finalized segment...",
      "language_codes": ["en-IN"]
    }
  ],
  "total": 1,
  "limit": 10,
  "offset": 0
}
```

Session detail returns the ordered segments, with `sequence` starting at 0:

```json
{
  "session_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
  "started_at": "2026-10-22T10:00:00+00:00",
  "ended_at": "2026-10-22T10:01:00+00:00",
  "segment_count": 2,
  "segments": [
    {
      "id": "6c1f7d8e-3d20-4b38-9b9c-1f4f7d4d0d1a",
      "session_id": "0f8fad5b-d9cb-469f-a165-70867728950e",
      "sequence": 0,
      "text": "First segment.",
      "language_code": "en-IN",
      "created_at": "2026-10-22T10:00:10+00:00"
    }
  ]
}
```

An edit request contains `{"text":"Corrected text."}`. The server trims the
text, rejects a blank result with HTTP 422, and returns the updated segment.
Deletion returns HTTP 204 with no body and removes every segment in the session.
Sessions are derived from the `transcripts` table, so no migration is required
for these endpoints beyond the existing initial migration.

PowerShell examples (take `$sessionId` and `$segmentId` from a list or detail
response):

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/transcription-sessions?q=project&limit=10&offset=0"
Invoke-RestMethod "http://127.0.0.1:8000/api/transcription-sessions/$sessionId"
Invoke-RestMethod -Method Patch -ContentType "application/json" `
  -Body '{"text":"Corrected text."}' `
  "http://127.0.0.1:8000/api/transcript-segments/$segmentId"
Invoke-RestMethod -Method Delete `
  "http://127.0.0.1:8000/api/transcription-sessions/$sessionId"
```

Deleting a session is permanent. Do not expose this API to untrusted networks
or use it against a database shared with other users.

## Frontend (Phases 4-5)

The `frontend/` app is a Vite, React, and TypeScript single-page interface for
the WebSocket service and the history API. It has two views. The Live session
view captures mono microphone audio, resamples it to 16 kHz, converts it to
signed PCM16 little-endian, and sends 3,200-byte frames (100 ms). Interim
captions are display-only; final segments are appended in `sequence` order.
Stopping sends the exact frame `{"type":"stop"}` and waits for the server's
`completed` event before reporting completion.

The History view lists persisted sessions newest first, loads 10 sessions at a
time with a load-more control, supports case-insensitive text search, and shows
the ordered final segments for a selected session. Segments can be edited in
place, and a session can be deleted after an in-app confirmation dialog (not a
browser alert). Completing a live session refreshes the history data without a
full page reload. List, detail, edit, and delete requests use the `/api`
endpoints documented above.

Start the backend first in one terminal (see above), with `DATABASE_URL` and
`GEMINI_API_KEY` configured. Then start the frontend in a second terminal:

```powershell
npm --prefix frontend run dev
```

Open `http://127.0.0.1:5173`. The Vite development server proxies `/health` and
`/api` to `http://127.0.0.1:8000` and `/ws` to `ws://127.0.0.1:8000`, so the
browser uses the same origin and no backend CORS configuration is required. The
microphone requires a secure context; `localhost` and `127.0.0.1` are treated as
secure. Restart the Vite server after changing `vite.config.ts`.

To use a different backend address, create `frontend/.env.local` (ignored by
Git) and set the optional WebSocket base URL:

```dotenv
VITE_WS_URL=ws://127.0.0.1:8000
```

`VITE_WS_URL` must use `ws://` or `wss://`. The frontend appends
`/ws/transcribe` when the override does not already end with that path. It is a
public endpoint address, not a credential; do not put API keys in frontend
environment variables.

Language options map to the existing `language_codes` query parameter:

- Automatic: `auto` (used for English, Hindi, and Hinglish); stores no code
- Hindi and English: `hi-IN,en-IN`; stores `hi-IN,en-IN`
- English: `en-IN`; stores `en-IN`
- Hindi: `hi-IN`; stores `hi-IN`

The history list splits comma-separated stored codes so bilingual sessions show
both language codes.

The session hook implements `idle → connecting → recording → stopping →
completed` with an `error` path. It waits for `ready` before requesting the
microphone, prevents duplicate starts and duplicate final sequences, rejects
malformed or out-of-session messages, and stops the microphone if the socket
closes, the backend reports an error, the client stops, or the 600-second limit
is reached. A hidden AudioWorklet forwards audio blocks to a tested
`Pcm16Framer`, which handles arbitrary AudioContext sample rates, partial
frames, and multiple frames per block.

Frontend commands:

```powershell
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend run preview
```

The production build is written to `frontend/dist/`. `npm run preview` uses the
same proxy configuration. History is loaded from the backend REST API; the
frontend does not persist transcripts in browser storage or authenticate users.
The API and frontend are intended for local development only.

The application package is organized as:

```text
backend/app/
  config.py        app and redacted database configuration
  database.py      engine, sessions, and transaction scope
  models.py        transcript table model
  repositories.py  transcript persistence and history queries
  services.py      final-segment validation, persistence, and history operations
  live.py          Gemini runner, event sequencing, and error mapping
  logging_config.py idempotent console logging setup
  errors.py        {"detail": "..."} error responses
  main.py          create_app(), lifespan, and the ASGI app
  routes/health.py GET /health
  routes/transcription.py /ws/transcribe and audio protocol
  routes/transcripts.py /api history list, detail, edit, and delete
```

The frontend is organized as:

```text
frontend/
  public/pcm-worklet.js        AudioWorklet that forwards Float32 blocks
  src/api/history.ts           typed history REST client and error mapping
  src/audio/capture.ts         microphone, AudioContext, worklet cleanup
  src/history/HistoryDashboard.tsx history list, search, detail, edit, delete
  src/lib/pcm.ts               PCM16 conversion, resampling, 100 ms framing
  src/lib/protocol.ts          typed WebSocket messages and URL construction
  src/session/sessionState.ts  pure session reducer and final ordering
  src/session/useTranscription.ts WebSocket/microphone orchestration
  src/App.tsx                   live/history views and session completion refresh
  src/styles.css                responsive light/dark styling
  src/**/*.test.{ts,tsx}        Vitest unit and dashboard tests
```

Unhandled HTTP errors return HTTP 500 with a generic
`{"detail":"Internal server error"}` response. Missing database configuration
returns HTTP 503 if a database-backed HTTP operation reaches a request. WebSocket
errors use the JSON envelope documented above. The server logs the HTTP method
and path, but not request bodies, audio frames, transcript text, credentials,
database URLs, or provider response bodies.

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
| `DATABASE_URL` | FastAPI app, `/ws/transcribe`, and Alembic | No for startup; yes for streaming and migrations | None |
| `TEST_DATABASE_URL` | PostgreSQL tests | No; yes to run them | None |
| `GEMINI_API_KEY` | Phase 0 CLI and `/ws/transcribe` | Yes for CLI and WebSocket sessions | None |
| `GEMINI_LIVE_MODEL` | Phase 0 CLI and `/ws/transcribe` | No | `gemini-3.5-transcribe-live` |
| `VITE_WS_URL` | Frontend WebSocket client | No | Vite proxy to `127.0.0.1:8000` |

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
app, Alembic, tests, the WebSocket endpoint, and the CLI. Missing, blank, and
placeholder Gemini keys are rejected by the CLI before any network request and
by `/ws/transcribe` with an `invalid_configuration` error. The FastAPI app starts
without any Gemini setting, but transcription sessions require the key.

Frontend settings are read by Vite from `frontend/.env.local` or the process
environment. `VITE_WS_URL` is public configuration and must contain only a
WebSocket endpoint, never a Gemini key or database credential. Without it, the
frontend uses the Vite `/ws` proxy target (`ws://127.0.0.1:8000`).

Use `--language auto` (the default) to omit language hints and let the model
detect language. `--language hi-IN,en-IN` supplies hints for Hindi and English
(India). Hinglish is not a separate language code; mixed-language support
depends on automatic detection and must be tested with representative audio.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

The suite covers Phase 0 configuration validation and redaction, WAV/PCM
validation, chunking, transcript event extraction, fake-session orchestration,
CLI device validation, and the installed `google-genai` contract. It also covers
Phase 1 app configuration, `/health`, and HTTP/error responses, plus Phase 2
database configuration, degraded startup, persistence, constraints, and SQLite
migration upgrades and downgrades. Phase 3 tests cover the optional callback
contract, final-only persistence and sequence ordering, WebSocket readiness,
audio and text validation, configuration/database/upstream/persistence errors,
client stop, shortened session timeout, and disconnect cleanup. Phase 5 tests
cover history session summaries, ordering, search and wildcard escaping,
pagination, session detail, edit validation, deletion, query validation, and
database-unavailable responses. Tests do not call Gemini or other external
network services and use fake Gemini sessions and a temporary SQLite database.

The frontend Vitest suite covers Float32-to-PCM16 conversion and clipping,
resampling to 16 kHz, exact 1,600-sample frames, partial and multi-frame
buffering, WebSocket protocol parsing and malformed messages, URL construction,
session transitions, final-segment ordering, duplicate final handling, and
error states. History tests cover the typed REST client and jsdom dashboard
flows for list, detail, search, edit, delete, and database-unavailable errors.
Network calls are mocked; no live Gemini request is made. The production build
runs the TypeScript compiler before Vite.

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
- **History shows "database is not configured" or HTTP 503:** Set
  `DATABASE_URL`, run the Alembic upgrade, and restart the backend. The live
  WebSocket endpoint also rejects sessions without persistence.
- **History is empty after a live session:** Only finalized segments are
  persisted. Wait for the completion event, confirm the backend has a working
  `DATABASE_URL`, and clear an active search or refresh the list.
- **History edit returns HTTP 422:** Transcript text is trimmed and must not be
  blank. Invalid IDs or query parameters also return HTTP 422.
- **History edit or delete returns HTTP 404:** The segment or session no longer
  exists. Refresh the list and retry against the current session.
- **`DATABASE_URL must be set to run database migrations`:** Set the URL before
  running Alembic. The application itself can start without it.
- **PostgreSQL test is skipped:** Set `TEST_DATABASE_URL` to a dedicated
  disposable test database. Do not point it at a production database.
- **Database connection or migration failure:** Verify PostgreSQL is running,
  the URL uses `postgresql+psycopg://`, the database exists, and migrations have
  been applied.
- **`ModuleNotFoundError: No module named 'app'`:** Start Uvicorn with the
  documented commands so the `backend` package root is on `sys.path`.
- **`GEMINI_API_KEY is not set` / exit code 2:** Create `backend/.env` from
  `backend/.env.example` and add a real key, or set the environment variable.
- **WebSocket `invalid_configuration` / close code 1008:** Set `GEMINI_API_KEY`
  in `backend/.env` or the process environment. A missing database URL also
  causes `database_unavailable` / close code 1011 before the ready message.
- **WebSocket `invalid_audio` / close code 1007 or 1009:** Send even-length PCM16
  frames no larger than 32,000 bytes. Send the exact text frame
  `{"type":"stop"}` to finish.
- **WebSocket `invalid_message` / close code 1003:** Only the stop text frame is
  accepted; other text frames are rejected.
- **Frontend page returns a proxy or connection error:** Start the FastAPI
  service on `127.0.0.1:8000` before using the Vite server on port 5173. The
  development proxy does not start the backend automatically.
- **History requests return 404 through the Vite server:** Restart Vite after
  changing `vite.config.ts` so the `/api` proxy is loaded. Vite may listen on
  `localhost` (including IPv6) rather than only `127.0.0.1`.
- **Microphone permission denied or unavailable:** Allow microphone access in
  the browser, close other applications using the device, and use a browser with
  AudioWorklet support. Browsers require localhost or HTTPS for microphone
  access.
- **`browser not supported` in the UI:** The page needs `getUserMedia`,
  AudioWorklet, and `AudioContext`. Update the browser or use a Chromium-based
  browser local to the machine.
- **`VITE_WS_URL must use the ws:// or wss:// scheme`:** Correct the public
  frontend environment value in `frontend/.env.local`; never place secrets there.
- **Swagger does not show `/ws/transcribe`:** This is expected. `/health` and
  the `/api` history routes are listed, but WebSocket routes are not represented
  in OpenAPI.
- **Uvicorn reports no WebSocket implementation:** Install
  `backend/requirements.txt`, which pins `websockets`.
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
