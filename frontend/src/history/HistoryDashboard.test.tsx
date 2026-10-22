// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as historyApi from '../api/history'
import {
  deleteSession,
  getSession,
  listSessions,
  updateSegment,
  type SessionDetail,
  type SessionList,
  type SessionSummary,
  type TranscriptSegment,
} from '../api/history'
import { HistoryDashboard } from './HistoryDashboard'

vi.mock('../api/history', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/history')>()
  return {
    ...actual,
    listSessions: vi.fn(),
    getSession: vi.fn(),
    updateSegment: vi.fn(),
    deleteSession: vi.fn(),
  }
})

const listSessionsMock = vi.mocked(listSessions)
const getSessionMock = vi.mocked(getSession)
const updateSegmentMock = vi.mocked(updateSegment)
const deleteSessionMock = vi.mocked(deleteSession)

const summary: SessionSummary = {
  session_id: 'session-1',
  started_at: '2026-10-22T10:00:00Z',
  ended_at: '2026-10-22T10:01:00Z',
  segment_count: 2,
  preview: 'Hello from the live session.',
  language_codes: ['en-IN'],
}

const segments: TranscriptSegment[] = [
  {
    id: 'segment-1',
    session_id: 'session-1',
    sequence: 0,
    text: 'Hello from the live session.',
    language_code: 'en-IN',
    created_at: '2026-10-22T10:00:10Z',
  },
  {
    id: 'segment-2',
    session_id: 'session-1',
    sequence: 1,
    text: 'Second finalized segment.',
    language_code: 'en-IN',
    created_at: '2026-10-22T10:00:20Z',
  },
]

const detail: SessionDetail = {
  session_id: summary.session_id,
  started_at: summary.started_at,
  ended_at: summary.ended_at,
  segment_count: summary.segment_count,
  segments,
}

function listResult(sessions: SessionSummary[] = [summary]): SessionList {
  return {
    sessions,
    total: sessions.length,
    limit: 20,
    offset: 0,
  }
}

beforeEach(() => {
  listSessionsMock.mockReset()
  getSessionMock.mockReset()
  updateSegmentMock.mockReset()
  deleteSessionMock.mockReset()
  listSessionsMock.mockResolvedValue(listResult())
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('HistoryDashboard', () => {
  it('lists sessions and loads a selected transcript in order', async () => {
    getSessionMock.mockResolvedValue(detail)
    render(<HistoryDashboard refreshToken={0} />)

    const sessionButton = await screen.findByRole('button', {
      name: /Hello from the live session/,
    })
    fireEvent.click(sessionButton)

    expect(await screen.findByText('Hello from the live session.')).toBeTruthy()
    expect(screen.getByText('Second finalized segment.')).toBeTruthy()
    expect(getSessionMock).toHaveBeenCalledWith('session-1')
    expect(screen.getByText(/2 final segments/)).toBeTruthy()
  })

  it('edits and trims a segment, then refreshes the list', async () => {
    getSessionMock.mockResolvedValue({
      ...detail,
      segment_count: 1,
      segments: [segments[0]],
    })
    updateSegmentMock.mockResolvedValue({
      ...segments[0],
      text: 'Corrected text.',
    })
    render(<HistoryDashboard refreshToken={0} />)

    fireEvent.click(
      await screen.findByRole('button', {
        name: /Hello from the live session/,
      }),
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }))
    fireEvent.change(screen.getByLabelText('Transcript text'), {
      target: { value: '  Corrected text.  ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(updateSegmentMock).toHaveBeenCalledWith(
        'segment-1',
        'Corrected text.',
      )
    })
    expect(await screen.findByText('Corrected text.')).toBeTruthy()
    await waitFor(() => {
      expect(listSessionsMock).toHaveBeenCalledTimes(2)
    })
  })

  it('rejects a blank edit without calling the API', async () => {
    getSessionMock.mockResolvedValue(detail)
    render(<HistoryDashboard refreshToken={0} />)

    fireEvent.click(
      await screen.findByRole('button', {
        name: /Hello from the live session/,
      }),
    )
    fireEvent.click((await screen.findAllByRole('button', { name: 'Edit' }))[0])
    fireEvent.change(screen.getByLabelText('Transcript text'), {
      target: { value: '   ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(screen.getByText('Transcript text must not be blank.')).toBeTruthy()
    expect(updateSegmentMock).not.toHaveBeenCalled()
  })

  it('deletes a session after confirmation', async () => {
    getSessionMock.mockResolvedValue(detail)
    deleteSessionMock.mockResolvedValue(undefined)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<HistoryDashboard refreshToken={0} />)

    fireEvent.click(
      await screen.findByRole('button', {
        name: /Hello from the live session/,
      }),
    )
    fireEvent.click(
      await screen.findByRole('button', { name: 'Delete session' }),
    )

    await waitFor(() => {
      expect(deleteSessionMock).toHaveBeenCalledWith('session-1')
    })
    expect(
      await screen.findByText(
        'Select a session to view and edit its finalized transcript.',
      ),
    ).toBeTruthy()
  })

  it('searches with the trimmed query', async () => {
    render(<HistoryDashboard refreshToken={0} />)
    await screen.findByRole('button', {
      name: /Hello from the live session/,
    })

    fireEvent.change(
      screen.getByLabelText('Search finalized transcript text'),
      { target: { value: '  second  ' } },
    )
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))

    await waitFor(() => {
      expect(listSessionsMock).toHaveBeenLastCalledWith({
        query: 'second',
        limit: 20,
        offset: 0,
      })
    })
  })

  it('refreshes when the live session completion token changes', async () => {
    const { rerender } = render(<HistoryDashboard refreshToken={0} />)
    await screen.findByRole('button', {
      name: /Hello from the live session/,
    })

    rerender(<HistoryDashboard refreshToken={1} />)

    await waitFor(() => {
      expect(listSessionsMock).toHaveBeenCalledTimes(2)
    })
  })

  it('shows a database setup message when history is unavailable', async () => {
    listSessionsMock.mockRejectedValue(
      new historyApi.ApiError(503, 'Database unavailable'),
    )
    render(<HistoryDashboard refreshToken={0} />)

    expect(
      await screen.findByText(
        'Transcription history is unavailable because the database is not configured.',
      ),
    ).toBeTruthy()
  })
})
