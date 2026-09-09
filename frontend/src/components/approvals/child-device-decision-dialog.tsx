/**
 * The child-device decision dialog (T047, issue #44).
 *
 * `_docs/approval-authentication.md`: "On a child's device the flow names
 * the approving parent first, chosen from that household's active parents,
 * then checks the PIN against that one parent's hash." The child's own
 * session never gains any authority here - it only hosts the flow; the
 * named parent's PIN is what the server actually verifies, and "Parent
 * names show on a child device before anyone signs in."
 *
 * The parent list loads only while this dialog is open (`enabled: open`),
 * so a child browsing chores never fetches it. An empty list "says so and
 * offers no other route" (the approved contract's own words): no fallback
 * link, no different flow, just the one sentence.
 *
 * The PIN field is always visible; it is disabled until a parent is picked,
 * so a child cannot type a PIN against nobody. Both secret and selection
 * state are cleared on every open and on every failed attempt, matching
 * `pin-settings-screen.tsx` clearing its own fields after every submission.
 */

import { useEffect, useId, useState } from 'react'

import { useMutation, useQuery } from '@tanstack/react-query'

import {
  APPROVING_PARENTS_QUERY_KEY,
  decideSubmission,
  ensureCsrfToken,
  fetchApprovingParents,
  type DecidedSubmission,
} from '../../api/approvals'
import type { Submission } from '../../api/submissions'
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
import { describeApprovalQueueFailure, describeDecisionFailure } from './approval-messages'

export const REASON_MAX_LENGTH = 200
export const NO_PARENTS_AVAILABLE_MESSAGE =
  'No parent is available to approve right now.'

export interface ChildDeviceDecisionDialogProps {
  submission: Submission
  open: boolean
  onOpenChange: (open: boolean) => void
  onDecided: (submission: DecidedSubmission) => void
}

export function ChildDeviceDecisionDialog({
  onDecided,
  onOpenChange,
  open,
  submission,
}: ChildDeviceDecisionDialogProps) {
  const pinId = useId()
  const reasonId = useId()
  const [approvingParentId, setApprovingParentId] = useState<number | null>(null)
  const [pin, setPin] = useState('')
  const [reason, setReason] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setApprovingParentId(null)
      setPin('')
      setReason('')
      setFormError(null)
    }
  }, [open])

  const parents = useQuery({
    enabled: open,
    queryKey: APPROVING_PARENTS_QUERY_KEY,
    queryFn: ({ signal }) => fetchApprovingParents({ signal }),
  })

  const mutation = useMutation({
    mutationFn: async ({ decision }: { decision: 'approve' | 'reject' }) => {
      if (approvingParentId === null) {
        throw new Error('no parent selected')
      }
      const csrfToken = await ensureCsrfToken()
      return decideSubmission({
        approvingParentId,
        csrfToken,
        decision,
        pin,
        reason: decision === 'reject' ? reason.trim() : undefined,
        submissionId: submission.id,
      })
    },
    onSuccess: (decided) => onDecided(decided),
    onError: (error) => {
      setPin('')
      setFormError(describeDecisionFailure(error))
    },
  })

  const canSubmit = approvingParentId !== null && pin !== '' && !mutation.isPending

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Get &quot;{submission.chore_name}&quot; approved</DialogTitle>
          <DialogDescription>
            {submission.chore_points} point{submission.chore_points === 1 ? '' : 's'}.
            Hand the device to a parent to decide now.
          </DialogDescription>
        </DialogHeader>

        {parents.isPending ? (
          <p aria-live="polite" className="approval-queue-status" role="status">
            Loading parents...
          </p>
        ) : parents.isError ? (
          <div className="approval-queue-error">
            <FormMessage role="alert" tone="error">
              {describeApprovalQueueFailure(parents.error)}
            </FormMessage>
            <Button onClick={() => void parents.refetch()} variant="secondary">
              Try again
            </Button>
          </div>
        ) : parents.data.length === 0 ? (
          <FormMessage role="status" tone="help">
            {NO_PARENTS_AVAILABLE_MESSAGE}
          </FormMessage>
        ) : (
          <div className="approving-parent-picker" role="radiogroup" aria-label="Which parent is approving">
            {parents.data.map((parent) => (
              <label className="approving-parent-option" key={parent.id}>
                <input
                  checked={approvingParentId === parent.id}
                  disabled={!parent.available}
                  name="approving-parent"
                  onChange={() => setApprovingParentId(parent.id)}
                  type="radio"
                  value={parent.id}
                />
                {parent.username}
                {parent.available ? '' : ' (temporarily unavailable)'}
              </label>
            ))}
          </div>
        )}

        <div className="chore-form-field">
          <label className="auth-label" htmlFor={pinId}>
            Parent PIN
          </label>
          <Input
            autoComplete="off"
            disabled={approvingParentId === null}
            id={pinId}
            inputMode="numeric"
            onChange={(event) => setPin(event.target.value)}
            type="password"
            value={pin}
          />
        </div>
        <div className="chore-form-field">
          <label className="auth-label" htmlFor={reasonId}>
            Reason if rejecting (optional)
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
            disabled={!canSubmit}
            onClick={() => mutation.mutate({ decision: 'reject' })}
            type="button"
            variant="secondary"
          >
            Reject
          </Button>
          <Button
            aria-busy={mutation.isPending || undefined}
            disabled={!canSubmit}
            onClick={() => mutation.mutate({ decision: 'approve' })}
            type="button"
          >
            Approve
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
