/**
 * The household audit-history API client (T086, issue #84's absorbed #87):
 * `GET /api/v1/audit/`.
 *
 * Read-only and parent-only, matching the server (`api/audit.py`): the
 * caller's own household's events, newest first, twenty-five to a page,
 * through DRF's native page-number pagination, with three optional filters -
 * `actor` (a user id), `action` (an exact code) and a `date_from`/`date_to`
 * range. `context` arrives already redacted by the model at write time; this
 * client passes it through unchanged rather than filtering it a second time.
 *
 * `fetchAuditEvents` takes a plain page number and the filter values, and
 * rebuilds the query string itself on every call - unlike `api/ledger.ts`,
 * a page here is never meaningful on its own, since changing a filter must
 * also return to page one. There is no client override of the page size.
 *
 * Same-origin session authentication only; there is no write here, so
 * unlike `api/members.ts` there is no CSRF token to carry.
 */

export interface AuditEvent {
  id: number
  actor: number | null
  action: string
  target_type: string
  target_id: string
  created_at: string
  context: Record<string, unknown>
}

export interface AuditEventPage {
  events: AuditEvent[]
  count: number
  hasNext: boolean
  hasPrevious: boolean
}

export interface AuditEventFilters {
  actor?: number
  action?: string
  dateFrom?: string
  dateTo?: string
}

export const auditEventsQueryKey = (page: number, filters: AuditEventFilters) =>
  ['audit', page, filters] as const

/**
 * - `validation`: a filter value was refused. `fieldErrors` carries the
 *   first message per field the server named (`actor`, `action`,
 *   `date_from` or `date_to`).
 * - `forbidden`: the caller is no longer an active parent of this household.
 * - `unavailable`: unreachable, timed out, not JSON, or an unexpected status.
 */
export type AuditFailureKind = 'validation' | 'forbidden' | 'unavailable'

export class AuditRequestError extends Error {
  readonly kind: AuditFailureKind
  readonly fieldErrors: Readonly<Record<string, string>>

  constructor(kind: AuditFailureKind, fieldErrors: Record<string, string> = {}) {
    super(`Audit request failed: ${kind}`)
    this.name = 'AuditRequestError'
    this.kind = kind
    this.fieldErrors = fieldErrors
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const isJsonMediaType = (contentType: string | null) =>
  contentType !== null &&
  /^application\/(?:[a-z0-9!#$&^_.+-]+\+)?json(?:\s*;|$)/i.test(contentType)

const isAuditEvent = (value: unknown): value is AuditEvent =>
  isRecord(value) &&
  Object.keys(value).length === 7 &&
  typeof value.id === 'number' &&
  Number.isInteger(value.id) &&
  (value.actor === null ||
    (typeof value.actor === 'number' && Number.isInteger(value.actor))) &&
  typeof value.action === 'string' &&
  typeof value.target_type === 'string' &&
  typeof value.target_id === 'string' &&
  typeof value.created_at === 'string' &&
  isRecord(value.context)

/** The exact four-key DRF page envelope this route returns. */
const isAuditEnvelope = (
  value: unknown,
): value is {
  count: number
  next: string | null
  previous: string | null
  results: AuditEvent[]
} =>
  isRecord(value) &&
  Object.keys(value).length === 4 &&
  typeof value.count === 'number' &&
  Number.isInteger(value.count) &&
  value.count >= 0 &&
  (value.next === null || typeof value.next === 'string') &&
  (value.previous === null || typeof value.previous === 'string') &&
  Array.isArray(value.results) &&
  value.results.every(isAuditEvent)

/** Reduce a 400 body to one first message per named field. */
const readFieldErrors = (body: unknown): Record<string, string> => {
  if (!isRecord(body)) {
    return {}
  }
  const fieldErrors: Record<string, string> = {}
  for (const [field, messages] of Object.entries(body)) {
    if (
      Array.isArray(messages) &&
      messages.length > 0 &&
      typeof messages[0] === 'string'
    ) {
      fieldErrors[field] = messages[0]
    }
  }
  return fieldErrors
}

const readJsonBody = async (response: Response): Promise<unknown> => {
  if (!isJsonMediaType(response.headers.get('Content-Type'))) {
    return undefined
  }
  try {
    return await response.json()
  } catch {
    return undefined
  }
}

const buildQuery = (page: number, filters: AuditEventFilters): string => {
  const params = new URLSearchParams()
  params.set('page', String(page))
  if (filters.actor !== undefined) {
    params.set('actor', String(filters.actor))
  }
  if (filters.action !== undefined && filters.action !== '') {
    params.set('action', filters.action)
  }
  if (filters.dateFrom !== undefined && filters.dateFrom !== '') {
    params.set('date_from', filters.dateFrom)
  }
  if (filters.dateTo !== undefined && filters.dateTo !== '') {
    params.set('date_to', filters.dateTo)
  }
  return params.toString()
}

/** `GET /api/v1/audit/?...`: one page of the caller's own-household events. */
export const fetchAuditEvents = async ({
  page,
  filters,
  signal,
}: {
  page: number
  filters: AuditEventFilters
  signal?: AbortSignal
}): Promise<AuditEventPage> => {
  let response: Response
  try {
    response = await fetch(`/api/v1/audit/?${buildQuery(page, filters)}`, {
      method: 'GET',
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal,
    })
  } catch {
    throw new AuditRequestError('unavailable')
  }

  if (response.redirected) {
    throw new AuditRequestError('unavailable')
  }
  if (response.status === 403) {
    throw new AuditRequestError('forbidden')
  }

  const body = await readJsonBody(response)

  if (response.status === 400) {
    throw new AuditRequestError('validation', readFieldErrors(body))
  }
  if (response.status !== 200 || !isAuditEnvelope(body)) {
    throw new AuditRequestError('unavailable')
  }

  return {
    events: body.results,
    count: body.count,
    hasNext: body.next !== null,
    hasPrevious: body.previous !== null,
  }
}
