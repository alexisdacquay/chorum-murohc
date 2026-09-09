/**
 * The chore-approval API client (issue #44): a parent's own-household
 * pending queue, the child-device parent picker, and the one shared
 * decision endpoint both devices call.
 *
 * Three routes, same-origin session authentication and CSRF only, shaped
 * like `api/redemptions.ts` and `api/pin.ts`: `ensureCsrfToken` and the CSRF
 * header they export are reused here rather than duplicated, and every
 * response crosses a trust boundary, so a body is validated at runtime
 * before it is trusted. A submitted PIN is never placed in a thrown error:
 * only the server's own compact, non-enumerating message survives.
 */

import { CSRF_HEADER_NAME, ensureCsrfToken } from './session'

export type SubmissionStatus = 'pending' | 'approved' | 'rejected' | 'withdrawn'

export interface PendingApproval {
  id: number
  child_id: number
  child_username: string
  chore: number | null
  chore_name: string
  chore_points: number
  note: string
  created_at: string
}

export interface PendingApprovalPage {
  count: number
  next: string | null
  previous: string | null
  results: PendingApproval[]
}

export interface ApprovingParent {
  id: number
  username: string
  available: boolean
}

export interface DecidedSubmission {
  id: number
  chore_name: string
  chore_points: number
  note: string
  status: SubmissionStatus
  rejection_reason: string
  created_at: string
  decided_at: string | null
}

export const PENDING_APPROVALS_QUERY_KEY = ['approvals', 'pending'] as const
export const APPROVING_PARENTS_QUERY_KEY = ['approvals', 'approving-parents'] as const

/**
 * - `validation`: the request body was refused. `fieldErrors` carries the
 *   first message per field the server named - most often `pin` (wrong or
 *   locked, both already compact and generic) or `approving_parent`.
 * - `forbidden`: the caller may not perform this action in this household.
 * - `notFound`: the submission is missing, belongs to another household, or
 *   was already decided.
 * - `unavailable`: unreachable, timed out, not JSON, or an unexpected status.
 */
export type ApprovalFailureKind = 'validation' | 'forbidden' | 'notFound' | 'unavailable'

export class ApprovalRequestError extends Error {
  readonly kind: ApprovalFailureKind
  readonly fieldErrors: Readonly<Record<string, string>>

  constructor(kind: ApprovalFailureKind, fieldErrors: Record<string, string> = {}) {
    super(`Approval request failed: ${kind}`)
    this.name = 'ApprovalRequestError'
    this.kind = kind
    this.fieldErrors = fieldErrors
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const isJsonMediaType = (contentType: string | null) =>
  contentType !== null &&
  /^application\/(?:[a-z0-9!#$&^_.+-]+\+)?json(?:\s*;|$)/i.test(contentType)

const isSubmissionStatus = (value: unknown): value is SubmissionStatus =>
  value === 'pending' ||
  value === 'approved' ||
  value === 'rejected' ||
  value === 'withdrawn'

const isPendingApproval = (value: unknown): value is PendingApproval =>
  isRecord(value) &&
  Object.keys(value).length === 8 &&
  typeof value.id === 'number' &&
  typeof value.child_id === 'number' &&
  typeof value.child_username === 'string' &&
  (value.chore === null || typeof value.chore === 'number') &&
  typeof value.chore_name === 'string' &&
  typeof value.chore_points === 'number' &&
  typeof value.note === 'string' &&
  typeof value.created_at === 'string'

const isPendingApprovalPage = (value: unknown): value is PendingApprovalPage =>
  isRecord(value) &&
  Object.keys(value).length === 4 &&
  typeof value.count === 'number' &&
  (value.next === null || typeof value.next === 'string') &&
  (value.previous === null || typeof value.previous === 'string') &&
  Array.isArray(value.results) &&
  value.results.every(isPendingApproval)

const isApprovingParent = (value: unknown): value is ApprovingParent =>
  isRecord(value) &&
  Object.keys(value).length === 3 &&
  typeof value.id === 'number' &&
  typeof value.username === 'string' &&
  typeof value.available === 'boolean'

const isApprovingParentList = (value: unknown): value is ApprovingParent[] =>
  Array.isArray(value) && value.every(isApprovingParent)

const isDecidedSubmission = (value: unknown): value is DecidedSubmission =>
  isRecord(value) &&
  Object.keys(value).length === 8 &&
  typeof value.id === 'number' &&
  typeof value.chore_name === 'string' &&
  typeof value.chore_points === 'number' &&
  typeof value.note === 'string' &&
  isSubmissionStatus(value.status) &&
  typeof value.rejection_reason === 'string' &&
  typeof value.created_at === 'string' &&
  (value.decided_at === null || typeof value.decided_at === 'string')

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
    throw new ApprovalRequestError('unavailable')
  }
}

/** `GET /api/v1/approvals/`: the household's pending queue, one page. */
export const fetchPendingApprovals = async ({
  page,
  signal,
}: {
  page?: string
  signal?: AbortSignal
} = {}): Promise<PendingApprovalPage> => {
  const path = page ?? '/api/v1/approvals/'
  const response = await send(path, {
    method: 'GET',
    headers: { Accept: 'application/json' },
    signal,
  })

  if (response.redirected) {
    throw new ApprovalRequestError('unavailable')
  }
  if (response.status === 403) {
    throw new ApprovalRequestError('forbidden')
  }
  const body = await readJsonBody(response)
  if (response.status !== 200 || !isPendingApprovalPage(body)) {
    throw new ApprovalRequestError('unavailable')
  }
  return body
}

/** `GET /api/v1/approving-parents/`: parents a child device may choose. */
export const fetchApprovingParents = async ({
  signal,
}: { signal?: AbortSignal } = {}): Promise<ApprovingParent[]> => {
  const response = await send('/api/v1/approving-parents/', {
    method: 'GET',
    headers: { Accept: 'application/json' },
    signal,
  })

  if (response.redirected) {
    throw new ApprovalRequestError('unavailable')
  }
  if (response.status === 403) {
    throw new ApprovalRequestError('forbidden')
  }
  const body = await readJsonBody(response)
  if (response.status !== 200 || !isApprovingParentList(body)) {
    throw new ApprovalRequestError('unavailable')
  }
  return body
}

/**
 * `POST /api/v1/submissions/<id>/decide/`: approve or reject.
 *
 * `approvingParentId` is required only for a child-device call; a
 * parent-device call ignores it entirely (the server does too - the session
 * user is always who is recorded, never a client-named third party).
 */
export const decideSubmission = async ({
  approvingParentId,
  csrfToken,
  decision,
  pin,
  reason,
  signal,
  submissionId,
}: {
  approvingParentId?: number
  csrfToken: string
  decision: 'approve' | 'reject'
  pin: string
  reason?: string
  signal?: AbortSignal
  submissionId: number
}): Promise<DecidedSubmission> => {
  const response = await send(`/api/v1/submissions/${submissionId}/decide/`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      [CSRF_HEADER_NAME]: csrfToken,
    },
    body: JSON.stringify({
      decision,
      pin,
      ...(approvingParentId === undefined
        ? {}
        : { approving_parent: approvingParentId }),
      ...(reason === undefined ? {} : { reason }),
    }),
    signal,
  })

  if (response.redirected) {
    throw new ApprovalRequestError('unavailable')
  }
  const body = await readJsonBody(response)

  if (response.status === 400) {
    throw new ApprovalRequestError('validation', readFieldErrors(body))
  }
  if (response.status === 403) {
    throw new ApprovalRequestError('forbidden')
  }
  if (response.status === 404) {
    throw new ApprovalRequestError('notFound')
  }
  if (response.status !== 200 || !isDecidedSubmission(body)) {
    throw new ApprovalRequestError('unavailable')
  }
  return body
}

export { ensureCsrfToken }
