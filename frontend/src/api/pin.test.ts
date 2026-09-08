import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { PinRequestError, setOrReplacePin } from './pin'

const TEST_CSRF_TOKEN = 'test-csrf-token'
const TEST_PASSWORD = 'synthetic-only-password'
const TEST_PIN = '3947'

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })

beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
afterEach(() => vi.unstubAllGlobals())

describe('setOrReplacePin', () => {
  test('posts the two fields, the CSRF header, and same-origin credentials', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }))

    await expect(
      setOrReplacePin({
        csrfToken: TEST_CSRF_TOKEN,
        currentPassword: TEST_PASSWORD,
        pin: TEST_PIN,
      }),
    ).resolves.toBeUndefined()

    expect(fetch).toHaveBeenCalledWith('/api/v1/auth/pin/', {
      credentials: 'same-origin',
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-CSRFToken': TEST_CSRF_TOKEN,
      },
      body: JSON.stringify({ current_password: TEST_PASSWORD, pin: TEST_PIN }),
      signal: undefined,
    })
  })

  test('resolves on 204 with no body read', async () => {
    const response = new Response(null, { status: 204 })
    const jsonSpy = vi.spyOn(response, 'json')
    vi.mocked(fetch).mockResolvedValue(response)

    await setOrReplacePin({
      csrfToken: TEST_CSRF_TOKEN,
      currentPassword: TEST_PASSWORD,
      pin: TEST_PIN,
    })

    expect(jsonSpy).not.toHaveBeenCalled()
  })

  test('rejects a 400 as validation, carrying the first message per field', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ pin: ['Choose a different PIN.'] }, 400),
    )

    const failure = await setOrReplacePin({
      csrfToken: TEST_CSRF_TOKEN,
      currentPassword: TEST_PASSWORD,
      pin: TEST_PIN,
    }).catch((error: unknown) => error)

    expect(failure).toBeInstanceOf(PinRequestError)
    expect((failure as PinRequestError).kind).toBe('validation')
    expect((failure as PinRequestError).fieldErrors).toEqual({
      pin: 'Choose a different PIN.',
    })
  })

  test('rejects a 403 as forbidden', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: 'nope' }, 403))

    const failure = await setOrReplacePin({
      csrfToken: TEST_CSRF_TOKEN,
      currentPassword: TEST_PASSWORD,
      pin: TEST_PIN,
    }).catch((error: unknown) => error)

    expect(failure).toBeInstanceOf(PinRequestError)
    expect((failure as PinRequestError).kind).toBe('forbidden')
  })

  test('rejects an unexpected status as unavailable', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({}, 500))

    const failure = await setOrReplacePin({
      csrfToken: TEST_CSRF_TOKEN,
      currentPassword: TEST_PASSWORD,
      pin: TEST_PIN,
    }).catch((error: unknown) => error)

    expect(failure).toBeInstanceOf(PinRequestError)
    expect((failure as PinRequestError).kind).toBe('unavailable')
  })

  test('rejects a network failure as unavailable', async () => {
    vi.mocked(fetch).mockRejectedValue(new Error('offline'))

    const failure = await setOrReplacePin({
      csrfToken: TEST_CSRF_TOKEN,
      currentPassword: TEST_PASSWORD,
      pin: TEST_PIN,
    }).catch((error: unknown) => error)

    expect(failure).toBeInstanceOf(PinRequestError)
    expect((failure as PinRequestError).kind).toBe('unavailable')
  })

  test('never places the password or the PIN in a thrown error', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ current_password: ['Enter your current account password correctly.'] }, 400),
    )

    const failure = (await setOrReplacePin({
      csrfToken: TEST_CSRF_TOKEN,
      currentPassword: TEST_PASSWORD,
      pin: TEST_PIN,
    }).catch((error: unknown) => error)) as PinRequestError

    const rendered = JSON.stringify({
      message: failure.message,
      fieldErrors: failure.fieldErrors,
    })
    expect(rendered).not.toContain(TEST_PASSWORD)
    expect(rendered).not.toContain(TEST_PIN)
  })
})
