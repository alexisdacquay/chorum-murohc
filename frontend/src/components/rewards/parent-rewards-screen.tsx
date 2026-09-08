/**
 * The parent rewards screen at `/reward-requests` (issue #55).
 *
 * Two sections on one screen: the fulfilment queue, where a parent hands
 * over a pending request or cancels it, and the catalogue underneath, built
 * on the same create/edit/deactivate/reactivate/delete shape as
 * `chore-pool-screen.tsx`. They share one screen because a household this
 * small does not need two menu entries for one feature, and a parent
 * settling a request usually wants the catalogue open too.
 *
 * This screen owns no authority decision: the route that reaches it is
 * already parent-only (usability, per invariant 10 in `_docs/design.md`),
 * and every request still answers for itself.
 */

import { useState, type ReactNode } from 'react'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  REDEMPTIONS_QUERY_KEY,
  cancelRedemption,
  ensureCsrfToken,
  fetchParentRedemptions,
  fulfilRedemption,
  type ParentRedemption,
} from '../../api/redemptions'
import {
  REWARDS_QUERY_KEY_ROOT,
  deactivateReward,
  fetchRewards,
  reactivateReward,
  rewardsQueryKey,
  type Reward,
} from '../../api/rewards'
import { Button } from '../ui/button'
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from '../ui/card'
import { FormMessage } from '../ui/form-message'
import { DeleteRewardDialog } from './delete-reward-dialog'
import { RewardFormDialog } from './reward-form-dialog'
import { describeRedemptionFailure, describeRewardFailure } from './reward-messages'

const EMPTY_ACTIVE_COPY =
  'No active rewards. Add one, or show inactive rewards to see what is hidden.'
const EMPTY_ALL_COPY = 'No rewards yet. Add the first one.'
const EMPTY_QUEUE_COPY = 'No reward requests yet.'

type FormTarget = 'create' | Reward | null

const pointsLabel = (points: number) => `${points} point${points === 1 ? '' : 's'}`

const STATUS_LABEL: Record<ParentRedemption['status'], string> = {
  pending: 'Pending',
  fulfilled: 'Fulfilled',
  cancelled: 'Cancelled',
}

function RequestQueue() {
  const queryClient = useQueryClient()
  const [actionError, setActionError] = useState<string | null>(null)

  const redemptions = useQuery({
    queryKey: REDEMPTIONS_QUERY_KEY,
    queryFn: ({ signal }) => fetchParentRedemptions({ signal }),
  })

  const decision = useMutation({
    mutationFn: async ({
      id,
      action,
    }: {
      id: number
      action: 'fulfil' | 'cancel'
    }) => {
      const csrfToken = await ensureCsrfToken()
      return action === 'fulfil'
        ? fulfilRedemption({ csrfToken, id })
        : cancelRedemption({ csrfToken, id })
    },
    onSuccess: () => {
      setActionError(null)
      void queryClient.invalidateQueries({ queryKey: REDEMPTIONS_QUERY_KEY })
    },
    onError: (error) => setActionError(describeRedemptionFailure(error)),
  })

  const rowBusy = (id: number) =>
    decision.isPending && decision.variables?.id === id

  let body: ReactNode
  if (redemptions.isPending) {
    body = (
      <p aria-live="polite" className="reward-queue-status" role="status">
        Loading requests...
      </p>
    )
  } else if (redemptions.isError) {
    body = (
      <div className="reward-queue-error">
        <FormMessage role="alert" tone="error">
          {describeRedemptionFailure(redemptions.error)}
        </FormMessage>
        <Button onClick={() => void redemptions.refetch()} variant="secondary">
          Try again
        </Button>
      </div>
    )
  } else if (redemptions.data.length === 0) {
    body = <p className="page-panel-copy">{EMPTY_QUEUE_COPY}</p>
  } else {
    body = (
      <ul className="reward-queue-list">
        {redemptions.data.map((redemption) => (
          <li key={redemption.id}>
            <Card className="reward-queue-card">
              <CardHeader>
                <CardTitle>
                  <h3>{redemption.reward_name}</h3>
                </CardTitle>
                <CardDescription>
                  {redemption.child_username} - {pointsLabel(redemption.reward_points)}{' '}
                  - {STATUS_LABEL[redemption.status]}
                </CardDescription>
              </CardHeader>
              {redemption.status === 'pending' ? (
                <CardFooter className="reward-queue-actions">
                  <Button
                    aria-busy={rowBusy(redemption.id) || undefined}
                    aria-label={`Fulfil ${redemption.reward_name} for ${redemption.child_username}`}
                    disabled={rowBusy(redemption.id)}
                    onClick={() =>
                      decision.mutate({ id: redemption.id, action: 'fulfil' })
                    }
                  >
                    Fulfil
                  </Button>
                  <Button
                    aria-busy={rowBusy(redemption.id) || undefined}
                    aria-label={`Cancel ${redemption.reward_name} for ${redemption.child_username}`}
                    disabled={rowBusy(redemption.id)}
                    onClick={() =>
                      decision.mutate({ id: redemption.id, action: 'cancel' })
                    }
                    variant="secondary"
                  >
                    Cancel
                  </Button>
                </CardFooter>
              ) : null}
            </Card>
          </li>
        ))}
      </ul>
    )
  }

  return (
    <section className="reward-queue" aria-labelledby="reward-queue-heading">
      <h2 id="reward-queue-heading">Requests</h2>
      {actionError !== null ? (
        <FormMessage role="alert" tone="error">
          {actionError}
        </FormMessage>
      ) : null}
      {body}
    </section>
  )
}

function RewardCatalogue() {
  const queryClient = useQueryClient()
  const [includeInactive, setIncludeInactive] = useState(false)
  const [formTarget, setFormTarget] = useState<FormTarget>(null)
  const [deleteTarget, setDeleteTarget] = useState<Reward | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const rewards = useQuery({
    queryKey: rewardsQueryKey(includeInactive),
    queryFn: ({ signal }) => fetchRewards({ includeInactive, signal }),
  })

  const invalidateCatalogue = () =>
    queryClient.invalidateQueries({ queryKey: [REWARDS_QUERY_KEY_ROOT] })

  const stateMutation = useMutation({
    mutationFn: async ({ reward, activate }: { reward: Reward; activate: boolean }) => {
      const csrfToken = await ensureCsrfToken()
      return activate
        ? reactivateReward({ csrfToken, id: reward.id })
        : deactivateReward({ csrfToken, id: reward.id })
    },
    onSuccess: () => {
      setActionError(null)
      void invalidateCatalogue()
    },
    onError: (error) => setActionError(describeRewardFailure(error)),
  })

  const rowBusy = (reward: Reward) =>
    stateMutation.isPending && stateMutation.variables?.reward.id === reward.id

  const closeForm = () => setFormTarget(null)
  const handleSaved = () => {
    closeForm()
    void invalidateCatalogue()
  }
  const closeDelete = () => setDeleteTarget(null)
  const handleDeleted = () => {
    closeDelete()
    void invalidateCatalogue()
  }

  let body: ReactNode
  if (rewards.isPending) {
    body = (
      <p aria-live="polite" className="reward-catalogue-status" role="status">
        Loading rewards...
      </p>
    )
  } else if (rewards.isError) {
    body = (
      <div className="reward-catalogue-error">
        <FormMessage role="alert" tone="error">
          {describeRewardFailure(rewards.error)}
        </FormMessage>
        <Button onClick={() => void rewards.refetch()} variant="secondary">
          Try again
        </Button>
      </div>
    )
  } else if (rewards.data.length === 0) {
    body = (
      <p className="page-panel-copy">
        {includeInactive ? EMPTY_ALL_COPY : EMPTY_ACTIVE_COPY}
      </p>
    )
  } else {
    body = (
      <ul className="reward-list">
        {rewards.data.map((reward) => (
          <li key={reward.id}>
            <Card className="reward-card">
              <CardHeader>
                <CardTitle>
                  <h3>{reward.name}</h3>
                </CardTitle>
                <CardDescription>
                  {pointsLabel(reward.points)}
                  {reward.is_active ? '' : ' - Inactive'}
                </CardDescription>
              </CardHeader>
              <CardFooter className="reward-card-actions">
                <Button
                  aria-label={`Edit ${reward.name}`}
                  onClick={() => setFormTarget(reward)}
                  variant="secondary"
                >
                  Edit
                </Button>
                <Button
                  aria-busy={rowBusy(reward) || undefined}
                  aria-label={`${reward.is_active ? 'Deactivate' : 'Reactivate'} ${reward.name}`}
                  disabled={rowBusy(reward)}
                  onClick={() =>
                    stateMutation.mutate({ reward, activate: !reward.is_active })
                  }
                  variant="secondary"
                >
                  {reward.is_active ? 'Deactivate' : 'Reactivate'}
                </Button>
                <Button
                  aria-label={`Delete ${reward.name}`}
                  onClick={() => setDeleteTarget(reward)}
                  variant="secondary"
                >
                  Delete
                </Button>
              </CardFooter>
            </Card>
          </li>
        ))}
      </ul>
    )
  }

  return (
    <section className="reward-catalogue" aria-labelledby="reward-catalogue-heading">
      <div className="reward-catalogue-header">
        <h2 id="reward-catalogue-heading">Catalogue</h2>
        <Button onClick={() => setFormTarget('create')}>Add reward</Button>
      </div>
      <label className="reward-catalogue-filter">
        <input
          checked={includeInactive}
          onChange={(event) => setIncludeInactive(event.target.checked)}
          type="checkbox"
        />
        Show inactive rewards
      </label>
      {actionError !== null ? (
        <FormMessage role="alert" tone="error">
          {actionError}
        </FormMessage>
      ) : null}
      {body}
      <RewardFormDialog
        mode={formTarget === 'create' ? 'create' : 'edit'}
        onOpenChange={(open) => {
          if (!open) {
            closeForm()
          }
        }}
        onSaved={handleSaved}
        open={formTarget !== null}
        reward={formTarget === 'create' || formTarget === null ? undefined : formTarget}
      />
      {deleteTarget !== null ? (
        <DeleteRewardDialog
          onDeleted={handleDeleted}
          onOpenChange={(open) => {
            if (!open) {
              closeDelete()
            }
          }}
          open={deleteTarget !== null}
          reward={deleteTarget}
        />
      ) : null}
    </section>
  )
}

export function ParentRewardsScreen() {
  return (
    <div className="page-panel reward-requests">
      <h1 className="page-panel-title">Reward requests</h1>
      <RequestQueue />
      <RewardCatalogue />
    </div>
  )
}
