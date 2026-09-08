/**
 * The child completion-attestation API client for the merged T042 contract
 * (issue #36's absorbed submission API).
 *
 * One route, `/api/v1/submissions/`, child-only both ways:
 *
 * - `createSubmission` posts the attestation itself: one chore, an optional
 *   note, and a client-generated idempotency key. A network retry of the
 *   same confirm click must reuse the same key (`createIdempotencyKey`
 *   below makes one once per attempt), so the server can answer with the
 *   submission it already made instead of a second one; `submit-chore-
 *   dialog.tsx` is the one caller and owns that reuse.
 * - `fetchPendingSubmissions` reads the caller's own pending submissions, so
 *   the browser can show "pending review" on a chore instead of letting a
 *   child re-attempt one nobody has decided yet.
 *
 * Same-origin session authentication and CSRF only, matching `api/chores.ts`
 * exactly: `ensureCsrfToken` and the CSRF header it exports are reused here
 * rather than duplicated. Every response crosses a trust boundary, so a body
 * is validated at runtime before it is trusted.
 *
 * Failures are reduced to four kinds, exactly as `api/chores.ts` reduces its
 * own. `validation` is the one kind whose per-field messages are shown
 * verbatim: the duplicate-pending and reused-key details the server sends
 * are already compact, non-enumerating, product-authored copy, so there is
 * nothing to translate. Every other failure maps to this module's own fixed
 * copy, never to server text.
 */

import { CSRF_HEADER_NAME, ensureCsrfToken } from './session'

export interface Submission {
  id: number
  chore: number | null
  chore_name: string
  chore_points: number
  note: string
  status: 'pending' | 'approved' | 'rejected' | 'withdrawn'
  created_at: string
}

export const PENDING_SUBMISSIONS_QUERY_KEY = ['submissions', 'pending'] as const

/**
 * - `validation`: the request body was refused. `fieldErrors` carries the
 *   first message per field the server named, including a duplicate-pending
 *   or reused-key detail on `chore` or `idempotency_key`.
 * - `forbidden`: the caller is no longer an active child of this household.
 * - `notFound`: the chore does not exist, is inactive, or belongs to another
 *   household.
 * - `unavailable`: unreachable, timed out, not JSON, or an unexpected status.
 */
export type SubmissionFailureKind =
  | 'validation'
  | 'forbidden'
  | 'notFound'
  | 'unavailable'

export class SubmissionRequestError extends Error {
  readonly kind: SubmissionFailureKind
  readonly fieldErrors: Readonly<Record<string, string>>

  constructor(
    kind: SubmissionFailureKind,
    fieldErrors: Record<string, string> = {},
  ) {
    super(`Submission request failed: ${kind}`)
    this.name = 'SubmissionRequestError'
    this.kind = kind
    this.fieldErrors = fieldErrors
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const isJsonMediaType = (contentType: string | null) =>
  contentType !== null &&
  /^application\/(?:[a-z0-9!#$&^_.+-]+\+)?json(?:\s*;|$)/i.test(contentType)

const SUBMISSION_STATUSES = new Set(['pending', 'approved', 'rejected', 'withdrawn'])

/** The exact seven-key shape the merged contract returns for one submission. */
export const isSubmission = (value: unknown): value is Submission => {
  if (!isRecord(value) || Object.keys(value).length !== 7) {
    return false
  }
  for (const key of [
    'id',
    'chore',
    'chore_name',
    'chore_points',
    'note',
    'status',
    'created_at',
  ]) {
    if (!Object.hasOwn(value, key)) {
      return false
    }
  }

  return (
    typeof value.id === 'number' &&
    Number.isInteger(value.id) &&
    (value.chore === null ||
      (typeof value.chore === 'number' && Number.isInteger(value.chore))) &&
    typeof value.chore_name === 'string' &&
    typeof value.chore_points === 'number' &&
    Number.isInteger(value.chore_points) &&
    typeof value.note === 'string' &&
    typeof value.status === 'string' &&
    SUBMISSION_STATUSES.has(value.status) &&
    typeof value.created_at === 'string'
  )
}

const isSubmissionList = (value: unknown): value is Submission[] =>
  Array.isArray(value) && value.every(isSubmission)

/**
 * Reduce a 400 body to one first message per field, exactly as
 * `api/chores.ts` does for its own write serializer.
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
    throw new SubmissionRequestError('unavailable')
  }
}

/**
 * One idempotency key for one confirm attempt.
 *
 * `submit-chore-dialog.tsx` makes one when it opens and reuses it across a
 * retry of the same attempt, so a network retry of the same confirm click
 * lands on the submission it already made rather than a second one. Falls
 * back to a non-cryptographic key only where `crypto.randomUUID` is
 * unavailable; the key is never a security boundary, only a retry match.
 */
export const createIdempotencyKey = (): string => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

/** `GET /api/v1/submissions/`: the caller's own pending submissions. */
export const fetchPendingSubmissions = async ({
  signal,
}: { signal?: AbortSignal } = {}): Promise<Submission[]> => {
  const response = await send('/api/v1/submissions/', {
    method: 'GET',
    headers: { Accept: 'application/json' },
    signal,
  })

  if (response.redirected) {
    throw new SubmissionRequestError('unavailable')
  }
  if (response.status === 403) {
    throw new SubmissionRequestError('forbidden')
  }
  const body = await readJsonBody(response)
  if (response.status !== 200 || !isSubmissionList(body)) {
    throw new SubmissionRequestError('unavailable')
  }
  return body
}

/**
 * `POST /api/v1/submissions/`: attest one chore is done.
 *
 * 201 (created) and 200 (the same key's earlier submission, replayed) are
 * both success: the caller never needs to tell them apart.
 */
export const createSubmission = async ({
  choreId,
  csrfToken,
  idempotencyKey,
  note,
  signal,
}: {
  choreId: number
  csrfToken: string
  idempotencyKey: string
  note: string
  signal?: AbortSignal
}): Promise<Submission> => {
  const response = await send('/api/v1/submissions/', {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      [CSRF_HEADER_NAME]: csrfToken,
    },
    body: JSON.stringify({
      chore: choreId,
      note,
      idempotency_key: idempotencyKey,
    }),
    signal,
  })

  if (response.redirected) {
    throw new SubmissionRequestError('unavailable')
  }
  const body = await readJsonBody(response)

  if (response.status === 400) {
    throw new SubmissionRequestError('validation', readFieldErrors(body))
  }
  if (response.status === 403) {
    throw new SubmissionRequestError('forbidden')
  }
  if (response.status === 404) {
    throw new SubmissionRequestError('notFound')
  }
  if (
    (response.status !== 200 && response.status !== 201) ||
    !isSubmission(body)
  ) {
    throw new SubmissionRequestError('unavailable')
  }
  return body
}

export { ensureCsrfToken }
