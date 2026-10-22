class PcmCaptureProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0]
    if (input && input.length > 0) {
      const channel = input[0]
      if (channel && channel.length > 0) {
        const copy = channel.slice()
        this.port.postMessage(copy, [copy.buffer])
      }
    }
    return true
  }
}

registerProcessor('pcm-capture', PcmCaptureProcessor)
