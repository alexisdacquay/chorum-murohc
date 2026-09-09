/**
 * The child chore browser at `/chores` (issue #36), extended with the
 * submission interaction it was merged with.
 *
 * A mobile-first list of cards, each showing only a chore's name and point
 * value, exactly what the child-visible endpoint returns. Reusing the same
 * card, dialog, and status primitives as the parent chore-pool screen
 * (`chore-pool-screen.tsx`) rather than inventing a new shape. This module
 * owns no authority decision and no editing: the route that reaches it is
 * already child-only (usability, per invariant 10 in `_docs/design.md`), and
 * every request still answers for itself.
 *
 * A chore already pending review shows that instead of a button, so a child
 * cannot start a second attempt on a chore nobody has decided yet; the
 * server's own duplicate policy is still the real guard (`submissions.py`),
 * this is only the same convenience deactivating a chore already gets in the
 * parent screen.
 */

import { useState, type ReactNode } from 'react'

import { useQuery, useQueryClient } from '@tanstack/react-query'

import type { DecidedSubmission } from '../../api/approvals'
import { CHILD_CHORES_QUERY_KEY, fetchChildChores, type ChildChore } from '../../api/chores'
import {
  PENDING_SUBMISSIONS_QUERY_KEY,
  fetchPendingSubmissions,
  type Submission,
} from '../../api/submissions'
import { ChildDeviceDecisionDialog } from '../approvals/child-device-decision-dialog'
import { Button } from '../ui/button'
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from '../ui/card'
import { FormMessage } from '../ui/form-message'
import { describeChoreListFailure, describeSubmissionFailure } from './submission-messages'
import { SubmitChoreDialog } from './submit-chore-dialog'

const EMPTY_COPY = 'No chores yet. Check back once a parent adds some.'

const pointsLabel = (points: number) => `${points} point${points === 1 ? '' : 's'}`

export function ChildChoreScreen() {
  const queryClient = useQueryClient()
  const [confirmTarget, setConfirmTarget] = useState<ChildChore | null>(null)
  const [approvalTarget, setApprovalTarget] = useState<Submission | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const chores = useQuery({
    queryKey: CHILD_CHORES_QUERY_KEY,
    queryFn: ({ signal }) => fetchChildChores({ signal }),
  })
  const pendingSubmissions = useQuery({
    queryKey: PENDING_SUBMISSIONS_QUERY_KEY,
    queryFn: ({ signal }) => fetchPendingSubmissions({ signal }),
  })

  const pendingSubmissionByChoreId = new Map(
    (pendingSubmissions.data ?? [])
      .filter((submission): submission is Submission & { chore: number } =>
        submission.chore !== null,
      )
      .map((submission) => [submission.chore, submission]),
  )

  const closeConfirm = () => setConfirmTarget(null)
  const handleSubmitted = (submission: Submission) => {
    closeConfirm()
    setSuccessMessage(
      `"${submission.chore_name}" marked as done. A parent will review it.`,
    )
    void queryClient.invalidateQueries({ queryKey: PENDING_SUBMISSIONS_QUERY_KEY })
  }
  const openConfirm = (chore: ChildChore) => {
    setSuccessMessage(null)
    setConfirmTarget(chore)
  }

  const closeApproval = () => setApprovalTarget(null)
  const handleDecided = (submission: DecidedSubmission) => {
    closeApproval()
    setSuccessMessage(
      submission.status === 'approved'
        ? `"${submission.chore_name}" was approved.`
        : `"${submission.chore_name}" was rejected.`,
    )
    void queryClient.invalidateQueries({ queryKey: PENDING_SUBMISSIONS_QUERY_KEY })
  }

  let body: ReactNode
  if (chores.isPending || pendingSubmissions.isPending) {
    body = (
      <p aria-live="polite" className="chore-pool-status" role="status">
        Loading chores...
      </p>
    )
  } else if (chores.isError) {
    body = (
      <div className="chore-pool-error">
        <FormMessage role="alert" tone="error">
          {describeChoreListFailure(chores.error)}
        </FormMessage>
        <Button onClick={() => void chores.refetch()} variant="secondary">
          Try again
        </Button>
      </div>
    )
  } else if (pendingSubmissions.isError) {
    body = (
      <div className="chore-pool-error">
        <FormMessage role="alert" tone="error">
          {describeSubmissionFailure(pendingSubmissions.error)}
        </FormMessage>
        <Button onClick={() => void pendingSubmissions.refetch()} variant="secondary">
          Try again
        </Button>
      </div>
    )
  } else if (chores.data.length === 0) {
    body = <p className="page-panel-copy">{EMPTY_COPY}</p>
  } else {
    body = (
      <ul className="chore-list">
        {chores.data.map((chore) => {
          const pendingSubmission = pendingSubmissionByChoreId.get(chore.id)
          return (
            <li key={chore.id}>
              <Card className="chore-card">
                <CardHeader>
                  <CardTitle>
                    <h2>{chore.name}</h2>
                  </CardTitle>
                  <CardDescription>{pointsLabel(chore.points)}</CardDescription>
                </CardHeader>
                <CardFooter className="chore-card-actions">
                  {pendingSubmission !== undefined ? (
                    <>
                      <span className="submit-chore-pending-badge" role="status">
                        Pending review
                      </span>
                      <Button
                        aria-label={`Get ${chore.name} approved now`}
                        onClick={() => setApprovalTarget(pendingSubmission)}
                        variant="secondary"
                      >
                        Get approved now
                      </Button>
                    </>
                  ) : (
                    <Button
                      aria-label={`Mark ${chore.name} as done`}
                      onClick={() => openConfirm(chore)}
                    >
                      Mark as done
                    </Button>
                  )}
                </CardFooter>
              </Card>
            </li>
          )
        })}
      </ul>
    )
  }

  return (
    <div className="page-panel child-chore-screen">
      <h1 className="page-panel-title">Chores</h1>
      {successMessage !== null ? (
        <FormMessage role="status" tone="success">
          {successMessage}
        </FormMessage>
      ) : null}
      {body}
      {confirmTarget !== null ? (
        <SubmitChoreDialog
          chore={confirmTarget}
          onOpenChange={(open) => {
            if (!open) {
              closeConfirm()
            }
          }}
          onSubmitted={handleSubmitted}
          open={confirmTarget !== null}
        />
      ) : null}
      {approvalTarget !== null ? (
        <ChildDeviceDecisionDialog
          onDecided={handleDecided}
          onOpenChange={(open) => {
            if (!open) {
              closeApproval()
            }
          }}
          open={approvalTarget !== null}
          submission={approvalTarget}
        />
      ) : null}
    </div>
  )
}
