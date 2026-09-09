/**
 * The household activity screen at `/activity` (T087, issue #84's absorbed
 * #87), over the merged read-only audit API (T086, `GET /api/v1/audit/`).
 *
 * A parent-only, paginated list of what happened in their own household and
 * who did it: the action, its target, when, the acting member's name (a
 * plain id resolved against the account directory this screen already needs
 * for the actor filter - `api/members.ts`, reused rather than duplicated),
 * and the already-redacted safe context the server recorded. There is no
 * edit or delete control anywhere on this screen: the API exposes none, and
 * an audit trail a parent could rewrite would not be one.
 *
 * Filtering is the exact three dimensions the server accepts - actor,
 * action and a date range - applied together on submit rather than per
 * keystroke, so an in-progress action code is never sent as a probably-empty
 * exact-match query. Clearing the form returns to the unfiltered first page.
 */

import { useState, type FormEvent, type ReactNode } from 'react'

import { useQuery } from '@tanstack/react-query'

import {
  AuditRequestError,
  auditEventsQueryKey,
  fetchAuditEvents,
  type AuditEvent,
  type AuditEventFilters,
} from '../../api/audit'
import { fetchMembers, membersQueryKey } from '../../api/members'
import { handleInternalLinkClick } from '../../navigation/internal-link'
import { Button } from '../ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { FormMessage } from '../ui/form-message'
import { FILTER_VALIDATION_MESSAGE, describeAuditFailure, humanizeCode } from './audit-messages'

const EMPTY_COPY = 'No matching activity yet.'
const SYSTEM_ACTOR_LABEL = 'Chorum-murohc (automatic)'

const memberLabel = (username: string, isActive: boolean) =>
  isActive ? username : `${username} (inactive)`

const formatTimestamp = (isoTimestamp: string) =>
  new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(new Date(isoTimestamp))

const contextEntries = (context: Record<string, unknown>): [string, string][] =>
  Object.entries(context).map(([key, value]) => [
    key,
    typeof value === 'string' ? value : JSON.stringify(value),
  ])

function EventRow({
  event,
  actorLabel,
}: {
  event: AuditEvent
  actorLabel: string
}) {
  const entries = contextEntries(event.context)
  return (
    <li>
      <Card className="audit-event-card">
        <CardHeader>
          <CardTitle>
            <h3>{humanizeCode(event.action)}</h3>
          </CardTitle>
          <p className="audit-event-meta">
            {actorLabel} - {formatTimestamp(event.created_at)}
          </p>
        </CardHeader>
        <CardContent className="audit-event-content">
          <p className="audit-event-target">
            {humanizeCode(event.target_type)} #{event.target_id}
          </p>
          {entries.length > 0 ? (
            <dl className="audit-event-context">
              {entries.map(([key, value]) => (
                <div className="audit-event-context-entry" key={key}>
                  <dt>{key}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </CardContent>
      </Card>
    </li>
  )
}

export function AuditHistoryScreen() {
  const [page, setPage] = useState(1)
  const [actorDraft, setActorDraft] = useState('')
  const [actionDraft, setActionDraft] = useState('')
  const [dateFromDraft, setDateFromDraft] = useState('')
  const [dateToDraft, setDateToDraft] = useState('')
  const [filters, setFilters] = useState<AuditEventFilters>({})

  const members = useQuery({
    queryKey: membersQueryKey(true),
    queryFn: ({ signal }) => fetchMembers({ includeInactive: true, signal }),
  })
  const membersById = new Map((members.data ?? []).map((member) => [member.id, member]))

  const events = useQuery({
    queryKey: auditEventsQueryKey(page, filters),
    queryFn: ({ signal }) => fetchAuditEvents({ page, filters, signal }),
  })

  const fieldError = (field: string) =>
    events.error instanceof AuditRequestError
      ? events.error.fieldErrors[field]
      : undefined

  const applyFilters = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    // Built with only the keys actually set, rather than every key present
    // and possibly `undefined`: an empty filter set and a cleared one must
    // hash to genuinely different query keys, not merely equal-after-JSON.
    const next: AuditEventFilters = {}
    if (actorDraft !== '') {
      next.actor = Number(actorDraft)
    }
    if (actionDraft.trim() !== '') {
      next.action = actionDraft.trim()
    }
    if (dateFromDraft !== '') {
      next.dateFrom = dateFromDraft
    }
    if (dateToDraft !== '') {
      next.dateTo = dateToDraft
    }
    setFilters(next)
    setPage(1)
  }

  const clearFilters = () => {
    setActorDraft('')
    setActionDraft('')
    setDateFromDraft('')
    setDateToDraft('')
    setFilters({})
    setPage(1)
  }

  const actorLabelFor = (actorId: number | null): string => {
    if (actorId === null) {
      return SYSTEM_ACTOR_LABEL
    }
    const member = membersById.get(actorId)
    return member === undefined
      ? `Member #${actorId}`
      : memberLabel(member.username, member.is_active)
  }

  let listBody: ReactNode
  if (events.isPending) {
    listBody = (
      <p aria-live="polite" className="audit-status" role="status">
        Loading activity...
      </p>
    )
  } else if (events.isError) {
    // A `validation` failure is shown once, next to the field the server
    // named, in the filter form below - never repeated here as a second,
    // more alarming "could not reach" sentence for the very same response.
    const isFilterValidation =
      events.error instanceof AuditRequestError && events.error.kind === 'validation'
    listBody = (
      <div className="audit-error">
        <FormMessage role="alert" tone="error">
          {isFilterValidation ? FILTER_VALIDATION_MESSAGE : describeAuditFailure(events.error)}
        </FormMessage>
        {isFilterValidation ? null : (
          <Button onClick={() => void events.refetch()} variant="secondary">
            Try again
          </Button>
        )}
      </div>
    )
  } else if (events.data.events.length === 0) {
    listBody = <p className="page-panel-copy">{EMPTY_COPY}</p>
  } else {
    const { events: rows, hasNext, hasPrevious } = events.data
    listBody = (
      <>
        <ul className="audit-event-list">
          {rows.map((event) => (
            <EventRow actorLabel={actorLabelFor(event.actor)} event={event} key={event.id} />
          ))}
        </ul>
        <div className="audit-pagination">
          <Button
            disabled={!hasPrevious}
            onClick={() => setPage((current) => current - 1)}
            variant="secondary"
          >
            Previous page
          </Button>
          <p aria-live="polite" className="audit-pagination-status" role="status">
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
    <div className="page-panel audit-screen">
      <h1 className="page-panel-title">Activity</h1>
      <a className="page-panel-link" href="/overview" onClick={handleInternalLinkClick}>
        Back to overview
      </a>
      <form className="audit-filters" onSubmit={applyFilters}>
        <div className="chore-form-field">
          <label className="auth-label" htmlFor="audit-filter-actor">
            Who
          </label>
          <select
            className="ui-input"
            id="audit-filter-actor"
            onChange={(event) => setActorDraft(event.target.value)}
            value={actorDraft}
          >
            <option value="">Anyone</option>
            {(members.data ?? []).map((member) => (
              <option key={member.id} value={member.id}>
                {memberLabel(member.username, member.is_active)}
              </option>
            ))}
          </select>
          {fieldError('actor') ? (
            <FormMessage role="alert" tone="error">
              {fieldError('actor')}
            </FormMessage>
          ) : null}
        </div>
        <div className="chore-form-field">
          <label className="auth-label" htmlFor="audit-filter-action">
            Action
          </label>
          <input
            className="ui-input"
            id="audit-filter-action"
            onChange={(event) => setActionDraft(event.target.value)}
            placeholder="e.g. chore.create"
            type="text"
            value={actionDraft}
          />
          {fieldError('action') ? (
            <FormMessage role="alert" tone="error">
              {fieldError('action')}
            </FormMessage>
          ) : null}
        </div>
        <div className="chore-form-field">
          <label className="auth-label" htmlFor="audit-filter-date-from">
            From
          </label>
          <input
            className="ui-input"
            id="audit-filter-date-from"
            onChange={(event) => setDateFromDraft(event.target.value)}
            type="date"
            value={dateFromDraft}
          />
          {fieldError('date_from') ? (
            <FormMessage role="alert" tone="error">
              {fieldError('date_from')}
            </FormMessage>
          ) : null}
        </div>
        <div className="chore-form-field">
          <label className="auth-label" htmlFor="audit-filter-date-to">
            To
          </label>
          <input
            className="ui-input"
            id="audit-filter-date-to"
            onChange={(event) => setDateToDraft(event.target.value)}
            type="date"
            value={dateToDraft}
          />
          {fieldError('date_to') ? (
            <FormMessage role="alert" tone="error">
              {fieldError('date_to')}
            </FormMessage>
          ) : null}
        </div>
        <div className="audit-filter-actions">
          <Button type="submit">Apply filters</Button>
          <Button onClick={clearFilters} type="button" variant="secondary">
            Clear filters
          </Button>
        </div>
      </form>
      {listBody}
    </div>
  )
}
