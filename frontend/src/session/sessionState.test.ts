import { describe, expect, it } from 'vitest'
import type { AudioInfo } from '../lib/protocol'
import {
  initialSessionState,
  sessionReducer,
  type SessionState,
} from './sessionState'

const audio: AudioInfo = {
  encoding: 'pcm_s16le',
  sample_rate_hz: 16000,
  channels: 1,
  recommended_frame_bytes: 3200,
  max_frame_bytes: 32000,
  max_session_seconds: 600,
}

function readyState(): SessionState {
  return sessionReducer(
    sessionReducer(initialSessionState, { type: 'start' }),
    { type: 'ready', sessionId: 'session-1', audio },
  )
}

describe('sessionReducer', () => {
  it('moves from idle to connecting on start', () => {
    const state = sessionReducer(initialSessionState, { type: 'start' })

    expect(state.status).toBe('connecting')
    expect(state.sessionId).toBeNull()
    expect(state.finals).toEqual([])
    expect(state.error).toBeNull()
  })

  it('moves from connecting to recording on ready', () => {
    const state = readyState()

    expect(state.status).toBe('recording')
    expect(state.sessionId).toBe('session-1')
    expect(state.audio).toEqual(audio)
  })

  it('ignores ready outside the connecting state', () => {
    const state = sessionReducer(initialSessionState, {
      type: 'ready',
      sessionId: 'session-1',
      audio,
    })

    expect(state).toBe(initialSessionState)
  })

  it('tracks interim text while recording', () => {
    const state = sessionReducer(readyState(), {
      type: 'interim',
      text: 'partial',
    })

    expect(state.interim).toBe('partial')
  })

  it('orders final segments and ignores duplicate sequences', () => {
    let state = readyState()
    state = sessionReducer(state, {
      type: 'final',
      segment: { sequence: 1, text: 'second' },
    })
    state = sessionReducer(state, {
      type: 'final',
      segment: { sequence: 0, text: 'first' },
    })
    state = sessionReducer(state, {
      type: 'final',
      segment: { sequence: 1, text: 'duplicate' },
    })

    expect(state.finals).toEqual([
      { sequence: 0, text: 'first' },
      { sequence: 1, text: 'second' },
    ])
    expect(state.interim).toBe('')
  })

  it('accepts final segments while stopping', () => {
    let state = readyState()
    state = sessionReducer(state, { type: 'stop_requested' })
    state = sessionReducer(state, {
      type: 'final',
      segment: { sequence: 0, text: 'last words' },
    })

    expect(state.status).toBe('stopping')
    expect(state.finals).toEqual([{ sequence: 0, text: 'last words' }])
  })

  it('ignores interim updates while stopping', () => {
    let state = readyState()
    state = sessionReducer(state, { type: 'interim', text: 'old' })
    state = sessionReducer(state, { type: 'stop_requested' })
    state = sessionReducer(state, { type: 'interim', text: 'late' })

    expect(state.interim).toBe('')
  })

  it('completes with the server count and reason', () => {
    let state = readyState()
    state = sessionReducer(state, { type: 'stop_requested' })
    state = sessionReducer(state, {
      type: 'completed',
      finalCount: 2,
      reason: 'client_stop',
    })

    expect(state.status).toBe('completed')
    expect(state.finalCount).toBe(2)
    expect(state.completionReason).toBe('client_stop')
  })

  it('supports completion at the maximum duration', () => {
    const state = sessionReducer(readyState(), {
      type: 'completed',
      finalCount: 4,
      reason: 'max_duration',
    })

    expect(state.status).toBe('completed')
    expect(state.completionReason).toBe('max_duration')
  })

  it('records errors and clears stale interim text', () => {
    let state = readyState()
    state = sessionReducer(state, { type: 'interim', text: 'stale' })
    state = sessionReducer(state, {
      type: 'error',
      code: 'upstream_error',
      message: 'Transcription service unavailable',
    })

    expect(state.status).toBe('error')
    expect(state.interim).toBe('')
    expect(state.error).toEqual({
      code: 'upstream_error',
      message: 'Transcription service unavailable',
    })
  })

  it('resets previous results on a new start', () => {
    let state = readyState()
    state = sessionReducer(state, {
      type: 'final',
      segment: { sequence: 0, text: 'old result' },
    })
    state = sessionReducer(state, {
      type: 'error',
      code: 'connection_closed',
      message: 'closed',
    })
    state = sessionReducer(state, { type: 'start' })

    expect(state).toMatchObject({
      status: 'connecting',
      sessionId: null,
      interim: '',
      finals: [],
      finalCount: null,
      completionReason: null,
      error: null,
    })
  })

  it('ignores final events before a session is ready', () => {
    const state = sessionReducer(initialSessionState, {
      type: 'final',
      segment: { sequence: 0, text: 'invalid' },
    })

    expect(state.finals).toEqual([])
  })
})
