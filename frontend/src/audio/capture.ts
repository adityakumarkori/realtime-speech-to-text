import {
  Pcm16Framer,
  TARGET_SAMPLE_RATE,
} from '../lib/pcm'

export interface AudioCaptureHandle {
  stop: () => Promise<void>
}

export class MicrophoneCaptureError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'MicrophoneCaptureError'
  }
}

function microphoneErrorMessage(error: unknown): string {
  const name = error instanceof Error ? error.name : ''
  switch (name) {
    case 'NotAllowedError':
    case 'PermissionDeniedError':
      return 'Microphone permission was denied. Allow access and try again.'
    case 'NotFoundError':
    case 'DevicesNotFoundError':
      return 'No microphone was found on this device.'
    case 'NotReadableError':
    case 'TrackStartError':
      return 'The microphone is unavailable or already in use.'
    case 'SecurityError':
      return 'Microphone access requires localhost or HTTPS.'
    case 'OverconstrainedError':
      return 'The microphone does not support the required audio format.'
    default:
      return 'Could not start microphone capture.'
  }
}

export async function startAudioCapture(
  onFrame: (frame: Int16Array) => void,
): Promise<AudioCaptureHandle> {
  let stream: MediaStream | null = null
  let context: AudioContext | null = null

  try {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new MicrophoneCaptureError(
        'Microphone capture is not supported in this browser.',
      )
    }

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: { ideal: TARGET_SAMPLE_RATE },
        },
        video: false,
      })
    } catch (error) {
      throw new MicrophoneCaptureError(microphoneErrorMessage(error))
    }

    context = new AudioContext({
      sampleRate: TARGET_SAMPLE_RATE,
      latencyHint: 'interactive',
    })
    await context.audioWorklet.addModule(
      `${import.meta.env.BASE_URL}pcm-worklet.js`,
    )

    const source = context.createMediaStreamSource(stream)
    const worklet = new AudioWorkletNode(context, 'pcm-capture', {
      numberOfInputs: 1,
      numberOfOutputs: 1,
      outputChannelCount: [1],
      channelCount: 1,
      channelCountMode: 'explicit',
      channelInterpretation: 'speakers',
    })
    const silentGain = context.createGain()
    silentGain.gain.value = 0

    source.connect(worklet)
    worklet.connect(silentGain)
    silentGain.connect(context.destination)

    const framer = new Pcm16Framer(context.sampleRate, TARGET_SAMPLE_RATE)
    worklet.port.onmessage = (event: MessageEvent<unknown>) => {
      if (!(event.data instanceof Float32Array)) {
        return
      }
      for (const frame of framer.push(event.data)) {
        onFrame(frame)
      }
    }

    await context.resume()

    let stopped = false
    const stop = async () => {
      if (stopped) {
        return
      }
      stopped = true
      worklet.port.onmessage = null
      source.disconnect()
      worklet.disconnect()
      silentGain.disconnect()
      for (const track of stream?.getTracks() ?? []) {
        track.stop()
      }
      if (context && context.state !== 'closed') {
        await context.close().catch(() => undefined)
      }
    }

    return { stop }
  } catch (error) {
    for (const track of stream?.getTracks() ?? []) {
      track.stop()
    }
    if (context && context.state !== 'closed') {
      await context.close().catch(() => undefined)
    }
    if (error instanceof MicrophoneCaptureError) {
      throw error
    }
    throw new MicrophoneCaptureError('Could not start microphone capture.')
  }
}
