/**
 * The chore-pool API client for the merged T035 contract (issue #35).
 *
 * Five routes under `/api/v1/chores/`, parent-only for every write. This
 * client is used only from the parent chore-pool screen, so it always reads
 * and sends the parent shape (id, name, points, is_active, created_at,
 * updated_at); the shorter child shape belongs to a future child screen.
 *
 * Same-origin session authentication and CSRF only, matching `api/session.ts`
 * exactly: `ensureCsrfToken` and the CSRF header it exports are reused here
 * rather than duplicated. Every response crosses a trust boundary, so a body
 * is validated at runtime before it is trusted.
 *
 * Failures are reduced to four kinds. `validation` is the one kind whose
 * per-field messages are shown verbatim: the backend already writes them as
 * compact, non-enumerating, product-authored copy (T035's docstring is
 * explicit that its duplicate-name detail "names no other household and
 * echoes no stored row"), so there is nothing to translate. Every other
 * failure maps to this module's own fixed copy, never to server text.
 */

import { CSRF_HEADER_NAME, ensureCsrfToken } from './session'

export interface Chore {
  id: number
  name: string
  points: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export const CHORES_QUERY_KEY_ROOT = 'chores' as const

export const choresQueryKey = (includeInactive: boolean) =>
  [CHORES_QUERY_KEY_ROOT, { includeInactive }] as const

/**
 * - `validation`: the request body was refused. `fieldErrors` carries the
 *   first message per field the server named.
 * - `forbidden`: the caller is no longer an active parent of this household.
 * - `notFound`: the chore does not exist, or belongs to another household,
 *   or was already removed by another session.
 * - `unavailable`: unreachable, timed out, not JSON, or an unexpected status.
 */
export type ChoreFailureKind = 'validation' | 'forbidden' | 'notFound' | 'unavailable'

export class ChoreRequestError extends Error {
  readonly kind: ChoreFailureKind
  readonly fieldErrors: Readonly<Record<string, string>>

  constructor(kind: ChoreFailureKind, fieldErrors: Record<string, string> = {}) {
    super(`Chore request failed: ${kind}`)
    this.name = 'ChoreRequestError'
    this.kind = kind
    this.fieldErrors = fieldErrors
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const isJsonMediaType = (contentType: string | null) =>
  contentType !== null &&
  /^application\/(?:[a-z0-9!#$&^_.+-]+\+)?json(?:\s*;|$)/i.test(contentType)

/** The exact six-key parent shape the merged contract returns for one chore. */
export const isChore = (value: unknown): value is Chore => {
  if (!isRecord(value) || Object.keys(value).length !== 6) {
    return false
  }
  for (const key of [
    'id',
    'name',
    'points',
    'is_active',
    'created_at',
    'updated_at',
  ]) {
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

const isChoreList = (value: unknown): value is Chore[] =>
  Array.isArray(value) && value.every(isChore)

/**
 * Reduce a 400 body to one first message per field.
 *
 * Only a plain object whose values are non-empty arrays of strings is
 * accepted; a shape the DRF error format never actually takes (a nested
 * object, a bare string, a number) yields no field errors, so a caller can
 * still fall back to its own generic validation copy instead of rendering
 * something unrecognised.
 */
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
    // The reason is dropped: it can carry a URL or a platform diagnostic, and
    // the interface shows one fixed sentence either way.
    throw new ChoreRequestError('unavailable')
  }
}

/** Read a 200/201 JSON chore body, or fail as `unavailable`. */
const readChoreBody = async (response: Response): Promise<Chore> => {
  if (response.redirected) {
    throw new ChoreRequestError('unavailable')
  }
  const body = await readJsonBody(response)

  if (response.status === 400) {
    throw new ChoreRequestError('validation', readFieldErrors(body))
  }
  if (response.status === 403) {
    throw new ChoreRequestError('forbidden')
  }
  if (response.status === 404) {
    throw new ChoreRequestError('notFound')
  }
  if ((response.status !== 200 && response.status !== 201) || !isChore(body)) {
    throw new ChoreRequestError('unavailable')
  }
  return body
}

/** `GET /api/v1/chores/`: the pool, active-only unless `includeInactive`. */
export const fetchChores = async ({
  includeInactive,
  signal,
}: {
  includeInactive: boolean
  signal?: AbortSignal
}): Promise<Chore[]> => {
  const path = includeInactive
    ? '/api/v1/chores/?include_inactive=true'
    : '/api/v1/chores/'
  const response = await send(path, {
    method: 'GET',
    headers: { Accept: 'application/json' },
    signal,
  })

  if (response.redirected) {
    throw new ChoreRequestError('unavailable')
  }
  if (response.status === 403) {
    throw new ChoreRequestError('forbidden')
  }
  const body = await readJsonBody(response)
  if (response.status !== 200 || !isChoreList(body)) {
    throw new ChoreRequestError('unavailable')
  }
  return body
}

interface WriteArgs {
  csrfToken: string
  signal?: AbortSignal
}

/** `POST /api/v1/chores/`: create one chore. */
export const createChore = async ({
  csrfToken,
  name,
  points,
  signal,
}: WriteArgs & { name: string; points: number }): Promise<Chore> =>
  readChoreBody(
    await send('/api/v1/chores/', {
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

/** `PATCH /api/v1/chores/<id>/`: edit an existing chore's name and points. */
export const updateChore = async ({
  csrfToken,
  id,
  name,
  points,
  signal,
}: WriteArgs & { id: number; name: string; points: number }): Promise<Chore> =>
  readChoreBody(
    await send(`/api/v1/chores/${id}/`, {
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

/** `DELETE /api/v1/chores/<id>/`: remove a chore permanently. 204 is success. */
export const deleteChore = async ({
  csrfToken,
  id,
  signal,
}: WriteArgs & { id: number }): Promise<void> => {
  const response = await send(`/api/v1/chores/${id}/`, {
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
    throw new ChoreRequestError('forbidden')
  }
  if (response.status === 404) {
    throw new ChoreRequestError('notFound')
  }
  throw new ChoreRequestError('unavailable')
}

const postStateChange = async (
  path: string,
  { csrfToken, signal }: WriteArgs,
): Promise<Chore> =>
  readChoreBody(
    await send(path, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        [CSRF_HEADER_NAME]: csrfToken,
      },
      signal,
    }),
  )

/** `POST /api/v1/chores/<id>/deactivate/`: take a chore out of use. */
export const deactivateChore = async (
  args: WriteArgs & { id: number },
): Promise<Chore> => postStateChange(`/api/v1/chores/${args.id}/deactivate/`, args)

/** `POST /api/v1/chores/<id>/reactivate/`: put a chore back into use. */
export const reactivateChore = async (
  args: WriteArgs & { id: number },
): Promise<Chore> => postStateChange(`/api/v1/chores/${args.id}/reactivate/`, args)

export { ensureCsrfToken }
