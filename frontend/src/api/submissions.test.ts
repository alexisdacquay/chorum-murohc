import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import {
  SubmissionRequestError,
  createIdempotencyKey,
  createSubmission,
  fetchPendingSubmissions,
  isSubmission,
} from './submissions'

const TEST_CSRF_TOKEN = 'test-csrf-token'

const SUBMISSION = {
  id: 9,
  chore: 5,
  chore_name: 'Wash dishes',
  chore_points: 10,
  note: 'Left the mop out',
  status: 'pending' as const,
  created_at: '2026-09-01T00:00:00Z',
}

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })

beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
afterEach(() => vi.unstubAllGlobals())

describe('isSubmission', () => {
  test('accepts exactly the seven-key shape', () => {
    expect(isSubmission(SUBMISSION)).toBe(true)
  })

  test('accepts a null chore', () => {
    expect(isSubmission({ ...SUBMISSION, chore: null })).toBe(true)
  })

  test.each([
    ['missing a field', { ...SUBMISSION, created_at: undefined }],
    ['extra field', { ...SUBMISSION, decided_at: null }],
    ['wrong type', { ...SUBMISSION, chore_points: '10' }],
    ['unknown status', { ...SUBMISSION, status: 'in_review' }],
    ['fractional id', { ...SUBMISSION, id: 9.5 }],
    ['null', null],
    ['array', [SUBMISSION]],
  ])('rejects %s', (_name, value) => {
    expect(isSubmission(value)).toBe(false)
  })
})

describe('createIdempotencyKey', () => {
  test('returns a non-empty string and never repeats', () => {
    const first = createIdempotencyKey()
    const second = createIdempotencyKey()

    expect(typeof first).toBe('string')
    expect(first.length).toBeGreaterThan(0)
    expect(first).not.toBe(second)
  })
})

describe('fetchPendingSubmissions', () => {
  test('requests the collection and returns it', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse([SUBMISSION]))

    await expect(fetchPendingSubmissions()).resolves.toEqual([SUBMISSION])

    expect(fetch).toHaveBeenCalledWith('/api/v1/submissions/', {
      credentials: 'same-origin',
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: undefined,
    })
  })

  test('maps a 403 to forbidden without touching the body', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: 'nope' }, 403))

    await expect(fetchPendingSubmissions()).rejects.toMatchObject({
      kind: 'forbidden',
    })
  })

  test('maps a network failure and a malformed body to unavailable', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error('offline'))
    await expect(fetchPendingSubmissions()).rejects.toMatchObject({
      kind: 'unavailable',
    })

    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse([{ ...SUBMISSION, id: 'nine' }]))
    await expect(fetchPendingSubmissions()).rejects.toMatchObject({
      kind: 'unavailable',
    })
  })
})

describe('createSubmission', () => {
  test('posts the chore, note and idempotency key with the CSRF header', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(SUBMISSION, 201))

    await expect(
      createSubmission({
        choreId: 5,
        csrfToken: TEST_CSRF_TOKEN,
        idempotencyKey: 'key-1',
        note: 'Left the mop out',
      }),
    ).resolves.toEqual(SUBMISSION)

    expect(fetch).toHaveBeenCalledWith('/api/v1/submissions/', {
      credentials: 'same-origin',
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-CSRFToken': TEST_CSRF_TOKEN,
      },
      body: JSON.stringify({
        chore: 5,
        note: 'Left the mop out',
        idempotency_key: 'key-1',
      }),
      signal: undefined,
    })
  })

  test('treats a 200 idempotent replay as a success', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(SUBMISSION, 200))

    await expect(
      createSubmission({
        choreId: 5,
        csrfToken: TEST_CSRF_TOKEN,
        idempotencyKey: 'key-1',
        note: '',
      }),
    ).resolves.toEqual(SUBMISSION)
  })

  test('reduces a 400 duplicate-pending body to one message on chore', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ chore: ['You already have a pending submission.'] }, 400),
    )

    const failure = (await createSubmission({
      choreId: 5,
      csrfToken: TEST_CSRF_TOKEN,
      idempotencyKey: 'key-1',
      note: '',
    }).catch((error: unknown) => error)) as SubmissionRequestError

    expect(failure).toBeInstanceOf(SubmissionRequestError)
    expect(failure.kind).toBe('validation')
    expect(failure.fieldErrors).toEqual({
      chore: 'You already have a pending submission.',
    })
  })

  test.each([
    [403, 'forbidden'],
    [404, 'notFound'],
    [500, 'unavailable'],
  ])('maps status %d to %s', async (status, kind) => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({}, status))

    await expect(
      createSubmission({
        choreId: 5,
        csrfToken: TEST_CSRF_TOKEN,
        idempotencyKey: 'key-1',
        note: '',
      }),
    ).rejects.toMatchObject({ kind })
  })
})
