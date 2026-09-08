import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { createQueryClient } from '../../api/query-client'
import { ChorePoolScreen } from './chore-pool-screen'
import {
  NAME_REQUIRED_MESSAGE,
  POINTS_REQUIRED_MESSAGE,
} from './chore-form-dialog'
import {
  NOT_FOUND_MESSAGE,
  PERMISSION_MESSAGE,
} from './chore-messages'

const TEST_CSRF_TOKEN = 'test-csrf-token'

const CHORE_A = {
  id: 1,
  name: 'Wash dishes',
  points: 10,
  is_active: true,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
}
const CHORE_B = {
  id: 2,
  name: 'Sweep porch',
  points: 5,
  is_active: false,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-01T00:00:00Z',
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

let fetchSpy: ReturnType<typeof vi.fn>

const renderScreen = () => {
  const queryClient = createQueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      <ChorePoolScreen />
    </QueryClientProvider>,
  )
}

const listCalls = () =>
  fetchSpy.mock.calls.filter(
    (call) => typeof call[0] === 'string' && call[0].startsWith('/api/v1/chores/'),
  )

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

describe('loading the pool', () => {
  test('shows loading, then the active-only list with points and no state label', async () => {
    fetchSpy.mockResolvedValue(jsonResponse([CHORE_A]))
    renderScreen()

    expect(screen.getByRole('status').textContent).toContain('Loading')

    await waitFor(() =>
      expect(
        screen.getByRole('heading', { level: 2, name: 'Wash dishes' }),
      ).toBeDefined(),
    )
    expect(screen.getByText('10 points')).toBeDefined()
    expect(screen.queryByText(/Inactive/)).toBeNull()
    expect(fetchSpy).toHaveBeenCalledWith('/api/v1/chores/', expect.anything())
  })

  test('shows an empty-state sentence instead of an empty list', async () => {
    fetchSpy.mockResolvedValue(jsonResponse([]))
    renderScreen()

    await waitFor(() =>
      expect(screen.getByText(/No active chores/)).toBeDefined(),
    )
    expect(screen.queryByRole('list')).toBeNull()
  })

  test('the inactive toggle refetches both states and labels the inactive one', async () => {
    fetchSpy.mockImplementation(async (input: string) =>
      input.includes('include_inactive=true')
        ? jsonResponse([CHORE_A, CHORE_B])
        : jsonResponse([CHORE_A]),
    )
    renderScreen()

    await waitFor(() => expect(screen.getByText('Wash dishes')).toBeDefined())
    fireEvent.click(screen.getByRole('checkbox', { name: 'Show inactive chores' }))

    await waitFor(() => expect(screen.getByText('Sweep porch')).toBeDefined())
    expect(screen.getByText('5 points - Inactive')).toBeDefined()
    expect(
      fetchSpy.mock.calls.some(
        (call) => call[0] === '/api/v1/chores/?include_inactive=true',
      ),
    ).toBe(true)
  })

  test('offers a working retry when the list request fails', async () => {
    fetchSpy.mockRejectedValueOnce(new Error('offline'))
    fetchSpy.mockResolvedValue(jsonResponse([CHORE_A]))
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toContain(
        'We could not reach Chorum-murohc',
      ),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))

    await waitFor(() => expect(screen.getByText('Wash dishes')).toBeDefined())
  })

  test('shows the fixed permission sentence for a 403, never server text', async () => {
    fetchSpy.mockResolvedValue(jsonResponse({ detail: 'nope' }, 403))
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe(PERMISSION_MESSAGE),
    )
    expect(document.body.textContent).not.toContain('nope')
  })
})

describe('adding a chore', () => {
  test('refuses an empty submission locally, with no request sent', async () => {
    fetchSpy.mockResolvedValue(jsonResponse([]))
    renderScreen()

    await waitFor(() => expect(screen.getByText(/No active chores/)).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Add chore' }))

    const dialog = await screen.findByRole('dialog', { name: 'Add chore' })
    const postCallsBefore = listCalls().filter((call) => call[1]?.method === 'POST')
      .length

    fireEvent.click(within(dialog).getByRole('button', { name: 'Add chore' }))

    expect(within(dialog).getByText(NAME_REQUIRED_MESSAGE)).toBeDefined()
    expect(within(dialog).getByText(POINTS_REQUIRED_MESSAGE)).toBeDefined()
    expect(document.activeElement).toBe(within(dialog).getByLabelText('Name'))
    expect(
      listCalls().filter((call) => call[1]?.method === 'POST').length,
    ).toBe(postCallsBefore)
  })

  test('creates a chore and shows it in the refreshed list', async () => {
    fetchSpy.mockImplementation(async (input: string, init?: RequestInit) => {
      if (input === '/api/v1/chores/' && init?.method === 'POST') {
        return jsonResponse({ ...CHORE_A, id: 9, name: 'Feed cat', points: 3 }, 201)
      }
      if (input === '/api/v1/chores/') {
        const priorGets = fetchSpy.mock.calls.filter(
          (call) => call[0] === '/api/v1/chores/' && call[1]?.method === 'GET',
        ).length
        return jsonResponse(
          priorGets <= 1 ? [] : [{ ...CHORE_A, id: 9, name: 'Feed cat', points: 3 }],
        )
      }
      return jsonResponse({}, 404)
    })
    renderScreen()

    await waitFor(() => expect(screen.getByText(/No active chores/)).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Add chore' }))
    const dialog = await screen.findByRole('dialog', { name: 'Add chore' })

    fireEvent.change(within(dialog).getByLabelText('Name'), {
      target: { value: 'Feed cat' },
    })
    fireEvent.change(within(dialog).getByLabelText('Points'), {
      target: { value: '3' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add chore' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(screen.getByText('Feed cat')).toBeDefined())

    const [, postInit] = fetchSpy.mock.calls.find(
      (call) => call[0] === '/api/v1/chores/' && call[1]?.method === 'POST',
    )!
    expect(JSON.parse(postInit.body as string)).toEqual({
      name: 'Feed cat',
      points: 3,
    })
    expect(postInit.headers['X-CSRFToken']).toBe(TEST_CSRF_TOKEN)
  })

  test('shows the server duplicate-name message on its own field, dialog stays open', async () => {
    fetchSpy.mockImplementation(async (input: string, init?: RequestInit) => {
      if (input === '/api/v1/chores/' && init?.method === 'POST') {
        return jsonResponse(
          { name: ['A chore with this name already exists in this household.'] },
          400,
        )
      }
      return jsonResponse([CHORE_A])
    })
    renderScreen()

    await waitFor(() => expect(screen.getByText('Wash dishes')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Add chore' }))
    const dialog = await screen.findByRole('dialog', { name: 'Add chore' })

    fireEvent.change(within(dialog).getByLabelText('Name'), {
      target: { value: 'Wash dishes' },
    })
    fireEvent.change(within(dialog).getByLabelText('Points'), {
      target: { value: '4' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add chore' }))

    await waitFor(() =>
      expect(
        within(dialog).getByText(
          'A chore with this name already exists in this household.',
        ),
      ).toBeDefined(),
    )
    expect(screen.getByRole('dialog')).toBeDefined()
  })

  test('Escape closes the dialog and sends no request', async () => {
    fetchSpy.mockResolvedValue(jsonResponse([CHORE_A]))
    renderScreen()

    await waitFor(() => expect(screen.getByText('Wash dishes')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Add chore' }))
    await screen.findByRole('dialog', { name: 'Add chore' })

    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())

    expect(
      fetchSpy.mock.calls.some((call) => call[1]?.method === 'POST'),
    ).toBe(false)

    // Reopening starts from a clean form, not the closed attempt's values.
    fireEvent.click(screen.getByRole('button', { name: 'Add chore' }))
    const dialog = await screen.findByRole('dialog', { name: 'Add chore' })
    expect(within(dialog).getByLabelText('Name')).toHaveProperty('value', '')
  })
})

describe('editing a chore', () => {
  test('prefills the form and saves the change', async () => {
    fetchSpy.mockImplementation(async (input: string, init?: RequestInit) => {
      if (input === '/api/v1/chores/1/' && init?.method === 'PATCH') {
        return jsonResponse({ ...CHORE_A, points: 15 })
      }
      return jsonResponse([CHORE_A])
    })
    renderScreen()

    await waitFor(() => expect(screen.getByText('Wash dishes')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Edit Wash dishes' }))

    const dialog = await screen.findByRole('dialog', { name: 'Edit chore' })
    expect(within(dialog).getByLabelText('Name')).toHaveProperty(
      'value',
      'Wash dishes',
    )
    expect(within(dialog).getByLabelText('Points')).toHaveProperty('value', '10')

    fireEvent.change(within(dialog).getByLabelText('Points'), {
      target: { value: '15' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    const [, patchInit] = fetchSpy.mock.calls.find(
      (call) => call[0] === '/api/v1/chores/1/' && call[1]?.method === 'PATCH',
    )!
    expect(JSON.parse(patchInit.body as string)).toEqual({
      name: 'Wash dishes',
      points: 15,
    })
  })

  test('a chore removed by someone else shows one recoverable notice', async () => {
    fetchSpy.mockImplementation(async (input: string, init?: RequestInit) => {
      if (input === '/api/v1/chores/1/' && init?.method === 'PATCH') {
        return jsonResponse({}, 404)
      }
      return jsonResponse([CHORE_A])
    })
    renderScreen()

    await waitFor(() => expect(screen.getByText('Wash dishes')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Edit Wash dishes' }))
    const dialog = await screen.findByRole('dialog', { name: 'Edit chore' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(within(dialog).getByText(NOT_FOUND_MESSAGE)).toBeDefined(),
    )
  })
})

describe('deactivating and reactivating', () => {
  test('one click each way, no confirmation', async () => {
    fetchSpy.mockImplementation(async (input: string, init?: RequestInit) => {
      if (input === '/api/v1/chores/1/deactivate/' && init?.method === 'POST') {
        return jsonResponse({ ...CHORE_A, is_active: false })
      }
      return jsonResponse([CHORE_A])
    })
    renderScreen()

    await waitFor(() => expect(screen.getByText('Wash dishes')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Deactivate Wash dishes' }))

    await waitFor(() =>
      expect(
        fetchSpy.mock.calls.some(
          (call) => call[0] === '/api/v1/chores/1/deactivate/',
        ),
      ).toBe(true),
    )
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})

describe('deleting a chore', () => {
  test('cancel sends no request and keeps the chore', async () => {
    fetchSpy.mockResolvedValue(jsonResponse([CHORE_A]))
    renderScreen()

    await waitFor(() => expect(screen.getByText('Wash dishes')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Delete Wash dishes' }))
    const dialog = await screen.findByRole('dialog')
    expect(dialog.textContent).toContain('cannot be undone')

    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(
      fetchSpy.mock.calls.some((call) => call[1]?.method === 'DELETE'),
    ).toBe(false)
    expect(screen.getByText('Wash dishes')).toBeDefined()
  })

  test('confirming removes the chore from the list', async () => {
    fetchSpy.mockImplementation(async (input: string, init?: RequestInit) => {
      if (input === '/api/v1/chores/1/' && init?.method === 'DELETE') {
        return new Response(null, { status: 204 })
      }
      const stillThere = !fetchSpy.mock.calls.some(
        (call) => call[0] === '/api/v1/chores/1/' && call[1]?.method === 'DELETE',
      )
      return jsonResponse(stillThere ? [CHORE_A] : [])
    })
    renderScreen()

    await waitFor(() => expect(screen.getByText('Wash dishes')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Delete Wash dishes' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete chore' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(screen.queryByText('Wash dishes')).toBeNull())
  })
})
