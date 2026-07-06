import { useState, useEffect } from 'react'

export function useEndpoint<T>(url: string, intervalMs = 30_000) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function fetch_() {
      try {
        const r = await fetch(url)
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const json = await r.json() as T
        if (!cancelled) { setData(json); setError(null) }
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetch_()
    const id = setInterval(fetch_, intervalMs)
    return () => { cancelled = true; clearInterval(id) }
  }, [url, intervalMs])

  return { data, loading, error }
}
