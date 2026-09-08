import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import {
  CSRF_COOKIE_NAME,
  SessionRequestError,
  ensureCsrfToken,
  fetchSession,
  login,
  logout,
  readCsrfToken,
  sessionQueryKey,
} from './session'

// Synthetic values only. Nothing here is a real credential or a real token.
const TEST_CSRF_TOKEN = 'test-csrf-token'
const TEST_USERNAME = 'test-parent'
const TEST_PASSWORD = 'test-only-password'

const SIGNED_OUT = {
  is_authenticated: false,
  user: null,
  household: null,
  role: null,
}
const PARENT = {
  is_authenticated: true,
  user: { id: 7, username: TEST_USERNAME },
  household: { id: 3, name: 'Test household' },
  role: 'parent',
}

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })

const emptyResponse = (status: number) => new Response(null, { status })

const setCookie = (value: string) => {
  document.cookie = `${CSRF_COOKIE_NAME}=${value}`
}

const clearCookies = () => {
  for (const part of document.cookie.split(';')) {
    const name = part.split('=')[0].trim()

    if (name !== '') {
      document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT`
    }
  }
}

const failureOf = async (call: Promise<unknown>) => {
  try {
    await call
    return 'resolved'
  } catch (error) {
    return error instanceof SessionRequestError ? error.failure : 'other'
  }
}

const signal = () => new AbortController().signal

beforeEach(() => {
  clearCookies()
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
  clearCookies()
})

describe('fetchSession', () => {
  test('uses the exact same-origin request contract and stable key', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(SIGNED_OUT))
    const abortSignal = signal()

    await expect(fetchSession({ signal: abortSignal })).resolves.toEqual(
      SIGNED_OUT,
    )

    expect(sessionQueryKey).toEqual(['session'])
    expect(fetch).toHaveBeenCalledExactlyOnceWith('/api/v1/auth/session/', {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      method: 'GET',
      signal: abortSignal,
    })
  })

  test('accepts an authenticated body with a household and a role', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(PARENT))

    await expect(fetchSession()).resolves.toEqual(PARENT)
  })

  test.each([
    ['missing key', { is_authenticated: false, user: null, household: null }],
    ['extra key', { ...SIGNED_OUT, is_staff: true }],
    ['flag as a string', { ...SIGNED_OUT, is_authenticated: 'false' }],
    ['user without an id', { ...PARENT, user: { username: TEST_USERNAME } }],
    ['user with an extra key', {
      ...PARENT,
      user: { id: 7, username: TEST_USERNAME, email: 'x' },
    }],
    ['non-integer id', { ...PARENT, user: { id: 1.5, username: 'x' } }],
    ['household as a string', { ...PARENT, household: 'Test household' }],
    ['role as a number', { ...PARENT, role: 1 }],
    ['null body', null],
    ['array body', [SIGNED_OUT]],
    ['string body', 'parent'],
  ])('treats a 200 body with %s as a failed request', async (_name, body) => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(body))

    await expect(failureOf(fetchSession())).resolves.toBe('unavailable')
  })

  test('rejects a body whose keys are inherited rather than its own', async () => {
    vi.mocked(fetch).mockResolvedValue({
      headers: new Headers({ 'Content-Type': 'application/json' }),
      json: vi.fn().mockResolvedValue(Object.create(SIGNED_OUT)),
      redirected: false,
      status: 200,
    } as unknown as Response)

    await expect(failureOf(fetchSession())).resolves.toBe('unavailable')
  })

  test.each([
    ['an error status', 503, 'application/json'],
    ['an unexpected success status', 204, 'application/json'],
    ['no content type', 200, null],
    ['a non-JSON content type', 200, 'text/html'],
  ])('fails before parsing %s response', async (_name, status, contentType) => {
    const parseBody = vi.fn()
    vi.mocked(fetch).mockResolvedValue({
      headers: new Headers(contentType ? { 'Content-Type': contentType } : {}),
      json: parseBody,
      redirected: false,
      status,
    } as unknown as Response)

    await expect(failureOf(fetchSession())).resolves.toBe('unavailable')
    expect(parseBody).not.toHaveBeenCalled()
  })

  test('fails on a redirect, on invalid JSON, and on a network rejection', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      headers: new Headers({ 'Content-Type': 'application/json' }),
      json: vi.fn().mockResolvedValue(SIGNED_OUT),
      redirected: true,
      status: 200,
    } as unknown as Response)
    await expect(failureOf(fetchSession())).resolves.toBe('unavailable')

    vi.mocked(fetch).mockResolvedValueOnce(
      new Response('{', {
        headers: { 'Content-Type': 'application/json' },
        status: 200,
      }),
    )
    await expect(failureOf(fetchSession())).resolves.toBe('unavailable')

    vi.mocked(fetch).mockRejectedValueOnce(
      new Error('internal diagnostic for http://internal.invalid/'),
    )
    await expect(failureOf(fetchSession())).resolves.toBe('unavailable')
  })

  test('drops the platform diagnostic instead of carrying it outward', async () => {
    vi.mocked(fetch).mockRejectedValue(new Error('internal diagnostic'))

    await expect(fetchSession()).rejects.toThrow(
      /^Session request failed: unavailable$/,
    )
  })
})

describe('readCsrfToken', () => {
  test('reads only its own cookie, among others and with spacing', () => {
    document.cookie = 'other=first'
    setCookie(TEST_CSRF_TOKEN)
    document.cookie = 'trailing=last'

    expect(readCsrfToken()).toBe(TEST_CSRF_TOKEN)
  })

  test('answers null when there is no cookie at all', () => {
    expect(document.cookie).toBe('')
    expect(readCsrfToken()).toBeNull()
  })

  test('answers null for a different cookie and for an empty value', () => {
    document.cookie = 'sessionid-lookalike=irrelevant'
    expect(readCsrfToken()).toBeNull()

    setCookie('')
    expect(readCsrfToken()).toBeNull()
  })
})

describe('ensureCsrfToken', () => {
  test('uses the cookie already present and makes no request', async () => {
    setCookie(TEST_CSRF_TOKEN)

    await expect(ensureCsrfToken()).resolves.toBe(TEST_CSRF_TOKEN)
    expect(fetch).not.toHaveBeenCalled()
  })

  test('calls the session endpoint once when the cookie is missing', async () => {
    vi.mocked(fetch).mockImplementation(async () => {
      setCookie(TEST_CSRF_TOKEN)
      return jsonResponse(SIGNED_OUT)
    })

    await expect(ensureCsrfToken()).resolves.toBe(TEST_CSRF_TOKEN)
    expect(fetch).toHaveBeenCalledOnce()
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe('/api/v1/auth/session/')
  })

  test('fails when the endpoint delivers no cookie, and when it cannot be reached', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(SIGNED_OUT))
    await expect(failureOf(ensureCsrfToken())).resolves.toBe('unavailable')

    vi.mocked(fetch).mockRejectedValue(new Error('offline'))
    await expect(failureOf(ensureCsrfToken())).resolves.toBe('unavailable')
  })
})

describe('login', () => {
  const attempt = () =>
    login({
      csrfToken: TEST_CSRF_TOKEN,
      password: TEST_PASSWORD,
      username: TEST_USERNAME,
    })

  test('posts the credentials same-origin with the CSRF header only', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(PARENT))
    const abortSignal = signal()

    await expect(
      login({
        csrfToken: TEST_CSRF_TOKEN,
        password: TEST_PASSWORD,
        signal: abortSignal,
        username: TEST_USERNAME,
      }),
    ).resolves.toEqual(PARENT)

    expect(fetch).toHaveBeenCalledExactlyOnceWith('/api/v1/auth/login/', {
      body: JSON.stringify({
        username: TEST_USERNAME,
        password: TEST_PASSWORD,
      }),
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-CSRFToken': TEST_CSRF_TOKEN,
      },
      method: 'POST',
      signal: abortSignal,
    })
  })

  test.each([
    ['a refusal', 400, 'credentials'],
    ['a throttled attempt', 429, 'throttled'],
    ['a rejected token', 403, 'forbidden'],
    ['a server fault', 500, 'unavailable'],
    ['an unexpected success', 202, 'unavailable'],
  ])('maps %s to one failure kind', async (_name, status, expected) => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ detail: 'server wording that must never be shown' }, status),
    )

    await expect(failureOf(attempt())).resolves.toBe(expected)
  })

  test('maps an unreachable service and a contract-breaking body alike', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error('offline'))
    await expect(failureOf(attempt())).resolves.toBe('unavailable')

    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ ok: true }))
    await expect(failureOf(attempt())).resolves.toBe('unavailable')

    vi.mocked(fetch).mockResolvedValueOnce(
      new Response('<html></html>', {
        headers: { 'Content-Type': 'text/html' },
        status: 200,
      }),
    )
    await expect(failureOf(attempt())).resolves.toBe('unavailable')
  })

  test('never carries the password or the token into the failure', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ detail: 'Unable to log in with the credentials provided.' }, 400),
    )

    await expect(attempt()).rejects.toMatchObject({
      failure: 'credentials',
      message: 'Session request failed: credentials',
    })

    const raised = await attempt().catch((error: unknown) => String(error))

    expect(raised).not.toContain(TEST_PASSWORD)
    expect(raised).not.toContain(TEST_CSRF_TOKEN)
    expect(raised).not.toContain('Unable to log in')
  })
})

describe('logout', () => {
  const attempt = () => logout({ csrfToken: TEST_CSRF_TOKEN })

  test('posts nothing but the CSRF header and accepts 204', async () => {
    vi.mocked(fetch).mockResolvedValue(emptyResponse(204))
    const abortSignal = signal()

    await expect(
      logout({ csrfToken: TEST_CSRF_TOKEN, signal: abortSignal }),
    ).resolves.toBeUndefined()

    expect(fetch).toHaveBeenCalledExactlyOnceWith('/api/v1/auth/logout/', {
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        'X-CSRFToken': TEST_CSRF_TOKEN,
      },
      method: 'POST',
      signal: abortSignal,
    })
  })

  test.each([
    ['an expired session', 403, 'forbidden'],
    ['a server fault', 500, 'unavailable'],
    ['an unexpected success', 200, 'unavailable'],
  ])('maps %s to one failure kind', async (_name, status, expected) => {
    vi.mocked(fetch).mockResolvedValue(emptyResponse(status))

    await expect(failureOf(attempt())).resolves.toBe(expected)
  })

  test('maps an unreachable service to a connection failure', async () => {
    vi.mocked(fetch).mockRejectedValue(new Error('offline'))

    await expect(failureOf(attempt())).resolves.toBe('unavailable')
  })
})
