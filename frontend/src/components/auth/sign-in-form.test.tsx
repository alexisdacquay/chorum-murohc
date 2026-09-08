import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import {
  CONNECTION_MESSAGE,
  SIGN_IN_FAILED_MESSAGE,
  SIGN_IN_THROTTLED_MESSAGE,
  SignInForm,
  type SignInFormProps,
} from './sign-in-form'
import { createQueryClient } from '../../api/query-client'
import { fetchSession, sessionQueryKey } from '../../api/session'

// Synthetic credentials only. None of these is a real account or a real token.
const TEST_CSRF_TOKEN = 'test-csrf-token'
const TEST_USERNAME = 'test-parent'
const TEST_PASSWORD = 'test-only-password'

const PARENT_SESSION = {
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

const clearCookies = () => {
  for (const part of document.cookie.split(';')) {
    const name = part.split('=')[0].trim()

    if (name !== '') {
      document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT`
    }
  }
}

const renderForm = (props: SignInFormProps = {}) => {
  const queryClient = createQueryClient()
  const view = render(
    <QueryClientProvider client={queryClient}>
      <SignInForm {...props} />
    </QueryClientProvider>,
  )

  return { ...view, queryClient }
}

const usernameField = () => screen.getByLabelText('Username')
const passwordField = () => screen.getByLabelText('Password')
const submitButton = () => screen.getByRole('button', { name: /^Sign(ing)? in/ })
const alertText = () => screen.getByRole('alert').textContent

const enter = (username: string, password: string) => {
  fireEvent.change(usernameField(), { target: { value: username } })
  fireEvent.change(passwordField(), { target: { value: password } })
}

const loginCalls = () =>
  vi.mocked(fetch).mock.calls.filter(
    (call) => call[0] === '/api/v1/auth/login/',
  )

const sessionCalls = () =>
  vi.mocked(fetch).mock.calls.filter(
    (call) => call[0] === '/api/v1/auth/session/',
  )

beforeEach(() => {
  clearCookies()
  document.cookie = `csrftoken=${TEST_CSRF_TOKEN}`
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
  clearCookies()
})

describe('the sign-in form', () => {
  test('labels both fields, hides the password, and keeps one keyboard order', () => {
    const { container } = renderForm()

    const username = usernameField()
    const password = passwordField()
    const submit = submitButton()
    const form = container.querySelector('form')

    expect(username).toHaveProperty('type', 'text')
    expect(username.getAttribute('autocomplete')).toBe('username')
    expect(password).toHaveProperty('type', 'password')
    expect(password.getAttribute('autocomplete')).toBe('current-password')
    expect(submit).toHaveProperty('type', 'submit')
    expect(form?.contains(submit)).toBe(true)

    // Nothing reorders the sequence, so Tab reaches them in document order.
    expect([...(form?.querySelectorAll('input, button') ?? [])]).toEqual([
      username,
      password,
      submit,
    ])
    for (const control of [username, password, submit]) {
      expect(control.getAttribute('tabindex')).toBeNull()
      control.focus()
      expect(document.activeElement).toBe(control)
    }

    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      'Sign in',
    )
    expect(screen.getAllByRole('alert')).toHaveLength(1)
    expect(alertText()).toBe('')
    expect(username.getAttribute('aria-invalid')).toBeNull()
    expect(password.getAttribute('aria-invalid')).toBeNull()
  })

  test('refuses an empty field locally, with no request and the first field focused', () => {
    renderForm()

    fireEvent.click(submitButton())

    expect(fetch).not.toHaveBeenCalled()
    expect(alertText()).toBe(SIGN_IN_FAILED_MESSAGE)
    expect(document.activeElement).toBe(usernameField())

    fireEvent.change(usernameField(), { target: { value: TEST_USERNAME } })
    fireEvent.click(submitButton())

    expect(fetch).not.toHaveBeenCalled()
    expect(alertText()).toBe(SIGN_IN_FAILED_MESSAGE)
    expect(document.activeElement).toBe(passwordField())
    expect(usernameField()).toHaveProperty('value', TEST_USERNAME)
  })

  test('submits on Enter as it does on a click', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(PARENT_SESSION))
    const { container } = renderForm()

    enter(TEST_USERNAME, TEST_PASSWORD)
    // What pressing Enter in a field dispatches.
    fireEvent.submit(container.querySelector('form') as HTMLFormElement)

    await waitFor(() => expect(loginCalls()).toHaveLength(1))
  })

  test('answers a wrong password, an unknown user, and a disabled account alike', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(
        { detail: 'Unable to log in with the credentials provided.' },
        400,
      ),
    )
    renderForm()

    const rendered: string[] = []
    for (const username of ['test-parent', 'test-unknown', 'test-disabled']) {
      enter(username, TEST_PASSWORD)
      fireEvent.click(submitButton())
      await waitFor(() => expect(alertText()).toBe(SIGN_IN_FAILED_MESSAGE))
      rendered.push(screen.getByRole('alert').outerHTML)
    }

    expect(new Set(rendered).size).toBe(1)
    expect(alertText()).not.toContain('test-unknown')
    expect(alertText()).not.toContain('Unable to log in')
    expect(usernameField().getAttribute('aria-invalid')).toBe('true')
    expect(passwordField().getAttribute('aria-invalid')).toBe('true')

    const region = screen.getByRole('alert')
    expect(usernameField().getAttribute('aria-describedby')).toBe(region.id)
    expect(passwordField().getAttribute('aria-describedby')).toBe(region.id)
    expect(region.id).not.toBe('')

    // The typed username survives; the password does not.
    expect(usernameField()).toHaveProperty('value', 'test-disabled')
    expect(passwordField()).toHaveProperty('value', '')
  })

  test('shows the throttle message with no wait hint and stays submittable', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ detail: 'Too many login attempts. Try again later.' }, 429),
    )
    renderForm()

    enter(TEST_USERNAME, TEST_PASSWORD)
    fireEvent.click(submitButton())

    await waitFor(() => expect(alertText()).toBe(SIGN_IN_THROTTLED_MESSAGE))
    expect(alertText()).not.toMatch(/\d/)
    expect(alertText()).not.toContain('Try again later')
    expect(submitButton()).toHaveProperty('disabled', false)
    expect(usernameField().getAttribute('aria-invalid')).toBeNull()

    enter(TEST_USERNAME, TEST_PASSWORD)
    fireEvent.click(submitButton())
    await waitFor(() => expect(loginCalls()).toHaveLength(2))
  })

  test.each([
    ['an unreachable service', () => Promise.reject(new Error('offline'))],
    [
      'a non-JSON body',
      async () =>
        new Response('<html></html>', {
          headers: { 'Content-Type': 'text/html' },
          status: 200,
        }),
    ],
    ['an unexpected status', async () => jsonResponse({}, 500)],
  ])('shows the connection message for %s', async (_name, respond) => {
    vi.mocked(fetch).mockImplementation(respond as unknown as typeof fetch)
    renderForm()

    enter(TEST_USERNAME, TEST_PASSWORD)
    fireEvent.click(submitButton())

    await waitFor(() => expect(alertText()).toBe(CONNECTION_MESSAGE))
    expect(usernameField()).toHaveProperty('value', TEST_USERNAME)
    expect(passwordField()).toHaveProperty('value', '')
  })

  test('disables the control in flight so a second activation posts nothing', async () => {
    vi.mocked(fetch).mockReturnValue(new Promise<Response>(() => undefined))
    renderForm()

    enter(TEST_USERNAME, TEST_PASSWORD)
    fireEvent.click(submitButton())

    await waitFor(() =>
      expect(submitButton()).toHaveProperty('disabled', true),
    )
    expect(submitButton().getAttribute('aria-busy')).toBe('true')
    expect(submitButton().textContent).toBe('Signing in...')

    fireEvent.click(submitButton())
    fireEvent.submit(
      submitButton().closest('form') as HTMLFormElement,
    )

    expect(loginCalls()).toHaveLength(1)
  })

  test('fetches the CSRF cookie first when it is missing, then posts it', async () => {
    clearCookies()
    vi.mocked(fetch).mockImplementation(async (input) => {
      if (input === '/api/v1/auth/session/') {
        document.cookie = `csrftoken=${TEST_CSRF_TOKEN}`
        return jsonResponse({
          is_authenticated: false,
          user: null,
          household: null,
          role: null,
        })
      }
      return jsonResponse(PARENT_SESSION)
    })
    renderForm()

    enter(TEST_USERNAME, TEST_PASSWORD)
    fireEvent.click(submitButton())

    await waitFor(() => expect(loginCalls()).toHaveLength(1))
    expect(sessionCalls()).toHaveLength(1)
    expect(
      new Headers(loginCalls()[0][1]?.headers).get('X-CSRFToken'),
    ).toBe(TEST_CSRF_TOKEN)
  })

  test('posts nothing when the cookie is still missing afterwards', async () => {
    clearCookies()
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({
        is_authenticated: false,
        user: null,
        household: null,
        role: null,
      }),
    )
    renderForm()

    enter(TEST_USERNAME, TEST_PASSWORD)
    fireEvent.click(submitButton())

    await waitFor(() => expect(alertText()).toBe(CONNECTION_MESSAGE))
    expect(loginCalls()).toHaveLength(0)
  })

  test('renews the token once after a 403 and never resubmits the credentials', async () => {
    vi.mocked(fetch).mockImplementation(async (input) =>
      input === '/api/v1/auth/session/'
        ? jsonResponse({
            is_authenticated: false,
            user: null,
            household: null,
            role: null,
          })
        : jsonResponse({ detail: 'CSRF Failed.' }, 403),
    )
    const { queryClient } = renderForm()

    await queryClient.fetchQuery({
      queryKey: sessionQueryKey,
      queryFn: ({ signal }) => fetchSession({ signal }),
    })
    expect(sessionCalls()).toHaveLength(1)

    enter(TEST_USERNAME, TEST_PASSWORD)
    fireEvent.click(submitButton())

    await waitFor(() => expect(alertText()).toBe(CONNECTION_MESSAGE))
    // Exactly one renewal of the token, and the credentials are never sent
    // again on the viewer's behalf.
    await waitFor(() => expect(sessionCalls()).toHaveLength(2))
    expect(loginCalls()).toHaveLength(1)
    expect(alertText()).not.toContain('CSRF')
  })

  test('turns a successful login into the session with no second round trip', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(PARENT_SESSION))
    const { queryClient } = renderForm()

    enter(TEST_USERNAME, TEST_PASSWORD)
    fireEvent.click(submitButton())

    await waitFor(() =>
      expect(queryClient.getQueryData(sessionQueryKey)).toEqual(PARENT_SESSION),
    )
    expect(fetch).toHaveBeenCalledOnce()
    expect(alertText()).toBe('')
  })

  test('keeps the password out of the document, the URL, and browser storage', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ detail: 'Unable to log in with the credentials provided.' }, 400),
    )
    const { container } = renderForm()

    enter(TEST_USERNAME, TEST_PASSWORD)
    // The field masks the value; nothing renders it as text.
    expect(passwordField()).toHaveProperty('value', TEST_PASSWORD)
    expect(passwordField()).toHaveProperty('type', 'password')
    expect(document.body.textContent).not.toContain(TEST_PASSWORD)

    fireEvent.click(submitButton())
    await waitFor(() => expect(alertText()).toBe(SIGN_IN_FAILED_MESSAGE))

    expect(container.innerHTML).not.toContain(TEST_PASSWORD)
    expect(container.innerHTML).not.toContain(TEST_CSRF_TOKEN)
    expect(document.body.textContent).not.toContain(TEST_USERNAME)
    expect(window.location.href).not.toContain(TEST_PASSWORD)
    expect(window.localStorage.length).toBe(0)
    expect(window.sessionStorage.length).toBe(0)
  })
})

describe('the recoverable session notice', () => {
  test('is absent until the session request itself fails', () => {
    renderForm()

    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull()
    expect(screen.queryByRole('status')).toBeNull()
  })

  test('offers one working retry beside the same form, with no spinner left behind', () => {
    const onRetrySession = vi.fn()
    renderForm({ isSessionUnavailable: true, onRetrySession })

    const notice = screen.getByRole('status')

    expect(notice.textContent).toContain(CONNECTION_MESSAGE)
    expect(submitButton()).toHaveProperty('disabled', false)

    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onRetrySession).toHaveBeenCalledOnce()
  })

  test('marks the retry busy while it runs', () => {
    renderForm({
      isRetryingSession: true,
      isSessionUnavailable: true,
      onRetrySession: vi.fn(),
    })

    const retry = screen.getByRole('button', { name: 'Trying again...' })

    expect(retry).toHaveProperty('disabled', true)
    expect(retry.getAttribute('aria-busy')).toBe('true')
  })
})
