/**
 * The destructive confirmation for removing one household member.
 *
 * Deleting a member is real removal, never a disguised deactivation
 * (`_docs/retention-policy.md`, "Deleting a member ... removes their
 * memberships, submissions, ledger entries, rewards, progression rows and
 * creature selection"), so this is the one member action that asks first and
 * states the exact consequence for a child account. Deactivate and
 * reactivate are reversible and stay one click, in `household-screen.tsx`.
 */

import { useEffect, useState } from 'react'

import { useMutation } from '@tanstack/react-query'

import { deleteMember, ensureCsrfToken, type Member } from '../../api/members'
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
import { describeMemberFailure } from './member-messages'

export interface DeleteMemberDialogProps {
  member: Member
  open: boolean
  onOpenChange: (open: boolean) => void
  onDeleted: () => void
}

export function DeleteMemberDialog({
  member,
  onDeleted,
  onOpenChange,
  open,
}: DeleteMemberDialogProps) {
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setFormError(null)
    }
  }, [open])

  const mutation = useMutation({
    mutationFn: async () => {
      const csrfToken = await ensureCsrfToken()
      return deleteMember({ csrfToken, id: member.id })
    },
    onSuccess: () => onDeleted(),
    onError: (error) => setFormError(describeMemberFailure(error)),
  })

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete &quot;{member.username}&quot;?</DialogTitle>
          <DialogDescription>
            {member.role === 'child'
              ? 'This permanently removes the account, and its points, level and creature go with it. This cannot be undone.'
              : 'This permanently removes the account. This cannot be undone.'}
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
            {mutation.isPending ? 'Deleting...' : 'Delete account'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
