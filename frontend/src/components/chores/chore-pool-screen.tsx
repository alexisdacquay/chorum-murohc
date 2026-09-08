/**
 * The parent chore-pool screen at `/chore-pool` (issue #37).
 *
 * Create, edit, deactivate, reactivate and delete against the merged T035
 * API, reusing the existing card, dialog and form-control primitives rather
 * than inventing new ones. This module owns no authority decision: the
 * route that reaches it is already parent-only (usability, per invariant
 * 10), and every request still answers for itself, so a session that loses
 * parent standing mid-visit surfaces as an ordinary permission failure
 * rather than a client-side guess.
 */

import { useState, type ReactNode } from 'react'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  CHORES_QUERY_KEY_ROOT,
  choresQueryKey,
  deactivateChore,
  ensureCsrfToken,
  fetchChores,
  reactivateChore,
  type Chore,
} from '../../api/chores'
import { Button } from '../ui/button'
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from '../ui/card'
import { FormMessage } from '../ui/form-message'
import { ChoreFormDialog } from './chore-form-dialog'
import { describeChoreFailure } from './chore-messages'
import { DeleteChoreDialog } from './delete-chore-dialog'

const EMPTY_ACTIVE_COPY =
  'No active chores. Add one, or show inactive chores to see what is hidden.'
const EMPTY_ALL_COPY = 'No chores yet. Add the first one.'

type FormTarget = 'create' | Chore | null

const pointsLabel = (points: number) => `${points} point${points === 1 ? '' : 's'}`

export function ChorePoolScreen() {
  const queryClient = useQueryClient()
  const [includeInactive, setIncludeInactive] = useState(false)
  const [formTarget, setFormTarget] = useState<FormTarget>(null)
  const [deleteTarget, setDeleteTarget] = useState<Chore | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const chores = useQuery({
    queryKey: choresQueryKey(includeInactive),
    queryFn: ({ signal }) => fetchChores({ includeInactive, signal }),
  })

  const invalidatePool = () =>
    queryClient.invalidateQueries({ queryKey: [CHORES_QUERY_KEY_ROOT] })

  const stateMutation = useMutation({
    mutationFn: async ({ chore, activate }: { chore: Chore; activate: boolean }) => {
      const csrfToken = await ensureCsrfToken()
      return activate
        ? reactivateChore({ csrfToken, id: chore.id })
        : deactivateChore({ csrfToken, id: chore.id })
    },
    onSuccess: () => {
      setActionError(null)
      void invalidatePool()
    },
    onError: (error) => setActionError(describeChoreFailure(error)),
  })

  const rowBusy = (chore: Chore) =>
    stateMutation.isPending && stateMutation.variables?.chore.id === chore.id

  const closeForm = () => setFormTarget(null)
  const handleSaved = () => {
    closeForm()
    void invalidatePool()
  }
  const closeDelete = () => setDeleteTarget(null)
  const handleDeleted = () => {
    closeDelete()
    void invalidatePool()
  }

  let body: ReactNode
  if (chores.isPending) {
    body = (
      <p aria-live="polite" className="chore-pool-status" role="status">
        Loading chores...
      </p>
    )
  } else if (chores.isError) {
    body = (
      <div className="chore-pool-error">
        <FormMessage role="alert" tone="error">
          {describeChoreFailure(chores.error)}
        </FormMessage>
        <Button onClick={() => void chores.refetch()} variant="secondary">
          Try again
        </Button>
      </div>
    )
  } else if (chores.data.length === 0) {
    body = (
      <p className="page-panel-copy">
        {includeInactive ? EMPTY_ALL_COPY : EMPTY_ACTIVE_COPY}
      </p>
    )
  } else {
    body = (
      <ul className="chore-list">
        {chores.data.map((chore) => (
          <li key={chore.id}>
            <Card className="chore-card">
              <CardHeader>
                <CardTitle>
                  <h2>{chore.name}</h2>
                </CardTitle>
                <CardDescription>
                  {pointsLabel(chore.points)}
                  {chore.is_active ? '' : ' - Inactive'}
                </CardDescription>
              </CardHeader>
              <CardFooter className="chore-card-actions">
                <Button
                  aria-label={`Edit ${chore.name}`}
                  onClick={() => setFormTarget(chore)}
                  variant="secondary"
                >
                  Edit
                </Button>
                <Button
                  aria-busy={rowBusy(chore) || undefined}
                  aria-label={`${chore.is_active ? 'Deactivate' : 'Reactivate'} ${chore.name}`}
                  disabled={rowBusy(chore)}
                  onClick={() =>
                    stateMutation.mutate({ chore, activate: !chore.is_active })
                  }
                  variant="secondary"
                >
                  {chore.is_active ? 'Deactivate' : 'Reactivate'}
                </Button>
                <Button
                  aria-label={`Delete ${chore.name}`}
                  onClick={() => setDeleteTarget(chore)}
                  variant="secondary"
                >
                  Delete
                </Button>
              </CardFooter>
            </Card>
          </li>
        ))}
      </ul>
    )
  }

  return (
    <div className="page-panel chore-pool">
      <div className="chore-pool-header">
        <h1 className="page-panel-title">Chore pool</h1>
        <Button onClick={() => setFormTarget('create')}>Add chore</Button>
      </div>
      <label className="chore-pool-filter">
        <input
          checked={includeInactive}
          onChange={(event) => setIncludeInactive(event.target.checked)}
          type="checkbox"
        />
        Show inactive chores
      </label>
      {actionError !== null ? (
        <FormMessage role="alert" tone="error">
          {actionError}
        </FormMessage>
      ) : null}
      {body}
      <ChoreFormDialog
        chore={formTarget === 'create' || formTarget === null ? undefined : formTarget}
        mode={formTarget === 'create' ? 'create' : 'edit'}
        onOpenChange={(open) => {
          if (!open) {
            closeForm()
          }
        }}
        onSaved={handleSaved}
        open={formTarget !== null}
      />
      {deleteTarget !== null ? (
        <DeleteChoreDialog
          chore={deleteTarget}
          onDeleted={handleDeleted}
          onOpenChange={(open) => {
            if (!open) {
              closeDelete()
            }
          }}
          open={deleteTarget !== null}
        />
      ) : null}
    </div>
  )
}
