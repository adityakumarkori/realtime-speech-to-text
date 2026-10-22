import { useState } from 'react'
import { useTranscription } from './session/useTranscription'
import type { SessionStatus } from './session/sessionState'

const LANGUAGE_OPTIONS = [
  { value: 'auto', label: 'Automatic (English, Hindi, Hinglish)' },
  { value: 'hi-IN,en-IN', label: 'Hindi + English (India)' },
  { value: 'en-IN', label: 'English (India)' },
  { value: 'hi-IN', label: 'Hindi (India)' },
]

const STATUS_LABELS: Record<SessionStatus, string> = {
  idle: 'Ready to start',
  connecting: 'Connecting to the server',
  recording: 'Recording — speak now',
  stopping: 'Finishing transcription',
  completed: 'Session completed',
  error: 'Session failed',
}

function completionText(reason: string): string {
  if (reason === 'client_stop') {
    return 'Stopped by you.'
  }
  if (reason === 'max_duration') {
    return 'The 10-minute session limit was reached.'
  }
  return `Completion reason: ${reason}`
}

function App() {
  const { state, start, stop } = useTranscription()
  const [language, setLanguage] = useState('auto')

  const microphoneSupported =
    typeof navigator !== 'undefined' &&
    Boolean(navigator.mediaDevices?.getUserMedia) &&
    typeof AudioContext !== 'undefined' &&
    typeof AudioWorkletNode !== 'undefined'

  const isBusy =
    state.status === 'connecting' ||
    state.status === 'recording' ||
    state.status === 'stopping'
  const canStart = microphoneSupported && !isBusy
  const canStop = state.status === 'recording'
  const finalCount = state.finalCount ?? state.finals.length

  return (
    <main className="app-shell">
      <header className="app-header">
        <p className="eyebrow">Gemini Live · Speech to text</p>
        <h1>Live transcription</h1>
        <p className="lede">
          Stream microphone audio in English, Hindi, or Hinglish. Finalized
          segments are persisted as they arrive.
        </p>
      </header>

      {!microphoneSupported && (
        <div className="alert" role="alert">
          <strong>Browser not supported</strong>
          <span>
            This app requires microphone access, AudioWorklet, and a secure
            context such as localhost or HTTPS.
          </span>
        </div>
      )}

      <section className="panel controls" aria-labelledby="controls-heading">
        <h2 id="controls-heading" className="visually-hidden">
          Session controls
        </h2>

        <div className="control-row">
          <div className="field">
            <label htmlFor="language">Language</label>
            <select
              id="language"
              value={language}
              onChange={(event) => setLanguage(event.target.value)}
              disabled={isBusy}
            >
              {LANGUAGE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <div className="button-row">
            <button
              type="button"
              className="button primary"
              onClick={() => start(language)}
              disabled={!canStart}
            >
              Start transcription
            </button>
            <button
              type="button"
              className="button secondary"
              onClick={stop}
              disabled={!canStop}
            >
              Stop
            </button>
          </div>
        </div>

        <div className="session-meta">
          <span
            className={`status status-${state.status}`}
            role="status"
            aria-live="polite"
          >
            <span className="status-dot" aria-hidden="true" />
            {STATUS_LABELS[state.status]}
          </span>

          {state.sessionId && (
            <span className="session-id">
              Session <code>{state.sessionId}</code>
            </span>
          )}
        </div>

        {state.audio && (
          <p className="audio-meta">
            {(state.audio.sample_rate_hz / 1000).toFixed(0)} kHz ·{' '}
            {state.audio.channels === 1 ? 'mono' : `${state.audio.channels} channels`}{' '}
            · {Math.round(state.audio.max_session_seconds / 60)} min maximum
          </p>
        )}
      </section>

      {state.error && (
        <div className="alert" role="alert">
          <strong>{state.error.message}</strong>
          <span className="error-code">{state.error.code}</span>
        </div>
      )}

      {state.status === 'completed' && (
        <section className="panel outcome" aria-live="polite">
          <h2>Session complete</h2>
          <p>
            {finalCount} final {finalCount === 1 ? 'segment' : 'segments'}{' '}
            persisted. {completionText(state.completionReason ?? '')}
          </p>
        </section>
      )}

      <div className="transcript-grid">
        <section className="panel transcript-panel" aria-labelledby="interim-heading">
          <div className="panel-heading">
            <h2 id="interim-heading">Live interim</h2>
            <span className="hint">Not saved</span>
          </div>
          <p className="interim-text" aria-live="polite">
            {state.interim || 'Speak to see a live caption here.'}
          </p>
        </section>

        <section className="panel transcript-panel" aria-labelledby="final-heading">
          <div className="panel-heading">
            <h2 id="final-heading">Final transcript</h2>
            <span className="count">{finalCount}</span>
          </div>

          {state.finals.length === 0 ? (
            <p className="empty-state">
              Finalized segments will appear here in sequence order.
            </p>
          ) : (
            <ol className="final-list">
              {state.finals.map((segment) => (
                <li key={segment.sequence} className="final-segment">
                  <span className="sequence" aria-hidden="true">
                    {segment.sequence + 1}
                  </span>
                  <p>{segment.text}</p>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>

      <footer className="app-footer">
        <p>
          Audio is streamed to the local backend and Gemini Live. Only final
          segments are persisted. This endpoint is intended for local
          development and is not authenticated.
        </p>
      </footer>
    </main>
  )
}

export default App
