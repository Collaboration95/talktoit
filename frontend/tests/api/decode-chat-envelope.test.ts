import { decodeChatEnvelope, recoveryChatEnvelope } from '@/api/decode-chat-envelope'

describe('decodeChatEnvelope', () => {
  it('accepts an unknown template so the template dispatcher can safely fall back', () => {
    expect(
      decodeChatEnvelope({ template_id: 'future_template', data: { value: 1 }, narrative: 'Test.' }),
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
