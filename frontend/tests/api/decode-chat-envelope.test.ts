import { decodeChatEnvelope, recoveryChatEnvelope } from '@/api/decode-chat-envelope'

describe('decodeChatEnvelope', () => {
  it('accepts an unknown template so the template dispatcher can safely fall back', () => {
    expect(
      decodeChatEnvelope({
        template_id: 'future_template',
        data: { value: 1 },
        narrative: 'Test.',
      }),
    ).toEqual({ template_id: 'future_template', data: { value: 1 }, narrative: 'Test.' })
  })

  it('rejects malformed envelope and metadata contracts', () => {
    expect(decodeChatEnvelope({ template_id: 'fallback', data: {} })).toBeNull()
    expect(
      decodeChatEnvelope({
        template_id: 'fallback',
        data: {},
        narrative: 'Test.',
        metadata: { api_version: 'v1', provenance: 'not-a-real-source' },
      }),
    ).toBeNull()
  })

  it('creates a safe recovered answer with the original question', () => {
    expect(recoveryChatEnvelope('How many steps?')).toMatchObject({
      template_id: 'fallback',
      data: { question: 'How many steps?' },
    })
  })
})

it('preserves additive comparison coverage and legacy workout rows', () => {
  for (const metric of [
    {
      label: 'Sessions',
      unit: 'sessions',
      this_value: 2,
      last_value: 1,
      delta: 1,
      direction: 'up',
    },
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
      value_basis: 'observed_day_mean',
    },
  ]) {
    const envelope = {
      template_id: 'comparison',
      data: {
        title: 'Comparison',
        this_period_label: '1–7 Jun 2026',
        last_period_label: '25–27 May 2026',
        metrics: [metric],
      },
      narrative: 'Measured comparison.',
    }
    expect(decodeChatEnvelope(envelope)).toEqual(envelope)
  }
})
