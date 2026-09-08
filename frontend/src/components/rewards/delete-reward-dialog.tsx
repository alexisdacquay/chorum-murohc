/**
 * The destructive confirmation for removing one reward, matching
 * `delete-chore-dialog.tsx`: deactivate and reactivate stay one click on the
 * catalogue screen, and delete is the one action that asks first.
 */

import { useEffect, useState } from 'react'

import { useMutation } from '@tanstack/react-query'

import { deleteReward, ensureCsrfToken, type Reward } from '../../api/rewards'
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
import { describeRewardFailure } from './reward-messages'

export interface DeleteRewardDialogProps {
  reward: Reward
  open: boolean
  onOpenChange: (open: boolean) => void
  onDeleted: () => void
}

export function DeleteRewardDialog({
  onDeleted,
  onOpenChange,
  open,
  reward,
}: DeleteRewardDialogProps) {
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setFormError(null)
    }
  }, [open])

  const mutation = useMutation({
    mutationFn: async () => {
      const csrfToken = await ensureCsrfToken()
      return deleteReward({ csrfToken, id: reward.id })
    },
    onSuccess: () => onDeleted(),
    onError: (error) => setFormError(describeRewardFailure(error)),
  })

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete &quot;{reward.name}&quot;?</DialogTitle>
          <DialogDescription>
            This permanently removes the reward from the catalogue. This cannot be
            undone.
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
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
            type="button"
          >
            {mutation.isPending ? 'Deleting...' : 'Delete reward'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
