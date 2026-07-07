import { useState, useEffect, useRef } from 'react'
import type { SystemData } from '../types'

const WS_URL = `ws://${window.location.host}/ws/live`
const RECONNECT_MS = 5000

export function useSDOS() {
  const [data, setData] = useState<SystemData | null>(null)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let dead = false

    function connect() {
      if (dead) return
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => { setConnected(true); setError(null) }

      ws.onmessage = (e) => {
        try {
          const parsed = JSON.parse(e.data) as SystemData
          setData(parsed)
        } catch { /* ignore malformed */ }
      }

      ws.onerror = () => setError('WebSocket error')

      ws.onclose = () => {
        setConnected(false)
        if (!dead) setTimeout(connect, RECONNECT_MS)
      }
    }

    connect()
    return () => {
      dead = true
      wsRef.current?.close()
    }
  }, [])

  // Fallback: HTTP polling when WS is not connected
  useEffect(() => {
    if (connected) return
    const id = setInterval(async () => {
      try {
        const r = await fetch('/api/system')
        if (r.ok) setData(await r.json())
      } catch { /* ignore */ }
    }, 10_000)
    // Initial fetch
    fetch('/api/system').then(r => r.ok ? r.json() : null).then(d => d && setData(d))
    return () => clearInterval(id)
  }, [connected])

  return { data, connected, error }
}
