/**
 * The ledger-history API client, for the merged T039 contract's second
 * route: `GET /api/v1/ledger/`.
 *
 * Read-only and child-only, matching the server (`api/balances.ts`'s
 * `LedgerHistoryView`): the caller's own history, newest first, twenty-five
 * rows to a page, through DRF's native page-number pagination. There is no
 * client override of the page size, and no query string ever names another
 * user or household - the server derives both from the session.
 *
 * `fetchLedgerHistory` takes a plain page number rather than the `next` and
 * `previous` URLs the envelope carries: those are absolute URLs (scheme and
 * host included), and rebuilding a request from `?page=N` is simpler than
 * parsing one back down to a same-origin path. `count`, `has_next`, and
 * `has_previous` in the returned shape are exactly enough for a screen to
 * decide which controls to show.
 */

export interface LedgerEntry {
  id: number
  amount: number
  reason: string
  reason_label: string
  created_at: string
}

export interface LedgerPage {
  entries: LedgerEntry[]
  count: number
  hasNext: boolean
  hasPrevious: boolean
}

export const ledgerQueryKey = (page: number) => ['ledger', page] as const

/**
 * - `notFound`: the requested page does not exist (before the first page,
 *   past the last one, or not a whole number).
 * - `forbidden`: the caller is no longer an active child of this household.
 * - `unavailable`: unreachable, timed out, not JSON, or an unexpected status.
 */
export type LedgerFailureKind = 'notFound' | 'forbidden' | 'unavailable'

export class LedgerRequestError extends Error {
  readonly kind: LedgerFailureKind

  constructor(kind: LedgerFailureKind) {
    super(`Ledger history request failed: ${kind}`)
    this.name = 'LedgerRequestError'
    this.kind = kind
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const isJsonMediaType = (contentType: string | null) =>
  contentType !== null &&
  /^application\/(?:[a-z0-9!#$&^_.+-]+\+)?json(?:\s*;|$)/i.test(contentType)

const isLedgerEntry = (value: unknown): value is LedgerEntry =>
  isRecord(value) &&
  Object.keys(value).length === 5 &&
  typeof value.id === 'number' &&
  Number.isInteger(value.id) &&
  typeof value.amount === 'number' &&
  Number.isInteger(value.amount) &&
  typeof value.reason === 'string' &&
  typeof value.reason_label === 'string' &&
  typeof value.created_at === 'string'

/** The exact four-key DRF page envelope this route returns. */
const isLedgerEnvelope = (
  value: unknown,
): value is {
  count: number
  next: string | null
  previous: string | null
  results: LedgerEntry[]
} =>
  isRecord(value) &&
  Object.keys(value).length === 4 &&
  typeof value.count === 'number' &&
  Number.isInteger(value.count) &&
  value.count >= 0 &&
  (value.next === null || typeof value.next === 'string') &&
  (value.previous === null || typeof value.previous === 'string') &&
  Array.isArray(value.results) &&
  value.results.every(isLedgerEntry)

const readJsonBody = async (response: Response): Promise<unknown> => {
  if (!isJsonMediaType(response.headers.get('Content-Type'))) {
    return undefined
  }
  try {
    return await response.json()
  } catch {
    return undefined
  }
}

/** `GET /api/v1/ledger/?page=<page>`: one page of the caller's own history. */
export const fetchLedgerHistory = async ({
  page,
  signal,
}: {
  page: number
  signal?: AbortSignal
}): Promise<LedgerPage> => {
  let response: Response
  try {
    response = await fetch(`/api/v1/ledger/?page=${page}`, {
      method: 'GET',
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal,
    })
  } catch {
    throw new LedgerRequestError('unavailable')
  }

  if (response.redirected) {
    throw new LedgerRequestError('unavailable')
  }
  if (response.status === 403) {
    throw new LedgerRequestError('forbidden')
  }
  if (response.status === 404) {
    throw new LedgerRequestError('notFound')
  }

  const body = await readJsonBody(response)
  if (response.status !== 200 || !isLedgerEnvelope(body)) {
    throw new LedgerRequestError('unavailable')
  }

  return {
    entries: body.results,
    count: body.count,
    hasNext: body.next !== null,
    hasPrevious: body.previous !== null,
  }
}
