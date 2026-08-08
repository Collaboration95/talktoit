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
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 3000)
    fetch('/health', { signal: controller.signal })
      .then((response) => {
        if (!response.ok) setBackendDown(true)
      })
      .catch(() => setBackendDown(true))
      .finally(() => clearTimeout(timer))
  }, [])
  return backendDown
}
