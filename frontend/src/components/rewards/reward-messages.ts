/**
 * Fixed copy for the reward screens (issue #55).
 *
 * The screens never render server text for a failure that is not a named
 * validation field: a 403, a 404, or an unreachable request all map to one
 * of these fixed sentences, exactly as `components/chores/chore-messages.ts`
 * does for the chore pool.
 */

import { RedemptionRequestError } from '../../api/redemptions'
import { RewardRequestError } from '../../api/rewards'

export const CONNECTION_MESSAGE =
  'We could not reach Chorum-murohc. Check your connection and try again.'

export const REWARD_PERMISSION_MESSAGE =
  'You do not have permission to manage rewards. Refresh the page and try again.'

export const REWARD_NOT_FOUND_MESSAGE =
  'That reward could not be found. It may have just changed elsewhere. Refresh and try again.'

export const GENERIC_VALIDATION_MESSAGE = 'Check the reward details and try again.'

export const REDEMPTION_PERMISSION_MESSAGE =
  'You do not have permission to do that. Refresh the page and try again.'

export const REDEMPTION_NOT_FOUND_MESSAGE =
  'That request could not be found. It may have just changed elsewhere. Refresh and try again.'

export const INSUFFICIENT_POINTS_MESSAGE = 'Not enough points for this reward yet.'

/** Map any failed reward-catalogue request to one fixed sentence. */
export const describeRewardFailure = (error: unknown): string => {
  if (!(error instanceof RewardRequestError)) {
    return CONNECTION_MESSAGE
  }
  if (error.kind === 'forbidden') {
    return REWARD_PERMISSION_MESSAGE
  }
  if (error.kind === 'notFound') {
    return REWARD_NOT_FOUND_MESSAGE
  }
  if (error.kind === 'validation') {
    return GENERIC_VALIDATION_MESSAGE
  }
  return CONNECTION_MESSAGE
}

/** Map any failed redemption request to one fixed sentence. */
export const describeRedemptionFailure = (error: unknown): string => {
  if (!(error instanceof RedemptionRequestError)) {
    return CONNECTION_MESSAGE
  }
  if (error.kind === 'forbidden') {
    return REDEMPTION_PERMISSION_MESSAGE
  }
  if (error.kind === 'notFound') {
    return REDEMPTION_NOT_FOUND_MESSAGE
  }
  if (error.kind === 'validation') {
    return error.fieldErrors.reward ?? GENERIC_VALIDATION_MESSAGE
  }
  return CONNECTION_MESSAGE
}
