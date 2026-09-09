/**
 * The child points dashboard at `/points` (issue #49).
 *
 * Two things, both read-only and both the caller's own: a balance card
 * built on `GET /api/v1/balance/` (T039), and a paginated ledger history
 * built on `GET /api/v1/ledger/` (T039). This screen adds no endpoint of
 * its own and duplicates neither: it is the dashboard the balance API
 * already supports, not a new source of the numbers it shows.
 *
 * The balance is shown exactly as the ledger states it - positive, zero, or
 * negative - with no clamping and no euphemism, matching
 * `ledger/services.py`'s own contract. Every history row shows the
 * server's own `reason_label` (never a client-side reason-to-copy mapping,
 * so a later transaction reason needs no frontend change) and a
 * plus-or-minus signed amount.
 *
 * This route is already child-only in `navigation/role-router.tsx`'s
 * approved table (usability, per invariant 10 in `_docs/design.md`); the
 * balance and ledger endpoints enforce that independently.
 */

import { useState, type ReactNode } from 'react'

import { useQuery } from '@tanstack/react-query'

import { balanceQueryKey, fetchBalance } from '../../api/balance'
import {
  LedgerRequestError,
  fetchLedgerHistory,
  ledgerQueryKey,
  type LedgerEntry,
} from '../../api/ledger'
import { Button } from '../ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { FormMessage } from '../ui/form-message'
import { describePointsFailure } from './points-messages'

const EMPTY_COPY = 'No points activity yet. Complete a chore to start earning.'

const pointsLabel = (points: number) => {
  const magnitude = Math.abs(points)
  return `${points} point${magnitude === 1 ? '' : 's'}`
}

const signedAmountLabel = (amount: number) => (amount > 0 ? `+${amount}` : `${amount}`)

const formatEntryTimestamp = (isoTimestamp: string) =>
  new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(new Date(isoTimestamp))

function BalanceCard({ balance }: { balance: number }) {
  return (
    <Card className="points-balance-card">
      <CardHeader>
        <CardTitle>
          <h2>Your balance</h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="points-balance-figure" data-testid="points-balance-figure">
          {pointsLabel(balance)}
        </p>
      </CardContent>
    </Card>
  )
}

function HistoryRow({ entry }: { entry: LedgerEntry }) {
  const isCredit = entry.amount > 0
  return (
    <li className="points-history-row">
      <Card className="points-history-card">
        <CardContent className="points-history-card-content">
          <div className="points-history-details">
            <p className="points-history-reason">{entry.reason_label}</p>
            <p className="points-history-timestamp">
              {formatEntryTimestamp(entry.created_at)}
            </p>
          </div>
          <p
            className={
              isCredit
                ? 'points-history-amount points-history-amount-credit'
                : 'points-history-amount points-history-amount-debit'
            }
          >
            {signedAmountLabel(entry.amount)}
          </p>
        </CardContent>
      </Card>
    </li>
  )
}

export function PointsDashboardScreen() {
  const [page, setPage] = useState(1)

  const balance = useQuery({
    queryKey: balanceQueryKey,
    queryFn: ({ signal }) => fetchBalance({ signal }),
  })
  const history = useQuery({
    queryKey: ledgerQueryKey(page),
    queryFn: ({ signal }) => fetchLedgerHistory({ page, signal }),
  })

  if (balance.isPending) {
    return (
      <div className="page-panel points-screen">
        <h1 className="page-panel-title">Points</h1>
        <p aria-live="polite" className="points-status" role="status">
          Loading your points...
        </p>
      </div>
    )
  }

  if (balance.isError) {
    return (
      <div className="page-panel points-screen">
        <h1 className="page-panel-title">Points</h1>
        <div className="points-error">
          <FormMessage role="alert" tone="error">
            {describePointsFailure(balance.error)}
          </FormMessage>
          <Button onClick={() => void balance.refetch()} variant="secondary">
            Try again
          </Button>
        </div>
      </div>
    )
  }

  const historyIsInvalidPage =
    history.isError &&
    history.error instanceof LedgerRequestError &&
    history.error.kind === 'notFound'

  const retryHistory = () => {
    if (historyIsInvalidPage) {
      setPage(1)
      return
    }
    void history.refetch()
  }

  let historyBody: ReactNode
  if (history.isPending) {
    historyBody = (
      <p aria-live="polite" className="points-status" role="status">
        Loading your history...
      </p>
    )
  } else if (history.isError) {
    historyBody = (
      <div className="points-error">
        <FormMessage role="alert" tone="error">
          {describePointsFailure(history.error)}
        </FormMessage>
        <Button onClick={retryHistory} variant="secondary">
          {historyIsInvalidPage ? 'Go to page 1' : 'Try again'}
        </Button>
      </div>
    )
  } else if (history.data.entries.length === 0) {
    historyBody = <p className="page-panel-copy">{EMPTY_COPY}</p>
  } else {
    const { entries, hasNext, hasPrevious } = history.data
    historyBody = (
      <>
        <ul className="points-history-list">
          {entries.map((entry) => (
            <HistoryRow entry={entry} key={entry.id} />
          ))}
        </ul>
        <div className="points-pagination">
          <Button
            disabled={!hasPrevious}
            onClick={() => setPage((current) => current - 1)}
            variant="secondary"
          >
            Previous page
          </Button>
          <p aria-live="polite" className="points-pagination-status" role="status">
            Page {page}
          </p>
          <Button
            disabled={!hasNext}
            onClick={() => setPage((current) => current + 1)}
            variant="secondary"
          >
            Next page
          </Button>
        </div>
      </>
    )
  }

  return (
    <div className="page-panel points-screen">
      <h1 className="page-panel-title">Points</h1>
      <BalanceCard balance={balance.data} />
      <section aria-label="Points history" className="points-history">
        <h2 className="points-history-title">History</h2>
        {historyBody}
      </section>
    </div>
  )
}
