/**
 * The household switcher in the banner (issue #130).
 *
 * Presentational only, like `RoleNavigation`: the composition root already
 * holds the caller's own household list (it needs the same list to decide
 * whether to show the post-login picker), so this receives it as a prop
 * rather than fetching its own copy.
 *
 * Rendered by the router only once a role has resolved, beside "Sign out",
 * and only when the list holds more than one household: a single-household
 * viewer has nothing to switch between. Hiding it otherwise is a
 * convenience, not a control (invariant 10) - `POST auth/household/`
 * re-confirms a live membership on every call regardless of what this
 * control shows.
 */

import { useId } from 'react'

import type { HouseholdOption } from '../../api/session'
import { FormMessage } from '../ui/form-message'
import { useHouseholdSwitch } from './use-household-switch'

export const HOUSEHOLD_SWITCH_FAILED_MESSAGE =
  'We could not switch households. Check your connection and try again.'

export interface HouseholdSwitcherProps {
  households: readonly HouseholdOption[]
  /** The active household id, so the control opens on the right option. */
  currentHouseholdId: number | null
}

export function HouseholdSwitcher({
  currentHouseholdId,
  households,
}: HouseholdSwitcherProps) {
  const labelId = useId()
  const { switchHousehold, isPending, hasFailed } = useHouseholdSwitch()

  if (households.length < 2) {
    return null
  }

  return (
    <div className="shell-household-switcher">
      <label className="auth-label" htmlFor={labelId}>
        Switch household
      </label>
      <select
        aria-busy={isPending || undefined}
        className="ui-input"
        disabled={isPending}
        id={labelId}
        onChange={(event) => switchHousehold(Number(event.target.value))}
        value={currentHouseholdId ?? ''}
      >
        {households.map((household) => (
          <option key={household.id} value={household.id}>
            {household.name}
          </option>
        ))}
      </select>
      {hasFailed ? (
        <FormMessage role="alert" tone="error">
          {HOUSEHOLD_SWITCH_FAILED_MESSAGE}
        </FormMessage>
      ) : null}
    </div>
  )
}
