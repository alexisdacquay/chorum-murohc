import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { fetchHealth, healthQueryKey } from './health'

const successResponse = () =>
  new Response(JSON.stringify({ status: 'ok' }), {
    headers: { 'Content-Type': 'application/json' },
    status: 200,
  })

describe('fetchHealth', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
  afterEach(() => vi.unstubAllGlobals())

  test('uses the exact same-origin request contract and stable key', async () => {
    vi.mocked(fetch).mockResolvedValue(successResponse())
    const controller = new AbortController()

    await expect(fetchHealth({ signal: controller.signal })).resolves.toEqual({
      status: 'ok',
    })

    expect(healthQueryKey).toEqual(['health'])
    expect(fetch).toHaveBeenCalledOnce()
    expect(fetch).toHaveBeenCalledWith('/api/v1/health/', {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      method: 'GET',
      signal: controller.signal,
    })
  })

  test.each([
    ['missing field', {}],
    ['extra field', { status: 'ok', extra: true }],
    ['wrong value', { status: 'down' }],
    ['wrong case', { status: 'OK' }],
    ['wrong type', { status: 1 }],
    ['null', null],
    ['array', [{ status: 'ok' }]],
  ])('rejects a 200 JSON response with %s', async (_name, body) => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify(body), {
        headers: { 'Content-Type': 'application/json' },
        status: 200,
      }),
    )

    await expect(
      fetchHealth({ signal: new AbortController().signal }),
    ).rejects.toBeDefined()
  })

  test('rejects inherited status instead of accepting a non-own field', async () => {
    const inherited = Object.create({ status: 'ok' })
    vi.mocked(fetch).mockResolvedValue({
      headers: new Headers({ 'Content-Type': 'application/json' }),
      json: vi.fn().mockResolvedValue(inherited),
      redirected: false,
      status: 200,
    } as unknown as Response)

    await expect(
      fetchHealth({ signal: new AbortController().signal }),
    ).rejects.toBeDefined()
  })

  test.each([
    ['error status', 503, 'application/json'],
    ['unexpected success status', 204, 'application/json'],
    ['missing content type', 200, null],
    ['wrong content type', 200, 'text/plain'],
  ])('fails before parsing an %s response', async (_name, status, contentType) => {
    const parseBody = vi.fn()
    vi.mocked(fetch).mockResolvedValue({
      headers: new Headers(contentType ? { 'Content-Type': contentType } : {}),
      json: parseBody,
      redirected: false,
      status,
    } as unknown as Response)

    await expect(
      fetchHealth({ signal: new AbortController().signal }),
    ).rejects.toBeDefined()
    expect(parseBody).not.toHaveBeenCalled()
  })

  test('rejects redirects, invalid JSON, and network rejection', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      headers: new Headers({ 'Content-Type': 'application/json' }),
      json: vi.fn().mockResolvedValue({ status: 'ok' }),
      redirected: true,
      status: 200,
    } as unknown as Response)
    await expect(
      fetchHealth({ signal: new AbortController().signal }),
    ).rejects.toBeDefined()

    vi.mocked(fetch).mockResolvedValueOnce(
      new Response('{', {
        headers: { 'Content-Type': 'application/json' },
        status: 200,
      }),
    )
    await expect(
      fetchHealth({ signal: new AbortController().signal }),
    ).rejects.toBeDefined()

    vi.mocked(fetch).mockRejectedValueOnce(new Error('internal diagnostic'))
    await expect(
      fetchHealth({ signal: new AbortController().signal }),
    ).rejects.toBeDefined()
  })
})
