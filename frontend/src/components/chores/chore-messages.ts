/**
 * Fixed copy for the chore-pool screen (issue #37).
 *
 * The screen never renders server text for a failure that is not a named
 * validation field: a 403, a 404, or an unreachable request all map to one
 * of these three sentences, exactly as `api/session.ts` maps a login
 * failure. Field-level validation messages are the one exception, handled
 * separately in `chore-form-dialog.tsx`: T035's write serializer already
 * returns compact, non-enumerating, product-authored text for those.
 */

import { ChoreRequestError } from '../../api/chores'

export const CONNECTION_MESSAGE =
  'We could not reach Chorum-murohc. Check your connection and try again.'

export const PERMISSION_MESSAGE =
  'You do not have permission to manage chores. Refresh the page and try again.'

export const NOT_FOUND_MESSAGE =
  'That chore could not be found. It may have just changed elsewhere. Refresh and try again.'

export const GENERIC_VALIDATION_MESSAGE = 'Check the chore details and try again.'

/** Map any failed chore request to one fixed sentence. */
export const describeChoreFailure = (error: unknown): string => {
  if (!(error instanceof ChoreRequestError)) {
    return CONNECTION_MESSAGE
  }
  if (error.kind === 'forbidden') {
    return PERMISSION_MESSAGE
  }
  if (error.kind === 'notFound') {
    return NOT_FOUND_MESSAGE
  }
  if (error.kind === 'validation') {
    return GENERIC_VALIDATION_MESSAGE
  }
  return CONNECTION_MESSAGE
}
