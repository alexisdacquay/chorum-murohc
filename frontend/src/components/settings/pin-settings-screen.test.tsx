import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { createQueryClient } from '../../api/query-client'
import {
  CONNECTION_MESSAGE,
  CURRENT_PASSWORD_REQUIRED_MESSAGE,
  PERMISSION_MESSAGE,
  PIN_CONFIRM_MISMATCH_MESSAGE,
  PIN_CONFIRM_REQUIRED_MESSAGE,
  PIN_FORMAT_MESSAGE,
  PIN_REQUIRED_MESSAGE,
  PinSettingsScreen,
  SUCCESS_MESSAGE,
} from './pin-settings-screen'

const TEST_CSRF_TOKEN = 'test-csrf-token'
const TEST_PASSWORD = 'synthetic-only-account-password'
const TEST_PIN = '3947'

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

let fetchSpy: ReturnType<typeof vi.fn>

const renderScreen = () => {
  const queryClient = createQueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      <PinSettingsScreen />
    </QueryClientProvider>,
  )
}

const passwordField = () => screen.getByLabelText('Current account password')
const pinField = () => screen.getByLabelText('New PIN')
const confirmField = () => screen.getByLabelText('Confirm new PIN')
const submitButton = () => screen.getByRole('button', { name: /^Sav/ })

const fillForm = (password: string, pin: string, confirm: string) => {
  fireEvent.change(passwordField(), { target: { value: password } })
  fireEvent.change(pinField(), { target: { value: pin } })
  fireEvent.change(confirmField(), { target: { value: confirm } })
}

const pinCalls = () =>
  fetchSpy.mock.calls.filter((call) => call[0] === '/api/v1/auth/pin/')

beforeEach(() => {
  clearCookies()
  document.cookie = `csrftoken=${TEST_CSRF_TOKEN}`
  fetchSpy = vi.fn()
  vi.stubGlobal('fetch', fetchSpy)
})

afterEach(() => {
  vi.unstubAllGlobals()
  clearCookies()
})

describe('layout and keyboard order', () => {
  test('labels three password-type fields in document order with no custom tabindex', () => {
    renderScreen()

    const password = passwordField()
    const pin = pinField()
    const confirm = confirmField()
    const submit = submitButton()

    for (const field of [password, pin, confirm]) {
      expect(field).toHaveProperty('type', 'password')
    }
    expect(password.getAttribute('autocomplete')).toBe('current-password')
    expect(submit).toHaveProperty('type', 'submit')

    const form = password.closest('form')
    expect([...(form?.querySelectorAll('input, button') ?? [])]).toEqual([
      password,
      pin,
      confirm,
      submit,
    ])
    for (const control of [password, pin, confirm, submit]) {
      expect(control.getAttribute('tabindex')).toBeNull()
    }
  })
})

describe('local validation', () => {
  test('refuses an empty submission with no request, focused on the password field', () => {
    renderScreen()

    fireEvent.click(submitButton())

    expect(screen.getByText(CURRENT_PASSWORD_REQUIRED_MESSAGE)).toBeDefined()
    expect(screen.getByText(PIN_REQUIRED_MESSAGE)).toBeDefined()
    expect(document.activeElement).toBe(passwordField())
    expect(pinCalls()).toHaveLength(0)
  })

  test('names the format rule for a non-digit or wrongly sized PIN', () => {
    renderScreen()
    fillForm(TEST_PASSWORD, '12a4', '12a4')

    fireEvent.click(submitButton())

    expect(screen.getByText(PIN_FORMAT_MESSAGE)).toBeDefined()
    expect(pinCalls()).toHaveLength(0)
  })

  test('requires the confirmation and flags a mismatch, without sending a request', () => {
    renderScreen()
    fillForm(TEST_PASSWORD, TEST_PIN, '')

    fireEvent.click(submitButton())
    expect(screen.getByText(PIN_CONFIRM_REQUIRED_MESSAGE)).toBeDefined()

    fireEvent.change(confirmField(), { target: { value: '8156' } })
    fireEvent.click(submitButton())
    expect(screen.getByText(PIN_CONFIRM_MISMATCH_MESSAGE)).toBeDefined()
    expect(pinCalls()).toHaveLength(0)
  })
})

describe('submitting', () => {
  test('posts the two fields and shows success, clearing every field', async () => {
    fetchSpy.mockResolvedValue(new Response(null, { status: 204 }))
    renderScreen()
    fillForm(TEST_PASSWORD, TEST_PIN, TEST_PIN)

    fireEvent.click(submitButton())

    await waitFor(() =>
      expect(screen.getByRole('status').textContent).toBe(SUCCESS_MESSAGE),
    )
    expect(pinCalls()).toHaveLength(1)
    const [, init] = pinCalls()[0]
    expect(JSON.parse(String(init?.body))).toEqual({
      current_password: TEST_PASSWORD,
      pin: TEST_PIN,
    })
    expect((init?.headers as Record<string, string>)['X-CSRFToken']).toBe(
      TEST_CSRF_TOKEN,
    )
    expect(passwordField()).toHaveProperty('value', '')
    expect(pinField()).toHaveProperty('value', '')
    expect(confirmField()).toHaveProperty('value', '')
  })

  test('typing again after success hides the success message', async () => {
    fetchSpy.mockResolvedValue(new Response(null, { status: 204 }))
    renderScreen()
    fillForm(TEST_PASSWORD, TEST_PIN, TEST_PIN)
    fireEvent.click(submitButton())
    await waitFor(() => expect(screen.getByRole('status').textContent).toBe(SUCCESS_MESSAGE))

    fireEvent.change(passwordField(), { target: { value: 'x' } })

    expect(screen.queryByText(SUCCESS_MESSAGE)).toBeNull()
  })

  test('shows a server field error verbatim and clears both secret fields', async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse(
        { current_password: ['Enter your current account password correctly.'] },
        400,
      ),
    )
    renderScreen()
    fillForm(TEST_PASSWORD, TEST_PIN, TEST_PIN)

    fireEvent.click(submitButton())

    await waitFor(() =>
      expect(
        screen.getByText('Enter your current account password correctly.'),
      ).toBeDefined(),
    )
    expect(passwordField()).toHaveProperty('value', '')
    expect(pinField()).toHaveProperty('value', '')
    expect(confirmField()).toHaveProperty('value', '')
    expect(document.body.textContent).not.toContain(TEST_PASSWORD)
    expect(document.body.textContent).not.toContain(TEST_PIN)
  })

  test('shows the fixed permission sentence for a 403, never server text', async () => {
    fetchSpy.mockResolvedValue(jsonResponse({ detail: 'nope' }, 403))
    renderScreen()
    fillForm(TEST_PASSWORD, TEST_PIN, TEST_PIN)

    fireEvent.click(submitButton())

    await waitFor(() => expect(screen.getByText(PERMISSION_MESSAGE)).toBeDefined())
    expect(document.body.textContent).not.toContain('nope')
  })

  test('shows the fixed connection sentence when the request cannot be reached', async () => {
    fetchSpy.mockRejectedValue(new Error('offline'))
    renderScreen()
    fillForm(TEST_PASSWORD, TEST_PIN, TEST_PIN)

    fireEvent.click(submitButton())

    await waitFor(() => expect(screen.getByText(CONNECTION_MESSAGE)).toBeDefined())
  })

  test('a second submission while one is in flight sends only one request', async () => {
    let resolveResponse: (response: Response) => void = () => undefined
    fetchSpy.mockReturnValue(
      new Promise<Response>((resolve) => {
        resolveResponse = resolve
      }),
    )
    renderScreen()
    fillForm(TEST_PASSWORD, TEST_PIN, TEST_PIN)

    fireEvent.click(submitButton())
    await waitFor(() => expect(pinCalls()).toHaveLength(1))

    // The request is still in flight, so this second activation must be a
    // no-op: the pending guard, not a race with the mock, is under test.
    fireEvent.click(submitButton())
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(pinCalls()).toHaveLength(1)

    resolveResponse(new Response(null, { status: 204 }))
    await waitFor(() => expect(screen.getByRole('status').textContent).toBe(SUCCESS_MESSAGE))
  })
})
