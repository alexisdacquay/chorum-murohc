/**
 * Fixed copy for the points dashboard (issue #49).
 *
 * The screen never renders server text: every failure the balance or ledger
 * routes can produce maps to one of these two sentences, matching
 * `progression/progression-messages.ts`'s precedent for the same two
 * outcomes.
 */

import { BalanceRequestError } from '../../api/balance'
import { LedgerRequestError } from '../../api/ledger'

export const CONNECTION_MESSAGE =
  'We could not reach Chorum-murohc. Check your connection and try again.'

export const PERMISSION_MESSAGE =
  'You do not have permission to see points here. Refresh the page and try again.'

/** Map a failed balance or ledger-history request to one fixed sentence. */
export const describePointsFailure = (error: unknown): string =>
  (error instanceof BalanceRequestError && error.kind === 'forbidden') ||
  (error instanceof LedgerRequestError && error.kind === 'forbidden')
    ? PERMISSION_MESSAGE
    : CONNECTION_MESSAGE
