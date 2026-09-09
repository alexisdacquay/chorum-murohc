import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import {
  PROGRESSION_QUERY_KEY,
  ProgressionRequestError,
  acknowledgeLevelUp,
  fetchProgression,
  isProgression,
} from './progression'

const TEST_CSRF_TOKEN = 'test-csrf-token'

const PROGRESSION = {
  level: 3,
  max_level: 10,
  lifetime_points: 320,
  next_level_threshold: 500,
  points_to_next_level: 180,
  pending_level_up: null,
}

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })

beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
afterEach(() => vi.unstubAllGlobals())

describe('PROGRESSION_QUERY_KEY', () => {
  test('is a stable literal key', () => {
    expect(PROGRESSION_QUERY_KEY).toEqual(['progression'])
  })
})

describe('isProgression', () => {
  test('accepts exactly the six-key shape', () => {
    expect(isProgression(PROGRESSION)).toBe(true)
  })

  test('accepts null next-level and pending fields at the maximum', () => {
    expect(
      isProgression({
        ...PROGRESSION,
        next_level_threshold: null,
        points_to_next_level: null,
        pending_level_up: null,
      }),
    ).toBe(true)
  })

  test('accepts a pending level-up as an integer', () => {
    expect(isProgression({ ...PROGRESSION, pending_level_up: 3 })).toBe(true)
  })

  test.each([
    ['missing a field', { ...PROGRESSION, max_level: undefined }],
    ['extra field', { ...PROGRESSION, cost: 500 }],
    ['negative level', { ...PROGRESSION, level: -1 }],
    ['fractional level', { ...PROGRESSION, level: 2.5 }],
    ['wrong type', { ...PROGRESSION, lifetime_points: '320' }],
    ['null', null],
    ['array', [PROGRESSION]],
  ])('rejects %s', (_name, value) => {
    expect(isProgression(value)).toBe(false)
  })
})

describe('fetchProgression', () => {
  test('reads the callers own level state', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(PROGRESSION))

    await expect(fetchProgression()).resolves.toEqual(PROGRESSION)

    expect(fetch).toHaveBeenCalledWith('/api/v1/progression/', {
      credentials: 'same-origin',
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: undefined,
    })
  })

  test('maps a 403 to forbidden without touching the body', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: 'nope' }, 403))

    await expect(fetchProgression()).rejects.toMatchObject({
      kind: 'forbidden',
    })
  })

  test('maps an unexpected shape to unavailable', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ level: 1 }))

    await expect(fetchProgression()).rejects.toBeInstanceOf(ProgressionRequestError)
  })

  test('maps a network failure to unavailable', async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError('network down'))

    await expect(fetchProgression()).rejects.toMatchObject({ kind: 'unavailable' })
  })
})

describe('acknowledgeLevelUp', () => {
  test('posts with the csrf header and no body content beyond it', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ ...PROGRESSION, pending_level_up: null }),
    )

    await acknowledgeLevelUp({ csrfToken: TEST_CSRF_TOKEN })

    expect(fetch).toHaveBeenCalledWith('/api/v1/progression/acknowledge/', {
      credentials: 'same-origin',
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-CSRFToken': TEST_CSRF_TOKEN,
      },
      signal: undefined,
    })
  })

  test('returns the servers fresh summary', async () => {
    const acknowledged = { ...PROGRESSION, pending_level_up: null }
    vi.mocked(fetch).mockResolvedValue(jsonResponse(acknowledged))

    await expect(
      acknowledgeLevelUp({ csrfToken: TEST_CSRF_TOKEN }),
    ).resolves.toEqual(acknowledged)
  })

  test('maps a 403 to forbidden', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: 'nope' }, 403))

    await expect(
      acknowledgeLevelUp({ csrfToken: TEST_CSRF_TOKEN }),
    ).rejects.toMatchObject({ kind: 'forbidden' })
  })
})
