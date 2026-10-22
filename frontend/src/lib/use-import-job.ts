import { useEffect, useRef, useState } from 'react'
import { cancelImport, fetchImport, listImports, startImport } from '@/api/imports'
import type { ImportJob } from '@/api/imports'

const isActive = (job: ImportJob | null) => job?.state === 'queued' || job?.state === 'running'

/** Reconnect to process-local imports; abort polling and discard responses superseded by cancel. */
export function useImportJob() {
  const [job, setJob] = useState<ImportJob | null>(null)
  const [discoveryFailed, setDiscoveryFailed] = useState(false)
  const [discovering, setDiscovering] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [tracking, setTracking] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [discovery, setDiscovery] = useState(0)
  const mounted = useRef(false)
  const revision = useRef(0)
  const [actions] = useState(() => new Set<AbortController>())

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      for (const controller of actions) controller.abort()
    }
  }, [actions])

  useEffect(() => {
    const controller = new AbortController()
    let current = true
    setDiscovering(true)
    setDiscoveryFailed(false)
    listImports(controller.signal)
      .then((jobs) => {
        if (!current) return
        setJob(jobs.find(isActive) ?? jobs[0] ?? null)
        setTracking(true)
        setError(null)
      })
      .catch(() => {
        if (current) {
          setDiscoveryFailed(true)
          setError('Could not check for an active import. Retry before uploading.')
        }
      })
      .finally(() => {
        if (current) setDiscovering(false)
      })
    return () => {
      current = false
      controller.abort()
    }
  }, [discovery])

  const active = isActive(job) && tracking
  const jobId = job?.id
  useEffect(() => {
    if (!active || !jobId) return
    const controller = new AbortController()
    let current = true
    let timer: number
    const poll = async () => {
      const requestRevision = revision.current
      try {
        const latest = await fetchImport(jobId, controller.signal)
        if (current && revision.current === requestRevision) setJob(latest)
      } catch {
        if (current && revision.current === requestRevision) {
          setTracking(false)
          setError(
            'Import status is unknown or interrupted. The backend may have restarted; check the dataset before retrying.',
          )
        }
      } finally {
        if (current) timer = window.setTimeout(() => void poll(), 750)
      }
    }
    timer = window.setTimeout(() => void poll(), 750)
    return () => {
      current = false
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [active, jobId])

  async function upload(file: File) {
    if (uploading || active || discovering || discoveryFailed) return
    revision.current++
    const controller = new AbortController()
    actions.add(controller)
    setUploading(true)
    setError(null)
    setJob(null)
    try {
      const created = await startImport(file, controller.signal)
      if (mounted.current) {
        setJob(created)
        setTracking(true)
      }
    } catch {
      if (mounted.current)
        setError('Could not start the import. Check active imports before retrying.')
    } finally {
      actions.delete(controller)
      if (mounted.current) setUploading(false)
    }
  }

  async function cancel() {
    if (!job || cancelling || !active) return
    revision.current++
    const controller = new AbortController()
    actions.add(controller)
    setCancelling(true)
    setError(null)
    try {
      let latest: ImportJob
      try {
        latest = await cancelImport(job.id, controller.signal)
      } catch {
        latest = await fetchImport(job.id, controller.signal)
      }
      if (mounted.current) {
        revision.current++
        setJob(latest)
        if (isActive(latest))
          setError(
            'Cancellation was not confirmed. The import is still running; retry cancellation.',
          )
      }
    } catch {
      if (mounted.current) {
        setTracking(false)
        setError('Import status is unknown or interrupted. Check active imports before retrying.')
      }
    } finally {
      actions.delete(controller)
      if (mounted.current) setCancelling(false)
    }
  }

  return {
    job,
    error,
    discovering,
    cancelling,
    busy: discovering || discoveryFailed || uploading || active,
    upload,
    cancel,
    retry: () => setDiscovery((value) => value + 1),
  }
}
