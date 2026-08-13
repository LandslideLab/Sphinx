import { useEffect, useRef, useState } from 'react'
import { api } from './api'

export interface LiveState {
  /** true while a WebSocket connection is open */
  live: boolean
  /** increments on every live event published to the requested topics */
  revision: number
  /** re-open the socket (used for manual reconnect) */
  reconnect: () => void
}

/**
 * Subscribes to the Sphinx live event bus over WebSocket and exposes a
 * revision counter that bumps whenever an event arrives on one of `topics`.
 * Falls back silently to polling (the caller keeps its interval timer).
 */
export function useLive(topics: string[] = ['requests', 'decisions', 'policies']): LiveState {
  const [live, setLive] = useState(false)
  const [revision, setRevision] = useState(0)
  const [tick, setTick] = useState(0)
  const wsRef = useRef<WebSocket | null>(null)
  const topicsRef = useRef(topics)
  topicsRef.current = topics

  const open = () => {
    try {
      const ws = api.ws()
      wsRef.current = ws
      ws.onopen = () => setLive(true)
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data as string)
          if (msg && msg.topic && topicsRef.current.includes(msg.topic)) {
            setRevision((r) => r + 1)
          }
        } catch {
          /* non-JSON keepalive — ignore */
        }
      }
      ws.onclose = () => {
        setLive(false)
        wsRef.current = null
      }
      ws.onerror = () => {
        setLive(false)
        try {
          ws.close()
        } catch {
          /* ignore */
        }
      }
    } catch {
      setLive(false)
    }
  }

  useEffect(() => {
    open()
    const guard = setTimeout(() => {
      if (!wsRef.current || wsRef.current.readyState === WebSocket.CLOSED) open()
    }, 4000)
    return () => {
      clearTimeout(guard)
      if (wsRef.current) {
        wsRef.current.onclose = null
        try {
          wsRef.current.close()
        } catch {
          /* ignore */
        }
        wsRef.current = null
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // bounded auto-reconnect while the page is visible
  useEffect(() => {
    if (live) return
    const t = setInterval(() => {
      if (!wsRef.current || wsRef.current.readyState === WebSocket.CLOSED) {
        setTick((n) => n + 1)
        open()
      }
    }, 6000)
    return () => clearInterval(t)
  }, [live, tick])

  const reconnect = () => {
    if (wsRef.current) {
      try {
        wsRef.current.close()
      } catch {
        /* ignore */
      }
      wsRef.current = null
    }
    open()
  }

  return { live, revision, reconnect }
}
