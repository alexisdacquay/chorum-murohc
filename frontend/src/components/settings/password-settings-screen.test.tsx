import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { createQueryClient } from '../../api/query-client'
import {
  CONFIRM_MISMATCH_MESSAGE,
  CONFIRM_REQUIRED_MESSAGE,
  CONNECTION_MESSAGE,
  CURRENT_PASSWORD_REQUIRED_MESSAGE,
  NEW_PASSWORD_REQUIRED_MESSAGE,
  PERMISSION_MESSAGE,
  PasswordSettingsScreen,
  SUCCESS_MESSAGE,
} from './password-settings-screen'

const TEST_CSRF_TOKEN = 'test-csrf-token'
const CURRENT_PASSWORD = 'synthetic-only-current-password'
const NEW_PASSWORD = 'a genuinely unusual passphrase 42'

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
      <PasswordSettingsScreen />
    </QueryClientProvider>,
  )
}

const currentField = () => screen.getByLabelText('Current password')
const newField = () => screen.getByLabelText('New password')
const confirmField = () => screen.getByLabelText('Confirm new password')
const submitButton = () => screen.getByRole('button', { name: /^(Change|Sav)/ })

const fillForm = (current: string, next: string, confirm: string) => {
  fireEvent.change(currentField(), { target: { value: current } })
  fireEvent.change(newField(), { target: { value: next } })
  fireEvent.change(confirmField(), { target: { value: confirm } })
}

const passwordCalls = () =>
  fetchSpy.mock.calls.filter((call) => call[0] === '/api/v1/auth/password/')

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

describe('layout', () => {
  test('labels three password-type fields in document order', () => {
    renderScreen()

    const current = currentField()
    const next = newField()
    const confirm = confirmField()
    const submit = submitButton()

    for (const field of [current, next, confirm]) {
      expect(field).toHaveProperty('type', 'password')
    }
    expect(current.getAttribute('autocomplete')).toBe('current-password')
    expect(next.getAttribute('autocomplete')).toBe('new-password')

    const form = current.closest('form')
    expect([...(form?.querySelectorAll('input, button') ?? [])]).toEqual([
      current,
      next,
      confirm,
      submit,
    ])
  })
})

describe('local validation', () => {
  test('refuses an empty submission with no request, focused on the current-password field', () => {
    renderScreen()

    fireEvent.click(submitButton())

    expect(screen.getByText(CURRENT_PASSWORD_REQUIRED_MESSAGE)).toBeDefined()
    expect(screen.getByText(NEW_PASSWORD_REQUIRED_MESSAGE)).toBeDefined()
    expect(document.activeElement).toBe(currentField())
    expect(passwordCalls()).toHaveLength(0)
  })

  test('requires the confirmation and flags a mismatch, without sending a request', () => {
    renderScreen()
    fillForm(CURRENT_PASSWORD, NEW_PASSWORD, '')

    fireEvent.click(submitButton())
    expect(screen.getByText(CONFIRM_REQUIRED_MESSAGE)).toBeDefined()

    fireEvent.change(confirmField(), { target: { value: 'something else entirely' } })
    fireEvent.click(submitButton())
    expect(screen.getByText(CONFIRM_MISMATCH_MESSAGE)).toBeDefined()
    expect(passwordCalls()).toHaveLength(0)
  })
})

describe('submitting', () => {
  test('posts the two fields and shows success, clearing every field', async () => {
    fetchSpy.mockResolvedValue(new Response(null, { status: 204 }))
    renderScreen()
    fillForm(CURRENT_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)

    fireEvent.click(submitButton())

    await waitFor(() =>
      expect(screen.getByRole('status').textContent).toBe(SUCCESS_MESSAGE),
    )
    expect(passwordCalls()).toHaveLength(1)
    const [, init] = passwordCalls()[0]
    expect(JSON.parse(String(init?.body))).toEqual({
      current_password: CURRENT_PASSWORD,
      new_password: NEW_PASSWORD,
    })
    expect((init?.headers as Record<string, string>)['X-CSRFToken']).toBe(
      TEST_CSRF_TOKEN,
    )
    expect(currentField()).toHaveProperty('value', '')
    expect(newField()).toHaveProperty('value', '')
    expect(confirmField()).toHaveProperty('value', '')
  })

  test('shows a server field error verbatim and clears every secret field', async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse(
        { current_password: ['Enter your current account password correctly.'] },
        400,
      ),
    )
    renderScreen()
    fillForm(CURRENT_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)

    fireEvent.click(submitButton())

    await waitFor(() =>
      expect(
        screen.getByText('Enter your current account password correctly.'),
      ).toBeDefined(),
    )
    expect(currentField()).toHaveProperty('value', '')
    expect(newField()).toHaveProperty('value', '')
    expect(confirmField()).toHaveProperty('value', '')
    expect(document.body.textContent).not.toContain(CURRENT_PASSWORD)
    expect(document.body.textContent).not.toContain(NEW_PASSWORD)
  })

  test('shows the fixed permission sentence for a 403, never server text', async () => {
    fetchSpy.mockResolvedValue(jsonResponse({ detail: 'nope' }, 403))
    renderScreen()
    fillForm(CURRENT_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)

    fireEvent.click(submitButton())

    await waitFor(() => expect(screen.getByText(PERMISSION_MESSAGE)).toBeDefined())
    expect(document.body.textContent).not.toContain('nope')
  })

  test('shows the fixed connection sentence when the request cannot be reached', async () => {
    fetchSpy.mockRejectedValue(new Error('offline'))
    renderScreen()
    fillForm(CURRENT_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)

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
    fillForm(CURRENT_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)

    fireEvent.click(submitButton())
    await waitFor(() => expect(passwordCalls()).toHaveLength(1))

    fireEvent.click(submitButton())
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(passwordCalls()).toHaveLength(1)

    resolveResponse(new Response(null, { status: 204 }))
    await waitFor(() =>
      expect(screen.getByRole('status').textContent).toBe(SUCCESS_MESSAGE),
    )
  })
})
