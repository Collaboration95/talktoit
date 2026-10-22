import { Component, useEffect, useState } from 'react'
import type { ComponentType, ReactNode } from 'react'

type ChartLoader<P extends object> = () => Promise<{ default: ComponentType<P> }>
type ChartState<P extends object> =
  | { status: 'loading' }
  | { status: 'ready'; Chart: ComponentType<P> }
  | { status: 'failed'; error: unknown }

interface ChartResource<P extends object> {
  id: number
  state: ChartState<P>
  settled: Promise<ChartState<P>>
}

// Share imports and resolved components, never chart props or health data.
// A loader's identity fixes its component props type.
const charts = new WeakMap<() => Promise<unknown>, unknown>()
let nextResourceId = 0

function chartFor<P extends object>(load: ChartLoader<P>, retry = false) {
  const cached = charts.get(load) as ChartResource<P> | undefined
  if (cached && !retry) return cached
  let request: ReturnType<ChartLoader<P>>
  try {
    request = load()
  } catch (error) {
    request = Promise.reject(error)
  }
  const resource: ChartResource<P> = {
    id: nextResourceId++,
    state: { status: 'loading' },
    settled: request.then(
      ({ default: Chart }) => (resource.state = { status: 'ready', Chart }),
      (error: unknown) => (resource.state = { status: 'failed', error }),
    ),
  }
  charts.set(load, resource)
  return resource
}

function ChartContent<P extends object>({
  resource,
  chartProps,
}: {
  resource: ChartResource<P>
  chartProps: P
}) {
  const [state, setState] = useState(resource.state)
  useEffect(() => {
    let active = true
    void resource.settled.then((result) => {
      if (active) setState(result)
    })
    return () => {
      active = false
    }
  }, [resource])

  if (state.status === 'failed') throw state.error
  if (state.status === 'ready') {
    const Chart = state.Chart
    return <Chart {...chartProps} />
  }
  return (
    <p role="status" className="py-5 text-sm text-gray-500">
      Loading chart…
    </p>
  )
}

interface ChartBoundaryProps {
  children: ReactNode
  fallback: ReactNode
  onRetry: () => void
}

class ChartBoundary extends Component<ChartBoundaryProps, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div className="space-y-3 rounded border border-amber-200 bg-amber-50 p-3">
        <p role="alert" className="text-sm text-amber-900">
          Chart could not be loaded. You can still use the data below.
        </p>
        <button
          type="button"
          className="text-sm font-medium text-blue-700 underline"
          onClick={this.props.onRetry}
        >
          Retry chart
        </button>
        {this.props.fallback}
      </div>
    )
  }
}

/** Loads charts on use without a Suspense reveal delay; errors retain usable data. */
export function DeferredChart<P extends object>({
  load,
  chartProps,
  fallback,
}: {
  load: ChartLoader<P>
  chartProps: P
  fallback: ReactNode
}) {
  const [retry, setRetry] = useState<{ load: ChartLoader<P>; resource: ChartResource<P> } | null>(
    null,
  )
  const resource = retry?.load === load ? retry.resource : chartFor(load)
  return (
    <ChartBoundary
      key={resource.id}
      fallback={fallback}
      onRetry={() => {
        // The browser may retain a failed module; the formatted fallback remains
        // available even when another import attempt cannot recover it.
        setRetry({ load, resource: chartFor(load, true) })
      }}
    >
      <ChartContent resource={resource} chartProps={chartProps} />
    </ChartBoundary>
  )
}
