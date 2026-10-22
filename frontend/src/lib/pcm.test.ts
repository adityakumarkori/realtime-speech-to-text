import { describe, expect, it } from 'vitest'
import {
  FRAME_BYTES,
  FRAME_SAMPLES,
  Pcm16Framer,
  floatToPcm16,
} from './pcm'

function samples(count: number, value: number): Float32Array {
  return new Float32Array(count).fill(value)
}

describe('floatToPcm16', () => {
  it('converts and clips Float32 samples to signed 16-bit values', () => {
    const pcm = floatToPcm16(
      new Float32Array([0, 1, -1, 0.5, -0.5, 2, -2, Number.NaN]),
    )

    expect(Array.from(pcm)).toEqual([
      0, 32767, -32768, 16384, -16384, 32767, -32768, 0,
    ])
  })
})

describe('Pcm16Framer', () => {
  it('emits one exact frame for 1,600 samples at 16 kHz', () => {
    const frames = new Pcm16Framer().push(samples(FRAME_SAMPLES, 0.25))

    expect(frames).toHaveLength(1)
    expect(frames[0]).toHaveLength(FRAME_SAMPLES)
    expect(frames[0].byteLength).toBe(FRAME_BYTES)
    expect(frames[0][0]).toBe(8192)
    expect(frames[0][FRAME_SAMPLES - 1]).toBe(8192)
  })

  it('buffers partial frames until a full frame is available', () => {
    const framer = new Pcm16Framer()

    expect(framer.push(samples(800, 0.1))).toHaveLength(0)

    const frames = framer.push(samples(800, 0.2))
    expect(frames).toHaveLength(1)
    expect(frames[0]).toHaveLength(FRAME_SAMPLES)
    expect(frames[0][0]).toBe(3277)
    expect(frames[0][799]).toBe(3277)
    expect(frames[0][800]).toBe(6553)
    expect(frames[0][1599]).toBe(6553)
  })

  it('emits multiple frames from one large block', () => {
    const frames = new Pcm16Framer().push(
      samples(FRAME_SAMPLES * 3 + 12, 0),
    )

    expect(frames).toHaveLength(3)
    for (const frame of frames) {
      expect(frame).toHaveLength(FRAME_SAMPLES)
      expect(frame.byteLength).toBe(FRAME_BYTES)
    }
  })

  it('does not emit empty or incomplete final frames', () => {
    const framer = new Pcm16Framer()

    expect(framer.push(new Float32Array(0))).toHaveLength(0)
    expect(framer.push(samples(FRAME_SAMPLES - 1, 0))).toHaveLength(0)
    expect(framer.push(samples(1, 0))).toHaveLength(1)
  })

  it('resamples 32 kHz audio to 16 kHz', () => {
    const frames = new Pcm16Framer(32000).push(samples(3200, 0.5))

    expect(frames).toHaveLength(1)
    expect(frames[0]).toHaveLength(FRAME_SAMPLES)
    expect(Array.from(frames[0])).toEqual(
      new Array(FRAME_SAMPLES).fill(16384),
    )
  })

  it('resamples 48 kHz audio to 16 kHz', () => {
    const frames = new Pcm16Framer(48000).push(samples(4800, 0.25))

    expect(frames).toHaveLength(1)
    expect(frames[0]).toHaveLength(FRAME_SAMPLES)
    expect(frames[0].byteLength).toBe(FRAME_BYTES)
  })

  it('resamples 8 kHz audio to 16 kHz across blocks', () => {
    const frames = new Pcm16Framer(8000).push(samples(1601, 0.25))

    expect(frames).toHaveLength(2)
    for (const frame of frames) {
      expect(frame).toHaveLength(FRAME_SAMPLES)
      expect(frame[0]).toBe(8192)
    }
  })

  it('resamples arbitrary rates such as 44.1 kHz', () => {
    const frames = new Pcm16Framer(44100).push(samples(4410, 0.5))

    expect(frames).toHaveLength(1)
    expect(frames[0].byteLength).toBe(FRAME_BYTES)
  })

  it('preserves resampling state across chunk boundaries', () => {
    const framer = new Pcm16Framer(32000)

    expect(framer.push(samples(1600, 0.5))).toHaveLength(0)
    const frames = framer.push(samples(1600, 0.5))

    expect(frames).toHaveLength(1)
    expect(frames[0]).toHaveLength(FRAME_SAMPLES)
  })

  it('rejects invalid sample rates', () => {
    expect(() => new Pcm16Framer(0)).toThrow()
    expect(() => new Pcm16Framer(16000, -1)).toThrow()
  })
})
