/**
 * The self-service password change API client (issue #129).
 *
 * One route: `POST /api/v1/auth/password/`. It always changes the caller's
 * own account password, gated on the caller's own current password -
 * resetting a *different* member's forgotten password is `resetMemberPassword`
 * in `api/members.ts` instead, with its own PIN-or-password proof.
 *
 * Same-origin session authentication and CSRF only, matching `api/session.ts`
 * exactly: `ensureCsrfToken` and the CSRF header it exports are reused here
 * rather than duplicated. Every response crosses a trust boundary, so a body
 * is validated at runtime before it is trusted, and neither the current
 * password nor the new one is ever placed in a thrown error: only the
 * server's field name and its own compact, non-enumerating message survive.
 */

import { CSRF_HEADER_NAME, ensureCsrfToken } from './session'

/**
 * - `validation`: the request was refused. `fieldErrors` carries the first
 *   message per field the server named (`current_password` or `new_password`).
 * - `forbidden`: the caller is no longer an active parent of a household.
 * - `unavailable`: unreachable, timed out, not JSON where a body was
 *   expected, or an unexpected status.
 */
export type PasswordChangeFailureKind = 'validation' | 'forbidden' | 'unavailable'

export class PasswordChangeRequestError extends Error {
  readonly kind: PasswordChangeFailureKind
  readonly fieldErrors: Readonly<Record<string, string>>

  constructor(kind: PasswordChangeFailureKind, fieldErrors: Record<string, string> = {}) {
    super(`Password change request failed: ${kind}`)
    this.name = 'PasswordChangeRequestError'
    this.kind = kind
    this.fieldErrors = fieldErrors
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const isJsonMediaType = (contentType: string | null) =>
  contentType !== null &&
  /^application\/(?:[a-z0-9!#$&^_.+-]+\+)?json(?:\s*;|$)/i.test(contentType)

/** Reduce a 400 body to one first message per field. */
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
    throw new PasswordChangeRequestError('unavailable')
  }
}

/**
 * `POST /api/v1/auth/password/`: change the caller's own account password.
 * Resolves with nothing on success (the endpoint answers 204).
 */
export const changeOwnPassword = async ({
  csrfToken,
  currentPassword,
  newPassword,
  signal,
}: {
  csrfToken: string
  currentPassword: string
  newPassword: string
  signal?: AbortSignal
}): Promise<void> => {
  const response = await send('/api/v1/auth/password/', {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      [CSRF_HEADER_NAME]: csrfToken,
    },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    signal,
  })

  if (response.status === 204) {
    return
  }
  if (response.status === 400) {
    const body = await readJsonBody(response)
    throw new PasswordChangeRequestError('validation', readFieldErrors(body))
  }
  if (response.status === 403) {
    throw new PasswordChangeRequestError('forbidden')
  }
  throw new PasswordChangeRequestError('unavailable')
}

export { ensureCsrfToken }
