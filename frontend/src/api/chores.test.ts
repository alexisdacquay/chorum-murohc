import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import {
  ChoreRequestError,
  choresQueryKey,
  createChore,
  deactivateChore,
  deleteChore,
  fetchChildChores,
  fetchChores,
  isChildChore,
  isChore,
  reactivateChore,
  updateChore,
} from './chores'

const TEST_CSRF_TOKEN = 'test-csrf-token'

const CHORE = {
  id: 5,
  name: 'Wash dishes',
  points: 10,
  is_active: true,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
}

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })

beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
afterEach(() => vi.unstubAllGlobals())

describe('choresQueryKey', () => {
  test('carries the includeInactive flag so each filter gets its own cache', () => {
    expect(choresQueryKey(false)).toEqual(['chores', { includeInactive: false }])
    expect(choresQueryKey(true)).toEqual(['chores', { includeInactive: true }])
  })
})

describe('isChore', () => {
  test('accepts exactly the six-key parent shape', () => {
    expect(isChore(CHORE)).toBe(true)
  })

  test.each([
    ['missing a field', { ...CHORE, updated_at: undefined }],
    ['extra field', { ...CHORE, submissions: [] }],
    ['wrong type', { ...CHORE, points: '10' }],
    ['fractional id', { ...CHORE, id: 5.5 }],
    ['null', null],
    ['array', [CHORE]],
  ])('rejects %s', (_name, value) => {
    expect(isChore(value)).toBe(false)
  })
})

describe('fetchChores', () => {
  test('requests the active-only list by default', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse([CHORE]))

    await expect(fetchChores({ includeInactive: false })).resolves.toEqual([CHORE])

    expect(fetch).toHaveBeenCalledWith('/api/v1/chores/', {
      credentials: 'same-origin',
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: undefined,
    })
  })

  test('asks for both states with includeInactive', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse([CHORE, { ...CHORE, id: 6, is_active: false }]))

    await fetchChores({ includeInactive: true })

    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/chores/?include_inactive=true',
      expect.anything(),
    )
  })

  test('maps a 403 to forbidden without touching the body', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: 'nope' }, 403))

    await expect(fetchChores({ includeInactive: false })).rejects.toMatchObject({
      kind: 'forbidden',
    })
  })

  test('maps a network failure, a bad status and a malformed body to unavailable', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error('offline'))
    await expect(fetchChores({ includeInactive: false })).rejects.toMatchObject({
      kind: 'unavailable',
    })

    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse([CHORE], 500))
    await expect(fetchChores({ includeInactive: false })).rejects.toMatchObject({
      kind: 'unavailable',
    })

    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse([{ ...CHORE, points: 'ten' }]))
    await expect(fetchChores({ includeInactive: false })).rejects.toMatchObject({
      kind: 'unavailable',
    })
  })
})

describe('isChildChore', () => {
  const CHILD_CHORE = { id: 5, name: 'Wash dishes', points: 10 }

  test('accepts exactly the three-key child shape', () => {
    expect(isChildChore(CHILD_CHORE)).toBe(true)
  })

  test.each([
    ['missing a field', { id: 5, name: 'Wash dishes' }],
    ['extra field', { ...CHILD_CHORE, is_active: true }],
    ['wrong type', { ...CHILD_CHORE, points: '10' }],
    ['fractional id', { ...CHILD_CHORE, id: 5.5 }],
    ['null', null],
    ['array', [CHILD_CHORE]],
  ])('rejects %s', (_name, value) => {
    expect(isChildChore(value)).toBe(false)
  })
})

describe('fetchChildChores', () => {
  test('requests the child shape and returns it', async () => {
    const chore = { id: 5, name: 'Wash dishes', points: 10 }
    vi.mocked(fetch).mockResolvedValue(jsonResponse([chore]))

    await expect(fetchChildChores()).resolves.toEqual([chore])

    expect(fetch).toHaveBeenCalledWith('/api/v1/chores/', {
      credentials: 'same-origin',
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: undefined,
    })
  })

  test('maps a 403 to forbidden without touching the body', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: 'nope' }, 403))

    await expect(fetchChildChores()).rejects.toMatchObject({ kind: 'forbidden' })
  })

  test('rejects a body carrying the parent shape as unavailable', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse([CHORE]))

    await expect(fetchChildChores()).rejects.toMatchObject({ kind: 'unavailable' })
  })
})

describe('createChore', () => {
  test('posts the trimmed body with the CSRF header', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(CHORE, 201))

    await expect(
      createChore({ csrfToken: TEST_CSRF_TOKEN, name: 'Wash dishes', points: 10 }),
    ).resolves.toEqual(CHORE)

    expect(fetch).toHaveBeenCalledWith('/api/v1/chores/', {
      credentials: 'same-origin',
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-CSRFToken': TEST_CSRF_TOKEN,
      },
      body: JSON.stringify({ name: 'Wash dishes', points: 10 }),
      signal: undefined,
    })
  })

  test('reduces a 400 body to one message per field', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(
        { name: ['A chore with this name already exists in this household.'] },
        400,
      ),
    )

    const failure = await createChore({
      csrfToken: TEST_CSRF_TOKEN,
      name: 'Wash dishes',
      points: 10,
    }).catch((error: unknown) => error)

    expect(failure).toBeInstanceOf(ChoreRequestError)
    expect((failure as ChoreRequestError).kind).toBe('validation')
    expect((failure as ChoreRequestError).fieldErrors).toEqual({
      name: 'A chore with this name already exists in this household.',
    })
  })

  test('ignores a 400 body shaped unlike DRF field errors', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: 'nope' }, 400))

    const failure = (await createChore({
      csrfToken: TEST_CSRF_TOKEN,
      name: 'x',
      points: 1,
    }).catch((error: unknown) => error)) as ChoreRequestError

    expect(failure.kind).toBe('validation')
    expect(failure.fieldErrors).toEqual({})
  })
})

describe('updateChore', () => {
  test('patches the one chore by id', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(CHORE))

    await updateChore({
      csrfToken: TEST_CSRF_TOKEN,
      id: 5,
      name: 'Wash dishes',
      points: 12,
    })

    expect(fetch).toHaveBeenCalledWith('/api/v1/chores/5/', {
      credentials: 'same-origin',
      method: 'PATCH',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-CSRFToken': TEST_CSRF_TOKEN,
      },
      body: JSON.stringify({ name: 'Wash dishes', points: 12 }),
      signal: undefined,
    })
  })
})

describe('deleteChore', () => {
  test('treats 204 as the only success', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }))

    await expect(
      deleteChore({ csrfToken: TEST_CSRF_TOKEN, id: 5 }),
    ).resolves.toBeUndefined()

    expect(fetch).toHaveBeenCalledWith('/api/v1/chores/5/', {
      credentials: 'same-origin',
      method: 'DELETE',
      headers: { Accept: 'application/json', 'X-CSRFToken': TEST_CSRF_TOKEN },
      signal: undefined,
    })
  })

  test.each([
    [403, 'forbidden'],
    [404, 'notFound'],
    [500, 'unavailable'],
  ])('maps status %d to %s', async (status, kind) => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status }))

    await expect(
      deleteChore({ csrfToken: TEST_CSRF_TOKEN, id: 5 }),
    ).rejects.toMatchObject({ kind })
  })
})

describe('deactivateChore and reactivateChore', () => {
  test('post to the named action route and return the updated chore', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ ...CHORE, is_active: false }))
    await deactivateChore({ csrfToken: TEST_CSRF_TOKEN, id: 5 })
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/chores/5/deactivate/',
      expect.objectContaining({ method: 'POST' }),
    )

    vi.mocked(fetch).mockResolvedValue(jsonResponse(CHORE))
    await reactivateChore({ csrfToken: TEST_CSRF_TOKEN, id: 5 })
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/chores/5/reactivate/',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
