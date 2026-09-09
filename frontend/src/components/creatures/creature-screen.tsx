/**
 * The child creature screen at `/creature` (issue #66).
 *
 * One route with two states, because they are two halves of one thing: a
 * child who has not picked yet sees the chooser, and everyone else sees
 * their creature. Which one is shown is the server's answer, never a local
 * flag, so a creature picked on another device is already there on this one.
 *
 * The level shown here is read from this endpoint rather than from
 * `/levels`, so one request answers the whole screen and the level and the
 * forms can never disagree with each other.
 */

import { useQuery, useQueryClient } from '@tanstack/react-query'

import { CREATURE_QUERY_KEY, fetchCreature } from '../../api/creatures'
import { Button } from '../ui/button'
import { FormMessage } from '../ui/form-message'
import { CreatureChooser } from './creature-chooser'
import { CreatureGallery } from './creature-gallery'
import { describeCreatureFailure } from './creature-messages'

export function CreatureScreen() {
  const queryClient = useQueryClient()

  const creature = useQuery({
    queryKey: CREATURE_QUERY_KEY,
    queryFn: ({ signal }) => fetchCreature({ signal }),
  })

  if (creature.isPending) {
    return (
      <div className="page-panel creature-screen">
        <h1 className="page-panel-title">Creature</h1>
        <p aria-live="polite" className="creature-status" role="status">
          Loading your creature...
        </p>
      </div>
    )
  }

  if (creature.isError) {
    return (
      <div className="page-panel creature-screen">
        <h1 className="page-panel-title">Creature</h1>
        <div className="creature-error">
          <FormMessage role="alert" tone="error">
            {describeCreatureFailure(creature.error)}
          </FormMessage>
          <Button onClick={() => void creature.refetch()} variant="secondary">
            Try again
          </Button>
        </div>
      </div>
    )
  }

  const chosen = creature.data.line !== null

  return (
    <div className="page-panel creature-screen">
      <h1 className="page-panel-title">
        {chosen ? 'Creature' : 'Choose your creature'}
      </h1>
      {chosen ? (
        <CreatureGallery creature={creature.data} />
      ) : (
        <CreatureChooser
          onChosen={(saved) => queryClient.setQueryData(CREATURE_QUERY_KEY, saved)}
        />
      )}
    </div>
  )
}
