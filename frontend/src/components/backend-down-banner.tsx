/** Shared message for a failed backend health request. */
export function BackendDownBanner() {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
      Cannot reach the API at <code className="font-mono">/health</code>. Check that the backend is
      running and retry.
    </div>
  )
}
