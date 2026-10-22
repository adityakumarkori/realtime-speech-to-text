export interface AudioInfo {
  encoding: string
  sample_rate_hz: number
  channels: number
  recommended_frame_bytes: number
  max_frame_bytes: number
  max_session_seconds: number
}

export interface ReadyMessage {
  type: 'ready'
  session_id: string
  audio: AudioInfo
}

export interface InterimMessage {
  type: 'interim'
  session_id: string
  text: string
}

export interface FinalMessage {
  type: 'final'
  session_id: string
  sequence: number
  text: string
}

export interface CompletedMessage {
  type: 'completed'
  session_id: string
  final_count: number
  reason: string
}

export interface ErrorMessage {
  type: 'error'
  session_id: string
  code: string
  message: string
}

export type ServerMessage =
  | ReadyMessage
  | InterimMessage
  | FinalMessage
  | CompletedMessage
  | ErrorMessage

export class ProtocolError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ProtocolError'
  }
}

type JsonObject = Record<string, unknown>

function asObject(value: unknown, label: string): JsonObject {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new ProtocolError(`Expected ${label} to be a JSON object.`)
  }
  return value as JsonObject
}

function readString(object: JsonObject, key: string): string {
  const value = object[key]
  if (typeof value !== 'string') {
    throw new ProtocolError(`Expected "${key}" to be a string.`)
  }
  return value
}

function readNumber(object: JsonObject, key: string): number {
  const value = object[key]
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new ProtocolError(`Expected "${key}" to be a finite number.`)
  }
  return value
}

function readInteger(object: JsonObject, key: string): number {
  const value = readNumber(object, key)
  if (!Number.isInteger(value)) {
    throw new ProtocolError(`Expected "${key}" to be an integer.`)
  }
  return value
}

function parseAudioInfo(value: unknown): AudioInfo {
  const audio = asObject(value, 'audio')
  return {
    encoding: readString(audio, 'encoding'),
    sample_rate_hz: readInteger(audio, 'sample_rate_hz'),
    channels: readInteger(audio, 'channels'),
    recommended_frame_bytes: readInteger(audio, 'recommended_frame_bytes'),
    max_frame_bytes: readInteger(audio, 'max_frame_bytes'),
    max_session_seconds: readNumber(audio, 'max_session_seconds'),
  }
}

export function parseServerMessage(raw: string): ServerMessage {
  let value: unknown
  try {
    value = JSON.parse(raw)
  } catch {
    throw new ProtocolError('Received malformed JSON from the server.')
  }

  const message = asObject(value, 'message')
  const type = readString(message, 'type')

  switch (type) {
    case 'ready':
      return {
        type,
        session_id: readString(message, 'session_id'),
        audio: parseAudioInfo(message.audio),
      }
    case 'interim':
      return {
        type,
        session_id: readString(message, 'session_id'),
        text: readString(message, 'text'),
      }
    case 'final':
      return {
        type,
        session_id: readString(message, 'session_id'),
        sequence: readInteger(message, 'sequence'),
        text: readString(message, 'text'),
      }
    case 'completed':
      return {
        type,
        session_id: readString(message, 'session_id'),
        final_count: readInteger(message, 'final_count'),
        reason: readString(message, 'reason'),
      }
    case 'error':
      return {
        type,
        session_id: readString(message, 'session_id'),
        code: readString(message, 'code'),
        message: readString(message, 'message'),
      }
    default:
      throw new ProtocolError(`Unknown server message type "${type}".`)
  }
}

export interface LocationLike {
  protocol: string
  host: string
}

export interface WebSocketUrlOptions {
  override?: string
  languageCodes?: string
  location?: LocationLike
}

function resolveLocation(): LocationLike {
  if (typeof window === 'undefined') {
    throw new ProtocolError('Cannot determine the WebSocket location.')
  }
  return window.location
}

export function buildWebSocketUrl(options: WebSocketUrlOptions = {}): string {
  const languageCodes = (options.languageCodes || 'auto').trim() || 'auto'
  const override = options.override?.trim()
  let url: URL

  if (override) {
    url = new URL(override)
    if (url.protocol !== 'ws:' && url.protocol !== 'wss:') {
      throw new ProtocolError('VITE_WS_URL must use the ws:// or wss:// scheme.')
    }
    if (!url.pathname.endsWith('/ws/transcribe')) {
      const basePath = url.pathname.replace(/\/+$/, '')
      url.pathname = `${basePath}/ws/transcribe`
    }
  } else {
    const location = options.location ?? resolveLocation()
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    url = new URL(`${protocol}//${location.host}/ws/transcribe`)
  }

  url.searchParams.set('language_codes', languageCodes)
  return url.toString()
}
