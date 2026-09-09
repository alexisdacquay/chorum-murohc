import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { LedgerRequestError, fetchLedgerHistory, ledgerQueryKey } from './ledger'

const ENTRY = {
  id: 42,
  amount: 25,
  reason: 'chore_credit',
  reason_label: 'Chore credit',
  created_at: '2026-09-06T12:00:00Z',
}

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })

beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
afterEach(() => vi.unstubAllGlobals())

describe('ledgerQueryKey', () => {
  test('is a stable literal key that varies by page', () => {
    expect(ledgerQueryKey(1)).toEqual(['ledger', 1])
    expect(ledgerQueryKey(2)).toEqual(['ledger', 2])
  })
})

describe('fetchLedgerHistory', () => {
  test('requests the named page and returns the flattened shape', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({
        count: 60,
        next: 'http://testserver/api/v1/ledger/?page=2',
        previous: null,
        results: [ENTRY],
      }),
    )

    await expect(fetchLedgerHistory({ page: 1 })).resolves.toEqual({
      entries: [ENTRY],
      count: 60,
      hasNext: true,
      hasPrevious: false,
    })

    expect(fetch).toHaveBeenCalledWith('/api/v1/ledger/?page=1', {
      credentials: 'same-origin',
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: undefined,
    })
  })

  test('an empty page reports no next and no previous', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ count: 0, next: null, previous: null, results: [] }),
    )

    await expect(fetchLedgerHistory({ page: 1 })).resolves.toEqual({
      entries: [],
      count: 0,
      hasNext: false,
      hasPrevious: false,
    })
  })

  test('a later page reports both a next and a previous', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({
        count: 60,
        next: 'http://testserver/api/v1/ledger/?page=3',
        previous: 'http://testserver/api/v1/ledger/?page=1',
        results: [ENTRY],
      }),
    )

    const page = await fetchLedgerHistory({ page: 2 })

    expect(page.hasNext).toBe(true)
    expect(page.hasPrevious).toBe(true)
    expect(fetch).toHaveBeenCalledWith('/api/v1/ledger/?page=2', expect.anything())
  })

  test('a positive, a negative, and a zero amount all pass through untouched', async () => {
    const entries = [
      { ...ENTRY, id: 1, amount: 25, reason: 'chore_credit', reason_label: 'Chore credit' },
      { ...ENTRY, id: 2, amount: -10, reason: 'reward_debit', reason_label: 'Reward debit' },
    ]
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ count: 2, next: null, previous: null, results: entries }),
    )

    const page = await fetchLedgerHistory({ page: 1 })

    expect(page.entries.map((entry) => entry.amount)).toEqual([25, -10])
  })

  test('a 404 invalid-page body raises the notFound kind', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: 'Invalid page.' }, 404))

    await expect(fetchLedgerHistory({ page: 999 })).rejects.toMatchObject({
      kind: 'notFound',
    })
  })

  test('a 403 raises the forbidden kind', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: 'nope' }, 403))

    await expect(fetchLedgerHistory({ page: 1 })).rejects.toMatchObject({
      kind: 'forbidden',
    })
  })

  test('a network failure raises the unavailable kind', async () => {
    vi.mocked(fetch).mockRejectedValue(new Error('offline'))

    await expect(fetchLedgerHistory({ page: 1 })).rejects.toBeInstanceOf(
      LedgerRequestError,
    )
    await expect(fetchLedgerHistory({ page: 1 })).rejects.toMatchObject({
      kind: 'unavailable',
    })
  })

  test('a redirect (signed out) raises the unavailable kind', async () => {
    const response = jsonResponse({ ok: true })
    Object.defineProperty(response, 'redirected', { value: true })
    vi.mocked(fetch).mockResolvedValue(response)

    await expect(fetchLedgerHistory({ page: 1 })).rejects.toMatchObject({
      kind: 'unavailable',
    })
  })

  test('a malformed envelope raises the unavailable kind', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ count: 1, results: [ENTRY] }))

    await expect(fetchLedgerHistory({ page: 1 })).rejects.toMatchObject({
      kind: 'unavailable',
    })
  })

  test('a non-JSON body raises the unavailable kind', async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response('not json', { status: 200, headers: { 'Content-Type': 'text/plain' } }),
    )

    await expect(fetchLedgerHistory({ page: 1 })).rejects.toMatchObject({
      kind: 'unavailable',
    })
  })
})
