import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import {
  OVERVIEW_QUERY_KEY,
  OverviewRequestError,
  fetchOverview,
  isOverview,
} from './overview'

const OVERVIEW = {
  children: [
    {
      id: 5,
      username: 'avery',
      balance: 120,
      level: 3,
      max_level: 10,
      creature_line: 'Dragon',
      creature_form: 'Fledgling',
      pending_count: 2,
    },
  ],
  parents: [{ id: 2, username: 'jordan' }],
  pending_total: 2,
}

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })

beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
afterEach(() => vi.unstubAllGlobals())

describe('OVERVIEW_QUERY_KEY', () => {
  test('is a stable literal key', () => {
    expect(OVERVIEW_QUERY_KEY).toEqual(['overview'])
  })
})

describe('isOverview', () => {
  test('accepts the exact three-key shape', () => {
    expect(isOverview(OVERVIEW)).toBe(true)
  })

  test('accepts an empty household', () => {
    expect(isOverview({ children: [], parents: [], pending_total: 0 })).toBe(true)
  })

  test('accepts a child with no creature chosen yet', () => {
    expect(
      isOverview({
        ...OVERVIEW,
        children: [
          { ...OVERVIEW.children[0], creature_line: null, creature_form: null },
        ],
      }),
    ).toBe(true)
  })

  test.each([
    ['missing a top-level field', { children: [], parents: [] }],
    ['extra top-level field', { ...OVERVIEW, note: 'x' }],
    [
      'a child missing a field',
      { ...OVERVIEW, children: [{ ...OVERVIEW.children[0], level: undefined }] },
    ],
    [
      'a child with an extra field',
      { ...OVERVIEW, children: [{ ...OVERVIEW.children[0], note: 'x' }] },
    ],
    [
      'a negative balance typed as a string',
      { ...OVERVIEW, children: [{ ...OVERVIEW.children[0], balance: '120' }] },
    ],
    ['null', null],
    ['array', [OVERVIEW]],
  ])('rejects %s', (_name, value) => {
    expect(isOverview(value)).toBe(false)
  })

  test('a negative balance is still accepted: spending is never clamped', () => {
    expect(
      isOverview({
        ...OVERVIEW,
        children: [{ ...OVERVIEW.children[0], balance: -30 }],
      }),
    ).toBe(true)
  })
})

describe('fetchOverview', () => {
  test('reads the household summary', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(OVERVIEW))

    await expect(fetchOverview()).resolves.toEqual(OVERVIEW)

    expect(fetch).toHaveBeenCalledWith('/api/v1/overview/', {
      credentials: 'same-origin',
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: undefined,
    })
  })

  test('a child caller is refused', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: 'denied' }, 403))

    const error = await fetchOverview().catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(OverviewRequestError)
    expect((error as OverviewRequestError).kind).toBe('forbidden')
  })

  test.each([
    ['a network failure', () => Promise.reject(new Error('offline'))],
    ['a malformed body', () => Promise.resolve(jsonResponse({ children: [] }))],
    ['a non-JSON body', () => Promise.resolve(new Response('nope', { status: 200 }))],
  ])('%s is unavailable', async (_name, respond) => {
    vi.mocked(fetch).mockImplementation(respond)

    const error = await fetchOverview().catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(OverviewRequestError)
    expect((error as OverviewRequestError).kind).toBe('unavailable')
  })

  test('a redirected response is treated as unavailable, never followed silently', async () => {
    const redirected = jsonResponse(OVERVIEW)
    Object.defineProperty(redirected, 'redirected', { value: true })
    vi.mocked(fetch).mockResolvedValue(redirected)

    const error = await fetchOverview().catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(OverviewRequestError)
    expect((error as OverviewRequestError).kind).toBe('unavailable')
  })
})
