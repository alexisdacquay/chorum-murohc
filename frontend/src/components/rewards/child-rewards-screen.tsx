/**
 * The child rewards screen at `/rewards` (issue #55).
 *
 * Shows the household's active rewards, the child's current balance, and
 * lets the child redeem one through `RedeemDialog`'s confirmation step. A
 * successful redemption shows its pending state inline rather than
 * navigating away, and refreshes the balance so the next redemption is
 * judged against the real remaining total.
 *
 * This screen owns no authority decision: the route that reaches it is
 * already child-only (usability, per invariant 10 in `_docs/design.md`),
 * and every request still answers for itself.
 */

import { useState, type ReactNode } from 'react'

import { useQuery, useQueryClient } from '@tanstack/react-query'

import { balanceQueryKey, fetchBalance } from '../../api/balance'
import {
  CHILD_REWARDS_QUERY_KEY,
  fetchChildRewards,
  type ChildReward,
} from '../../api/rewards'
import { REDEMPTIONS_QUERY_KEY, type ChildRedemption } from '../../api/redemptions'
import { Button } from '../ui/button'
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from '../ui/card'
import { FormMessage } from '../ui/form-message'
import { RedeemDialog } from './redeem-dialog'
import { describeRewardFailure } from './reward-messages'

const EMPTY_COPY = 'No rewards yet. Ask a parent to add one.'

const pointsLabel = (points: number) => `${points} point${points === 1 ? '' : 's'}`

export function ChildRewardsScreen() {
  const queryClient = useQueryClient()
  const [redeemTarget, setRedeemTarget] = useState<ChildReward | null>(null)
  const [lastRedeemed, setLastRedeemed] = useState<ChildRedemption | null>(null)

  const balance = useQuery({
    queryKey: balanceQueryKey,
    queryFn: ({ signal }) => fetchBalance({ signal }),
  })
  const rewards = useQuery({
    queryKey: CHILD_REWARDS_QUERY_KEY,
    queryFn: ({ signal }) => fetchChildRewards({ signal }),
  })

  const closeRedeem = () => setRedeemTarget(null)
  const handleRedeemed = (redemption: ChildRedemption) => {
    closeRedeem()
    setLastRedeemed(redemption)
    void queryClient.invalidateQueries({ queryKey: balanceQueryKey })
    void queryClient.invalidateQueries({ queryKey: REDEMPTIONS_QUERY_KEY })
  }

  let body: ReactNode
  if (rewards.isPending || balance.isPending) {
    body = (
      <p aria-live="polite" className="rewards-status" role="status">
        Loading rewards...
      </p>
    )
  } else if (rewards.isError) {
    body = (
      <div className="rewards-error">
        <FormMessage role="alert" tone="error">
          {describeRewardFailure(rewards.error)}
        </FormMessage>
        <Button onClick={() => void rewards.refetch()} variant="secondary">
          Try again
        </Button>
      </div>
    )
  } else if (rewards.data.length === 0) {
    body = <p className="page-panel-copy">{EMPTY_COPY}</p>
  } else {
    body = (
      <ul className="reward-list">
        {rewards.data.map((reward) => (
          <li key={reward.id}>
            <Card className="reward-card">
              <CardHeader>
                <CardTitle>
                  <h2>{reward.name}</h2>
                </CardTitle>
                <CardDescription>{pointsLabel(reward.points)}</CardDescription>
              </CardHeader>
              <CardFooter className="reward-card-actions">
                <Button
                  aria-label={`Redeem ${reward.name}`}
                  onClick={() => setRedeemTarget(reward)}
                >
                  Redeem
                </Button>
              </CardFooter>
            </Card>
          </li>
        ))}
      </ul>
    )
  }

  return (
    <div className="page-panel rewards">
      <div className="rewards-header">
        <h1 className="page-panel-title">Rewards</h1>
        {balance.isSuccess ? (
          <p className="rewards-balance" data-testid="rewards-balance">
            {pointsLabel(balance.data)} available
          </p>
        ) : null}
      </div>
      {lastRedeemed !== null ? (
        <FormMessage role="status" tone="success">
          Requested &quot;{lastRedeemed.reward_name}&quot;. A parent will hand it over
          soon.
        </FormMessage>
      ) : null}
      {body}
      {redeemTarget !== null && balance.isSuccess ? (
        <RedeemDialog
          balance={balance.data}
          onOpenChange={(open) => {
            if (!open) {
              closeRedeem()
            }
          }}
          onRedeemed={handleRedeemed}
          open={redeemTarget !== null}
          reward={redeemTarget}
        />
      ) : null}
    </div>
  )
}
