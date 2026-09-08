/**
 * The confirmation for attesting one chore is done (issue #36's absorbed
 * child submission interaction).
 *
 * Submitting is not a disguised one-click action: a child confirms first,
 * exactly as deleting a chore asks a parent to confirm first in
 * `delete-chore-dialog.tsx`, because a submission cannot be taken back once
 * a parent has decided it. The optional note is the only other input; there
 * is no photo proof and no scheduling, matching `_docs/plan.md`.
 *
 * A fresh idempotency key is made once, when the dialog opens, and reused
 * across every retry of that same attempt within this one open. Reopening
 * the dialog for a new attempt makes a new key, so an accidental double
 * confirmation across two separate opens is still refused as a real
 * duplicate by the server rather than silently replayed.
 */

import { useEffect, useId, useRef, useState } from 'react'

import { useMutation } from '@tanstack/react-query'

import type { ChildChore } from '../../api/chores'
import {
  SubmissionRequestError,
  createIdempotencyKey,
  createSubmission,
  ensureCsrfToken,
  type Submission,
} from '../../api/submissions'
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
import { GENERIC_VALIDATION_MESSAGE, describeSubmissionFailure } from './submission-messages'

export const NOTE_MAX_LENGTH = 280

export interface SubmitChoreDialogProps {
  chore: ChildChore
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmitted: (submission: Submission) => void
}

export function SubmitChoreDialog({
  chore,
  onOpenChange,
  onSubmitted,
  open,
}: SubmitChoreDialogProps) {
  const noteId = useId()
  const idempotencyKey = useRef(createIdempotencyKey())
  // A synchronous lock, not `mutation.isPending`: two activations arriving in
  // the same tick (a fast double tap, or two rapid key presses) must not
  // both pass, and a React state flip is not guaranteed between them the way
  // a disabled button's own re-render is.
  const submitting = useRef(false)
  const [note, setNote] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  // Every open, including a reopen after cancelling or after a success this
  // dialog already reported, starts a clean attempt: a new key, an empty
  // note, and no leftover failure from the last one.
  useEffect(() => {
    if (!open) {
      return
    }
    idempotencyKey.current = createIdempotencyKey()
    submitting.current = false
    setNote('')
    setFormError(null)
  }, [open])

  const mutation = useMutation({
    mutationFn: async () => {
      const csrfToken = await ensureCsrfToken()
      return createSubmission({
        choreId: chore.id,
        csrfToken,
        idempotencyKey: idempotencyKey.current,
        note: note.trim(),
      })
    },
    onSuccess: (submission) => onSubmitted(submission),
    onError: (error) => {
      if (error instanceof SubmissionRequestError && error.kind === 'validation') {
        const fieldMessage =
          error.fieldErrors.chore ??
          error.fieldErrors.idempotency_key ??
          error.fieldErrors.note
        setFormError(fieldMessage ?? GENERIC_VALIDATION_MESSAGE)
        return
      }
      setFormError(describeSubmissionFailure(error))
    },
    onSettled: () => {
      submitting.current = false
    },
  })

  const confirm = () => {
    if (submitting.current) {
      return
    }
    submitting.current = true
    mutation.mutate()
  }

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Mark &quot;{chore.name}&quot; as done?</DialogTitle>
          <DialogDescription>
            You are confirming you finished this chore. A parent reviews it
            before the {chore.points} point{chore.points === 1 ? '' : 's'} are
            credited.
          </DialogDescription>
        </DialogHeader>
        <div className="chore-form-field">
          <label className="auth-label" htmlFor={noteId}>
            Add a note (optional)
          </label>
          <textarea
            className="ui-input submit-chore-note"
            id={noteId}
            maxLength={NOTE_MAX_LENGTH}
            onChange={(event) => setNote(event.target.value)}
            rows={3}
            value={note}
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
            disabled={mutation.isPending}
            onClick={confirm}
            type="button"
          >
            {mutation.isPending ? 'Submitting...' : 'Mark as done'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
