/**
 * The parent household screen at `/household` (issue #21).
 *
 * List, create, edit, deactivate, reactivate, delete and reset the password
 * of a member against the merged account-directory API, reusing the
 * chore-pool card, dialog and layout classes rather than inventing parallel
 * ones for a structurally identical screen. This module owns no authority
 * decision: the route that reaches it is already parent-only (usability, per
 * invariant 10), and every request still answers for itself, so a session
 * that loses parent standing mid-visit surfaces as an ordinary permission
 * failure rather than a client-side guess.
 *
 * The caller's own row never shows edit, reset-password, deactivate or
 * delete controls. That is also usability, not the authorisation boundary -
 * the API denies self-action on every one of those routes regardless - but
 * showing a control that always answers 403 would be a worse, more confusing
 * screen. Changing the caller's own password is the separate
 * `/change-password` screen instead.
 */

import { useState, type ReactNode } from 'react'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  MEMBERS_QUERY_KEY_ROOT,
  deactivateMember,
  ensureCsrfToken,
  fetchMembers,
  membersQueryKey,
  reactivateMember,
  type Member,
} from '../../api/members'
import { fetchSession, sessionQueryKey } from '../../api/session'
import { Button } from '../ui/button'
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from '../ui/card'
import { FormMessage } from '../ui/form-message'
import { DeleteMemberDialog } from './delete-member-dialog'
import { MemberFormDialog } from './member-form-dialog'
import { describeMemberFailure } from './member-messages'
import { ResetMemberPasswordDialog } from './reset-member-password-dialog'

const EMPTY_ACTIVE_COPY =
  'No other active household members yet. Add one, or show inactive members to see who is hidden.'
const EMPTY_ALL_COPY = 'No other household members yet. Add the first one.'

type FormTarget = 'create' | Member | null

const roleLabel = (role: Member['role']) => (role === 'parent' ? 'Parent' : 'Child')

export function HouseholdScreen() {
  const queryClient = useQueryClient()
  const [includeInactive, setIncludeInactive] = useState(false)
  const [formTarget, setFormTarget] = useState<FormTarget>(null)
  const [deleteTarget, setDeleteTarget] = useState<Member | null>(null)
  const [resetTarget, setResetTarget] = useState<Member | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  // Shares the session cache App.tsx's own query already fills, so this is
  // not a second request in the ordinary case.
  const session = useQuery({
    queryKey: sessionQueryKey,
    queryFn: ({ signal }) => fetchSession({ signal }),
  })
  const currentUserId = session.data?.user?.id ?? null

  const members = useQuery({
    queryKey: membersQueryKey(includeInactive),
    queryFn: ({ signal }) => fetchMembers({ includeInactive, signal }),
  })

  const invalidateDirectory = () =>
    queryClient.invalidateQueries({ queryKey: [MEMBERS_QUERY_KEY_ROOT] })

  const stateMutation = useMutation({
    mutationFn: async ({
      member,
      activate,
    }: {
      member: Member
      activate: boolean
    }) => {
      const csrfToken = await ensureCsrfToken()
      return activate
        ? reactivateMember({ csrfToken, id: member.id })
        : deactivateMember({ csrfToken, id: member.id })
    },
    onSuccess: () => {
      setActionError(null)
      void invalidateDirectory()
    },
    onError: (error) => setActionError(describeMemberFailure(error)),
  })

  const rowBusy = (member: Member) =>
    stateMutation.isPending && stateMutation.variables?.member.id === member.id

  const closeForm = () => setFormTarget(null)
  const handleSaved = () => {
    closeForm()
    void invalidateDirectory()
  }
  const closeDelete = () => setDeleteTarget(null)
  const handleDeleted = () => {
    closeDelete()
    void invalidateDirectory()
  }
  const closeReset = () => setResetTarget(null)
  const handleReset = () => {
    closeReset()
    void invalidateDirectory()
  }

  let body: ReactNode
  if (members.isPending) {
    body = (
      <p aria-live="polite" className="chore-pool-status" role="status">
        Loading household members...
      </p>
    )
  } else if (members.isError) {
    body = (
      <div className="chore-pool-error">
        <FormMessage role="alert" tone="error">
          {describeMemberFailure(members.error)}
        </FormMessage>
        <Button onClick={() => void members.refetch()} variant="secondary">
          Try again
        </Button>
      </div>
    )
  } else if (members.data.every((member) => member.id === currentUserId)) {
    // The caller is always a live parent of this household, so the list is
    // never literally empty - it is "empty" the moment it holds no one but
    // the caller. Showing a one-card list with every action hidden would be
    // a worse screen than this sentence.
    body = (
      <p className="page-panel-copy">
        {includeInactive ? EMPTY_ALL_COPY : EMPTY_ACTIVE_COPY}
      </p>
    )
  } else {
    body = (
      <ul className="chore-list">
        {members.data.map((member) => {
          const isSelf = member.id === currentUserId

          return (
            <li key={member.id}>
              <Card className="chore-card">
                <CardHeader>
                  <CardTitle>
                    <h2>{member.username}</h2>
                  </CardTitle>
                  <CardDescription>
                    {roleLabel(member.role)}
                    {member.is_active ? '' : ' - Inactive'}
                    {isSelf ? ' - You' : ''}
                  </CardDescription>
                </CardHeader>
                {isSelf ? null : (
                  <CardFooter className="chore-card-actions">
                    <Button
                      aria-label={`Edit ${member.username}`}
                      onClick={() => setFormTarget(member)}
                      variant="secondary"
                    >
                      Edit
                    </Button>
                    <Button
                      aria-busy={rowBusy(member) || undefined}
                      aria-label={`${member.is_active ? 'Deactivate' : 'Reactivate'} ${member.username}`}
                      disabled={rowBusy(member)}
                      onClick={() =>
                        stateMutation.mutate({
                          member,
                          activate: !member.is_active,
                        })
                      }
                      variant="secondary"
                    >
                      {member.is_active ? 'Deactivate' : 'Reactivate'}
                    </Button>
                    <Button
                      aria-label={`Reset password for ${member.username}`}
                      onClick={() => setResetTarget(member)}
                      variant="secondary"
                    >
                      Reset password
                    </Button>
                    <Button
                      aria-label={`Delete ${member.username}`}
                      onClick={() => setDeleteTarget(member)}
                      variant="secondary"
                    >
                      Delete
                    </Button>
                  </CardFooter>
                )}
              </Card>
            </li>
          )
        })}
      </ul>
    )
  }

  return (
    <div className="page-panel household-screen">
      <div className="chore-pool-header">
        <h1 className="page-panel-title">Household</h1>
        <Button onClick={() => setFormTarget('create')}>Add member</Button>
      </div>
      <label className="chore-pool-filter">
        <input
          checked={includeInactive}
          onChange={(event) => setIncludeInactive(event.target.checked)}
          type="checkbox"
        />
        Show inactive members
      </label>
      {actionError !== null ? (
        <FormMessage role="alert" tone="error">
          {actionError}
        </FormMessage>
      ) : null}
      {body}
      <MemberFormDialog
        member={
          formTarget === 'create' || formTarget === null ? undefined : formTarget
        }
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
        <DeleteMemberDialog
          member={deleteTarget}
          onDeleted={handleDeleted}
          onOpenChange={(open) => {
            if (!open) {
              closeDelete()
            }
          }}
          open={deleteTarget !== null}
        />
      ) : null}
      {resetTarget !== null ? (
        <ResetMemberPasswordDialog
          member={resetTarget}
          onOpenChange={(open) => {
            if (!open) {
              closeReset()
            }
          }}
          onReset={handleReset}
          open={resetTarget !== null}
        />
      ) : null}
    </div>
  )
}
