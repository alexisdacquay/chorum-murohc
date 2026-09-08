/**
 * The household account directory API client (issue #21).
 *
 * Seven routes under `/api/v1/household-members/`, parent-only for every
 * one of them including the list - unlike `api/chores.ts`, there is no
 * child-visible shape here at all. This client is used only from the parent
 * household screen.
 *
 * Same-origin session authentication and CSRF only, matching `api/session.ts`
 * exactly: `ensureCsrfToken` and the CSRF header it exports are reused here
 * rather than duplicated. Every response crosses a trust boundary, so a body
 * is validated at runtime before it is trusted.
 *
 * Failures are reduced to four kinds. `validation` carries two different
 * server shapes back to the caller: `fieldErrors` for a per-field message
 * (a taken username, a weak password, an unknown role) and `detail` for the
 * one business-rule message the API returns outside any field - "the
 * household must keep at least one active parent" - so a caller can show
 * either without special-casing which route sent it. Every field message is
 * shown verbatim: the backend already writes compact, non-enumerating,
 * product-authored copy for both shapes.
 */

import { CSRF_HEADER_NAME, ensureCsrfToken } from './session'

export type MemberRole = 'parent' | 'child'

export interface Member {
  id: number
  username: string
  role: MemberRole
  is_active: boolean
  date_joined: string
}

export const MEMBERS_QUERY_KEY_ROOT = 'household-members' as const

export const membersQueryKey = (includeInactive: boolean) =>
  [MEMBERS_QUERY_KEY_ROOT, { includeInactive }] as const

/**
 * - `validation`: the request body was refused, as a field message, a
 *   `detail` business-rule message (the last-active-parent guard), or both
 *   absent for a shape the server never actually sends.
 * - `forbidden`: the caller is no longer an active parent of this household,
 *   or tried to act on their own account.
 * - `notFound`: the account does not exist, belongs to another household, or
 *   was already removed by another session.
 * - `unavailable`: unreachable, timed out, not JSON, or an unexpected status.
 */
export type MemberFailureKind = 'validation' | 'forbidden' | 'notFound' | 'unavailable'

export class MemberRequestError extends Error {
  readonly kind: MemberFailureKind
  readonly fieldErrors: Readonly<Record<string, string>>
  readonly detail: string | null

  constructor(
    kind: MemberFailureKind,
    fieldErrors: Record<string, string> = {},
    detail: string | null = null,
  ) {
    super(`Household member request failed: ${kind}`)
    this.name = 'MemberRequestError'
    this.kind = kind
    this.fieldErrors = fieldErrors
    this.detail = detail
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const isJsonMediaType = (contentType: string | null) =>
  contentType !== null &&
  /^application\/(?:[a-z0-9!#$&^_.+-]+\+)?json(?:\s*;|$)/i.test(contentType)

/** The exact five-key shape the merged contract returns for one member. */
export const isMember = (value: unknown): value is Member => {
  if (!isRecord(value) || Object.keys(value).length !== 5) {
    return false
  }
  for (const key of ['id', 'username', 'role', 'is_active', 'date_joined']) {
    if (!Object.hasOwn(value, key)) {
      return false
    }
  }

  return (
    typeof value.id === 'number' &&
    Number.isInteger(value.id) &&
    typeof value.username === 'string' &&
    (value.role === 'parent' || value.role === 'child') &&
    typeof value.is_active === 'boolean' &&
    typeof value.date_joined === 'string'
  )
}

const isMemberList = (value: unknown): value is Member[] =>
  Array.isArray(value) && value.every(isMember)

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

/** Read the one business-rule message a 400 can carry outside any field. */
const readDetail = (body: unknown): string | null =>
  isRecord(body) && typeof body.detail === 'string' ? body.detail : null

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
    throw new MemberRequestError('unavailable')
  }
}

/** Read a 200/201 JSON member body, or fail. */
const readMemberBody = async (response: Response): Promise<Member> => {
  if (response.redirected) {
    throw new MemberRequestError('unavailable')
  }
  const body = await readJsonBody(response)

  if (response.status === 400) {
    throw new MemberRequestError('validation', readFieldErrors(body), readDetail(body))
  }
  if (response.status === 403) {
    throw new MemberRequestError('forbidden')
  }
  if (response.status === 404) {
    throw new MemberRequestError('notFound')
  }
  if ((response.status !== 200 && response.status !== 201) || !isMember(body)) {
    throw new MemberRequestError('unavailable')
  }
  return body
}

/** `GET /api/v1/household-members/`: the directory, active-only unless `includeInactive`. */
export const fetchMembers = async ({
  includeInactive,
  signal,
}: {
  includeInactive: boolean
  signal?: AbortSignal
}): Promise<Member[]> => {
  const path = includeInactive
    ? '/api/v1/household-members/?include_inactive=true'
    : '/api/v1/household-members/'
  const response = await send(path, {
    method: 'GET',
    headers: { Accept: 'application/json' },
    signal,
  })

  if (response.redirected) {
    throw new MemberRequestError('unavailable')
  }
  if (response.status === 403) {
    throw new MemberRequestError('forbidden')
  }
  const body = await readJsonBody(response)
  if (response.status !== 200 || !isMemberList(body)) {
    throw new MemberRequestError('unavailable')
  }
  return body
}

interface WriteArgs {
  csrfToken: string
  signal?: AbortSignal
}

/** `POST /api/v1/household-members/`: create one member. */
export const createMember = async ({
  csrfToken,
  username,
  password,
  role,
  signal,
}: WriteArgs & {
  username: string
  password: string
  role: MemberRole
}): Promise<Member> =>
  readMemberBody(
    await send('/api/v1/household-members/', {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        [CSRF_HEADER_NAME]: csrfToken,
      },
      body: JSON.stringify({ username, password, role }),
      signal,
    }),
  )

/**
 * `PATCH /api/v1/household-members/<id>/`: edit a member.
 *
 * Each of `username`, `password` and `role` is sent only when the caller
 * supplies it, so leaving the password field blank in the edit form leaves
 * the stored password untouched rather than sending an empty one.
 */
export const updateMember = async ({
  csrfToken,
  id,
  username,
  password,
  role,
  signal,
}: WriteArgs & {
  id: number
  username?: string
  password?: string
  role?: MemberRole
}): Promise<Member> => {
  const body: Record<string, string> = {}
  if (username !== undefined) {
    body.username = username
  }
  if (password !== undefined) {
    body.password = password
  }
  if (role !== undefined) {
    body.role = role
  }

  return readMemberBody(
    await send(`/api/v1/household-members/${id}/`, {
      method: 'PATCH',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        [CSRF_HEADER_NAME]: csrfToken,
      },
      body: JSON.stringify(body),
      signal,
    }),
  )
}

/** `DELETE /api/v1/household-members/<id>/`: remove a member permanently. 204 is success. */
export const deleteMember = async ({
  csrfToken,
  id,
  signal,
}: WriteArgs & { id: number }): Promise<void> => {
  const response = await send(`/api/v1/household-members/${id}/`, {
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
    throw new MemberRequestError('forbidden')
  }
  if (response.status === 404) {
    throw new MemberRequestError('notFound')
  }
  throw new MemberRequestError('unavailable')
}

const postStateChange = async (
  path: string,
  { csrfToken, signal }: WriteArgs,
): Promise<Member> =>
  readMemberBody(
    await send(path, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        [CSRF_HEADER_NAME]: csrfToken,
      },
      signal,
    }),
  )

/** `POST /api/v1/household-members/<id>/deactivate/`: end a member's login. */
export const deactivateMember = async (
  args: WriteArgs & { id: number },
): Promise<Member> =>
  postStateChange(`/api/v1/household-members/${args.id}/deactivate/`, args)

/** `POST /api/v1/household-members/<id>/reactivate/`: restore a member's login. */
export const reactivateMember = async (
  args: WriteArgs & { id: number },
): Promise<Member> =>
  postStateChange(`/api/v1/household-members/${args.id}/reactivate/`, args)

export { ensureCsrfToken }
