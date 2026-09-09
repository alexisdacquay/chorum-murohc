/**
 * Fixed copy for the parent overview dashboard (T085, issue #84).
 *
 * The screen never renders server text: the overview endpoint has only two
 * ways to fail a signed-in caller, matching `points/points-messages.ts`'s
 * precedent for the same two outcomes.
 */

import { OverviewRequestError } from '../../api/overview'

export const CONNECTION_MESSAGE =
  'We could not reach Chorum-murohc. Check your connection and try again.'

export const PERMISSION_MESSAGE =
  'You do not have permission to see the overview here. Refresh the page and try again.'

/** Map a failed overview request to one fixed sentence. */
export const describeOverviewFailure = (error: unknown): string =>
  error instanceof OverviewRequestError && error.kind === 'forbidden'
    ? PERMISSION_MESSAGE
    : CONNECTION_MESSAGE
