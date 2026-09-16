import { useEffect, useState } from 'react'

/**
 * Report whether the backend `/health` probe failed (R1-12).
 *
 * Runs once on mount with a 3s abort timeout so a dead backend surfaces a
 * banner instead of hanging. Shared by the chat and dashboard views.
 */
export function useBackendHealth(): boolean {
  const [backendDown, setBackendDown] = useState(false)
  useEffect(() => {
    let alive = true
    let timeoutTimer: ReturnType<typeof setTimeout> | undefined
    let retryTimer: ReturnType<typeof setTimeout> | undefined
    let controller: AbortController | undefined
    let attempt = 0
    const probe = () => {
      controller = new AbortController()
      timeoutTimer = setTimeout(() => controller?.abort(), 3000)
      fetch('/health', { signal: controller.signal })
        .then((response) => {
          if (!alive) return
          if (response.ok) {
            attempt = 0
            setBackendDown(false)
            retryTimer = setTimeout(probe, 30_000)
          } else {
            throw new Error('health check failed')
          }
        })
        .catch(() => {
          if (!alive) return
          setBackendDown(true)
          attempt += 1
          retryTimer = setTimeout(probe, Math.min(30_000, 1_000 * 2 ** attempt))
        })
        .finally(() => {
          if (timeoutTimer) clearTimeout(timeoutTimer)
        })
    }
    probe()
    return () => {
      alive = false
      controller?.abort()
      if (timeoutTimer) clearTimeout(timeoutTimer)
      if (retryTimer) clearTimeout(retryTimer)
    }
  }, [])
  return backendDown
}
