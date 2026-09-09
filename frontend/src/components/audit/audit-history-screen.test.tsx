import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { createQueryClient } from '../../api/query-client'
import { AuditHistoryScreen } from './audit-history-screen'
import { CONNECTION_MESSAGE, PERMISSION_MESSAGE } from './audit-messages'

const MEMBERS = [
  { id: 2, username: 'jordan', role: 'parent', is_active: true, date_joined: '2026-01-01' },
  { id: 5, username: 'avery', role: 'child', is_active: true, date_joined: '2026-01-02' },
  {
    id: 9,
    username: 'former-child',
    role: 'child',
    is_active: false,
    date_joined: '2026-01-03',
  },
]

const EVENT_A = {
  id: 20,
  actor: 2,
  action: 'chore.create',
  target_type: 'chore',
  target_id: '4',
  created_at: '2026-09-06T12:00:00Z',
  context: { chore_name: 'Wash dishes' },
}

const EVENT_B = {
  id: 21,
  actor: null,
  action: 'interest.accrue',
  target_type: 'ledger',
  target_id: '5',
  created_at: '2026-09-05T09:00:00Z',
  context: {},
}

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })

const emptyPage = { count: 0, next: null, previous: null, results: [] }

let fetchSpy: ReturnType<typeof vi.fn>

const renderScreen = () => {
  const queryClient = createQueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      <AuditHistoryScreen />
    </QueryClientProvider>,
  )
}

/** Route every request by exact URL and method, with a table of handlers. */
const route = (handlers: Record<string, (init?: RequestInit) => Response>) =>
  vi.fn(async (input: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    const key = `${method} ${input}`
    const handler = handlers[key]
    if (handler) {
      return handler(init)
    }
    if (input.startsWith('/api/v1/household-members/')) {
      return jsonResponse(MEMBERS)
    }
    if (input.startsWith('/api/v1/audit/')) {
      return jsonResponse(emptyPage)
    }
    return jsonResponse({}, 404)
  })

beforeEach(() => {
  fetchSpy = vi.fn()
  vi.stubGlobal('fetch', fetchSpy)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('loading, empty and success', () => {
  test('shows loading, then no matching activity', async () => {
    fetchSpy.mockImplementation(route({}))
    renderScreen()

    expect(screen.getByRole('status').textContent).toContain('Loading')

    await waitFor(() => expect(screen.getByText('No matching activity yet.')).toBeDefined())
  })

  test('renders each event with its actor, action, target and context', async () => {
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/audit/?page=1': () =>
          jsonResponse({ count: 2, next: null, previous: null, results: [EVENT_A, EVENT_B] }),
      }),
    )
    renderScreen()

    await waitFor(() => expect(screen.getByText('Chore Create')).toBeDefined())
    expect(screen.getByText('Chore #4')).toBeDefined()
    expect(screen.getByText('chore_name')).toBeDefined()
    expect(screen.getByText('Wash dishes')).toBeDefined()
    expect(screen.getByText(/jordan -/)).toBeDefined()

    // A system-recorded event (no human actor) reads as automatic, not blank.
    expect(screen.getByText('Interest Accrue')).toBeDefined()
    expect(screen.getByText(/Chorum-murohc \(automatic\)/)).toBeDefined()
  })

  test('an actor no longer in the directory still renders safely', async () => {
    const orphaned = { ...EVENT_A, actor: 404 }
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/audit/?page=1': () =>
          jsonResponse({ count: 1, next: null, previous: null, results: [orphaned] }),
      }),
    )
    renderScreen()

    await waitFor(() => expect(screen.getByText(/Member #404/)).toBeDefined())
  })

  test('a redacted context value passes through exactly as the server sent it', async () => {
    const withSecret = { ...EVENT_A, context: { password: '[REDACTED]' } }
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/audit/?page=1': () =>
          jsonResponse({ count: 1, next: null, previous: null, results: [withSecret] }),
      }),
    )
    renderScreen()

    await waitFor(() => expect(screen.getByText('[REDACTED]')).toBeDefined())
  })
})

describe('no edit or delete controls', () => {
  test('the only buttons are apply, clear and pagination', async () => {
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/audit/?page=1': () =>
          jsonResponse({ count: 1, next: null, previous: null, results: [EVENT_A] }),
      }),
    )
    renderScreen()

    await waitFor(() => expect(screen.getByText('Chore Create')).toBeDefined())

    const buttonNames = screen.getAllByRole('button').map((button) => button.textContent)
    expect(buttonNames).toEqual(
      expect.arrayContaining(['Apply filters', 'Clear filters']),
    )
    for (const name of buttonNames) {
      expect(name).not.toMatch(/edit/i)
      expect(name).not.toMatch(/delete/i)
      expect(name).not.toMatch(/remove/i)
    }
  })
})

describe('filtering', () => {
  test('applying a filter re-queries with the exact field values, from page one', async () => {
    fetchSpy.mockImplementation(route({}))
    renderScreen()

    await waitFor(() => expect(screen.getByText('No matching activity yet.')).toBeDefined())
    fetchSpy.mockClear()

    fireEvent.change(screen.getByLabelText('Who'), { target: { value: '5' } })
    fireEvent.change(screen.getByLabelText('Action'), {
      target: { value: 'chore.create' },
    })
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-09-01' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }))

    await waitFor(() => expect(fetchSpy).toHaveBeenCalled())
    const auditUrl = fetchSpy.mock.calls
      .map((call) => String(call[0]))
      .find((input) => input.startsWith('/api/v1/audit/'))
    const params = new URLSearchParams(auditUrl?.split('?')[1])
    expect(params.get('page')).toBe('1')
    expect(params.get('actor')).toBe('5')
    expect(params.get('action')).toBe('chore.create')
    expect(params.get('date_from')).toBe('2026-09-01')
  })

  test('clearing filters returns to the unfiltered first page', async () => {
    fetchSpy.mockImplementation(route({}))
    renderScreen()

    await waitFor(() => expect(screen.getByText('No matching activity yet.')).toBeDefined())
    fireEvent.change(screen.getByLabelText('Action'), { target: { value: 'chore.create' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }))
    fetchSpy.mockClear()

    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }))

    await waitFor(() => expect(fetchSpy).toHaveBeenCalled())
    const auditUrl = fetchSpy.mock.calls
      .map((call) => String(call[0]))
      .find((input) => input.startsWith('/api/v1/audit/'))
    expect(auditUrl).toBe('/api/v1/audit/?page=1')
    expect((screen.getByLabelText('Action') as HTMLInputElement).value).toBe('')
  })

  test('a bad date range shows the field message next to the field, not as a generic failure', async () => {
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/audit/?page=1&date_from=2026-09-10&date_to=2026-09-01': () =>
          jsonResponse(
            { date_to: ['date_from must not be later than date_to.'] },
            400,
          ),
      }),
    )
    renderScreen()

    await waitFor(() => expect(screen.getByText('No matching activity yet.')).toBeDefined())
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-09-10' } })
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-09-01' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply filters' }))

    await waitFor(() =>
      expect(
        screen.getByText('date_from must not be later than date_to.'),
      ).toBeDefined(),
    )
    expect(screen.queryByText(CONNECTION_MESSAGE)).toBeNull()
  })
})

describe('pagination', () => {
  test('next and previous page controls are real, focusable buttons', async () => {
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/audit/?page=1': () =>
          jsonResponse({
            count: 2,
            next: 'http://testserver/api/v1/audit/?page=2',
            previous: null,
            results: [EVENT_A],
          }),
        'GET /api/v1/audit/?page=2': () =>
          jsonResponse({
            count: 2,
            next: null,
            previous: 'http://testserver/api/v1/audit/?page=1',
            results: [EVENT_B],
          }),
      }),
    )
    renderScreen()

    const nextButton = await screen.findByRole('button', { name: 'Next page' })
    expect(nextButton.tagName).toBe('BUTTON')
    nextButton.focus()
    expect(document.activeElement).toBe(nextButton)
    fireEvent.click(nextButton)

    await waitFor(() => expect(screen.getByText('Interest Accrue')).toBeDefined())
    const previousButton = screen.getByRole('button', { name: 'Previous page' })
    expect(previousButton.hasAttribute('disabled')).toBe(false)
  })
})

describe('error and retry', () => {
  test('a forbidden caller sees the permission sentence', async () => {
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/audit/?page=1': () => jsonResponse({ detail: 'denied' }, 403),
      }),
    )
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe(PERMISSION_MESSAGE),
    )
  })

  test('an unreachable request shows the connection sentence with a working retry', async () => {
    let attempts = 0
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/audit/?page=1': () => {
          attempts += 1
          if (attempts === 1) {
            throw new Error('offline')
          }
          return jsonResponse(emptyPage)
        },
      }),
    )
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe(CONNECTION_MESSAGE),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))

    await waitFor(() => expect(screen.getByText('No matching activity yet.')).toBeDefined())
  })
})
