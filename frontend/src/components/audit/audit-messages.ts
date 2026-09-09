/**
 * Fixed copy for the household activity screen (T087, issue #84).
 *
 * The screen never renders server text for a failure that is not a named
 * filter field: a 403 or an unreachable request each map to one of these two
 * sentences, matching `points/points-messages.ts`'s precedent. A 400 is the
 * one exception - `date_from must not be later than date_to` and the
 * per-field format messages `api/audit.py` returns are already compact,
 * non-enumerating, product-authored text, so the filter form shows them
 * verbatim next to the field they name, exactly as `member-messages.ts`
 * shows a directory field error.
 */

import { AuditRequestError } from '../../api/audit'

export const CONNECTION_MESSAGE =
  'We could not reach Chorum-murohc. Check your connection and try again.'

export const PERMISSION_MESSAGE =
  'You do not have permission to see activity here. Refresh the page and try again.'

export const FILTER_VALIDATION_MESSAGE =
  'One of the filters above needs fixing before this can load.'

/**
 * Map a failed audit-history request to one fixed sentence, for the
 * top-of-list banner only. A `validation` failure is deliberately excluded:
 * `AuditHistoryScreen` shows that one next to the field it names instead, so
 * this never doubles up with it - a caller checks `kind` itself first.
 */
export const describeAuditFailure = (error: unknown): string =>
  error instanceof AuditRequestError && error.kind === 'forbidden'
    ? PERMISSION_MESSAGE
    : CONNECTION_MESSAGE

/** Turn a stored action or target-type code into readable words. */
export const humanizeCode = (code: string): string =>
  code
    .split(/[._]/)
    .filter((word) => word.length > 0)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(' ')
