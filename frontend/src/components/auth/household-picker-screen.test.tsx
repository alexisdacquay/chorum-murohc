import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { HOUSEHOLD_SWITCH_FAILED_MESSAGE } from './household-switcher'
import { HouseholdPickerScreen } from './household-picker-screen'
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

const renderPicker = () => {
  const queryClient = createQueryClient()
  const view = render(
    <QueryClientProvider client={queryClient}>
      <HouseholdPickerScreen households={HOUSEHOLDS} />
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

describe('the household picker screen', () => {
  test('lists one button per household, in the order given', () => {
    renderPicker()

    expect(screen.getByRole('heading', { name: 'Choose a household' })).toBeDefined()
    expect(
      screen.getAllByRole('button').map((button) => button.textContent),
    ).toEqual(['Test household', 'Household B'])
  })

  test('selecting a household posts its id and replaces the session', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({
        is_authenticated: true,
        user: { id: 7, username: 'test-parent' },
        household: { id: 9, name: 'Household B' },
        role: 'child',
      }),
    )
    const { queryClient } = renderPicker()

    fireEvent.click(screen.getByRole('button', { name: 'Household B' }))

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

  test('shows one failure message and leaves every button usable again', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: 'Not found.' }, 404))
    renderPicker()

    fireEvent.click(screen.getByRole('button', { name: 'Test household' }))

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe(
        HOUSEHOLD_SWITCH_FAILED_MESSAGE,
      ),
    )
    for (const button of screen.getAllByRole('button')) {
      expect(button).toHaveProperty('disabled', false)
    }
  })

  test('marks every button busy while a selection is in flight', async () => {
    vi.mocked(fetch).mockReturnValue(new Promise<Response>(() => undefined))
    renderPicker()

    fireEvent.click(screen.getByRole('button', { name: 'Test household' }))

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Test household' }),
      ).toHaveProperty('disabled', true),
    )
    expect(
      screen.getByRole('button', { name: 'Household B' }),
    ).toHaveProperty('disabled', true)
  })
})
