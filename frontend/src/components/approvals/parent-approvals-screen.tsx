/**
 * The parent's own approval queue at `/approvals` (T044, T048; issue #44).
 *
 * One paginated list, oldest decision-worthy work first shown as the server
 * returns it (newest submitted first): each card carries the child, the
 * chore snapshot, its point value, and Approve and Reject buttons. Either
 * button opens `ParentDecisionDialog` for that one submission, asking for
 * the parent's own PIN and, for a rejection, an optional reason -
 * `_docs/approval-authentication.md`'s parent-device path, where "the
 * approver is the session user, with no choice."
 *
 * Pagination follows the native DRF shape `GET /api/v1/approvals/` returns
 * (`count`/`next`/`previous`/`results`): a household this small rarely has
 * more than one page, so "Load more" appends the next page onto the list
 * already shown rather than replacing it, the simplest read of a "queue" a
 * parent can scan top to bottom.
 */

import { useState, type ReactNode } from 'react'

import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query'

import {
  PENDING_APPROVALS_QUERY_KEY,
  fetchPendingApprovals,
  type DecidedSubmission,
  type PendingApproval,
} from '../../api/approvals'
import { Button } from '../ui/button'
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from '../ui/card'
import { FormMessage } from '../ui/form-message'
import { describeApprovalQueueFailure } from './approval-messages'
import { ParentDecisionDialog } from './parent-decision-dialog'

const EMPTY_COPY = 'Nothing is waiting for a decision.'

const pointsLabel = (points: number) => `${points} point${points === 1 ? '' : 's'}`

type DialogTarget = { approval: PendingApproval; decision: 'approve' | 'reject' } | null

export function ParentApprovalsScreen() {
  const queryClient = useQueryClient()
  const [dialogTarget, setDialogTarget] = useState<DialogTarget>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const approvals = useInfiniteQuery({
    queryKey: PENDING_APPROVALS_QUERY_KEY,
    queryFn: ({ pageParam, signal }) => fetchPendingApprovals({ page: pageParam, signal }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next ?? undefined,
  })

  const items = approvals.data?.pages.flatMap((page) => page.results) ?? []

  const closeDialog = () => setDialogTarget(null)
  const handleDecided = (submission: DecidedSubmission) => {
    const verb = submission.status === 'approved' ? 'Approved' : 'Rejected'
    closeDialog()
    setSuccessMessage(`${verb} "${submission.chore_name}".`)
    void queryClient.invalidateQueries({ queryKey: PENDING_APPROVALS_QUERY_KEY })
  }
  const openDialog = (approval: PendingApproval, decision: 'approve' | 'reject') => {
    setSuccessMessage(null)
    setDialogTarget({ approval, decision })
  }

  let body: ReactNode
  if (approvals.isPending) {
    body = (
      <p aria-live="polite" className="approval-queue-status" role="status">
        Loading approvals...
      </p>
    )
  } else if (approvals.isError) {
    body = (
      <div className="approval-queue-error">
        <FormMessage role="alert" tone="error">
          {describeApprovalQueueFailure(approvals.error)}
        </FormMessage>
        <Button onClick={() => void approvals.refetch()} variant="secondary">
          Try again
        </Button>
      </div>
    )
  } else if (items.length === 0) {
    body = <p className="page-panel-copy">{EMPTY_COPY}</p>
  } else {
    body = (
      <>
        <ul className="approval-queue-list">
          {items.map((approval) => (
            <li key={approval.id}>
              <Card className="approval-queue-card">
                <CardHeader>
                  <CardTitle>
                    <h3>{approval.chore_name}</h3>
                  </CardTitle>
                  <CardDescription>
                    {approval.child_username} - {pointsLabel(approval.chore_points)}
                    {approval.note !== '' ? ` - "${approval.note}"` : ''}
                  </CardDescription>
                </CardHeader>
                <CardFooter className="approval-queue-actions">
                  <Button
                    aria-label={`Approve ${approval.chore_name} for ${approval.child_username}`}
                    onClick={() => openDialog(approval, 'approve')}
                  >
                    Approve
                  </Button>
                  <Button
                    aria-label={`Reject ${approval.chore_name} for ${approval.child_username}`}
                    onClick={() => openDialog(approval, 'reject')}
                    variant="secondary"
                  >
                    Reject
                  </Button>
                </CardFooter>
              </Card>
            </li>
          ))}
        </ul>
        {approvals.hasNextPage ? (
          <Button
            aria-busy={approvals.isFetchingNextPage || undefined}
            disabled={approvals.isFetchingNextPage}
            onClick={() => void approvals.fetchNextPage()}
            variant="secondary"
          >
            {approvals.isFetchingNextPage ? 'Loading...' : 'Load more'}
          </Button>
        ) : null}
      </>
    )
  }

  return (
    <div className="page-panel approvals-screen">
      <h1 className="page-panel-title">Approvals</h1>
      {successMessage !== null ? (
        <FormMessage role="status" tone="success">
          {successMessage}
        </FormMessage>
      ) : null}
      {body}
      {dialogTarget !== null ? (
        <ParentDecisionDialog
          approval={dialogTarget.approval}
          decision={dialogTarget.decision}
          onDecided={handleDecided}
          onOpenChange={(open) => {
            if (!open) {
              closeDialog()
            }
          }}
          open={dialogTarget !== null}
        />
      ) : null}
    </div>
  )
}
