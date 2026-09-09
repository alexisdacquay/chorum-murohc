/**
 * Fixed copy for the levels screen and its level-up celebration (issue #61).
 *
 * The screen never renders server text: every failure this endpoint can
 * produce maps to one of these two sentences, exactly as
 * `chores/submission-messages.ts` maps its own failures.
 */

import { ProgressionRequestError } from '../../api/progression'

export const CONNECTION_MESSAGE =
  'We could not reach Chorum-murohc. Check your connection and try again.'

export const PERMISSION_MESSAGE =
  'You do not have permission to see levels here. Refresh the page and try again.'

/** Map a failed progression request to one fixed sentence. */
export const describeProgressionFailure = (error: unknown): string =>
  error instanceof ProgressionRequestError && error.kind === 'forbidden'
    ? PERMISSION_MESSAGE
    : CONNECTION_MESSAGE
