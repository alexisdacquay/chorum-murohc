import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import {
  RewardRequestError,
  createReward,
  deactivateReward,
  deleteReward,
  fetchChildRewards,
  fetchRewards,
  isChildReward,
  isReward,
  reactivateReward,
  rewardsQueryKey,
  updateReward,
} from './rewards'

const TEST_CSRF_TOKEN = 'test-csrf-token'

const REWARD = {
  id: 5,
  name: 'Screen time',
  points: 15,
  is_active: true,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
}

const CHILD_REWARD = { id: 5, name: 'Screen time', points: 15 }

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })

beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
afterEach(() => vi.unstubAllGlobals())

describe('rewardsQueryKey', () => {
  test('carries the includeInactive flag so each filter gets its own cache', () => {
    expect(rewardsQueryKey(false)).toEqual(['rewards', { includeInactive: false }])
    expect(rewardsQueryKey(true)).toEqual(['rewards', { includeInactive: true }])
  })
})

describe('isReward', () => {
  test('accepts exactly the six-key parent shape', () => {
    expect(isReward(REWARD)).toBe(true)
  })

  test.each([
    ['missing a field', { ...REWARD, updated_at: undefined }],
    ['extra field', { ...REWARD, redemptions: [] }],
    ['wrong type', { ...REWARD, points: '15' }],
    ['fractional id', { ...REWARD, id: 5.5 }],
    ['the child shape', CHILD_REWARD],
    ['null', null],
  ])('rejects %s', (_name, value) => {
    expect(isReward(value)).toBe(false)
  })
})

describe('isChildReward', () => {
  test('accepts exactly the three-key child shape', () => {
    expect(isChildReward(CHILD_REWARD)).toBe(true)
  })

  test.each([
    ['the parent shape', REWARD],
    ['missing a field', { id: 5, name: 'Screen time' }],
    ['wrong type', { ...CHILD_REWARD, points: '15' }],
    ['null', null],
  ])('rejects %s', (_name, value) => {
    expect(isChildReward(value)).toBe(false)
  })
})

describe('fetchRewards', () => {
  test('requests the active-only list by default', async () => {
    const fetchSpy = vi.mocked(fetch).mockResolvedValue(jsonResponse([REWARD]))

    const rewards = await fetchRewards({ includeInactive: false })

    expect(rewards).toEqual([REWARD])
    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/v1/rewards/',
      expect.objectContaining({ method: 'GET' }),
    )
  })

  test('widens the query string when includeInactive is true', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse([]))

    await fetchRewards({ includeInactive: true })

    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/rewards/?include_inactive=true',
      expect.anything(),
    )
  })

  test('rejects a 403 as forbidden', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: 'nope' }, 403))

    await expect(fetchRewards({ includeInactive: false })).rejects.toMatchObject({
      kind: 'forbidden',
    })
  })

  test('rejects a body that is not a reward list as unavailable', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ not: 'a list' }))

    await expect(fetchRewards({ includeInactive: false })).rejects.toMatchObject({
      kind: 'unavailable',
    })
  })
})

describe('fetchChildRewards', () => {
  test('parses the three-field child shape', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse([CHILD_REWARD]))

    const rewards = await fetchChildRewards({})

    expect(rewards).toEqual([CHILD_REWARD])
  })

  test('rejects a network failure as unavailable', async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError('network down'))

    await expect(fetchChildRewards({})).rejects.toBeInstanceOf(RewardRequestError)
  })
})

describe('createReward', () => {
  test('posts the name and points with the CSRF header', async () => {
    const fetchSpy = vi.mocked(fetch).mockResolvedValue(jsonResponse(REWARD, 201))

    const created = await createReward({
      csrfToken: TEST_CSRF_TOKEN,
      name: 'Screen time',
      points: 15,
    })

    expect(created).toEqual(REWARD)
    const [path, init] = fetchSpy.mock.calls[0]
    expect(path).toBe('/api/v1/rewards/')
    expect(init).toMatchObject({
      method: 'POST',
      headers: expect.objectContaining({ 'X-CSRFToken': TEST_CSRF_TOKEN }),
      body: JSON.stringify({ name: 'Screen time', points: 15 }),
    })
  })

  test('surfaces field errors from a 400', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ name: ['A reward with this name already exists.'] }, 400),
    )

    await expect(
      createReward({ csrfToken: TEST_CSRF_TOKEN, name: 'Screen time', points: 15 }),
    ).rejects.toMatchObject({
      kind: 'validation',
      fieldErrors: { name: 'A reward with this name already exists.' },
    })
  })
})

describe('updateReward, deleteReward, deactivateReward, reactivateReward', () => {
  test('updateReward PATCHes the detail route', async () => {
    const fetchSpy = vi.mocked(fetch).mockResolvedValue(jsonResponse(REWARD))

    await updateReward({ csrfToken: TEST_CSRF_TOKEN, id: 5, name: 'Screen time', points: 20 })

    expect(fetchSpy.mock.calls[0][0]).toBe('/api/v1/rewards/5/')
    expect(fetchSpy.mock.calls[0][1]).toMatchObject({ method: 'PATCH' })
  })

  test('deleteReward resolves on 204 and rejects a 404 as notFound', async () => {
    const fetchSpy = vi.mocked(fetch)
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 204 }))
    await expect(
      deleteReward({ csrfToken: TEST_CSRF_TOKEN, id: 5 }),
    ).resolves.toBeUndefined()

    fetchSpy.mockResolvedValueOnce(jsonResponse({ detail: 'Not found.' }, 404))
    await expect(
      deleteReward({ csrfToken: TEST_CSRF_TOKEN, id: 5 }),
    ).rejects.toMatchObject({ kind: 'notFound' })
  })

  test('deactivateReward and reactivateReward POST to their own routes', async () => {
    // A `Response` body can only be read once, so each call needs its own
    // fresh instance rather than reusing one shared `mockResolvedValue`.
    const fetchSpy = vi.mocked(fetch).mockImplementation(() =>
      Promise.resolve(jsonResponse(REWARD)),
    )

    await deactivateReward({ csrfToken: TEST_CSRF_TOKEN, id: 5 })
    expect(fetchSpy.mock.calls[0][0]).toBe('/api/v1/rewards/5/deactivate/')

    await reactivateReward({ csrfToken: TEST_CSRF_TOKEN, id: 5 })
    expect(fetchSpy.mock.calls[1][0]).toBe('/api/v1/rewards/5/reactivate/')
  })
})
