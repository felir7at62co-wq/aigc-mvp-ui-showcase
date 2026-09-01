import { useEffect, useState } from 'react'

export function usePolling<T>(
  loader: () => Promise<T>,
  intervalMs = 3000,
): { data: T | null; error: string | null; refresh: () => void } {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    async function run() {
      try {
        const value = await loader()
        if (!cancelled) {
          setData(value)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err))
        }
      }
    }
    run()
    const timer = setInterval(run, intervalMs)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [loader, intervalMs, tick])

  return { data, error, refresh: () => setTick((value) => value + 1) }
}
