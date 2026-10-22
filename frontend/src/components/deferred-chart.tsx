import { Component, lazy, Suspense, useState } from 'react'
import type { ComponentType, LazyExoticComponent, ReactNode } from 'react'

type ChartLoader<P extends object> = () => Promise<{ default: ComponentType<P> }>

// Cache component types, never props or health data. The loader identity fixes
// its props type; sharing resolved types avoids suspending on every remount.
const chartTypes = new WeakMap<() => Promise<unknown>, unknown>()

function chartFor<P extends object>(load: ChartLoader<P>, retry = false) {
  const cached = chartTypes.get(load) as LazyExoticComponent<ComponentType<P>> | undefined
  if (cached && !retry) return cached
  const chart = lazy(load)
  chartTypes.set(load, chart)
  return chart
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

/** Loads a chart only on use; failures keep the surrounding answer and data usable. */
export function DeferredChart<P extends object>({
  load,
  chartProps,
  fallback,
}: {
  load: ChartLoader<P>
  chartProps: P
  fallback: ReactNode
}) {
  const [attempt, setAttempt] = useState(() => ({ Chart: chartFor(load), key: 0 }))
  const Chart = attempt.Chart
  return (
    <ChartBoundary
      key={attempt.key}
      fallback={fallback}
      onRetry={() => {
        // React.lazy caches rejections. A fresh type retries the loader; if the
        // browser retains a failed module, the data fallback remains available.
        setAttempt((current) => ({ Chart: chartFor(load, true), key: current.key + 1 }))
      }}
    >
      <Suspense
        fallback={
          <p role="status" className="py-5 text-sm text-gray-500">
            Loading chart…
          </p>
        }
      >
        <Chart {...chartProps} />
      </Suspense>
    </ChartBoundary>
  )
}
