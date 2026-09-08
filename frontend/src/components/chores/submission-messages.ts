/**
 * Fixed copy for the child chore browser and its submit dialog (issue #36).
 *
 * The screen never renders server text for a failure that is not a named
 * validation field: a 403, a 404, or an unreachable request all map to one
 * of these three sentences, exactly as `chore-messages.ts` maps the parent
 * screen's own failures, but in the child's own wording rather than reusing
 * the parent screen's copy. The duplicate-pending and reused-key details the
 * server sends on `chore` and `idempotency_key` are the one exception,
 * handled in `submit-chore-dialog.tsx`: T042's endpoint already returns
 * compact, non-enumerating, product-authored text for those.
 */

import { ChoreRequestError } from '../../api/chores'
import { SubmissionRequestError } from '../../api/submissions'

export const CONNECTION_MESSAGE =
  'We could not reach Chorum-murohc. Check your connection and try again.'

export const PERMISSION_MESSAGE =
  'You do not have permission to see chores here. Refresh the page and try again.'

export const NOT_FOUND_MESSAGE =
  'That chore is no longer available. Refresh the page and try again.'

export const GENERIC_VALIDATION_MESSAGE = 'Check the details and try again.'

type FailureKind = 'validation' | 'forbidden' | 'notFound' | 'unavailable'

const describeFailureKind = (kind: FailureKind): string => {
  if (kind === 'forbidden') {
    return PERMISSION_MESSAGE
  }
  if (kind === 'notFound') {
    return NOT_FOUND_MESSAGE
  }
  if (kind === 'validation') {
    return GENERIC_VALIDATION_MESSAGE
  }
  return CONNECTION_MESSAGE
}

/** Map a failed `GET /api/v1/chores/` request to one fixed sentence. */
export const describeChoreListFailure = (error: unknown): string =>
  error instanceof ChoreRequestError ? describeFailureKind(error.kind) : CONNECTION_MESSAGE

/** Map a failed submissions request to one fixed sentence. */
export const describeSubmissionFailure = (error: unknown): string =>
  error instanceof SubmissionRequestError
    ? describeFailureKind(error.kind)
    : CONNECTION_MESSAGE
