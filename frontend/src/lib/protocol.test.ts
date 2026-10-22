import { describe, expect, it } from 'vitest'
import {
  buildWebSocketUrl,
  parseServerMessage,
  ProtocolError,
} from './protocol'

const readyMessage = {
  type: 'ready',
  session_id: 'session-1',
  audio: {
    encoding: 'pcm_s16le',
    sample_rate_hz: 16000,
    channels: 1,
    recommended_frame_bytes: 3200,
    max_frame_bytes: 32000,
    max_session_seconds: 600,
  },
}

describe('parseServerMessage', () => {
  it('parses all backend message types', () => {
    expect(parseServerMessage(JSON.stringify(readyMessage))).toEqual(readyMessage)
    expect(
      parseServerMessage(
        JSON.stringify({
          type: 'interim',
          session_id: 'session-1',
          text: 'hello',
        }),
      ),
    ).toEqual({ type: 'interim', session_id: 'session-1', text: 'hello' })
    expect(
      parseServerMessage(
        JSON.stringify({
          type: 'final',
          session_id: 'session-1',
          sequence: 2,
          text: 'final text',
        }),
      ),
    ).toEqual({
      type: 'final',
      session_id: 'session-1',
      sequence: 2,
      text: 'final text',
    })
    expect(
      parseServerMessage(
        JSON.stringify({
          type: 'completed',
          session_id: 'session-1',
          final_count: 3,
          reason: 'client_stop',
        }),
      ),
    ).toEqual({
      type: 'completed',
      session_id: 'session-1',
      final_count: 3,
      reason: 'client_stop',
    })
    expect(
      parseServerMessage(
        JSON.stringify({
          type: 'error',
          session_id: 'session-1',
          code: 'upstream_error',
          message: 'Transcription service unavailable',
        }),
      ),
    ).toEqual({
      type: 'error',
      session_id: 'session-1',
      code: 'upstream_error',
      message: 'Transcription service unavailable',
    })
  })

  it.each([
    ['malformed JSON', 'not-json'],
    ['null', 'null'],
    ['array', '[]'],
    ['missing type', '{}'],
    ['unknown type', '{"type":"unknown","session_id":"s"}'],
    [
      'missing audio',
      '{"type":"ready","session_id":"s"}',
    ],
    [
      'invalid audio field',
      JSON.stringify({
        ...readyMessage,
        audio: { ...readyMessage.audio, sample_rate_hz: '16000' },
      }),
    ],
    [
      'non-integer sequence',
      '{"type":"final","session_id":"s","sequence":1.5,"text":"x"}',
    ],
    [
      'missing error message',
      '{"type":"error","session_id":"s","code":"upstream_error"}',
    ],
    [
      'missing completed count',
      '{"type":"completed","session_id":"s","reason":"client_stop"}',
    ],
  ])('rejects %s', (_label, raw) => {
    expect(() => parseServerMessage(raw)).toThrow(ProtocolError)
  })
})

describe('buildWebSocketUrl', () => {
  const location = { protocol: 'http:', host: 'localhost:5173' }

  it('uses the same origin and language query by default', () => {
    expect(buildWebSocketUrl({ location })).toBe(
      'ws://localhost:5173/ws/transcribe?language_codes=auto',
    )
  })

  it('uses a secure WebSocket on HTTPS pages', () => {
    expect(
      buildWebSocketUrl({
        location: { protocol: 'https:', host: 'example.test' },
      }),
    ).toBe('wss://example.test/ws/transcribe?language_codes=auto')
  })

  it('adds the endpoint to an override base URL', () => {
    expect(
      buildWebSocketUrl({
        override: 'wss://api.example.test',
        languageCodes: 'hi-IN,en-IN',
      }),
    ).toBe(
      'wss://api.example.test/ws/transcribe?language_codes=hi-IN%2Cen-IN',
    )
  })

  it('preserves an override base path and full endpoint', () => {
    expect(
      buildWebSocketUrl({
        override: 'wss://example.test/api/',
        location,
      }),
    ).toBe('wss://example.test/api/ws/transcribe?language_codes=auto')

    expect(
      buildWebSocketUrl({
        override: 'wss://example.test/custom/ws/transcribe',
        location,
      }),
    ).toBe('wss://example.test/custom/ws/transcribe?language_codes=auto')
  })

  it('rejects non-WebSocket override schemes', () => {
    expect(() =>
      buildWebSocketUrl({ override: 'https://example.test' }),
    ).toThrow(ProtocolError)
  })
})
