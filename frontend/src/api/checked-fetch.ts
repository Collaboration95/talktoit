/** Shared fetch wrapper that preserves FastAPI's useful problem detail. */
export async function checkedFetch(
  url: string,
  init?: RequestInit,
  failurePrefix = 'Request failed',
): Promise<Response> {
  const response = await fetch(url, init)
  if (response.ok) return response
  const payload = (await response
    .clone()
    .json()
    .catch(() => null)) as { detail?: unknown } | null
  const detail = payload?.detail
  const message =
    typeof detail === 'string'
      ? detail
      : typeof detail === 'object' && detail !== null && 'message' in detail
        ? String((detail as { message?: unknown }).message ?? '')
        : `${response.status} ${response.statusText}`.trim()
  throw new Error(`${failurePrefix}: ${message}`)
}
