/**
 * Fixed copy for the approval queue and both decision dialogs (issue #44).
 *
 * The screens never render server text for a failure that is not a named
 * validation field: a 403, a 404, or an unreachable request all map to one
 * of these fixed sentences, exactly as `components/rewards/reward-messages.ts`
 * does for the reward screens. `pin` and `approving_parent` are the two
 * exceptions: the server already writes compact, non-enumerating,
 * product-authored text for those (a wrong PIN, a lockout, or an unpicked
 * parent), so that text is shown verbatim rather than translated.
 */

import { ApprovalRequestError } from '../../api/approvals'

export const CONNECTION_MESSAGE =
  'We could not reach Chorum-murohc. Check your connection and try again.'

export const QUEUE_PERMISSION_MESSAGE =
  'You do not have permission to see approvals here. Refresh the page and try again.'

export const DECISION_NOT_FOUND_MESSAGE =
  'That submission is no longer waiting for a decision. It may have just been decided elsewhere. Refresh and try again.'

export const GENERIC_VALIDATION_MESSAGE = 'Check the details and try again.'

/** Map a failed pending-queue or approving-parents request to one sentence. */
export const describeApprovalQueueFailure = (error: unknown): string =>
  error instanceof ApprovalRequestError && error.kind === 'forbidden'
    ? QUEUE_PERMISSION_MESSAGE
    : CONNECTION_MESSAGE

/**
 * Map a failed decide request to one message: the server's own `pin` or
 * `approving_parent` detail when it named one, otherwise a fixed sentence.
 */
export const describeDecisionFailure = (error: unknown): string => {
  if (!(error instanceof ApprovalRequestError)) {
    return CONNECTION_MESSAGE
  }
  if (error.kind === 'validation') {
    return (
      error.fieldErrors.pin ??
      error.fieldErrors.approving_parent ??
      error.fieldErrors.reason ??
      GENERIC_VALIDATION_MESSAGE
    )
  }
  if (error.kind === 'forbidden') {
    return QUEUE_PERMISSION_MESSAGE
  }
  if (error.kind === 'notFound') {
    return DECISION_NOT_FOUND_MESSAGE
  }
  return CONNECTION_MESSAGE
}
