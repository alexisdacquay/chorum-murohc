import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { HOUSEHOLD_SWITCH_FAILED_MESSAGE, HouseholdSwitcher } from './household-switcher'
import { createQueryClient } from '../../api/query-client'
import { sessionQueryKey } from '../../api/session'

const TEST_CSRF_TOKEN = 'test-csrf-token'

const HOUSEHOLDS = [
  { id: 3, name: 'Test household', role: 'parent' },
  { id: 9, name: 'Household B', role: 'child' },
]

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

const renderSwitcher = (
  households: typeof HOUSEHOLDS,
  currentHouseholdId: number | null = 3,
) => {
  const queryClient = createQueryClient()
  const view = render(
    <QueryClientProvider client={queryClient}>
      <HouseholdSwitcher
        currentHouseholdId={currentHouseholdId}
        households={households}
      />
    </QueryClientProvider>,
  )

  return { ...view, queryClient }
}

beforeEach(() => {
  clearCookies()
  document.cookie = `csrftoken=${TEST_CSRF_TOKEN}`
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
  clearCookies()
})

describe('the household switcher', () => {
  test('renders nothing for zero or one household', () => {
    const { unmount } = renderSwitcher([])
    expect(screen.queryByLabelText('Switch household')).toBeNull()
    unmount()

    renderSwitcher([HOUSEHOLDS[0]])
    expect(screen.queryByLabelText('Switch household')).toBeNull()
  })

  test('lists every household and opens on the active one', () => {
    renderSwitcher(HOUSEHOLDS, 9)

    const select = screen.getByLabelText('Switch household')

    expect(
      within(select).getAllByRole('option').map((option) => option.textContent),
    ).toEqual(['Test household', 'Household B'])
    expect((select as HTMLSelectElement).value).toBe('9')
  })

  test('posts the selection and replaces the session on success', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({
        is_authenticated: true,
        user: { id: 7, username: 'test-parent' },
        household: { id: 9, name: 'Household B' },
        role: 'child',
      }),
    )
    const { queryClient } = renderSwitcher(HOUSEHOLDS, 3)

    fireEvent.change(screen.getByLabelText('Switch household'), {
      target: { value: '9' },
    })

    await waitFor(() =>
      expect(queryClient.getQueryData(sessionQueryKey)).toMatchObject({
        household: { id: 9, name: 'Household B' },
        role: 'child',
      }),
    )
    expect(fetch).toHaveBeenCalledExactlyOnceWith('/api/v1/auth/household/', {
      body: JSON.stringify({ household_id: 9 }),
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-CSRFToken': TEST_CSRF_TOKEN,
      },
      method: 'POST',
      signal: undefined,
    })
  })

  test('shows one failure message and stays on the previous household', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: 'Not found.' }, 404))
    const { queryClient } = renderSwitcher(HOUSEHOLDS, 3)
    queryClient.setQueryData(sessionQueryKey, {
      is_authenticated: true,
      user: { id: 7, username: 'test-parent' },
      household: { id: 3, name: 'Test household' },
      role: 'parent',
    })

    fireEvent.change(screen.getByLabelText('Switch household'), {
      target: { value: '9' },
    })

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe(
        HOUSEHOLD_SWITCH_FAILED_MESSAGE,
      ),
    )
    expect(queryClient.getQueryData(sessionQueryKey)).toMatchObject({
      household: { id: 3, name: 'Test household' },
    })
  })

  test('disables the control while a selection is in flight', async () => {
    vi.mocked(fetch).mockReturnValue(new Promise<Response>(() => undefined))
    renderSwitcher(HOUSEHOLDS, 3)

    fireEvent.change(screen.getByLabelText('Switch household'), {
      target: { value: '9' },
    })

    await waitFor(() =>
      expect(screen.getByLabelText('Switch household')).toHaveProperty('disabled', true),
    )
    expect(screen.getByLabelText('Switch household').getAttribute('aria-busy')).toBe('true')
  })
})
