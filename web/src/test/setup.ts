import '@testing-library/jest-dom/vitest'
import { vi } from 'vitest'

// Minimal WebSocket stub so `useLive` (which opens a socket on mount) can be
// exercised inside jsdom without a real connection.
class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  url: string
  readyState = MockWebSocket.CONNECTING
  onopen: (() => void) | null = null
  onmessage: ((ev: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  sent: string[] = []

  static instances: MockWebSocket[] = []

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.()
  }

  // helpers for tests
  _open() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.()
  }

  _emit(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) })
  }

  _error() {
    this.onerror?.()
  }
}

;(globalThis as Record<string, unknown>).WebSocket = MockWebSocket

export function createMockWS(url: string): WebSocket {
  return new (globalThis.WebSocket as unknown as { new (url: string): WebSocket })(url)
}

export { MockWebSocket }
