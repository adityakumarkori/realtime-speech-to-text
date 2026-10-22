import type { AudioInfo } from '../lib/protocol'

export type SessionStatus =
  | 'idle'
  | 'connecting'
  | 'recording'
  | 'stopping'
  | 'completed'
  | 'error'

export interface FinalSegment {
  sequence: number
  text: string
}

export interface SessionError {
  code: string
  message: string
}

export interface SessionState {
  status: SessionStatus
  sessionId: string | null
  audio: AudioInfo | null
  interim: string
  finals: FinalSegment[]
  finalCount: number | null
  completionReason: string | null
  error: SessionError | null
}

export const initialSessionState: SessionState = {
  status: 'idle',
  sessionId: null,
  audio: null,
  interim: '',
  finals: [],
  finalCount: null,
  completionReason: null,
  error: null,
}

export type SessionAction =
  | { type: 'start' }
  | { type: 'ready'; sessionId: string; audio: AudioInfo }
  | { type: 'interim'; text: string }
  | { type: 'final'; segment: FinalSegment }
  | { type: 'stop_requested' }
  | { type: 'completed'; finalCount: number; reason: string }
  | { type: 'error'; code: string; message: string }

function insertFinal(
  finals: FinalSegment[],
  segment: FinalSegment,
): FinalSegment[] {
  if (finals.some((item) => item.sequence === segment.sequence)) {
    return finals
  }
  return [...finals, segment].sort((left, right) => left.sequence - right.sequence)
}

export function sessionReducer(
  state: SessionState,
  action: SessionAction,
): SessionState {
  switch (action.type) {
    case 'start':
      return { ...initialSessionState, status: 'connecting' }

    case 'ready':
      if (state.status !== 'connecting') {
        return state
      }
      return {
        ...state,
        status: 'recording',
        sessionId: action.sessionId,
        audio: action.audio,
      }

    case 'interim':
      if (state.status !== 'recording') {
        return state
      }
      return { ...state, interim: action.text }

    case 'final':
      if (state.status !== 'recording' && state.status !== 'stopping') {
        return state
      }
      return {
        ...state,
        interim: '',
        finals: insertFinal(state.finals, action.segment),
      }

    case 'stop_requested':
      if (state.status !== 'recording') {
        return state
      }
      return { ...state, status: 'stopping', interim: '' }

    case 'completed':
      if (state.status !== 'recording' && state.status !== 'stopping') {
        return state
      }
      return {
        ...state,
        status: 'completed',
        interim: '',
        finalCount: action.finalCount,
        completionReason: action.reason,
      }

    case 'error':
      return {
        ...state,
        status: 'error',
        interim: '',
        error: { code: action.code, message: action.message },
      }

    default:
      return state
  }
}
