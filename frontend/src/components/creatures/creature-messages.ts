/**
 * Fixed copy for the creature screens (issue #66).
 *
 * The screens never render server text: every failure these endpoints can
 * produce maps to one of these sentences, exactly as
 * `progression/progression-messages.ts` maps its own.
 */

import { CreatureRequestError } from '../../api/creatures'

export const CONNECTION_MESSAGE =
  'We could not reach Chorum-murohc. Check your connection and try again.'

export const PERMISSION_MESSAGE =
  'You do not have permission to see creatures here. Refresh the page and try again.'

export const ALREADY_CHOSEN_MESSAGE =
  'A creature is already saved for this account. Refresh the page to see it.'

/** Map a failed creature request to one fixed sentence. */
export const describeCreatureFailure = (error: unknown): string => {
  if (!(error instanceof CreatureRequestError)) {
    return CONNECTION_MESSAGE
  }
  if (error.kind === 'forbidden') {
    return PERMISSION_MESSAGE
  }
  return error.kind === 'already-chosen'
    ? ALREADY_CHOSEN_MESSAGE
    : CONNECTION_MESSAGE
}
