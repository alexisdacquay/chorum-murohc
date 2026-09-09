/**
 * The parent's own device decision dialog (T048, issue #44).
 *
 * `_docs/approval-authentication.md`: "On a parent's own device the approver
 * is the session user, with no choice." There is no parent picker here, only
 * the caller's own PIN, re-entered fresh for this one decision - it is never
 * a cached or remembered "unlocked" state, matching `pin-settings-screen.tsx`
 * clearing its own secret fields after every submission.
 *
 * `decision` is fixed by which button the parent already pressed on the
 * queue screen (`parent-approvals-screen.tsx`), not chosen inside this
 * dialog, exactly as `submit-chore-dialog.tsx` asks for one confirmation of
 * one already-chosen action. The reason field only appears for a rejection.
 */

import { useEffect, useId, useState } from 'react'

import { useMutation } from '@tanstack/react-query'

import {
  decideSubmission,
  ensureCsrfToken,
  type DecidedSubmission,
  type PendingApproval,
} from '../../api/approvals'
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
import { Input } from '../ui/input'
import { describeDecisionFailure } from './approval-messages'

export const REASON_MAX_LENGTH = 200

export interface ParentDecisionDialogProps {
  approval: PendingApproval
  decision: 'approve' | 'reject'
  open: boolean
  onOpenChange: (open: boolean) => void
  onDecided: (submission: DecidedSubmission) => void
}

export function ParentDecisionDialog({
  approval,
  decision,
  onDecided,
  onOpenChange,
  open,
}: ParentDecisionDialogProps) {
  const pinId = useId()
  const reasonId = useId()
  const [pin, setPin] = useState('')
  const [reason, setReason] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setPin('')
      setReason('')
      setFormError(null)
    }
  }, [open])

  const mutation = useMutation({
    mutationFn: async () => {
      const csrfToken = await ensureCsrfToken()
      return decideSubmission({
        csrfToken,
        decision,
        pin,
        reason: decision === 'reject' ? reason.trim() : undefined,
        submissionId: approval.id,
      })
    },
    onSuccess: (submission) => onDecided(submission),
    onError: (error) => {
      setPin('')
      setFormError(describeDecisionFailure(error))
    },
  })

  const verb = decision === 'approve' ? 'Approve' : 'Reject'
  const verbBusy = decision === 'approve' ? 'Approving...' : 'Rejecting...'

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {verb} &quot;{approval.chore_name}&quot; for {approval.child_username}?
          </DialogTitle>
          <DialogDescription>
            {approval.chore_points} point{approval.chore_points === 1 ? '' : 's'}.
            Enter your approval PIN to confirm.
          </DialogDescription>
        </DialogHeader>
        <div className="chore-form-field">
          <label className="auth-label" htmlFor={pinId}>
            Your PIN
          </label>
          <Input
            autoComplete="off"
            id={pinId}
            inputMode="numeric"
            onChange={(event) => setPin(event.target.value)}
            type="password"
            value={pin}
          />
        </div>
        {decision === 'reject' ? (
          <div className="chore-form-field">
            <label className="auth-label" htmlFor={reasonId}>
              Reason (optional)
            </label>
            <textarea
              className="ui-input submit-chore-note"
              id={reasonId}
              maxLength={REASON_MAX_LENGTH}
              onChange={(event) => setReason(event.target.value)}
              rows={2}
              value={reason}
            />
          </div>
        ) : null}
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
            disabled={mutation.isPending || pin === ''}
            onClick={() => mutation.mutate()}
            type="button"
          >
            {mutation.isPending ? verbBusy : verb}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
