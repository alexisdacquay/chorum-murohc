/**
 * The parent overview dashboard at `/overview` (T085, issue #84).
 *
 * The household summary `GET /api/v1/overview/` (T084) already composes:
 * each active child's balance, level, creature and pending-submission count,
 * the household's active parents, and a household-wide pending total. This
 * screen renders that one response and adds no figure of its own - the
 * "partial data" state the issue asks for is just what a household with a
 * child who has not yet earned, chosen a creature, or reached level one
 * already looks like in the same response, not a separate case to detect.
 *
 * This is the parent's start screen (`navigation/role-router.tsx`'s
 * `START_PATH`), so it links onward to the screens that actually act on
 * what it shows - `/approvals` for the pending queue, `/chore-pool` and
 * `/reward-requests` for management, `/household` for the account
 * directory, `/activity` for the audit trail - rather than duplicating any
 * of their own list, filter or mutation behaviour here.
 */

import type { ReactNode } from 'react'

import { useQuery } from '@tanstack/react-query'

import { OVERVIEW_QUERY_KEY, fetchOverview, type OverviewChild } from '../../api/overview'
import { handleInternalLinkClick } from '../../navigation/internal-link'
import { Button } from '../ui/button'
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '../ui/card'
import { FormMessage } from '../ui/form-message'
import { describeOverviewFailure } from './overview-messages'

const EMPTY_CHILDREN_COPY =
  'No children in this household yet. Add one from Household to see them here.'

const pointsLabel = (points: number) => `${points} point${Math.abs(points) === 1 ? '' : 's'}`

const pendingLabel = (count: number) =>
  count === 0 ? 'Nothing pending' : `${count} pending decision${count === 1 ? '' : 's'}`

function QuickLinks() {
  // A plain group, not a `nav` landmark: these are shortcuts to screens the
  // primary navigation already links to (`navigation/role-navigation.tsx`),
  // and their own accessible names are deliberately worded differently from
  // that navigation's exact labels, so a viewer - and a test - can always
  // tell the two apart.
  return (
    <div aria-label="Manage your household" className="overview-quick-links" role="group">
      <Button asChild variant="secondary">
        <a href="/approvals" onClick={handleInternalLinkClick}>
          Review approvals
        </a>
      </Button>
      <Button asChild variant="secondary">
        <a href="/chore-pool" onClick={handleInternalLinkClick}>
          Manage chores
        </a>
      </Button>
      <Button asChild variant="secondary">
        <a href="/reward-requests" onClick={handleInternalLinkClick}>
          Manage rewards
        </a>
      </Button>
      <Button asChild variant="secondary">
        <a href="/household" onClick={handleInternalLinkClick}>
          Manage household
        </a>
      </Button>
      <Button asChild variant="secondary">
        <a href="/activity" onClick={handleInternalLinkClick}>
          View activity
        </a>
      </Button>
    </div>
  )
}

function ChildCard({ child }: { child: OverviewChild }) {
  const creature =
    child.creature_line === null
      ? 'No creature chosen yet'
      : (child.creature_form ?? `Chosen: ${child.creature_line}`)

  return (
    <li>
      <Card className="overview-child-card">
        <CardHeader>
          <CardTitle>
            <h3>{child.username}</h3>
          </CardTitle>
        </CardHeader>
        <CardContent className="overview-child-stats">
          <p className="overview-child-balance">{pointsLabel(child.balance)}</p>
          <dl className="overview-child-detail-list">
            <div className="overview-child-detail">
              <dt>Level</dt>
              <dd>
                {child.level} of {child.max_level}
              </dd>
            </div>
            <div className="overview-child-detail">
              <dt>Creature</dt>
              <dd>{creature}</dd>
            </div>
            <div className="overview-child-detail">
              <dt>Pending</dt>
              <dd>{pendingLabel(child.pending_count)}</dd>
            </div>
          </dl>
        </CardContent>
        {child.pending_count > 0 ? (
          <CardFooter>
            <Button asChild variant="secondary">
              <a href="/approvals" onClick={handleInternalLinkClick}>
                Review {child.username}&apos;s pending work
              </a>
            </Button>
          </CardFooter>
        ) : null}
      </Card>
    </li>
  )
}

export function ParentOverviewScreen() {
  const overview = useQuery({
    queryKey: OVERVIEW_QUERY_KEY,
    queryFn: ({ signal }) => fetchOverview({ signal }),
  })

  let body: ReactNode
  if (overview.isPending) {
    body = (
      <p aria-live="polite" className="overview-status" role="status">
        Loading your household overview...
      </p>
    )
  } else if (overview.isError) {
    body = (
      <div className="overview-error">
        <FormMessage role="alert" tone="error">
          {describeOverviewFailure(overview.error)}
        </FormMessage>
        <Button onClick={() => void overview.refetch()} variant="secondary">
          Try again
        </Button>
      </div>
    )
  } else {
    const { children, parents, pending_total: pendingTotal } = overview.data
    body = (
      <>
        <p aria-live="polite" className="overview-pending-summary" role="status">
          {pendingLabel(pendingTotal)}
        </p>
        {children.length === 0 ? (
          <p className="page-panel-copy">{EMPTY_CHILDREN_COPY}</p>
        ) : (
          <ul className="overview-child-list">
            {children.map((child) => (
              <ChildCard child={child} key={child.id} />
            ))}
          </ul>
        )}
        <p className="overview-parents">
          Parents: {parents.map((parent) => parent.username).join(', ')}
        </p>
        <QuickLinks />
      </>
    )
  }

  return (
    <div className="page-panel overview-screen">
      <h1 className="page-panel-title">Overview</h1>
      {body}
    </div>
  )
}
