/**
 * The destructive confirmation for removing one chore.
 *
 * Deleting a chore is real removal, never a disguised deactivation
 * (`_docs/retention-policy.md`, "Delete a chore"), so this is the one chore
 * action that asks first. Deactivate and reactivate are reversible and stay
 * one click, in `chore-pool-screen.tsx`.
 */

import { useEffect, useState } from 'react'

import { useMutation } from '@tanstack/react-query'

import { deleteChore, ensureCsrfToken, type Chore } from '../../api/chores'
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
import { describeChoreFailure } from './chore-messages'

export interface DeleteChoreDialogProps {
  chore: Chore
  open: boolean
  onOpenChange: (open: boolean) => void
  onDeleted: () => void
}

export function DeleteChoreDialog({
  chore,
  onDeleted,
  onOpenChange,
  open,
}: DeleteChoreDialogProps) {
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setFormError(null)
    }
  }, [open])

  const mutation = useMutation({
    mutationFn: async () => {
      const csrfToken = await ensureCsrfToken()
      return deleteChore({ csrfToken, id: chore.id })
    },
    onSuccess: () => onDeleted(),
    onError: (error) => setFormError(describeChoreFailure(error)),
  })

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete &quot;{chore.name}&quot;?</DialogTitle>
          <DialogDescription>
            This permanently removes the chore. This cannot be undone.
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
            {mutation.isPending ? 'Deleting...' : 'Delete chore'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
