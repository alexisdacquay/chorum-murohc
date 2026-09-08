import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { SIGN_OUT_FAILED_MESSAGE, SignOutButton } from './sign-out-button'
import { createQueryClient } from '../../api/query-client'
import { sessionQueryKey } from '../../api/session'
import { SIGNED_OUT_SESSION } from '../../navigation/role-router'

const TEST_CSRF_TOKEN = 'test-csrf-token'

const PARENT_SESSION = {
  is_authenticated: true,
  user: { id: 7, username: 'test-parent' },
  household: { id: 3, name: 'Test household' },
  role: 'parent',
}

const clearCookies = () => {
  for (const part of document.cookie.split(';')) {
    const name = part.split('=')[0].trim()

    if (name !== '') {
      document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT`
    }
  }
}

const renderButton = () => {
  const queryClient = createQueryClient()

  queryClient.setQueryData(sessionQueryKey, PARENT_SESSION)
  const view = render(
    <QueryClientProvider client={queryClient}>
      <SignOutButton />
    </QueryClientProvider>,
  )

  return { ...view, queryClient }
}

const control = () => screen.getByRole('button', { name: /^Sign(ing)? out/ })

beforeEach(() => {
  clearCookies()
  document.cookie = `csrftoken=${TEST_CSRF_TOKEN}`
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
  clearCookies()
})

describe('the sign-out control', () => {
  test('posts the CSRF header and clears the session on 204', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }))
    const { queryClient } = renderButton()

    expect(screen.queryByRole('alert')).toBeNull()
    fireEvent.click(control())

    await waitFor(() =>
      expect(queryClient.getQueryData(sessionQueryKey)).toEqual(
        SIGNED_OUT_SESSION,
      ),
    )
    expect(fetch).toHaveBeenCalledExactlyOnceWith('/api/v1/auth/logout/', {
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        'X-CSRFToken': TEST_CSRF_TOKEN,
      },
      method: 'POST',
      signal: undefined,
    })
    expect(screen.queryByRole('alert')).toBeNull()
  })

  test('treats a session that expired first as an ordinary sign-out', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 403 }))
    const { queryClient } = renderButton()

    fireEvent.click(control())

    await waitFor(() =>
      expect(queryClient.getQueryData(sessionQueryKey)).toEqual(
        SIGNED_OUT_SESSION,
      ),
    )
    expect(screen.queryByRole('alert')).toBeNull()
  })

  test('keeps the viewer signed in and offers one message when unreachable', async () => {
    vi.mocked(fetch).mockRejectedValue(new Error('offline'))
    const { queryClient } = renderButton()

    fireEvent.click(control())

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe(
        SIGN_OUT_FAILED_MESSAGE,
      ),
    )
    expect(queryClient.getQueryData(sessionQueryKey)).toEqual(PARENT_SESSION)
    expect(control()).toHaveProperty('disabled', false)

    // The same control retries, and a later success clears the message.
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }))
    fireEvent.click(control())

    await waitFor(() =>
      expect(queryClient.getQueryData(sessionQueryKey)).toEqual(
        SIGNED_OUT_SESSION,
      ),
    )
    expect(screen.queryByRole('alert')).toBeNull()
  })

  test('marks itself busy in flight so a second click posts nothing more', async () => {
    vi.mocked(fetch).mockReturnValue(new Promise<Response>(() => undefined))
    renderButton()

    fireEvent.click(control())

    await waitFor(() => expect(control()).toHaveProperty('disabled', true))
    expect(control().getAttribute('aria-busy')).toBe('true')
    expect(control().textContent).toBe('Signing out...')

    fireEvent.click(control())
    expect(fetch).toHaveBeenCalledOnce()
  })

  test('asks the session endpoint for a token when the cookie is missing', async () => {
    clearCookies()
    vi.mocked(fetch).mockImplementation(async (input) => {
      if (input === '/api/v1/auth/session/') {
        document.cookie = `csrftoken=${TEST_CSRF_TOKEN}`
        return new Response(JSON.stringify(PARENT_SESSION), {
          headers: { 'Content-Type': 'application/json' },
          status: 200,
        })
      }
      return new Response(null, { status: 204 })
    })
    const { queryClient } = renderButton()

    fireEvent.click(control())

    await waitFor(() =>
      expect(queryClient.getQueryData(sessionQueryKey)).toEqual(
        SIGNED_OUT_SESSION,
      ),
    )
    expect(vi.mocked(fetch).mock.calls.map((call) => call[0])).toEqual([
      '/api/v1/auth/session/',
      '/api/v1/auth/logout/',
    ])
  })

  test('writes nothing to browser storage', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }))
    renderButton()

    fireEvent.click(control())

    await waitFor(() => expect(fetch).toHaveBeenCalledOnce())
    expect(window.localStorage.length).toBe(0)
    expect(window.sessionStorage.length).toBe(0)
  })
})
