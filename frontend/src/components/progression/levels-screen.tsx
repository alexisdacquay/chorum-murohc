/**
 * The child levels screen at `/levels` (issue #61).
 *
 * A single card shows the caller's own level out of the fixed maximum, the
 * lifetime points earned so far, and the distance to the next level. There
 * is nothing to spend and no action to take here beyond acknowledging a
 * level-up: the level itself is a read-only consequence of earning, exactly
 * as `_docs/design.md`'s permission matrix describes it ("the client never
 * supplies ... the resulting level").
 *
 * `LevelUpCelebrationDialog` is shown whenever the server reports a
 * `pending_level_up`, and dismissing it (however that happens) acknowledges
 * it, so it is shown once and never replayed.
 */

import { useState } from 'react'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  PROGRESSION_QUERY_KEY,
  acknowledgeLevelUp,
  ensureCsrfToken,
  fetchProgression,
} from '../../api/progression'
import { Button } from '../ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'
import { FormMessage } from '../ui/form-message'
import { LevelUpCelebrationDialog } from './level-up-celebration-dialog'
import { describeProgressionFailure } from './progression-messages'

const pointsLabel = (points: number) => `${points} point${points === 1 ? '' : 's'}`

export function LevelsScreen() {
  const queryClient = useQueryClient()
  const [acknowledgeError, setAcknowledgeError] = useState<string | null>(null)

  const progression = useQuery({
    queryKey: PROGRESSION_QUERY_KEY,
    queryFn: ({ signal }) => fetchProgression({ signal }),
  })

  const acknowledge = useMutation({
    mutationFn: async () => {
      const csrfToken = await ensureCsrfToken()
      return acknowledgeLevelUp({ csrfToken })
    },
    onSuccess: (data) => {
      setAcknowledgeError(null)
      queryClient.setQueryData(PROGRESSION_QUERY_KEY, data)
    },
    onError: (error) => {
      setAcknowledgeError(describeProgressionFailure(error))
    },
  })

  const dismissCelebration = () => {
    if (acknowledge.isPending) {
      return
    }
    acknowledge.mutate()
  }

  if (progression.isPending) {
    return (
      <div className="page-panel levels-screen">
        <h1 className="page-panel-title">Levels</h1>
        <p aria-live="polite" className="levels-status" role="status">
          Loading your level...
        </p>
      </div>
    )
  }

  if (progression.isError) {
    return (
      <div className="page-panel levels-screen">
        <h1 className="page-panel-title">Levels</h1>
        <div className="levels-error">
          <FormMessage role="alert" tone="error">
            {describeProgressionFailure(progression.error)}
          </FormMessage>
          <Button onClick={() => void progression.refetch()} variant="secondary">
            Try again
          </Button>
        </div>
      </div>
    )
  }

  const state = progression.data

  return (
    <div className="page-panel levels-screen">
      <h1 className="page-panel-title">Levels</h1>
      <Card className="levels-card">
        <CardHeader>
          <CardTitle>
            <h2>
              Level {state.level} of {state.max_level}
            </h2>
          </CardTitle>
          <CardDescription>
            {state.next_level_threshold !== null && state.points_to_next_level !== null
              ? `${pointsLabel(state.points_to_next_level)} to level ${state.level + 1}`
              : 'You have reached the highest level. Points still add up and stay yours to spend.'}
          </CardDescription>
        </CardHeader>
        <CardContent className="levels-card-content">
          {state.next_level_threshold !== null ? (
            <progress
              aria-label={`Progress toward level ${state.level + 1}`}
              className="levels-progress-bar"
              max={state.next_level_threshold}
              value={state.lifetime_points}
            />
          ) : null}
          <p className="levels-lifetime-points">
            {pointsLabel(state.lifetime_points)} earned in total
          </p>
        </CardContent>
      </Card>
      {state.pending_level_up !== null ? (
        <LevelUpCelebrationDialog
          error={acknowledgeError}
          isAcknowledging={acknowledge.isPending}
          level={state.pending_level_up}
          maxLevel={state.max_level}
          onDismiss={dismissCelebration}
        />
      ) : null}
    </div>
  )
}
