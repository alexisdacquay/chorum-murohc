/**
 * The progression API client for the merged levelling contract (issue #61).
 *
 * Two routes under `/api/v1/progression/`, child-only both ways:
 *
 * - `fetchProgression` reads the caller's own level state: `level`,
 *   `max_level`, `lifetime_points`, `next_level_threshold`,
 *   `points_to_next_level`, and `pending_level_up`. The level is a function
 *   of lifetime points earned, never a stored counter and never something
 *   the client supplies.
 * - `acknowledgeLevelUp` tells the server the caller has now seen their
 *   current level, so it is shown once and never replayed. There is no body:
 *   the level being acknowledged is always the server's own freshly computed
 *   answer.
 *
 * Same-origin session authentication and CSRF only, matching `api/chores.ts`
 * and `api/submissions.ts` exactly: `ensureCsrfToken` and the CSRF header
 * they export are reused here rather than duplicated. Every response crosses
 * a trust boundary, so a body is validated at runtime before it is trusted.
 */

import { CSRF_HEADER_NAME, ensureCsrfToken } from './session'

export interface Progression {
  level: number
  max_level: number
  lifetime_points: number
  next_level_threshold: number | null
  points_to_next_level: number | null
  pending_level_up: number | null
}

export const PROGRESSION_QUERY_KEY = ['progression'] as const

/**
 * - `forbidden`: the caller is no longer an active child of this household.
 * - `unavailable`: unreachable, timed out, not JSON, or an unexpected status.
 */
export type ProgressionFailureKind = 'forbidden' | 'unavailable'

export class ProgressionRequestError extends Error {
  readonly kind: ProgressionFailureKind

  constructor(kind: ProgressionFailureKind) {
    super(`Progression request failed: ${kind}`)
    this.name = 'ProgressionRequestError'
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

const isIntegerOrNull = (value: unknown): value is number | null =>
  value === null || (typeof value === 'number' && Number.isInteger(value))

/** The exact six-key shape the merged contract returns. */
export const isProgression = (value: unknown): value is Progression => {
  if (!isRecord(value) || Object.keys(value).length !== 6) {
    return false
  }
  for (const key of [
    'level',
    'max_level',
    'lifetime_points',
    'next_level_threshold',
    'points_to_next_level',
    'pending_level_up',
  ]) {
    if (!Object.hasOwn(value, key)) {
      return false
    }
  }

  return (
    isNonNegativeInteger(value.level) &&
    isNonNegativeInteger(value.max_level) &&
    isNonNegativeInteger(value.lifetime_points) &&
    isIntegerOrNull(value.next_level_threshold) &&
    isIntegerOrNull(value.points_to_next_level) &&
    isIntegerOrNull(value.pending_level_up)
  )
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

const send = async (path: string, init: RequestInit): Promise<Response> => {
  try {
    return await fetch(path, { credentials: 'same-origin', ...init })
  } catch {
    // The reason is dropped: it can carry a URL or a platform diagnostic, and
    // the interface shows one fixed sentence either way.
    throw new ProgressionRequestError('unavailable')
  }
}

const readProgressionBody = async (response: Response): Promise<Progression> => {
  if (response.redirected) {
    throw new ProgressionRequestError('unavailable')
  }
  if (response.status === 403) {
    throw new ProgressionRequestError('forbidden')
  }
  const body = await readJsonBody(response)
  if (response.status !== 200 || !isProgression(body)) {
    throw new ProgressionRequestError('unavailable')
  }
  return body
}

/** `GET /api/v1/progression/`: the caller's own level state. */
export const fetchProgression = async ({
  signal,
}: { signal?: AbortSignal } = {}): Promise<Progression> =>
  readProgressionBody(
    await send('/api/v1/progression/', {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal,
    }),
  )

/**
 * `POST /api/v1/progression/acknowledge/`: mark the current level as shown.
 *
 * Idempotent: calling it again with nothing newly reached returns the same
 * shape, `pending_level_up` already `null`, and changes nothing on the
 * server.
 */
export const acknowledgeLevelUp = async ({
  csrfToken,
  signal,
}: {
  csrfToken: string
  signal?: AbortSignal
}): Promise<Progression> =>
  readProgressionBody(
    await send('/api/v1/progression/acknowledge/', {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        [CSRF_HEADER_NAME]: csrfToken,
      },
      signal,
    }),
  )

export { ensureCsrfToken }
