/**
 * The parent household overview API client (T084, issue #84): `GET
 * /api/v1/overview/`.
 *
 * Read-only and parent-only, matching the server exactly: one bounded
 * summary of the caller's own household - each active child's balance,
 * level, creature and pending-submission count, the household's active
 * parents by name, and a household-wide pending total. There is no query
 * string: the household always comes from the caller's own session, never
 * from a client-supplied id.
 *
 * Same-origin session authentication only; there is no write here, so unlike
 * `api/members.ts` there is no CSRF token to carry.
 *
 * Every response crosses a trust boundary, so the body is validated at
 * runtime before it is trusted, matching every other client in this
 * directory.
 */

export interface OverviewChild {
  id: number
  username: string
  balance: number
  level: number
  max_level: number
  creature_line: string | null
  creature_form: string | null
  pending_count: number
}

export interface OverviewParent {
  id: number
  username: string
}

export interface Overview {
  children: OverviewChild[]
  parents: OverviewParent[]
  pending_total: number
}

export const OVERVIEW_QUERY_KEY = ['overview'] as const

/**
 * - `forbidden`: the caller is no longer an active parent of this household.
 * - `unavailable`: unreachable, timed out, not JSON, or an unexpected status.
 */
export type OverviewFailureKind = 'forbidden' | 'unavailable'

export class OverviewRequestError extends Error {
  readonly kind: OverviewFailureKind

  constructor(kind: OverviewFailureKind) {
    super(`Overview request failed: ${kind}`)
    this.name = 'OverviewRequestError'
    this.kind = kind
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const isJsonMediaType = (contentType: string | null) =>
  contentType !== null &&
  /^application\/(?:[a-z0-9!#$&^_.+-]+\+)?json(?:\s*;|$)/i.test(contentType)

const isNonNegativeInteger = (value: unknown): value is number =>
  typeof value === 'number' && Number.isInteger(value) && value >= 0

const isStringOrNull = (value: unknown): value is string | null =>
  value === null || typeof value === 'string'

const isOverviewChild = (value: unknown): value is OverviewChild =>
  isRecord(value) &&
  Object.keys(value).length === 8 &&
  isNonNegativeInteger(value.id) &&
  typeof value.username === 'string' &&
  typeof value.balance === 'number' &&
  Number.isInteger(value.balance) &&
  isNonNegativeInteger(value.level) &&
  isNonNegativeInteger(value.max_level) &&
  isStringOrNull(value.creature_line) &&
  isStringOrNull(value.creature_form) &&
  isNonNegativeInteger(value.pending_count)

const isOverviewParent = (value: unknown): value is OverviewParent =>
  isRecord(value) &&
  Object.keys(value).length === 2 &&
  isNonNegativeInteger(value.id) &&
  typeof value.username === 'string'

/** The exact three-key shape the endpoint returns. */
export const isOverview = (value: unknown): value is Overview =>
  isRecord(value) &&
  Object.keys(value).length === 3 &&
  Array.isArray(value.children) &&
  value.children.every(isOverviewChild) &&
  Array.isArray(value.parents) &&
  value.parents.every(isOverviewParent) &&
  isNonNegativeInteger(value.pending_total)

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

/** `GET /api/v1/overview/`: the caller's own-household summary. */
export const fetchOverview = async ({
  signal,
}: { signal?: AbortSignal } = {}): Promise<Overview> => {
  let response: Response
  try {
    response = await fetch('/api/v1/overview/', {
      method: 'GET',
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal,
    })
  } catch {
    throw new OverviewRequestError('unavailable')
  }

  if (response.redirected) {
    throw new OverviewRequestError('unavailable')
  }
  if (response.status === 403) {
    throw new OverviewRequestError('forbidden')
  }

  const body = await readJsonBody(response)
  if (response.status !== 200 || !isOverview(body)) {
    throw new OverviewRequestError('unavailable')
  }
  return body
}
