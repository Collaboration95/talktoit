import { setImmediate as nextTask } from 'node:timers/promises'
import { createRoot } from 'react-dom/client'
import { flushSync } from 'react-dom'
import { within } from '@testing-library/react'
import { DeferredChart } from '@/components/deferred-chart'

it('shows the resolved first chart on the next update without waiting for a fallback timer', async () => {
  // async act eagerly flushes Suspense retries and hides the production reveal delay.
  // Exercise normal scheduled updates with an unresolved import and a controlled clock.
  const environment = globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }
  const previous = environment.IS_REACT_ACT_ENVIRONMENT
  environment.IS_REACT_ACT_ENVIRONMENT = false
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'performance'] })
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  let resolve!: (value: { default: () => React.ReactNode }) => void
  const load = () =>
    new Promise<{ default: () => React.ReactNode }>((done) => {
      resolve = done
    })
  try {
    flushSync(() =>
      root.render(
        <>
          <p>Show my steps</p>
          <DeferredChart load={load} chartProps={{}} fallback={<p>Steps table</p>} />
        </>,
      ),
    )
    await nextTask()
    expect(within(host).getByRole('status')).toHaveTextContent('Loading chart')
    resolve({ default: () => <div role="img" aria-label="Steps chart" /> })
    await nextTask()
    await vi.advanceTimersByTimeAsync(32)
    await nextTask()
    expect(within(host).getByText('Show my steps')).toBeVisible()
    expect(within(host).getByRole('img', { name: 'Steps chart' })).toBeVisible()
    expect(within(host).queryByRole('status')).not.toBeInTheDocument()
  } finally {
    flushSync(() => root.unmount())
    host.remove()
    vi.useRealTimers()
    environment.IS_REACT_ACT_ENVIRONMENT = previous
  }
})
