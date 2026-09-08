/**
 * The balance API client, for the one figure it returns: `GET /api/v1/balance/`
 * from the merged T039 contract.
 *
 * Read-only and child-only, matching the server: this is the caller's own
 * balance, never chosen by a query string, and there is nothing here for a
 * parent to call. Used by the child rewards screen to show what a redemption
 * would leave behind.
 */

export const balanceQueryKey = ['balance'] as const

export type BalanceFailureKind = 'forbidden' | 'unavailable'

export class BalanceRequestError extends Error {
  readonly kind: BalanceFailureKind

  constructor(kind: BalanceFailureKind) {
    super(`Balance request failed: ${kind}`)
    this.name = 'BalanceRequestError'
    this.kind = kind
  }
}

const isBalanceBody = (value: unknown): value is { balance: number } =>
  typeof value === 'object' &&
  value !== null &&
  !Array.isArray(value) &&
  Object.keys(value as Record<string, unknown>).length === 1 &&
  typeof (value as Record<string, unknown>).balance === 'number' &&
  Number.isInteger((value as Record<string, unknown>).balance)

const isJsonMediaType = (contentType: string | null) =>
  contentType !== null &&
  /^application\/(?:[a-z0-9!#$&^_.+-]+\+)?json(?:\s*;|$)/i.test(contentType)

/** `GET /api/v1/balance/`: the caller's own point total. */
export const fetchBalance = async ({
  signal,
}: {
  signal?: AbortSignal
}): Promise<number> => {
  let response: Response
  try {
    response = await fetch('/api/v1/balance/', {
      method: 'GET',
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal,
    })
  } catch {
    throw new BalanceRequestError('unavailable')
  }

  if (response.redirected) {
    throw new BalanceRequestError('unavailable')
  }
  if (response.status === 403) {
    throw new BalanceRequestError('forbidden')
  }

  let body: unknown
  if (isJsonMediaType(response.headers.get('Content-Type'))) {
    try {
      body = await response.json()
    } catch {
      body = undefined
    }
  }

  if (response.status !== 200 || !isBalanceBody(body)) {
    throw new BalanceRequestError('unavailable')
  }
  return body.balance
}
