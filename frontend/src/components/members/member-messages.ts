/**
 * Fixed copy for the household screen (issue #21).
 *
 * The screen never renders server text for a failure that is not a named
 * field or the one business-rule `detail` message: a 403, a 404, or an
 * unreachable request all map to one of these fixed sentences, exactly as
 * `chore-messages.ts` does. Field messages and the `detail` message are the
 * two exceptions: the backend already writes compact, non-enumerating,
 * product-authored text for both.
 */

import { MemberRequestError } from '../../api/members'

export const CONNECTION_MESSAGE =
  'We could not reach Chorum-murohc. Check your connection and try again.'

export const PERMISSION_MESSAGE =
  'You do not have permission to manage household accounts. Refresh the page and try again.'

export const NOT_FOUND_MESSAGE =
  'That account could not be found. It may have just changed elsewhere. Refresh and try again.'

export const GENERIC_VALIDATION_MESSAGE = 'Check the account details and try again.'

/** Map any failed member request to one sentence. */
export const describeMemberFailure = (error: unknown): string => {
  if (!(error instanceof MemberRequestError)) {
    return CONNECTION_MESSAGE
  }
  if (error.kind === 'forbidden') {
    return PERMISSION_MESSAGE
  }
  if (error.kind === 'notFound') {
    return NOT_FOUND_MESSAGE
  }
  if (error.kind === 'validation') {
    return error.detail ?? GENERIC_VALIDATION_MESSAGE
  }
  return CONNECTION_MESSAGE
}
