/**
 * The confirmation and outcome dialog for spending points on one reward.
 *
 * Redeeming moves real points immediately (`_docs/design.md` requires the
 * server compute the cost and reject a client-authored amount, and the
 * merged service debits at request time), so this asks for a plain
 * confirmation first, on the same pattern `DeleteChoreDialog` uses for its
 * one irreversible chore action.
 *
 * `idempotencyKey` is generated once when the dialog opens and reused for
 * every retry of that same attempt within it, so a lost response or a
 * double-tapped confirm button can never charge twice: the server replays
 * the first result instead.
 */

import { useEffect, useRef, useState } from 'react'

import { useMutation } from '@tanstack/react-query'

import type { ChildReward } from '../../api/rewards'
import {
  RedemptionRequestError,
  ensureCsrfToken,
  redeemReward,
  type ChildRedemption,
} from '../../api/redemptions'
import { Button } from '../ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog'
import { FormMessage } from '../ui/form-message'
import { describeRedemptionFailure } from './reward-messages'

const generateIdempotencyKey = () =>
  `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`

export interface RedeemDialogProps {
  reward: ChildReward
  balance: number
  open: boolean
  onOpenChange: (open: boolean) => void
  onRedeemed: (redemption: ChildRedemption) => void
}

export function RedeemDialog({
  balance,
  onOpenChange,
  onRedeemed,
  open,
  reward,
}: RedeemDialogProps) {
  const idempotencyKey = useRef(generateIdempotencyKey())
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      idempotencyKey.current = generateIdempotencyKey()
      setFormError(null)
    }
  }, [open])

  const mutation = useMutation({
    mutationFn: async () => {
      const csrfToken = await ensureCsrfToken()
      return redeemReward({
        csrfToken,
        rewardId: reward.id,
        idempotencyKey: idempotencyKey.current,
      })
    },
    onSuccess: (redemption) => onRedeemed(redemption),
    onError: (error) => {
      if (
        error instanceof RedemptionRequestError &&
        error.kind === 'validation' &&
        error.fieldErrors.reward
      ) {
        setFormError(error.fieldErrors.reward)
        return
      }
      setFormError(describeRedemptionFailure(error))
    },
  })

  const remaining = balance - reward.points
  const canAfford = remaining >= 0

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Redeem &quot;{reward.name}&quot;?</DialogTitle>
          <DialogDescription>
            {reward.points} point{reward.points === 1 ? '' : 's'}. You have {balance}{' '}
            now
            {canAfford
              ? `, and ${remaining} left after.`
              : ', which is not enough yet.'}
          </DialogDescription>
        </DialogHeader>
        <FormMessage role="alert" tone="error">
          {formError ?? ''}
        </FormMessage>
        <DialogFooter>
          <DialogClose asChild>
            <Button disabled={mutation.isPending} type="button" variant="secondary">
              Cancel
            </Button>
          </DialogClose>
          <Button
            aria-busy={mutation.isPending || undefined}
            disabled={mutation.isPending || !canAfford}
            onClick={() => mutation.mutate()}
            type="button"
          >
            {mutation.isPending ? 'Redeeming...' : 'Redeem'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
