import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import {
  RedemptionRequestError,
  cancelRedemption,
  fetchChildRedemptions,
  fetchParentRedemptions,
  fulfilRedemption,
  isChildRedemption,
  isParentRedemption,
  redeemReward,
} from './redemptions'

const TEST_CSRF_TOKEN = 'test-csrf-token'

const CHILD_REDEMPTION = {
  id: 9,
  reward_name: 'Screen time',
  reward_points: 15,
  status: 'pending' as const,
  created_at: '2026-09-01T00:00:00Z',
  decided_at: null,
}

const PARENT_REDEMPTION = {
  ...CHILD_REDEMPTION,
  child_id: 3,
  child_username: 'kid',
}

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })

beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
afterEach(() => vi.unstubAllGlobals())

describe('isChildRedemption', () => {
  test('accepts the exact six-key child shape', () => {
    expect(isChildRedemption(CHILD_REDEMPTION)).toBe(true)
  })

  test.each([
    ['the parent shape', PARENT_REDEMPTION],
    ['an unknown status', { ...CHILD_REDEMPTION, status: 'rejected' }],
    ['a non-null-non-string decided_at', { ...CHILD_REDEMPTION, decided_at: 5 }],
    ['null', null],
  ])('rejects %s', (_name, value) => {
    expect(isChildRedemption(value)).toBe(false)
  })
})

describe('isParentRedemption', () => {
  test('accepts the exact eight-key parent shape', () => {
    expect(isParentRedemption(PARENT_REDEMPTION)).toBe(true)
  })

  test('rejects the child shape, which is missing who asked', () => {
    expect(isParentRedemption(CHILD_REDEMPTION)).toBe(false)
  })
})

describe('fetchChildRedemptions and fetchParentRedemptions', () => {
  test('fetchChildRedemptions parses a list of the child shape', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse([CHILD_REDEMPTION]))

    await expect(fetchChildRedemptions({})).resolves.toEqual([CHILD_REDEMPTION])
  })

  test('fetchParentRedemptions parses a list of the parent shape', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse([PARENT_REDEMPTION]))

    await expect(fetchParentRedemptions({})).resolves.toEqual([PARENT_REDEMPTION])
  })

  test('fetchParentRedemptions rejects a child-shaped body as unavailable', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse([CHILD_REDEMPTION]))

    await expect(fetchParentRedemptions({})).rejects.toMatchObject({
      kind: 'unavailable',
    })
  })
})

describe('redeemReward', () => {
  test('posts the reward id and idempotency key with the CSRF header', async () => {
    const fetchSpy = vi
      .mocked(fetch)
      .mockResolvedValue(jsonResponse(CHILD_REDEMPTION, 201))

    const redemption = await redeemReward({
      csrfToken: TEST_CSRF_TOKEN,
      rewardId: 7,
      idempotencyKey: 'attempt-1',
    })

    expect(redemption).toEqual(CHILD_REDEMPTION)
    const [path, init] = fetchSpy.mock.calls[0]
    expect(path).toBe('/api/v1/redemptions/')
    expect(init).toMatchObject({
      method: 'POST',
      headers: expect.objectContaining({ 'X-CSRFToken': TEST_CSRF_TOKEN }),
      body: JSON.stringify({ reward: 7, idempotency_key: 'attempt-1' }),
    })
  })

  test('surfaces an insufficient-points 400 as a validation failure on "reward"', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ reward: ['Not enough points for this reward.'] }, 400),
    )

    await expect(
      redeemReward({ csrfToken: TEST_CSRF_TOKEN, rewardId: 7, idempotencyKey: 'k' }),
    ).rejects.toMatchObject({
      kind: 'validation',
      fieldErrors: { reward: 'Not enough points for this reward.' },
    })
  })

  test('a 200 (replayed retry) and a 201 (first attempt) both resolve', async () => {
    const fetchSpy = vi.mocked(fetch)
    fetchSpy.mockResolvedValueOnce(jsonResponse(CHILD_REDEMPTION, 201))
    fetchSpy.mockResolvedValueOnce(jsonResponse(CHILD_REDEMPTION, 200))

    const first = await redeemReward({
      csrfToken: TEST_CSRF_TOKEN,
      rewardId: 7,
      idempotencyKey: 'same-key',
    })
    const second = await redeemReward({
      csrfToken: TEST_CSRF_TOKEN,
      rewardId: 7,
      idempotencyKey: 'same-key',
    })

    expect(first).toEqual(second)
  })

  test('a 404 rejects as notFound', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: 'Not found.' }, 404))

    await expect(
      redeemReward({ csrfToken: TEST_CSRF_TOKEN, rewardId: 7, idempotencyKey: 'k' }),
    ).rejects.toBeInstanceOf(RedemptionRequestError)
  })
})

describe('fulfilRedemption and cancelRedemption', () => {
  test('POST to their own action routes and parse the parent shape', async () => {
    // A `Response` body can only be read once, so each call needs its own
    // fresh instance rather than reusing one shared `mockResolvedValue`.
    const fetchSpy = vi.mocked(fetch).mockImplementation(() =>
      Promise.resolve(jsonResponse(PARENT_REDEMPTION)),
    )

    const fulfilled = await fulfilRedemption({ csrfToken: TEST_CSRF_TOKEN, id: 9 })
    expect(fulfilled).toEqual(PARENT_REDEMPTION)
    expect(fetchSpy.mock.calls[0][0]).toBe('/api/v1/redemptions/9/fulfil/')

    await cancelRedemption({ csrfToken: TEST_CSRF_TOKEN, id: 9 })
    expect(fetchSpy.mock.calls[1][0]).toBe('/api/v1/redemptions/9/cancel/')
  })

  test('a 403 rejects as forbidden and a stale 404 rejects as notFound', async () => {
    const fetchSpy = vi.mocked(fetch)
    fetchSpy.mockResolvedValueOnce(jsonResponse({ detail: 'nope' }, 403))
    await expect(
      fulfilRedemption({ csrfToken: TEST_CSRF_TOKEN, id: 9 }),
    ).rejects.toMatchObject({ kind: 'forbidden' })

    fetchSpy.mockResolvedValueOnce(jsonResponse({ detail: 'Not found.' }, 404))
    await expect(
      cancelRedemption({ csrfToken: TEST_CSRF_TOKEN, id: 9 }),
    ).rejects.toMatchObject({ kind: 'notFound' })
  })
})
