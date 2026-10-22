import { useCallback, useEffect, useReducer, useRef } from 'react'
import {
  startAudioCapture,
  type AudioCaptureHandle,
} from '../audio/capture'
import {
  buildWebSocketUrl,
  parseServerMessage,
  ProtocolError,
  type ServerMessage,
} from '../lib/protocol'
import {
  initialSessionState,
  sessionReducer,
  type SessionAction,
  type SessionState,
} from './sessionState'

const STOP_MESSAGE = '{"type":"stop"}'

export interface TranscriptionController {
  state: SessionState
  start: (languageCodes: string) => void
  stop: () => void
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

export function useTranscription(): TranscriptionController {
  const [state, dispatch] = useReducer(sessionReducer, initialSessionState)
  const socketRef = useRef<WebSocket | null>(null)
  const captureRef = useRef<AudioCaptureHandle | null>(null)
  const generationRef = useRef(0)
  const activeRef = useRef(false)
  const stoppingRef = useRef(false)
  const readyRef = useRef(false)
  const sessionIdRef = useRef<string | null>(null)

  const closeSocket = useCallback(() => {
    const socket = socketRef.current
    socketRef.current = null
    if (!socket) {
      return
    }
    socket.onopen = null
    socket.onmessage = null
    socket.onerror = null
    socket.onclose = null
    if (
      socket.readyState === WebSocket.CONNECTING ||
      socket.readyState === WebSocket.OPEN
    ) {
      socket.close()
    }
  }, [])

  const stopCapture = useCallback(() => {
    const capture = captureRef.current
    captureRef.current = null
    if (capture) {
      void capture.stop().catch(() => undefined)
    }
  }, [])

  const finish = useCallback(
    (action: SessionAction) => {
      activeRef.current = false
      stoppingRef.current = false
      readyRef.current = false
      sessionIdRef.current = null
      generationRef.current += 1
      stopCapture()
      closeSocket()
      dispatch(action)
    },
    [closeSocket, stopCapture],
  )

  const handleMessage = useCallback(
    async (event: MessageEvent, generation: number) => {
      let message: ServerMessage
      try {
        if (typeof event.data !== 'string') {
          throw new ProtocolError('Expected a text message from the server.')
        }
        message = parseServerMessage(event.data)
      } catch (error) {
        finish({
          type: 'error',
          code: 'protocol_error',
          message: errorMessage(error, 'Received an invalid server message.'),
        })
        return
      }

      if (message.type === 'error') {
        finish({
          type: 'error',
          code: message.code,
          message: message.message,
        })
        return
      }

      if (message.type === 'ready') {
        if (readyRef.current || sessionIdRef.current !== null) {
          finish({
            type: 'error',
            code: 'protocol_error',
            message: 'Received a duplicate ready message.',
          })
          return
        }

        readyRef.current = true
        sessionIdRef.current = message.session_id
        dispatch({
          type: 'ready',
          sessionId: message.session_id,
          audio: message.audio,
        })

        let capture: AudioCaptureHandle
        try {
          capture = await startAudioCapture((frame) => {
            if (
              !activeRef.current ||
              stoppingRef.current ||
              generationRef.current !== generation
            ) {
              return
            }
            const socket = socketRef.current
            if (!socket || socket.readyState !== WebSocket.OPEN) {
              return
            }
            try {
              socket.send(frame.buffer as ArrayBuffer)
            } catch {
              finish({
                type: 'error',
                code: 'connection_error',
                message: 'Could not send audio to the transcription service.',
              })
            }
          })
        } catch (error) {
          if (generationRef.current !== generation) {
            return
          }
          finish({
            type: 'error',
            code: 'microphone_error',
            message: errorMessage(error, 'Could not start microphone capture.'),
          })
          return
        }

        if (generationRef.current !== generation || !activeRef.current) {
          void capture.stop().catch(() => undefined)
          return
        }

        if (stoppingRef.current) {
          void capture.stop().catch(() => undefined)
          return
        }

        captureRef.current = capture
        return
      }

      if (!readyRef.current || sessionIdRef.current === null) {
        finish({
          type: 'error',
          code: 'protocol_error',
          message: 'Received a transcript event before the session was ready.',
        })
        return
      }

      if (message.session_id !== sessionIdRef.current) {
        finish({
          type: 'error',
          code: 'protocol_error',
          message: 'Received a message for a different session.',
        })
        return
      }

      if (message.type === 'interim') {
        dispatch({ type: 'interim', text: message.text })
        return
      }

      if (message.type === 'final') {
        dispatch({
          type: 'final',
          segment: { sequence: message.sequence, text: message.text },
        })
        return
      }

      finish({
        type: 'completed',
        finalCount: message.final_count,
        reason: message.reason,
      })
    },
    [finish],
  )

  const start = useCallback(
    (languageCodes: string) => {
      if (activeRef.current) {
        return
      }

      const generation = generationRef.current + 1
      generationRef.current = generation
      activeRef.current = true
      stoppingRef.current = false
      readyRef.current = false
      sessionIdRef.current = null
      dispatch({ type: 'start' })

      let url: string
      try {
        url = buildWebSocketUrl({
          override: import.meta.env.VITE_WS_URL,
          languageCodes,
        })
      } catch (error) {
        finish({
          type: 'error',
          code: 'invalid_configuration',
          message: errorMessage(error, 'The WebSocket URL is invalid.'),
        })
        return
      }

      let socket: WebSocket
      try {
        socket = new WebSocket(url)
      } catch {
        finish({
          type: 'error',
          code: 'connection_error',
          message: 'Could not open the transcription connection.',
        })
        return
      }

      socket.binaryType = 'arraybuffer'
      socketRef.current = socket
      socket.onmessage = (event: MessageEvent) => {
        if (generationRef.current !== generation) {
          return
        }
        void handleMessage(event, generation)
      }
      socket.onerror = () => {
        if (generationRef.current !== generation) {
          return
        }
        finish({
          type: 'error',
          code: 'connection_error',
          message: 'The transcription connection failed.',
        })
      }
      socket.onclose = () => {
        if (generationRef.current !== generation) {
          return
        }
        finish({
          type: 'error',
          code: 'connection_closed',
          message: stoppingRef.current
            ? 'The connection closed before the session completed.'
            : 'The transcription connection closed unexpectedly.',
        })
      }
    },
    [finish, handleMessage],
  )

  const stop = useCallback(() => {
    if (!activeRef.current || stoppingRef.current || !readyRef.current) {
      return
    }

    stoppingRef.current = true
    stopCapture()
    dispatch({ type: 'stop_requested' })

    const socket = socketRef.current
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      finish({
        type: 'error',
        code: 'connection_closed',
        message: 'The connection closed before the stop request was sent.',
      })
      return
    }

    try {
      socket.send(STOP_MESSAGE)
    } catch {
      finish({
        type: 'error',
        code: 'connection_error',
        message: 'Could not send the stop request.',
      })
    }
  }, [finish, stopCapture])

  useEffect(
    () => () => {
      activeRef.current = false
      generationRef.current += 1
      stopCapture()
      closeSocket()
    },
    [closeSocket, stopCapture],
  )

  return { state, start, stop }
}
