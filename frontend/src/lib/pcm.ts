export const TARGET_SAMPLE_RATE = 16_000
export const FRAME_SAMPLES = 1_600
export const FRAME_BYTES = FRAME_SAMPLES * 2

export function floatToPcm16(samples: Float32Array): Int16Array {
  const pcm = new Int16Array(samples.length)
  for (let index = 0; index < samples.length; index += 1) {
    const sample = samples[index]
    const clamped = sample > 1 ? 1 : sample < -1 ? -1 : sample
    pcm[index] = Math.round(clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff)
  }
  return pcm
}

export class Pcm16Framer {
  readonly sourceRate: number
  readonly targetRate: number

  private readonly step: number
  private readonly frame = new Float32Array(FRAME_SAMPLES)
  private frameOffset = 0
  private resampleBuffer = new Float32Array(0)
  private resamplePosition = 0

  constructor(sourceRate = TARGET_SAMPLE_RATE, targetRate = TARGET_SAMPLE_RATE) {
    if (!Number.isFinite(sourceRate) || sourceRate <= 0) {
      throw new Error('Source sample rate must be a positive number.')
    }
    if (!Number.isFinite(targetRate) || targetRate <= 0) {
      throw new Error('Target sample rate must be a positive number.')
    }
    this.sourceRate = sourceRate
    this.targetRate = targetRate
    this.step = sourceRate / targetRate
  }

  push(samples: Float32Array): Int16Array[] {
    if (samples.length === 0) {
      return []
    }
    if (this.step === 1) {
      return this.pushAtTargetRate(samples)
    }
    return this.pushResampled(samples)
  }

  private pushAtTargetRate(samples: Float32Array): Int16Array[] {
    const frames: Int16Array[] = []
    let offset = 0

    while (offset < samples.length) {
      if (this.frameOffset === 0 && samples.length - offset >= FRAME_SAMPLES) {
        frames.push(floatToPcm16(samples.subarray(offset, offset + FRAME_SAMPLES)))
        offset += FRAME_SAMPLES
        continue
      }

      const take = Math.min(
        FRAME_SAMPLES - this.frameOffset,
        samples.length - offset,
      )
      this.frame.set(samples.subarray(offset, offset + take), this.frameOffset)
      this.frameOffset += take
      offset += take

      if (this.frameOffset === FRAME_SAMPLES) {
        frames.push(floatToPcm16(this.frame))
        this.frameOffset = 0
      }
    }

    return frames
  }

  private pushResampled(samples: Float32Array): Int16Array[] {
    const combined = new Float32Array(
      this.resampleBuffer.length + samples.length,
    )
    combined.set(this.resampleBuffer)
    combined.set(samples, this.resampleBuffer.length)

    const frames: Int16Array[] = []
    let position = this.resamplePosition

    while (Math.floor(position) + 1 < combined.length) {
      const index = Math.floor(position)
      const fraction = position - index
      const value =
        combined[index] +
        (combined[index + 1] - combined[index]) * fraction
      this.pushSample(value, frames)
      position += this.step
    }

    const consumed = Math.floor(position)
    this.resampleBuffer = combined.slice(consumed)
    this.resamplePosition = position - consumed
    return frames
  }

  private pushSample(value: number, frames: Int16Array[]): void {
    this.frame[this.frameOffset] = value
    this.frameOffset += 1

    if (this.frameOffset === FRAME_SAMPLES) {
      frames.push(floatToPcm16(this.frame))
      this.frameOffset = 0
    }
  }
}
