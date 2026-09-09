/**
 * The screen shown right after signing in with more than one live
 * membership and no household selected yet (issue #130).
 *
 * `role-router.tsx` resolves a viewer's role from the session body alone,
 * and an ambiguous household is deliberately indistinguishable there from
 * having none at all (both are `household: null, role: null`); this screen
 * is a gate the composition root renders in front of the router, once it
 * also knows - from `GET auth/household/` - that there is more than one
 * membership to choose from. Selecting one re-derives the role from that
 * membership alone and the router takes over from the next render on.
 */

import type { HouseholdOption } from '../../api/session'
import { Button } from '../ui/button'
import { FormMessage } from '../ui/form-message'
import { HOUSEHOLD_SWITCH_FAILED_MESSAGE } from './household-switcher'
import { useHouseholdSwitch } from './use-household-switch'

export interface HouseholdPickerScreenProps {
  households: readonly HouseholdOption[]
}

export function HouseholdPickerScreen({ households }: HouseholdPickerScreenProps) {
  const { switchHousehold, isPending, hasFailed } = useHouseholdSwitch()

  return (
    <div className="page-panel auth-panel">
      <h1 className="page-panel-title">Choose a household</h1>
      <p className="page-panel-copy">
        Your account belongs to more than one household. Pick the one to use
        now; you can switch again later.
      </p>
      <div className="household-picker-list">
        {households.map((household) => (
          <Button
            aria-busy={isPending || undefined}
            disabled={isPending}
            key={household.id}
            onClick={() => switchHousehold(household.id)}
            variant="secondary"
          >
            {household.name}
          </Button>
        ))}
      </div>
      {hasFailed ? (
        <FormMessage role="alert" tone="error">
          {HOUSEHOLD_SWITCH_FAILED_MESSAGE}
        </FormMessage>
      ) : null}
    </div>
  )
}
