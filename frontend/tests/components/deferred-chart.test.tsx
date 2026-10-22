import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DeferredChart } from '@/components/deferred-chart'

// A delayed/rejected import must leave surrounding answers usable; retry needs a fresh lazy type.
it('isolates a rejected chart import, preserves answer text and retries the loader', async () => {
  let reject!: (reason: Error) => void
  const load = vi
    .fn()
    .mockImplementationOnce(
      () =>
        new Promise((_resolve, fail) => {
          reject = fail
        }),
    )
    .mockResolvedValue({ default: ({ title }: { title: string }) => <div>{title} chart</div> })
  const user = userEvent.setup()
  const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
  try {
    render(
      <>
        <p>Show my measured sleep</p>
        <DeferredChart load={load} chartProps={{ title: 'Sleep' }} fallback={<p>150 min</p>} />
        <p>Another answer is available</p>
      </>,
    )
    expect(screen.getByRole('status')).toHaveTextContent('Loading chart')
    expect(screen.getByText('Show my measured sleep')).toBeInTheDocument()
    await act(async () =>
      reject(new Error('Failed to fetch dynamically imported module: private-url')),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('Chart could not be loaded.')
    expect(screen.queryByText(/private-url/)).not.toBeInTheDocument()
    expect(screen.getByText('150 min')).toBeInTheDocument()
    expect(screen.getByText('Show my measured sleep')).toBeInTheDocument()
    expect(screen.getByText('Another answer is available')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry chart' }))
    expect(await screen.findByText('Sleep chart')).toBeInTheDocument()
    expect(load).toHaveBeenCalledTimes(2)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  } finally {
    errors.mockRestore()
  }
})

it('keeps recovery usable when a retry still fails or a renderer throws', async () => {
  const load = vi.fn().mockResolvedValue({
    default: () => {
      throw new Error('render failure')
    },
  })
  const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
  try {
    const user = userEvent.setup()
    render(<DeferredChart load={load} chartProps={{}} fallback={<p>Download GeoJSON</p>} />)
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry chart' }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('Download GeoJSON')).toBeInTheDocument()
    expect(load).toHaveBeenCalledTimes(2)
  } finally {
    errors.mockRestore()
  }
})

it('reuses a resolved chart across instances and cached navigation without suspending again', async () => {
  const load = vi
    .fn()
    .mockResolvedValue({ default: ({ title }: { title: string }) => <p>{title}</p> })
  const first = render(
    <DeferredChart load={load} chartProps={{ title: 'First chart' }} fallback={null} />,
  )
  expect(await screen.findByText('First chart')).toBeInTheDocument()
  first.unmount()
  render(<DeferredChart load={load} chartProps={{ title: 'Cached chart' }} fallback={null} />)
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  expect(screen.getByText('Cached chart')).toBeInTheDocument()
  expect(load).toHaveBeenCalledTimes(1)
})

it('keeps the current chart and props when an older import resolves after a loader change', async () => {
  let resolveOld!: (value: { default: ({ title }: { title: string }) => React.ReactNode }) => void
  const oldLoad = vi.fn(
    () =>
      new Promise<{ default: ({ title }: { title: string }) => React.ReactNode }>((resolve) => {
        resolveOld = resolve
      }),
  )
  const newLoad = vi
    .fn()
    .mockResolvedValue({ default: ({ title }: { title: string }) => <p>{title}</p> })
  const view = render(
    <DeferredChart load={oldLoad} chartProps={{ title: 'Old chart' }} fallback={null} />,
  )
  view.rerender(
    <DeferredChart load={newLoad} chartProps={{ title: 'Current chart' }} fallback={null} />,
  )
  expect(await screen.findByText('Current chart')).toBeInTheDocument()
  await act(async () => resolveOld({ default: () => <p>Stale imported chart</p> }))
  expect(screen.getByText('Current chart')).toBeInTheDocument()
  expect(screen.queryByText('Stale imported chart')).not.toBeInTheDocument()
  view.unmount()
})

it('shares a pending import and uses current props after another chart unmounts', async () => {
  let resolve!: (value: { default: ({ title }: { title: string }) => React.ReactNode }) => void
  const load = vi.fn(
    () =>
      new Promise<{ default: ({ title }: { title: string }) => React.ReactNode }>((done) => {
        resolve = done
      }),
  )
  const first = render(
    <DeferredChart load={load} chartProps={{ title: 'Unmounted chart' }} fallback={null} />,
  )
  const second = render(
    <DeferredChart load={load} chartProps={{ title: 'Initial title' }} fallback={null} />,
  )
  expect(load).toHaveBeenCalledTimes(1)
  first.unmount()
  second.rerender(
    <DeferredChart load={load} chartProps={{ title: 'Latest title' }} fallback={null} />,
  )
  await act(async () => resolve({ default: ({ title }) => <p>{title}</p> }))
  expect(screen.getByText('Latest title')).toBeInTheDocument()
  expect(screen.queryByText('Unmounted chart')).not.toBeInTheDocument()
  expect(screen.queryByText('Initial title')).not.toBeInTheDocument()
})

it('contains a synchronous loader failure and offers a new import attempt', async () => {
  const load = vi
    .fn()
    .mockImplementationOnce(() => {
      throw new Error('loader unavailable')
    })
    .mockResolvedValue({ default: () => <p>Recovered chart</p> })
  const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
  try {
    const user = userEvent.setup()
    render(<DeferredChart load={load} chartProps={{}} fallback={<p>Formatted values</p>} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Chart could not be loaded.')
    expect(screen.getByText('Formatted values')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry chart' }))
    expect(await screen.findByText('Recovered chart')).toBeInTheDocument()
  } finally {
    errors.mockRestore()
  }
})
