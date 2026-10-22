import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  deleteSession,
  getSession,
  listSessions,
  updateSegment,
} from './history'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('history API client', () => {
  it('lists sessions with encoded query and pagination', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse({ sessions: [], total: 0, limit: 20, offset: 40 }),
      )
    vi.stubGlobal('fetch', fetchMock)

    const result = await listSessions({
      query: '  hello world ',
      limit: 20,
      offset: 40,
    })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/transcription-sessions?q=hello+world&limit=20&offset=40',
      expect.objectContaining({ method: 'GET' }),
    )
    expect(result.total).toBe(0)
  })

  it('omits an empty search query', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse({ sessions: [], total: 0, limit: 50, offset: 0 }),
      )
    vi.stubGlobal('fetch', fetchMock)

    await listSessions({ query: '   ' })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/transcription-sessions?limit=50&offset=0',
      expect.anything(),
    )
  })

  it('loads a session with its segments', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        session_id: 'session/one',
        started_at: '2026-10-22T10:00:00Z',
        ended_at: '2026-10-22T10:01:00Z',
        segment_count: 1,
        segments: [],
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const detail = await getSession('session/one')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/transcription-sessions/session%2Fone',
      expect.anything(),
    )
    expect(detail.segment_count).toBe(1)
  })

  it('updates a segment and sends JSON', async () => {
    const segment = {
      id: 'segment-1',
      session_id: 'session-1',
      sequence: 0,
      text: 'Corrected text',
      language_code: 'en-IN',
      created_at: '2026-10-22T10:00:00Z',
    }
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(segment))
    vi.stubGlobal('fetch', fetchMock)

    const updated = await updateSegment('segment-1', 'Corrected text')

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/transcript-segments/segment-1',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ text: 'Corrected text' }),
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
        }),
      }),
    )
    expect(updated.text).toBe('Corrected text')
  })

  it('deletes a session with a 204 response', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(deleteSession('session-1')).resolves.toBeUndefined()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/transcription-sessions/session-1',
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('turns API error details into ApiError instances', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ detail: 'Database unavailable' }, 503))
    vi.stubGlobal('fetch', fetchMock)

    const error = await listSessions().catch((reason: unknown) => reason)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 503,
      message: 'Database unavailable',
    })
  })

  it('reports an unreachable service', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new TypeError('network down')),
    )

    await expect(listSessions()).rejects.toMatchObject({
      status: 0,
      message: 'Could not reach the transcription service.',
    })
  })
})
