/**
 * The parent PIN management API client for the merged T031 contract
 * (issue #30).
 *
 * One route: `POST /api/v1/auth/pin/`. It always sets or replaces the
 * caller's own PIN, whichever applies, so there is exactly one call here and
 * no separate "does a PIN already exist?" read - matching
 * `chorum_murohc/api/pin.py`, which needs none either.
 *
 * Same-origin session authentication and CSRF only, matching `api/session.ts`
 * exactly: `ensureCsrfToken` and the CSRF header it exports are reused here
 * rather than duplicated. Every response crosses a trust boundary, so a body
 * is validated at runtime before it is trusted, and neither the submitted
 * password nor the submitted PIN is ever placed in a thrown error: only the
 * server's field name and its own compact, non-enumerating message survive.
 *
 * Failures are reduced to three kinds. `validation` is the one kind whose
 * per-field messages are shown verbatim: the backend already writes them as
 * compact, non-enumerating, product-authored copy (three fixed details, none
 * of which echoes a submitted value), so there is nothing to translate.
 * Every other failure maps to this module's own fixed copy, never to server
 * text.
 */

import { CSRF_HEADER_NAME, ensureCsrfToken } from './session'

/**
 * - `validation`: the request was refused. `fieldErrors` carries the first
 *   message per field the server named (`current_password` or `pin`).
 * - `forbidden`: the caller is no longer an active parent of a household.
 * - `unavailable`: unreachable, timed out, not JSON where a body was
 *   expected, or an unexpected status.
 */
export type PinFailureKind = 'validation' | 'forbidden' | 'unavailable'

export class PinRequestError extends Error {
  readonly kind: PinFailureKind
  readonly fieldErrors: Readonly<Record<string, string>>

  constructor(kind: PinFailureKind, fieldErrors: Record<string, string> = {}) {
    super(`PIN request failed: ${kind}`)
    this.name = 'PinRequestError'
    this.kind = kind
    this.fieldErrors = fieldErrors
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const isJsonMediaType = (contentType: string | null) =>
  contentType !== null &&
  /^application\/(?:[a-z0-9!#$&^_.+-]+\+)?json(?:\s*;|$)/i.test(contentType)

/**
 * Reduce a 400 body to one first message per field.
 *
 * Only a plain object whose values are non-empty arrays of strings is
 * accepted; a shape the DRF error format never actually takes yields no
 * field errors, so a caller still falls back to its own generic copy rather
 * than rendering something unrecognised.
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
    throw new PinRequestError('unavailable')
  }
}

/**
 * `POST /api/v1/auth/pin/`: set the caller's first PIN, or replace their
 * existing one. Resolves with nothing on success (the endpoint answers 204
 * either way, so the interface has no "was this a set or a change?" to show).
 */
export const setOrReplacePin = async ({
  csrfToken,
  currentPassword,
  pin,
  signal,
}: {
  csrfToken: string
  currentPassword: string
  pin: string
  signal?: AbortSignal
}): Promise<void> => {
  const response = await send('/api/v1/auth/pin/', {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      [CSRF_HEADER_NAME]: csrfToken,
    },
    body: JSON.stringify({ current_password: currentPassword, pin }),
    signal,
  })

  if (response.status === 204) {
    return
  }
  if (response.status === 400) {
    const body = await readJsonBody(response)
    throw new PinRequestError('validation', readFieldErrors(body))
  }
  if (response.status === 403) {
    throw new PinRequestError('forbidden')
  }
  throw new PinRequestError('unavailable')
}

export { ensureCsrfToken }
