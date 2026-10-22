import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse, delay } from 'msw'
import { setupServer } from 'msw/node'
import { ChatView } from '@/components/chat-view'

const server = setupServer(
  http.get('/health', () => HttpResponse.json({ status: 'ok' })),
  http.get('/api/conversations', () => HttpResponse.json([])),
  http.get('/api/settings', () => HttpResponse.json({ dataset: null })),
  http.post('/api/conversations', () => HttpResponse.json({ id: 'cv_test' })),
)
beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

// Mock echarts-for-react and Tremor for jsdom
vi.mock('echarts-for-react', () => ({ default: () => <div data-testid="echarts" /> }))
vi.mock('@tremor/react', () => ({ BarList: () => <div data-testid="bar-list" /> }))

const WORKOUT_ENVELOPE = {
  template_id: 'workout_card',
  data: {
    activity_type: 'Running',
    date: '2026-06-05T07:00:00+08:00',
    duration_minutes: 45.5,
    avg_heart_rate: null,
    max_heart_rate: null,
    distance_meters: null,
    distance_unit: 'km',
    energy_burned_kj: null,
    elevation_ascent_meters: null,
  },
  narrative: 'Your last run was on June 5.',
  metadata: {
    api_version: 'v1' as const,
    provenance: 'deterministic_local' as const,
    dataset_version_id: 'ds_fixture',
  },
}

describe('ChatView', () => {
  it('renders idle state initially', async () => {
    render(<ChatView />)
    expect(screen.getByText(/ask a question/i)).toBeInTheDocument()
    await act(async () => {})
  })

  it('shows loading state while request is in flight', async () => {
    let resolve: (v: Response) => void
    server.use(
      http.post('/api/chat', () =>
        new Promise((r) => {
          resolve = r
        }).then(() => HttpResponse.json(WORKOUT_ENVELOPE)),
      ),
    )
    const user = userEvent.setup()
    render(<ChatView />)
    await user.type(screen.getByRole('textbox'), 'last run')
    await user.click(screen.getByRole('button', { name: /ask/i }))
    expect(screen.getByText(/thinking about/i)).toBeInTheDocument()
    resolve!(new Response())
  })

  it('keeps a reader at the transcript end when a new turn is appended', async () => {
    const scrollIntoView = vi.fn()
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: scrollIntoView,
    })
    server.use(http.post('/api/chat', () => HttpResponse.json(WORKOUT_ENVELOPE)))
    const user = userEvent.setup()
    render(<ChatView />)
    await user.type(screen.getByRole('textbox'), 'last run')
    await user.click(screen.getByRole('button', { name: /ask/i }))
    await screen.findByText('Your last run was on June 5.')
    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'end' })
  })

  it('cancels an in-flight request via the real abort path without a flash of success', async () => {
    // GH-19: MSW delays the response; clicking Cancel aborts the request and
    // the turn must land in the cancelled-error state (holding in loading until
    // the abort surfaces is illegal, and a success flash is forbidden).
    server.use(
      http.post('/api/chat', async () => {
        await delay('infinite')
        return HttpResponse.json(WORKOUT_ENVELOPE)
      }),
    )
    const user = userEvent.setup()
    render(<ChatView />)
    await user.type(screen.getByRole('textbox'), 'last run')
    await user.click(screen.getByRole('button', { name: /ask/i }))
    expect(screen.getByText(/thinking about/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(await screen.findByText('This request was cancelled.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    // No success flash: the workout card must never appear.
    expect(screen.queryByText('Your last run was on June 5.')).not.toBeInTheDocument()
  })

  it('renders a workout card template on success with the query shown above', async () => {
    server.use(http.post('/api/chat', () => HttpResponse.json(WORKOUT_ENVELOPE)))
    const user = userEvent.setup()
    render(<ChatView />)
    await user.type(screen.getByRole('textbox'), 'last run')
    await user.click(screen.getByRole('button', { name: /ask/i }))
    await waitFor(() => {
      expect(screen.getByText('Running')).toBeInTheDocument()
    })
    // Query is displayed above the answer
    expect(screen.getByText('last run')).toBeInTheDocument()
    expect(screen.getByText('Your last run was on June 5.')).toBeInTheDocument()
    expect(screen.getByText(/Deterministic local answer · dataset ds_fixture/)).toBeInTheDocument()
  })

  it('collapses answer details without removing the query or stored answer', async () => {
    server.use(http.post('/api/chat', () => HttpResponse.json(WORKOUT_ENVELOPE)))
    const user = userEvent.setup()
    render(<ChatView />)
    await user.type(screen.getByRole('textbox'), 'last run')
    await user.click(screen.getByRole('button', { name: /ask/i }))
    await screen.findByText('Your last run was on June 5.')

    await user.click(screen.getByRole('button', { name: 'Hide answer details' }))
    expect(screen.getByText('last run')).toBeInTheDocument()
    expect(screen.queryByText('Your last run was on June 5.')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show answer details' })).toHaveAttribute(
      'aria-expanded',
      'false',
    )

    await user.click(screen.getByRole('button', { name: 'Show answer details' }))
    expect(await screen.findByText('Your last run was on June 5.')).toBeInTheDocument()
  })

  it('renders error state on API failure', async () => {
    server.use(http.post('/api/chat', () => HttpResponse.json({}, { status: 500 })))
    const user = userEvent.setup()
    render(<ChatView />)
    await user.type(screen.getByRole('textbox'), 'bad question')
    await user.click(screen.getByRole('button', { name: /ask/i }))
    await waitFor(() => {
      expect(screen.getByText(/request failed/i)).toBeInTheDocument()
    })
  })

  it('restores a persisted failed turn as a visible retryable transcript item', async () => {
    server.use(
      http.get('/api/conversations', () =>
        HttpResponse.json([
          { id: 'cv_failed', title: 'Retry me', created_at: 'now', updated_at: 'now' },
        ]),
      ),
      http.get('/api/conversations/cv_failed/turns', () =>
        HttpResponse.json([
          {
            id: 'tr_failed',
            question: 'Last run?',
            state: 'failed',
            response_json: null,
            error_message: 'The answer could not be completed.',
          },
        ]),
      ),
    )
    const user = userEvent.setup()
    render(<ChatView />)
    await user.click(await screen.findByRole('button', { name: 'Retry me' }))
    expect(await screen.findByText('The answer could not be completed.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('recovers a malformed saved response without losing its question', async () => {
    server.use(
      http.get('/api/conversations', () =>
        HttpResponse.json([
          { id: 'cv_malformed', title: 'Malformed history', created_at: 'now', updated_at: 'now' },
        ]),
      ),
      http.get('/api/conversations/cv_malformed/turns', () =>
        HttpResponse.json([
          {
            id: 'tr_malformed',
            question: 'How many steps did I take?',
            state: 'completed',
            response_json: '{not valid json',
            error_message: null,
          },
        ]),
      ),
    )
    const user = userEvent.setup()
    render(<ChatView />)

    await user.click(await screen.findByRole('button', { name: 'Malformed history' }))

    expect(await screen.findByText('How many steps did I take?')).toBeInTheDocument()
    expect(screen.getByText(/saved answer could not be restored/i)).toBeInTheDocument()
  })

  it('shows the safe unknown-template fallback for a live answer', async () => {
    server.use(
      http.post('/api/chat', () =>
        HttpResponse.json({
          template_id: 'future_template',
          data: {},
          narrative: 'Future answer.',
        }),
      ),
    )
    const user = userEvent.setup()
    render(<ChatView />)
    await user.type(screen.getByRole('textbox'), 'show something new')
    await user.click(screen.getByRole('button', { name: /ask/i }))

    expect(await screen.findByText(/unknown template: future_template/i)).toBeInTheDocument()
  })

  it('renames a selected local conversation without touching health data', async () => {
    let renamed = false
    server.use(
      http.get('/api/conversations', () =>
        HttpResponse.json([
          {
            id: 'cv_test',
            title: 'Morning runs',
            created_at: '2026-06-05T00:00:00Z',
            updated_at: '2026-06-05T00:00:00Z',
          },
        ]),
      ),
      http.patch('/api/conversations/cv_test', async ({ request }) => {
        expect(await request.json()).toEqual({ title: 'Weekend runs' })
        renamed = true
        return HttpResponse.json({ ok: true })
      }),
    )
    const user = userEvent.setup()
    render(<ChatView />)
    await user.click(await screen.findByRole('button', { name: 'Rename Morning runs' }))
    const input = screen.getByRole('textbox', { name: 'New conversation title' })
    await user.clear(input)
    await user.type(input, 'Weekend runs')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(renamed).toBe(true))
  })

  it('seed prompt submits directly and shows the query', async () => {
    server.use(
      http.post('/api/chat', () => HttpResponse.json(WORKOUT_ENVELOPE)),
      http.get('/api/settings', () =>
        HttpResponse.json({ dataset: { counts: { workouts: 3 } }, quality: { metric_states: {} } }),
      ),
    )
    const user = userEvent.setup()
    render(<ChatView />)
    await user.click(await screen.findByRole('button', { name: /last workout/i }))
    await waitFor(() => {
      expect(screen.getByText('Running')).toBeInTheDocument()
    })
    // Query label is visible
    expect(screen.getByText('Query')).toBeInTheDocument()
  })

  it('pins the composer to the bottom after the first query', async () => {
    server.use(http.post('/api/chat', () => HttpResponse.json(WORKOUT_ENVELOPE)))
    const user = userEvent.setup()
    render(<ChatView />)
    // Idle state: composer sits in the upper area, no pinned bottom bar.
    expect(screen.queryByTestId('composer-bar')).not.toBeInTheDocument()
    expect(screen.getByRole('textbox')).toBeInTheDocument()
    await user.type(screen.getByRole('textbox'), 'last run')
    await user.click(screen.getByRole('button', { name: /ask/i }))
    await screen.findByText('Your last run was on June 5.')
    // After the first turn the composer moves into the pinned bottom bar.
    const bar = screen.getByTestId('composer-bar')
    expect(bar).toHaveClass('sticky')
    expect(within(bar).getByRole('textbox')).toBeInTheDocument()
    // Seed prompts no longer clutter the active conversation.
    expect(screen.queryByRole('button', { name: /last long run/i })).not.toBeInTheDocument()
  })

  it('returns to the idle composer when starting a new conversation', async () => {
    server.use(http.post('/api/chat', () => HttpResponse.json(WORKOUT_ENVELOPE)))
    const user = userEvent.setup()
    render(<ChatView />)
    await user.type(screen.getByRole('textbox'), 'last run')
    await user.click(screen.getByRole('button', { name: /ask/i }))
    await screen.findByText('Your last run was on June 5.')
    expect(screen.getByTestId('composer-bar')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'New conversation' }))
    expect(screen.queryByTestId('composer-bar')).not.toBeInTheDocument()
    expect(screen.getByText(/ask a question/i)).toBeInTheDocument()
  })

  it('clears a selected parent answer when switching conversations', async () => {
    const answerWithTurn = {
      ...WORKOUT_ENVELOPE,
      metadata: { ...WORKOUT_ENVELOPE.metadata, turn_id: 'tr_parent' },
    }
    let laterRequest: Record<string, unknown> | undefined
    server.use(
      http.get('/api/conversations', () =>
        HttpResponse.json([
          { id: 'cv_a', title: 'Current', created_at: 'now', updated_at: 'now' },
          { id: 'cv_b', title: 'Other', created_at: 'now', updated_at: 'now' },
        ]),
      ),
      http.get('/api/conversations/cv_b/turns', () => HttpResponse.json([])),
      http.post('/api/conversations', () => HttpResponse.json({ id: 'cv_a' })),
      http.post('/api/chat', async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>
        if (body.question === 'new question') laterRequest = body
        return HttpResponse.json(answerWithTurn)
      }),
    )
    const user = userEvent.setup()
    render(<ChatView />)
    await user.type(screen.getByRole('textbox'), 'last run')
    await user.click(screen.getByRole('button', { name: /^ask$/i }))
    await screen.findByText('Your last run was on June 5.')
    await user.click(screen.getByRole('button', { name: 'Ask about this answer' }))
    expect(screen.getByText(/Following up on:/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Other' }))
    await waitFor(() => expect(screen.queryByText(/Following up on:/)).not.toBeInTheDocument())

    await user.type(screen.getByRole('textbox'), 'new question')
    await user.click(screen.getByRole('button', { name: /^ask$/i }))
    await waitFor(() => expect(laterRequest).toBeDefined())
    expect(laterRequest).toMatchObject({ question: 'new question', conversation_id: 'cv_b' })
    expect(laterRequest).not.toHaveProperty('parent_turn_id')
  })

  it('renders fallback guidance without blaming the local model', async () => {
    server.use(
      http.post('/api/chat', () =>
        HttpResponse.json({
          template_id: 'fallback',
          data: {
            question: 'pace',
            table: null,
            text: 'Pace ranking is unsupported.',
            reason: 'unsupported',
          },
          narrative: '',
        }),
      ),
    )
    const user = userEvent.setup()
    render(<ChatView />)
    await user.type(screen.getByRole('textbox'), 'pace')
    await user.click(screen.getByRole('button', { name: /^ask$/i }))
    expect(await screen.findByRole('heading', { name: 'Not supported yet' })).toBeInTheDocument()
    expect(screen.queryByText(/start it in Settings/i)).not.toBeInTheDocument()
  })

  it('shows no degraded-answer notice for full answers', async () => {
    server.use(http.post('/api/chat', () => HttpResponse.json(WORKOUT_ENVELOPE)))
    const user = userEvent.setup()
    render(<ChatView />)
    await user.type(screen.getByRole('textbox'), 'last run')
    await user.click(screen.getByRole('button', { name: /ask/i }))
    await screen.findByText('Your last run was on June 5.')
    expect(screen.queryByText(/showing a basic summary of your data/i)).not.toBeInTheDocument()
  })

  it('drops a late conversation load after starting a new conversation', async () => {
    server.use(
      http.get('/api/conversations', () =>
        HttpResponse.json([{ id: 'cv_slow', title: 'Slow', created_at: 'now', updated_at: 'now' }]),
      ),
      http.get('/api/conversations/cv_slow/turns', async () => {
        await delay(60)
        return HttpResponse.json([
          {
            id: 'tr_one',
            question: 'Old question',
            state: 'completed',
            response_json: JSON.stringify(WORKOUT_ENVELOPE),
            error_message: null,
          },
        ])
      }),
    )
    const user = userEvent.setup()
    render(<ChatView />)
    await user.click(await screen.findByRole('button', { name: 'Slow' }))
    // The load is still pending when the user resets to a new conversation.
    await user.click(screen.getByRole('button', { name: 'New conversation' }))
    await new Promise((resolve) => setTimeout(resolve, 150))
    expect(screen.queryByText('Old question')).not.toBeInTheDocument()
    expect(screen.getByText(/ask a question/i)).toBeInTheDocument()
  })

  it('resets the transcript when the active conversation is deleted', async () => {
    server.use(
      http.get('/api/conversations', () =>
        HttpResponse.json([
          { id: 'cv_del', title: 'Delete me', created_at: 'now', updated_at: 'now' },
        ]),
      ),
      http.get('/api/conversations/cv_del/turns', () =>
        HttpResponse.json([
          {
            id: 'tr_one',
            question: 'Old question',
            state: 'completed',
            response_json: JSON.stringify(WORKOUT_ENVELOPE),
            error_message: null,
          },
        ]),
      ),
      http.delete('/api/conversations/cv_del', () => HttpResponse.json({ ok: true })),
    )
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    render(<ChatView />)
    await user.click(await screen.findByRole('button', { name: 'Delete me' }))
    await screen.findByText('Old question')
    await user.click(screen.getByRole('button', { name: 'Delete Delete me' }))
    await waitFor(() => expect(screen.queryByText('Old question')).not.toBeInTheDocument())
    confirm.mockRestore()
  })

  it('shows the backend problem message for a failed answer', async () => {
    server.use(
      http.post('/api/chat', () =>
        HttpResponse.json(
          {
            detail: {
              code: 'provider_unavailable',
              message:
                'The optional language provider is unavailable. Try again or use local mode.',
            },
          },
          { status: 503 },
        ),
      ),
    )
    const user = userEvent.setup()
    render(<ChatView />)
    await user.type(screen.getByRole('textbox'), 'last run')
    await user.click(screen.getByRole('button', { name: /ask/i }))
    expect(
      await screen.findByText(
        'The optional language provider is unavailable. Try again or use local mode.',
      ),
    ).toBeInTheDocument()
  })

  it('surfaces a conversation-create failure in the turn', async () => {
    server.use(
      http.post('/api/conversations', () =>
        HttpResponse.json({ detail: 'Could not create' }, { status: 500 }),
      ),
    )
    const user = userEvent.setup()
    render(<ChatView />)
    await user.type(screen.getByRole('textbox'), 'last run')
    await user.click(screen.getByRole('button', { name: /ask/i }))
    expect(await screen.findByText(/Request failed: Could not create/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('shows a visible error when the conversation list cannot load', async () => {
    server.use(
      http.get('/api/conversations', () =>
        HttpResponse.json({ detail: 'List unavailable' }, { status: 500 }),
      ),
    )
    render(<ChatView />)
    expect(
      await screen.findByText('Could not load conversations: List unavailable'),
    ).toBeInTheDocument()
  })
})

it('formats provenance coverage with the shared readable date range', async () => {
  server.use(
    http.post('/api/chat', () =>
      HttpResponse.json({
        ...WORKOUT_ENVELOPE,
        metadata: {
          ...WORKOUT_ENVELOPE.metadata,
          coverage_start: '2026-06-01',
          coverage_end: '2026-06-10',
        },
      }),
    ),
  )
  const user = userEvent.setup()
  render(<ChatView />)
  await user.type(screen.getByRole('textbox'), 'last run')
  await user.click(screen.getByRole('button', { name: /ask/i }))
  expect(await screen.findByText(/data coverage 1 Jun 2026 to 10 Jun 2026/)).toBeInTheDocument()
  expect(screen.queryByText(/data coverage 2026-/)).not.toBeInTheDocument()
})

const ANALYTICS_ENVELOPES = [
  {
    template_id: 'trend_chart',
    data: {
      title: 'Sleep interval coverage',
      metric_label: 'Sleep',
      metric_unit: 'hours',
      granularity: 'day',
      series: [{ bucket: '2026-06-01', value: 2.5 }],
    },
    narrative: 'Coverage includes awake and in-bed records.',
  },
  {
    template_id: 'comparison',
    data: {
      title: 'Measured metric comparison',
      this_period_label: '1–7 Jun 2026',
      last_period_label: '25–27 May 2026',
      metrics: [
        {
          label: 'Steps per observed day',
          unit: 'steps/day',
          this_value: 8000,
          last_value: null,
          delta: null,
          direction: 'flat',
          direction_tone: 'neutral',
          this_observed_days: 4,
          this_requested_days: 7,
          last_observed_days: 0,
          last_requested_days: 3,
        },
      ],
    },
    narrative: 'Compare imported measurements.',
  },
]

it.each(ANALYTICS_ENVELOPES)(
  'keeps the analytics question visible through loading and success ($template_id)',
  async (envelope) => {
    let release: () => void = () => {}
    server.use(
      http.post('/api/chat', async () => {
        await new Promise<void>((resolve) => {
          release = resolve
        })
        return HttpResponse.json(envelope)
      }),
    )
    const user = userEvent.setup()
    render(<ChatView />)
    const question =
      envelope.template_id === 'trend_chart'
        ? 'Show daily sleep last week'
        : 'Compare steps from 1–7 June 2026 with 8–14 June 2026'
    await user.type(screen.getByRole('textbox'), question)
    await user.click(screen.getByRole('button', { name: /ask/i }))
    await screen.findByText(/thinking about/i)
    expect(screen.getByText(question)).toBeInTheDocument()
    release()
    expect(await screen.findByText(envelope.narrative)).toBeInTheDocument()
    expect(screen.getByText(question)).toBeInTheDocument()
  },
)

it.each([
  {
    template_id: 'fallback',
    data: {
      text: 'No matching sleep records. Try a wider date range.',
      reason: 'no_matching_data',
    },
    narrative: '',
  },
  { template_id: 'future_analytics', data: {}, narrative: '' },
])(
  'keeps the sleep question visible for empty and unknown answers ($template_id)',
  async (envelope) => {
    server.use(http.post('/api/chat', () => HttpResponse.json(envelope)))
    const user = userEvent.setup()
    render(<ChatView />)
    await user.type(screen.getByRole('textbox'), 'Show sleep last week')
    await user.click(screen.getByRole('button', { name: /ask/i }))
    await screen.findByText(
      envelope.template_id === 'fallback' ? /No matching sleep records/ : /Unknown template/,
    )
    expect(screen.getByText('Show sleep last week')).toBeInTheDocument()
  },
)

it('retains the metric question with an actionable error', async () => {
  server.use(
    http.post('/api/chat', () => HttpResponse.json({ detail: 'Synthetic error' }, { status: 500 })),
  )
  const user = userEvent.setup()
  render(<ChatView />)
  await user.type(screen.getByRole('textbox'), 'Compare steps this week')
  await user.click(screen.getByRole('button', { name: /ask/i }))
  await screen.findByRole('button', { name: /retry/i })
  expect(screen.getByText('Compare steps this week')).toBeInTheDocument()
})
