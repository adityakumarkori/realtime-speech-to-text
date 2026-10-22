import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  ApiError,
  deleteSession,
  getSession,
  listSessions,
  updateSegment,
  type SessionDetail,
  type SessionSummary,
  type TranscriptSegment,
} from '../api/history'

const PAGE_SIZE = 20

interface HistoryDashboardProps {
  refreshToken: number
}

interface UiError {
  status: number
  message: string
}

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function toUiError(error: unknown, fallback: string): UiError {
  if (error instanceof ApiError) {
    if (error.status === 503) {
      return {
        status: 503,
        message:
          'Transcription history is unavailable because the database is not configured.',
      }
    }
    return { status: error.status, message: error.message }
  }
  return { status: 0, message: fallback }
}

export function HistoryDashboard({ refreshToken }: HistoryDashboardProps) {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [query, setQuery] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [reloadKey, setReloadKey] = useState(0)
  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState<UiError | null>(null)

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<SessionDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<UiError | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editText, setEditText] = useState('')
  const [editError, setEditError] = useState<UiError | null>(null)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const detailRequest = useRef(0)
  const previousRefreshToken = useRef(refreshToken)

  useEffect(() => {
    let cancelled = false
    setListLoading(true)
    setListError(null)

    listSessions({
      query: query || undefined,
      limit: PAGE_SIZE,
      offset,
    })
      .then((data) => {
        if (cancelled) {
          return
        }
        setSessions((current) =>
          offset === 0 ? data.sessions : [...current, ...data.sessions],
        )
        setTotal(data.total)
        setListLoading(false)
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return
        }
        setListLoading(false)
        setListError(toUiError(error, 'Could not load transcription history.'))
      })

    return () => {
      cancelled = true
    }
  }, [offset, query, reloadKey])

  useEffect(() => {
    if (previousRefreshToken.current === refreshToken) {
      return
    }
    previousRefreshToken.current = refreshToken
    setOffset(0)
    setReloadKey((value) => value + 1)
  }, [refreshToken])

  function refreshList() {
    setOffset(0)
    setReloadKey((value) => value + 1)
  }

  function resetDetail() {
    detailRequest.current += 1
    setSelectedId(null)
    setDetail(null)
    setDetailLoading(false)
    setDetailError(null)
    setEditingId(null)
    setEditError(null)
  }

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const nextQuery = searchInput.trim()
    if (nextQuery !== query) {
      resetDetail()
    }
    setOffset(0)
    setQuery(nextQuery)
  }

  function clearSearch() {
    resetDetail()
    setSearchInput('')
    setOffset(0)
    setQuery('')
  }

  async function selectSession(sessionId: string) {
    setSelectedId(sessionId)
    setDetail(null)
    setDetailLoading(true)
    setDetailError(null)
    setEditingId(null)
    setEditError(null)
    const requestId = detailRequest.current + 1
    detailRequest.current = requestId

    try {
      const data = await getSession(sessionId)
      if (detailRequest.current !== requestId) {
        return
      }
      setDetail(data)
      setDetailLoading(false)
    } catch (error) {
      if (detailRequest.current !== requestId) {
        return
      }
      setDetailLoading(false)
      setDetailError(
        toUiError(error, 'Could not load this transcription session.'),
      )
    }
  }

  function startEditing(segment: TranscriptSegment) {
    setEditingId(segment.id)
    setEditText(segment.text)
    setEditError(null)
  }

  function cancelEditing() {
    setEditingId(null)
    setEditText('')
    setEditError(null)
  }

  async function saveEdit(segmentId: string) {
    const text = editText.trim()
    if (!text) {
      setEditError({
        status: 422,
        message: 'Transcript text must not be blank.',
      })
      return
    }

    setSaving(true)
    setEditError(null)
    try {
      const updated = await updateSegment(segmentId, text)
      setDetail((current) =>
        current === null
          ? current
          : {
              ...current,
              segments: current.segments.map((segment) =>
                segment.id === updated.id ? updated : segment,
              ),
            },
      )
      setEditingId(null)
      setEditText('')
      setReloadKey((value) => value + 1)
    } catch (error) {
      setEditError(toUiError(error, 'Could not update the transcript segment.'))
    } finally {
      setSaving(false)
    }
  }

  async function removeSelectedSession() {
    if (!selectedId || !detail) {
      return
    }
    const confirmed = window.confirm(
      'Delete this transcription session and all of its finalized segments? This cannot be undone.',
    )
    if (!confirmed) {
      return
    }

    const sessionId = selectedId
    const requestId = detailRequest.current
    setDeleting(true)
    setDetailError(null)
    try {
      await deleteSession(sessionId)
      refreshList()
      if (detailRequest.current === requestId) {
        detailRequest.current += 1
        setSelectedId(null)
        setDetail(null)
        setDetailLoading(false)
        setEditingId(null)
      }
    } catch (error) {
      if (detailRequest.current === requestId) {
        setDetailError(
          toUiError(error, 'Could not delete the transcription session.'),
        )
      }
    } finally {
      setDeleting(false)
    }
  }

  const hasSessions = sessions.length > 0
  const dbUnavailable = listError?.status === 503

  return (
    <section className="panel history-panel" aria-labelledby="history-heading">
      <div className="history-header">
        <div>
          <p className="eyebrow">Dashboard</p>
          <h2 id="history-heading">Transcription history</h2>
          <p className="hint">
            Finalized segments persisted by your live sessions.
          </p>
        </div>
        <button
          type="button"
          className="button secondary"
          onClick={refreshList}
          disabled={listLoading}
        >
          Refresh
        </button>
      </div>

      <form className="search-row" onSubmit={handleSearch}>
        <label className="visually-hidden" htmlFor="history-search">
          Search finalized transcript text
        </label>
        <input
          id="history-search"
          type="search"
          value={searchInput}
          onChange={(event) => setSearchInput(event.target.value)}
          placeholder="Search finalized transcript text"
          maxLength={200}
        />
        <button type="submit" className="button secondary">
          Search
        </button>
        {query && (
          <button
            type="button"
            className="button secondary"
            onClick={clearSearch}
          >
            Clear
          </button>
        )}
      </form>

      {listError && (
        <div className="alert" role="alert">
          <strong>{listError.message}</strong>
          {dbUnavailable && (
            <span>
              Set the backend DATABASE_URL and run the Alembic migration to
              enable history.
            </span>
          )}
        </div>
      )}

      <div className="history-layout">
        <section
          className="history-list"
          aria-label="Transcription sessions"
          aria-busy={listLoading}
        >
          {listLoading && !hasSessions && (
            <p className="empty-state" role="status">
              Loading transcription history…
            </p>
          )}

          {!listLoading && !hasSessions && !listError && (
            <p className="empty-state">
              {query
                ? 'No sessions match this search.'
                : 'No finalized transcription sessions yet. Complete a live session to see it here.'}
            </p>
          )}

          {hasSessions && (
            <ul className="history-items">
              {sessions.map((session) => (
                <li key={session.session_id}>
                  <button
                    type="button"
                    className="history-item"
                    aria-pressed={selectedId === session.session_id}
                    onClick={() => void selectSession(session.session_id)}
                  >
                    <span className="history-time">
                      {formatDate(session.ended_at)}
                    </span>
                    <span className="history-preview">
                      {session.preview || 'No transcript preview available.'}
                    </span>
                    <span className="history-meta">
                      {session.segment_count}{' '}
                      {session.segment_count === 1 ? 'segment' : 'segments'}
                      {' · '}
                      {session.language_codes.length > 0
                        ? session.language_codes.join(', ')
                        : 'Language auto'}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {hasSessions && sessions.length < total && (
            <button
              type="button"
              className="button secondary load-more"
              onClick={() => setOffset(sessions.length)}
              disabled={listLoading}
            >
              Load more
            </button>
          )}

          {hasSessions && (
            <p className="hint history-count">
              Showing {sessions.length} of {total}
            </p>
          )}
        </section>

        <section
          className="history-detail"
          aria-label="Session details"
          aria-busy={detailLoading}
        >
          {!selectedId && (
            <p className="empty-state">
              Select a session to view and edit its finalized transcript.
            </p>
          )}

          {detailLoading && (
            <p className="empty-state" role="status">
              Loading session…
            </p>
          )}

          {detailError && (
            <div className="alert" role="alert">
              <strong>{detailError.message}</strong>
            </div>
          )}

          {detail && !detailLoading && (
            <>
              <div className="detail-header">
                <div>
                  <h3>{formatDate(detail.started_at)}</h3>
                  <p className="session-id">
                    Session <code>{detail.session_id}</code>
                  </p>
                  <p className="hint">
                    {detail.segment_count}{' '}
                    {detail.segment_count === 1
                      ? 'final segment'
                      : 'final segments'}
                    {' · ended '}
                    {formatDate(detail.ended_at)}
                  </p>
                </div>
                <button
                  type="button"
                  className="button danger"
                  onClick={() => void removeSelectedSession()}
                  disabled={deleting || saving}
                >
                  {deleting ? 'Deleting…' : 'Delete session'}
                </button>
              </div>

              <ol className="final-list history-segments">
                {detail.segments.map((segment) => (
                  <li key={segment.id} className="history-segment">
                    <div className="segment-heading">
                      <span className="sequence" aria-hidden="true">
                        {segment.sequence + 1}
                      </span>
                      <span className="hint">
                        {formatDate(segment.created_at)}
                      </span>
                    </div>

                    {editingId === segment.id ? (
                      <div className="edit-form">
                        <label
                          className="visually-hidden"
                          htmlFor={`edit-${segment.id}`}
                        >
                          Transcript text
                        </label>
                        <textarea
                          id={`edit-${segment.id}`}
                          value={editText}
                          onChange={(event) => setEditText(event.target.value)}
                          rows={3}
                          autoFocus
                        />
                        {editError && (
                          <p className="inline-error" role="alert">
                            {editError.message}
                          </p>
                        )}
                        <div className="button-row">
                          <button
                            type="button"
                            className="button primary"
                            onClick={() => void saveEdit(segment.id)}
                            disabled={saving}
                          >
                            {saving ? 'Saving…' : 'Save'}
                          </button>
                          <button
                            type="button"
                            className="button secondary"
                            onClick={cancelEditing}
                            disabled={saving}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="segment-text">
                        <p>{segment.text}</p>
                        <button
                          type="button"
                          className="button text-button"
                          onClick={() => startEditing(segment)}
                          disabled={deleting || saving}
                        >
                          Edit
                        </button>
                      </div>
                    )}
                  </li>
                ))}
              </ol>
            </>
          )}
        </section>
      </div>
    </section>
  )
}
