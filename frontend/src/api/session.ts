/**
 * The session API client for the merged T027 contract (issue #27) and the
 * household switch it deliberately left out (issue #130).
 *
 * Same-origin Django sessions and CSRF only. There is no JWT, no bearer
 * token, no browser-stored credential, and no cross-origin credential flow,
 * as required by the Session and CSRF Policy in `_docs/design.md`.
 *
 * Five calls, matching the merged endpoints exactly:
 *
 * - `fetchSession` reads `GET /api/v1/auth/session/`. It is open to everyone,
 *   always answers 200, and delivers the CSRF cookie a browser needs before
 *   it can make an unsafe call.
 * - `login` posts `POST /api/v1/auth/login/` with the CSRF header.
 * - `logout` posts `POST /api/v1/auth/logout/` with the CSRF header.
 * - `fetchHouseholds` reads `GET /api/v1/auth/household/`: the caller's own
 *   live memberships, and nothing about any other user or household.
 * - `selectHousehold` posts `POST /api/v1/auth/household/` with a household
 *   id and the CSRF header, and returns the same session shape `login` does,
 *   re-derived from that one membership.
 *
 * Every response crosses a trust boundary, so the body is validated at
 * runtime rather than trusted through a static type, exactly as
 * `api/health.ts` does. A body that does not match the contract is a failed
 * request, not a signed-out viewer.
 *
 * Failures are reduced to a small set of kinds, and no server text ever
 * reaches the interface: the caller maps a kind to its own fixed copy.
 * Nothing here logs, stores, or returns a cookie, a session identifier, a
 * CSRF value, or a password, and only the `csrftoken` cookie is ever read -
 * the session cookie is HttpOnly and is never touched.
 */

import type { SessionSnapshot } from '../navigation/role-router'

export type { SessionSnapshot }

/** The cookie the CSRF token arrives in, and the header it goes back out in. */
export const CSRF_COOKIE_NAME = 'csrftoken'
export const CSRF_HEADER_NAME = 'X-CSRFToken'

export const sessionQueryKey = ['session'] as const
export const householdsQueryKey = ['households'] as const

/** One of the caller's own live memberships, as `GET auth/household/` lists it. */
export interface HouseholdOption {
  id: number
  name: string
  role: string
}

/**
 * What went wrong, at the coarsest useful grain.
 *
 * - `credentials`: the login was refused. One kind for a wrong password, an
 *   unknown username, a disabled account and an invalid body, because the
 *   endpoint answers all four identically on purpose.
 * - `throttled`: the login abuse control refused the attempt.
 * - `forbidden`: CSRF or session authority was rejected.
 * - `not_found`: a household switch named an id that is not one of the
 *   caller's own live memberships. Identical whether the id belongs to
 *   someone else's household or does not exist at all.
 * - `unavailable`: unreachable, timed out, not JSON, an unexpected status, or
 *   a body that does not match the contract.
 */
export type SessionFailure =
  | 'credentials'
  | 'throttled'
  | 'forbidden'
  | 'not_found'
  | 'unavailable'

/** The one error type these calls reject with. It carries no server text. */
export class SessionRequestError extends Error {
  readonly failure: SessionFailure

  constructor(failure: SessionFailure) {
    super(`Session request failed: ${failure}`)
    this.name = 'SessionRequestError'
    this.failure = failure
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const isJsonMediaType = (contentType: string | null) =>
  contentType !== null &&
  /^application\/(?:[a-z0-9!#$&^_.+-]+\+)?json(?:\s*;|$)/i.test(contentType)

/** An `{id, name-like}` pair, and nothing else. */
const isNamedEntity = (value: unknown, nameKey: 'username' | 'name') => {
  if (!isRecord(value)) {
    return false
  }

  return (
    Object.keys(value).length === 2 &&
    Object.hasOwn(value, 'id') &&
    Object.hasOwn(value, nameKey) &&
    typeof value.id === 'number' &&
    Number.isInteger(value.id) &&
    typeof value[nameKey] === 'string'
  )
}

/** The exact four-key body the merged contract returns, and nothing else. */
export const isSessionSnapshot = (
  value: unknown,
): value is SessionSnapshot => {
  if (!isRecord(value) || Object.keys(value).length !== 4) {
    return false
  }
  for (const key of ['is_authenticated', 'user', 'household', 'role']) {
    if (!Object.hasOwn(value, key)) {
      return false
    }
  }

  return (
    typeof value.is_authenticated === 'boolean' &&
    (value.user === null || isNamedEntity(value.user, 'username')) &&
    (value.household === null || isNamedEntity(value.household, 'name')) &&
    (value.role === null || typeof value.role === 'string')
  )
}

/** Read a 200 JSON session body, or fail. Never reads a non-JSON body. */
const readSessionBody = async (response: Response) => {
  if (
    response.redirected ||
    response.status !== 200 ||
    !isJsonMediaType(response.headers.get('Content-Type'))
  ) {
    throw new SessionRequestError('unavailable')
  }

  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new SessionRequestError('unavailable')
  }

  if (!isSessionSnapshot(body)) {
    throw new SessionRequestError('unavailable')
  }
  return body
}

/** One `{id, name, role}` triple, and nothing else. */
const isHouseholdOption = (value: unknown): value is HouseholdOption => {
  if (!isRecord(value) || Object.keys(value).length !== 3) {
    return false
  }

  return (
    typeof value.id === 'number' &&
    Number.isInteger(value.id) &&
    typeof value.name === 'string' &&
    typeof value.role === 'string'
  )
}

/** The exact one-key body `GET auth/household/` returns. */
const isHouseholdListResponse = (
  value: unknown,
): value is { households: HouseholdOption[] } =>
  isRecord(value) &&
  Object.keys(value).length === 1 &&
  Array.isArray(value.households) &&
  value.households.every(isHouseholdOption)

const send = async (path: string, init: RequestInit) => {
  try {
    return await fetch(path, { credentials: 'same-origin', ...init })
  } catch {
    // The reason is deliberately dropped: it can carry a URL or a platform
    // diagnostic, and the interface shows one fixed sentence either way.
    throw new SessionRequestError('unavailable')
  }
}

/** `GET /api/v1/auth/session/`: who the caller is, and the CSRF cookie. */
export const fetchSession = async ({
  signal,
}: { signal?: AbortSignal } = {}): Promise<SessionSnapshot> =>
  readSessionBody(
    await send('/api/v1/auth/session/', {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal,
    }),
  )

/**
 * Read the CSRF token from its cookie.
 *
 * Only the `csrftoken` cookie is matched. The session cookie is HttpOnly and
 * is unreadable here by design, and no cookie value is logged or rendered.
 */
export const readCsrfToken = (): string | null => {
  for (const part of document.cookie.split(';')) {
    const separator = part.indexOf('=')

    if (separator === -1 || part.slice(0, separator).trim() !== CSRF_COOKIE_NAME) {
      continue
    }

    const value = part.slice(separator + 1).trim()
    return value === '' ? null : value
  }
  return null
}

/**
 * The token to send with an unsafe request.
 *
 * If the cookie is missing, the session endpoint is called once to deliver
 * it. If it is still missing the request must not be sent at all, so this
 * fails as an unreachable service rather than posting without a token.
 */
export const ensureCsrfToken = async ({
  signal,
}: { signal?: AbortSignal } = {}): Promise<string> => {
  const existing = readCsrfToken()
  if (existing !== null) {
    return existing
  }

  await fetchSession({ signal })

  const delivered = readCsrfToken()
  if (delivered === null) {
    throw new SessionRequestError('unavailable')
  }
  return delivered
}

/** `POST /api/v1/auth/login/`: exchange a username and password. */
export const login = async ({
  csrfToken,
  password,
  signal,
  username,
}: {
  csrfToken: string
  password: string
  signal?: AbortSignal
  username: string
}): Promise<SessionSnapshot> => {
  const response = await send('/api/v1/auth/login/', {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      [CSRF_HEADER_NAME]: csrfToken,
    },
    body: JSON.stringify({ username, password }),
    signal,
  })

  if (response.status === 400) {
    throw new SessionRequestError('credentials')
  }
  if (response.status === 429) {
    throw new SessionRequestError('throttled')
  }
  if (response.status === 403) {
    throw new SessionRequestError('forbidden')
  }
  return readSessionBody(response)
}

/**
 * `POST /api/v1/auth/logout/`: end the caller's own session.
 *
 * 204 is the only success. A 403 means the session had already gone, which
 * the caller treats as an ordinary sign-out rather than as an error.
 */
export const logout = async ({
  csrfToken,
  signal,
}: {
  csrfToken: string
  signal?: AbortSignal
}): Promise<void> => {
  const response = await send('/api/v1/auth/logout/', {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      [CSRF_HEADER_NAME]: csrfToken,
    },
    signal,
  })

  if (response.status === 204) {
    return
  }
  throw new SessionRequestError(
    response.status === 403 ? 'forbidden' : 'unavailable',
  )
}

/**
 * `GET /api/v1/auth/household/`: the caller's own live memberships.
 *
 * Authenticated only, like `logout`. An empty list is a normal answer for a
 * single-membership viewer; the caller decides what, if anything, to show.
 */
export const fetchHouseholds = async ({
  signal,
}: { signal?: AbortSignal } = {}): Promise<HouseholdOption[]> => {
  const response = await send('/api/v1/auth/household/', {
    method: 'GET',
    headers: { Accept: 'application/json' },
    signal,
  })

  if (
    response.redirected ||
    response.status !== 200 ||
    !isJsonMediaType(response.headers.get('Content-Type'))
  ) {
    throw new SessionRequestError('unavailable')
  }

  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new SessionRequestError('unavailable')
  }

  if (!isHouseholdListResponse(body)) {
    throw new SessionRequestError('unavailable')
  }
  return body.households
}

/**
 * `POST /api/v1/auth/household/`: switch the active household.
 *
 * `householdId` only ever selects a candidate among the caller's own
 * memberships; the server re-confirms it before honouring it. A 404 means
 * the id was not one of them, and is indistinguishable from an id that does
 * not exist at all, so this never confirms or denies a foreign household.
 */
export const selectHousehold = async ({
  csrfToken,
  householdId,
  signal,
}: {
  csrfToken: string
  householdId: number
  signal?: AbortSignal
}): Promise<SessionSnapshot> => {
  const response = await send('/api/v1/auth/household/', {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      [CSRF_HEADER_NAME]: csrfToken,
    },
    body: JSON.stringify({ household_id: householdId }),
    signal,
  })

  if (response.status === 404) {
    throw new SessionRequestError('not_found')
  }
  if (response.status === 403) {
    throw new SessionRequestError('forbidden')
  }
  return readSessionBody(response)
}
