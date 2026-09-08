/**
 * The reward-catalogue API client, for the merged `/api/v1/rewards/` routes
 * (issue #55). Shaped exactly like `api/chores.ts`, which those routes
 * mirror on the server: same-origin session authentication and CSRF only,
 * `ensureCsrfToken` and its header reused rather than duplicated, and every
 * response validated at runtime before it is trusted.
 *
 * `fetchRewards` and every write belong to the parent reward-management
 * screen, so they read and send the parent shape (id, name, points,
 * is_active, created_at, updated_at). `fetchChildRewards` is the separate,
 * narrower call the child rewards screen uses instead: it validates the
 * three-field shape the server actually sends a child, exactly as
 * `api/chores.ts` reserves its own six-field validator for the parent alone.
 */

import { CSRF_HEADER_NAME, ensureCsrfToken } from './session'

export interface Reward {
  id: number
  name: string
  points: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export const REWARDS_QUERY_KEY_ROOT = 'rewards' as const

export const rewardsQueryKey = (includeInactive: boolean) =>
  [REWARDS_QUERY_KEY_ROOT, { includeInactive }] as const

/**
 * - `validation`: the request body was refused. `fieldErrors` carries the
 *   first message per field the server named.
 * - `forbidden`: the caller is no longer an active parent of this household.
 * - `notFound`: the reward does not exist, or belongs to another household,
 *   or was already removed by another session.
 * - `unavailable`: unreachable, timed out, not JSON, or an unexpected status.
 */
export type RewardFailureKind = 'validation' | 'forbidden' | 'notFound' | 'unavailable'

export class RewardRequestError extends Error {
  readonly kind: RewardFailureKind
  readonly fieldErrors: Readonly<Record<string, string>>

  constructor(kind: RewardFailureKind, fieldErrors: Record<string, string> = {}) {
    super(`Reward request failed: ${kind}`)
    this.name = 'RewardRequestError'
    this.kind = kind
    this.fieldErrors = fieldErrors
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const isJsonMediaType = (contentType: string | null) =>
  contentType !== null &&
  /^application\/(?:[a-z0-9!#$&^_.+-]+\+)?json(?:\s*;|$)/i.test(contentType)

export const isReward = (value: unknown): value is Reward => {
  if (!isRecord(value) || Object.keys(value).length !== 6) {
    return false
  }
  for (const key of ['id', 'name', 'points', 'is_active', 'created_at', 'updated_at']) {
    if (!Object.hasOwn(value, key)) {
      return false
    }
  }

  return (
    typeof value.id === 'number' &&
    Number.isInteger(value.id) &&
    typeof value.name === 'string' &&
    typeof value.points === 'number' &&
    Number.isInteger(value.points) &&
    typeof value.is_active === 'boolean' &&
    typeof value.created_at === 'string' &&
    typeof value.updated_at === 'string'
  )
}

const isRewardList = (value: unknown): value is Reward[] =>
  Array.isArray(value) && value.every(isReward)

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
    throw new RewardRequestError('unavailable')
  }
}

const readRewardBody = async (response: Response): Promise<Reward> => {
  if (response.redirected) {
    throw new RewardRequestError('unavailable')
  }
  const body = await readJsonBody(response)

  if (response.status === 400) {
    throw new RewardRequestError('validation', readFieldErrors(body))
  }
  if (response.status === 403) {
    throw new RewardRequestError('forbidden')
  }
  if (response.status === 404) {
    throw new RewardRequestError('notFound')
  }
  if ((response.status !== 200 && response.status !== 201) || !isReward(body)) {
    throw new RewardRequestError('unavailable')
  }
  return body
}

export interface ChildReward {
  id: number
  name: string
  points: number
}

export const isChildReward = (value: unknown): value is ChildReward => {
  if (!isRecord(value) || Object.keys(value).length !== 3) {
    return false
  }
  for (const key of ['id', 'name', 'points']) {
    if (!Object.hasOwn(value, key)) {
      return false
    }
  }
  return (
    typeof value.id === 'number' &&
    Number.isInteger(value.id) &&
    typeof value.name === 'string' &&
    typeof value.points === 'number' &&
    Number.isInteger(value.points)
  )
}

const isChildRewardList = (value: unknown): value is ChildReward[] =>
  Array.isArray(value) && value.every(isChildReward)

export const CHILD_REWARDS_QUERY_KEY = ['rewards', 'child'] as const

/** `GET /api/v1/rewards/`: the active catalogue, in the child's own shape. */
export const fetchChildRewards = async ({
  signal,
}: {
  signal?: AbortSignal
}): Promise<ChildReward[]> => {
  const response = await send('/api/v1/rewards/', {
    method: 'GET',
    headers: { Accept: 'application/json' },
    signal,
  })

  if (response.redirected) {
    throw new RewardRequestError('unavailable')
  }
  if (response.status === 403) {
    throw new RewardRequestError('forbidden')
  }
  const body = await readJsonBody(response)
  if (response.status !== 200 || !isChildRewardList(body)) {
    throw new RewardRequestError('unavailable')
  }
  return body
}

/** `GET /api/v1/rewards/`: the catalogue, active-only unless `includeInactive`. */
export const fetchRewards = async ({
  includeInactive,
  signal,
}: {
  includeInactive: boolean
  signal?: AbortSignal
}): Promise<Reward[]> => {
  const path = includeInactive
    ? '/api/v1/rewards/?include_inactive=true'
    : '/api/v1/rewards/'
  const response = await send(path, {
    method: 'GET',
    headers: { Accept: 'application/json' },
    signal,
  })

  if (response.redirected) {
    throw new RewardRequestError('unavailable')
  }
  if (response.status === 403) {
    throw new RewardRequestError('forbidden')
  }
  const body = await readJsonBody(response)
  if (response.status !== 200 || !isRewardList(body)) {
    throw new RewardRequestError('unavailable')
  }
  return body
}

interface WriteArgs {
  csrfToken: string
  signal?: AbortSignal
}

/** `POST /api/v1/rewards/`: create one reward. */
export const createReward = async ({
  csrfToken,
  name,
  points,
  signal,
}: WriteArgs & { name: string; points: number }): Promise<Reward> =>
  readRewardBody(
    await send('/api/v1/rewards/', {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        [CSRF_HEADER_NAME]: csrfToken,
      },
      body: JSON.stringify({ name, points }),
      signal,
    }),
  )

/** `PATCH /api/v1/rewards/<id>/`: edit an existing reward's name and points. */
export const updateReward = async ({
  csrfToken,
  id,
  name,
  points,
  signal,
}: WriteArgs & { id: number; name: string; points: number }): Promise<Reward> =>
  readRewardBody(
    await send(`/api/v1/rewards/${id}/`, {
      method: 'PATCH',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        [CSRF_HEADER_NAME]: csrfToken,
      },
      body: JSON.stringify({ name, points }),
      signal,
    }),
  )

/** `DELETE /api/v1/rewards/<id>/`: remove a reward permanently. 204 is success. */
export const deleteReward = async ({
  csrfToken,
  id,
  signal,
}: WriteArgs & { id: number }): Promise<void> => {
  const response = await send(`/api/v1/rewards/${id}/`, {
    method: 'DELETE',
    headers: {
      Accept: 'application/json',
      [CSRF_HEADER_NAME]: csrfToken,
    },
    signal,
  })

  if (response.status === 204) {
    return
  }
  if (response.status === 403) {
    throw new RewardRequestError('forbidden')
  }
  if (response.status === 404) {
    throw new RewardRequestError('notFound')
  }
  throw new RewardRequestError('unavailable')
}

const postStateChange = async (
  path: string,
  { csrfToken, signal }: WriteArgs,
): Promise<Reward> =>
  readRewardBody(
    await send(path, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        [CSRF_HEADER_NAME]: csrfToken,
      },
      signal,
    }),
  )

/** `POST /api/v1/rewards/<id>/deactivate/`: take a reward out of use. */
export const deactivateReward = async (
  args: WriteArgs & { id: number },
): Promise<Reward> => postStateChange(`/api/v1/rewards/${args.id}/deactivate/`, args)

/** `POST /api/v1/rewards/<id>/reactivate/`: put a reward back into use. */
export const reactivateReward = async (
  args: WriteArgs & { id: number },
): Promise<Reward> => postStateChange(`/api/v1/rewards/${args.id}/reactivate/`, args)

export { ensureCsrfToken }
