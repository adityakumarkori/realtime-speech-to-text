import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  apiUrl,
  normalizeBackendUrl,
  websocketUrlOverride,
} from './backend'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('normalizeBackendUrl', () => {
  it('returns undefined for blank values', () => {
    expect(normalizeBackendUrl(undefined)).toBeUndefined()
    expect(normalizeBackendUrl('   ')).toBeUndefined()
  })

  it('normalizes trailing slashes and keeps the port', () => {
    expect(
      normalizeBackendUrl(' https://api.example.test:8443/ '),
    ).toBe('https://api.example.test:8443')
    expect(normalizeBackendUrl('http://127.0.0.1:8000')).toBe(
      'http://127.0.0.1:8000',
    )
  })

  it('rejects http backend URLs on HTTPS pages', () => {
    vi.stubGlobal('window', { location: { protocol: 'https:' } })

    expect(() =>
      normalizeBackendUrl('http://api.example.test'),
    ).toThrow(/https/)
  })

  it.each([
    'api.example.test',
    'ftp://api.example.test',
    'https://api.example.test/api',
    'https://user:secret@api.example.test',
    'https://api.example.test?debug=1',
    'https://api.example.test#section',
  ])('rejects %s', (value) => {
    expect(() => normalizeBackendUrl(value)).toThrow(/VITE_BACKEND_URL/)
  })
})

describe('apiUrl', () => {
  it('prefixes API paths with the backend origin', () => {
    expect(
      apiUrl(
        '/api/transcription-sessions?limit=10',
        'https://api.example.test/',
      ),
    ).toBe('https://api.example.test/api/transcription-sessions?limit=10')
  })

  it('keeps relative paths without a backend URL', () => {
    expect(apiUrl('/api/transcription-sessions', undefined)).toBe(
      '/api/transcription-sessions',
    )
  })
})

describe('websocketUrlOverride', () => {
  it('derives the WebSocket scheme from the backend URL', () => {
    expect(
      websocketUrlOverride('https://api.example.test', undefined),
    ).toBe('wss://api.example.test')
    expect(
      websocketUrlOverride('http://127.0.0.1:8000', undefined),
    ).toBe('ws://127.0.0.1:8000')
  })

  it('prefers an explicit WebSocket URL', () => {
    expect(
      websocketUrlOverride(
        'https://api.example.test',
        'wss://ws.example.test',
      ),
    ).toBe('wss://ws.example.test')
  })

  it('returns undefined without configuration', () => {
    expect(websocketUrlOverride(undefined, undefined)).toBeUndefined()
    expect(websocketUrlOverride('   ', undefined)).toBeUndefined()
  })
})
