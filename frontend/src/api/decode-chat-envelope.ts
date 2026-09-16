import type { ChatEnvelope } from '@/types/templates'

const PROVENANCE = new Set([
  'unknown',
  'deterministic_local',
  'remote_planned',
  'fallback',
  'cached',
  'semantic_cached',
])

/**
 * Decode the envelope returned by the chat API or stored in local history.
 *
 * Template payloads intentionally remain opaque here: the template dispatcher
 * owns their per-template validation, and accepting an unknown template lets it
 * render its existing safe fallback. This decoder protects the common envelope
 * contract so live and restored answers fail the same way.
 */
export function decodeChatEnvelope(value: unknown): ChatEnvelope | null {
  if (!isRecord(value)) return null
  if (typeof value['template_id'] !== 'string' || value['template_id'].trim() === '') return null
  if (!('data' in value) || typeof value['narrative'] !== 'string') return null

  const metadata = decodeMetadata(value['metadata'])
  if (value['metadata'] !== undefined && metadata === null) return null

  return {
    template_id: value['template_id'],
    data: value['data'],
    narrative: value['narrative'],
    ...(metadata ? { metadata } : {}),
  }
}

/** Return a safe fallback for corrupt historical records while retaining its query. */
export function recoveryChatEnvelope(question: string): ChatEnvelope {
  return {
    template_id: 'fallback',
    data: {
      question,
      table: null,
      text: null,
      message: 'This saved answer is unavailable because its stored format is invalid.',
    },
    narrative: 'This saved answer could not be restored. Please try asking the question again.',
  }
}

function decodeMetadata(value: unknown): ChatEnvelope['metadata'] | null {
  if (!isRecord(value)) return null
  if (value['api_version'] !== 'v1' || typeof value['provenance'] !== 'string') return null
  if (!PROVENANCE.has(value['provenance'])) return null
  if (!isNullableString(value['dataset_version_id'])) return null
  if (!isNullableString(value['coverage_start'])) return null
  if (!isNullableString(value['coverage_end'])) return null
  if (!isNullableString(value['generated_at'])) return null
  if (!isNullableString(value['turn_id'])) return null

  return {
    api_version: 'v1',
    provenance: value['provenance'] as NonNullable<ChatEnvelope['metadata']>['provenance'],
    ...(value['dataset_version_id'] !== undefined
      ? { dataset_version_id: value['dataset_version_id'] as string | null }
      : {}),
    ...(value['coverage_start'] !== undefined
      ? { coverage_start: value['coverage_start'] as string | null }
      : {}),
    ...(value['coverage_end'] !== undefined
      ? { coverage_end: value['coverage_end'] as string | null }
      : {}),
    ...(value['generated_at'] !== undefined
      ? { generated_at: value['generated_at'] as string | null }
      : {}),
    ...(value['turn_id'] !== undefined ? { turn_id: value['turn_id'] as string | null } : {}),
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isNullableString(value: unknown): value is string | null | undefined {
  return value === undefined || value === null || typeof value === 'string'
}
