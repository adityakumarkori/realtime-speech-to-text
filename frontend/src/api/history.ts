export interface TranscriptSegment {
  id: string
  session_id: string
  sequence: number
  text: string
  language_code: string | null
  created_at: string
}

export interface SessionSummary {
  session_id: string
  started_at: string
  ended_at: string
  segment_count: number
  preview: string
  language_codes: string[]
}

export interface SessionList {
  sessions: SessionSummary[]
  total: number
  limit: number
  offset: number
}

export interface SessionDetail {
  session_id: string
  started_at: string
  ended_at: string
  segment_count: number
  segments: TranscriptSegment[]
}

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

interface RequestOptions {
  method?: string
  body?: unknown
}

function detailFromPayload(value: unknown): string | null {
  if (typeof value !== 'object' || value === null) {
    return null
  }
  const detail = (value as Record<string, unknown>).detail
  return typeof detail === 'string' ? detail : null
}

async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const init: RequestInit = {
    method: options.method ?? 'GET',
    headers: { Accept: 'application/json' },
  }
  if (options.body !== undefined) {
    init.headers = {
      ...init.headers,
      'Content-Type': 'application/json',
    }
    init.body = JSON.stringify(options.body)
  }

  let response: Response
  try {
    response = await fetch(path, init)
  } catch {
    throw new ApiError(0, 'Could not reach the transcription service.')
  }

  if (!response.ok) {
    let payload: unknown = null
    try {
      payload = await response.json()
    } catch {
      payload = null
    }
    throw new ApiError(
      response.status,
      detailFromPayload(payload) ??
        `Request failed with status ${response.status}.`,
    )
  }

  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

export function listSessions(
  options: {
    query?: string
    limit?: number
    offset?: number
  } = {},
): Promise<SessionList> {
  const params = new URLSearchParams()
  const query = options.query?.trim()
  if (query) {
    params.set('q', query)
  }
  params.set('limit', String(options.limit ?? 50))
  params.set('offset', String(options.offset ?? 0))
  return request<SessionList>(
    `/api/transcription-sessions?${params.toString()}`,
  )
}

export function getSession(sessionId: string): Promise<SessionDetail> {
  return request<SessionDetail>(
    `/api/transcription-sessions/${encodeURIComponent(sessionId)}`,
  )
}

export function updateSegment(
  segmentId: string,
  text: string,
): Promise<TranscriptSegment> {
  return request<TranscriptSegment>(
    `/api/transcript-segments/${encodeURIComponent(segmentId)}`,
    { method: 'PATCH', body: { text } },
  )
}

export function deleteSession(sessionId: string): Promise<void> {
  return request<void>(
    `/api/transcription-sessions/${encodeURIComponent(sessionId)}`,
    { method: 'DELETE' },
  )
}
