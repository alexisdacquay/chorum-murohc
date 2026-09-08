/**
 * The redemption API client, for the merged `/api/v1/redemptions/` routes
 * (issue #55): a child spends points on a reward, and a parent fulfils or
 * cancels the request. Shaped like `api/rewards.ts` and `api/chores.ts`:
 * same-origin session authentication and CSRF only, and every response
 * validated at runtime before it is trusted.
 *
 * The child shape (`ChildRedemption`) and the parent shape
 * (`ParentRedemption`, which adds who asked) are two different response
 * bodies from the one `GET` route, exactly as the server's two serializers
 * differ; this client validates whichever one the caller asks for.
 */

import { CSRF_HEADER_NAME, ensureCsrfToken } from './session'

export type RedemptionStatus = 'pending' | 'fulfilled' | 'cancelled'

export interface ChildRedemption {
  id: number
  reward_name: string
  reward_points: number
  status: RedemptionStatus
  created_at: string
  decided_at: string | null
}

export interface ParentRedemption extends ChildRedemption {
  child_id: number
  child_username: string
}

export const REDEMPTIONS_QUERY_KEY = ['redemptions'] as const

/**
 * - `validation`: the request body was refused, most often because the
 *   reward is unaffordable. `fieldErrors` carries the first message per
 *   field the server named.
 * - `forbidden`: the caller may not perform this action in this household.
 * - `notFound`: the reward or redemption does not exist, belongs to another
 *   household, or (for fulfil and cancel) was already decided.
 * - `unavailable`: unreachable, timed out, not JSON, or an unexpected status.
 */
export type RedemptionFailureKind =
  | 'validation'
  | 'forbidden'
  | 'notFound'
  | 'unavailable'

export class RedemptionRequestError extends Error {
  readonly kind: RedemptionFailureKind
  readonly fieldErrors: Readonly<Record<string, string>>

  constructor(kind: RedemptionFailureKind, fieldErrors: Record<string, string> = {}) {
    super(`Redemption request failed: ${kind}`)
    this.name = 'RedemptionRequestError'
    this.kind = kind
    this.fieldErrors = fieldErrors
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const isJsonMediaType = (contentType: string | null) =>
  contentType !== null &&
  /^application\/(?:[a-z0-9!#$&^_.+-]+\+)?json(?:\s*;|$)/i.test(contentType)

const isRedemptionStatus = (value: unknown): value is RedemptionStatus =>
  value === 'pending' || value === 'fulfilled' || value === 'cancelled'

const hasChildShape = (value: Record<string, unknown>): boolean =>
  typeof value.id === 'number' &&
  Number.isInteger(value.id) &&
  typeof value.reward_name === 'string' &&
  typeof value.reward_points === 'number' &&
  Number.isInteger(value.reward_points) &&
  isRedemptionStatus(value.status) &&
  typeof value.created_at === 'string' &&
  (value.decided_at === null || typeof value.decided_at === 'string')

export const isChildRedemption = (value: unknown): value is ChildRedemption =>
  isRecord(value) && Object.keys(value).length === 6 && hasChildShape(value)

export const isParentRedemption = (value: unknown): value is ParentRedemption =>
  isRecord(value) &&
  Object.keys(value).length === 8 &&
  hasChildShape(value) &&
  typeof value.child_id === 'number' &&
  Number.isInteger(value.child_id) &&
  typeof value.child_username === 'string'

const isChildRedemptionList = (value: unknown): value is ChildRedemption[] =>
  Array.isArray(value) && value.every(isChildRedemption)

const isParentRedemptionList = (value: unknown): value is ParentRedemption[] =>
  Array.isArray(value) && value.every(isParentRedemption)

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

const send = async (path: string, init: RequestInit): Promise<Response> => {
  try {
    return await fetch(path, { credentials: 'same-origin', ...init })
  } catch {
    throw new RedemptionRequestError('unavailable')
  }
}

/** `GET /api/v1/redemptions/`: the child's own history, newest first. */
export const fetchChildRedemptions = async ({
  signal,
}: {
  signal?: AbortSignal
}): Promise<ChildRedemption[]> => {
  const response = await send('/api/v1/redemptions/', {
    method: 'GET',
    headers: { Accept: 'application/json' },
    signal,
  })

  if (response.redirected) {
    throw new RedemptionRequestError('unavailable')
  }
  if (response.status === 403) {
    throw new RedemptionRequestError('forbidden')
  }
  const body = await readJsonBody(response)
  if (response.status !== 200 || !isChildRedemptionList(body)) {
    throw new RedemptionRequestError('unavailable')
  }
  return body
}

/** `GET /api/v1/redemptions/`: every household redemption, with who asked. */
export const fetchParentRedemptions = async ({
  signal,
}: {
  signal?: AbortSignal
}): Promise<ParentRedemption[]> => {
  const response = await send('/api/v1/redemptions/', {
    method: 'GET',
    headers: { Accept: 'application/json' },
    signal,
  })

  if (response.redirected) {
    throw new RedemptionRequestError('unavailable')
  }
  if (response.status === 403) {
    throw new RedemptionRequestError('forbidden')
  }
  const body = await readJsonBody(response)
  if (response.status !== 200 || !isParentRedemptionList(body)) {
    throw new RedemptionRequestError('unavailable')
  }
  return body
}

const readChildRedemptionBody = async (response: Response): Promise<ChildRedemption> => {
  if (response.redirected) {
    throw new RedemptionRequestError('unavailable')
  }
  const body = await readJsonBody(response)

  if (response.status === 400) {
    throw new RedemptionRequestError('validation', readFieldErrors(body))
  }
  if (response.status === 403) {
    throw new RedemptionRequestError('forbidden')
  }
  if (response.status === 404) {
    throw new RedemptionRequestError('notFound')
  }
  if ((response.status !== 200 && response.status !== 201) || !isChildRedemption(body)) {
    throw new RedemptionRequestError('unavailable')
  }
  return body
}

/**
 * `POST /api/v1/redemptions/`: spend points on `rewardId`.
 *
 * `idempotencyKey` must be a fresh value per redemption attempt, and the
 * same value again for a retry of that same attempt (a lost response, a
 * double-tapped button): the server replays the first result rather than
 * charging twice.
 */
export const redeemReward = async ({
  csrfToken,
  rewardId,
  idempotencyKey,
  signal,
}: {
  csrfToken: string
  rewardId: number
  idempotencyKey: string
  signal?: AbortSignal
}): Promise<ChildRedemption> =>
  readChildRedemptionBody(
    await send('/api/v1/redemptions/', {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        [CSRF_HEADER_NAME]: csrfToken,
      },
      body: JSON.stringify({ reward: rewardId, idempotency_key: idempotencyKey }),
      signal,
    }),
  )

const readParentRedemptionBody = async (
  response: Response,
): Promise<ParentRedemption> => {
  if (response.redirected) {
    throw new RedemptionRequestError('unavailable')
  }
  const body = await readJsonBody(response)

  if (response.status === 403) {
    throw new RedemptionRequestError('forbidden')
  }
  if (response.status === 404) {
    throw new RedemptionRequestError('notFound')
  }
  if (response.status !== 200 || !isParentRedemption(body)) {
    throw new RedemptionRequestError('unavailable')
  }
  return body
}

const postAction = async (
  path: string,
  { csrfToken, signal }: { csrfToken: string; signal?: AbortSignal },
): Promise<ParentRedemption> =>
  readParentRedemptionBody(
    await send(path, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        [CSRF_HEADER_NAME]: csrfToken,
      },
      signal,
    }),
  )

/** `POST /api/v1/redemptions/<id>/fulfil/`: hand over the reward. Parent only. */
export const fulfilRedemption = async (
  args: { csrfToken: string; id: number; signal?: AbortSignal },
): Promise<ParentRedemption> => postAction(`/api/v1/redemptions/${args.id}/fulfil/`, args)

/** `POST /api/v1/redemptions/<id>/cancel/`: refuse and refund. Parent only. */
export const cancelRedemption = async (
  args: { csrfToken: string; id: number; signal?: AbortSignal },
): Promise<ParentRedemption> => postAction(`/api/v1/redemptions/${args.id}/cancel/`, args)

export { ensureCsrfToken }
