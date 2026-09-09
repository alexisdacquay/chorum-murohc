import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { createQueryClient } from '../../api/query-client'
import { PointsDashboardScreen } from './points-dashboard-screen'
import { CONNECTION_MESSAGE, PERMISSION_MESSAGE } from './points-messages'

const ENTRY_A = {
  id: 3,
  amount: 25,
  reason: 'chore_credit',
  reason_label: 'Chore credit',
  created_at: '2026-09-06T12:00:00Z',
}
const ENTRY_B = {
  id: 2,
  amount: -10,
  reason: 'reward_debit',
  reason_label: 'Reward debit',
  created_at: '2026-09-05T09:30:00Z',
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
      <PointsDashboardScreen />
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
    if (input === '/api/v1/balance/') {
      return jsonResponse({ balance: 0 })
    }
    if (input.startsWith('/api/v1/ledger/')) {
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

describe('loading and the balance card', () => {
  test('shows loading, then a positive balance and an empty history', async () => {
    fetchSpy.mockImplementation(
      route({ 'GET /api/v1/balance/': () => jsonResponse({ balance: 125 }) }),
    )
    renderScreen()

    expect(screen.getByRole('status').textContent).toContain('Loading your points')

    await waitFor(() =>
      expect(screen.getByTestId('points-balance-figure').textContent).toBe(
        '125 points',
      ),
    )
    await waitFor(() =>
      expect(screen.getByText(/No points activity yet/)).toBeDefined(),
    )
  })

  test('a zero balance reads as zero, not blank or missing', async () => {
    fetchSpy.mockImplementation(
      route({ 'GET /api/v1/balance/': () => jsonResponse({ balance: 0 }) }),
    )
    renderScreen()

    await waitFor(() =>
      expect(screen.getByTestId('points-balance-figure').textContent).toBe(
        '0 points',
      ),
    )
  })

  test('a negative balance is shown as-is, with the singular for exactly one point', async () => {
    fetchSpy.mockImplementation(
      route({ 'GET /api/v1/balance/': () => jsonResponse({ balance: -1 }) }),
    )
    renderScreen()

    await waitFor(() =>
      expect(screen.getByTestId('points-balance-figure').textContent).toBe(
        '-1 point',
      ),
    )
  })

  test('a negative balance below one point uses the plural', async () => {
    fetchSpy.mockImplementation(
      route({ 'GET /api/v1/balance/': () => jsonResponse({ balance: -5 }) }),
    )
    renderScreen()

    await waitFor(() =>
      expect(screen.getByTestId('points-balance-figure').textContent).toBe(
        '-5 points',
      ),
    )
  })

  test('a balance-read failure shows the fixed connection sentence with a working retry', async () => {
    let attempts = 0
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/balance/': () => {
          attempts += 1
          if (attempts === 1) {
            throw new Error('offline')
          }
          return jsonResponse({ balance: 40 })
        },
      }),
    )
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe(CONNECTION_MESSAGE),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))

    await waitFor(() =>
      expect(screen.getByTestId('points-balance-figure').textContent).toBe(
        '40 points',
      ),
    )
  })

  test('a 403 on the balance read shows the fixed permission sentence, never server text', async () => {
    fetchSpy.mockImplementation(
      route({ 'GET /api/v1/balance/': () => jsonResponse({ detail: 'nope' }, 403) }),
    )
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe(PERMISSION_MESSAGE),
    )
    expect(document.body.textContent).not.toContain('nope')
  })
})

describe('the history list', () => {
  test('renders each entry with its reason label and a signed amount', async () => {
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/balance/': () => jsonResponse({ balance: 15 }),
        'GET /api/v1/ledger/?page=1': () =>
          jsonResponse({ count: 2, next: null, previous: null, results: [ENTRY_A, ENTRY_B] }),
      }),
    )
    renderScreen()

    await waitFor(() => expect(screen.getByText('Chore credit')).toBeDefined())
    expect(screen.getByText('+25')).toBeDefined()
    expect(screen.getByText('Reward debit')).toBeDefined()
    expect(screen.getByText('-10')).toBeDefined()
  })

  test('a history read failure shows a retry that does not disturb the balance card', async () => {
    let attempts = 0
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/balance/': () => jsonResponse({ balance: 15 }),
        'GET /api/v1/ledger/?page=1': () => {
          attempts += 1
          if (attempts === 1) {
            throw new Error('offline')
          }
          return jsonResponse({
            count: 1,
            next: null,
            previous: null,
            results: [ENTRY_A],
          })
        },
      }),
    )
    renderScreen()

    await waitFor(() =>
      expect(screen.getByTestId('points-balance-figure').textContent).toBe(
        '15 points',
      ),
    )
    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe(CONNECTION_MESSAGE),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))

    await waitFor(() => expect(screen.getByText('Chore credit')).toBeDefined())
    // The balance figure was never removed while the history retried.
    expect(screen.getByTestId('points-balance-figure').textContent).toBe(
      '15 points',
    )
  })

  test('a 403 on the history read shows the fixed permission sentence', async () => {
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/balance/': () => jsonResponse({ balance: 15 }),
        'GET /api/v1/ledger/?page=1': () => jsonResponse({ detail: 'nope' }, 403),
      }),
    )
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe(PERMISSION_MESSAGE),
    )
  })
})

describe('pagination', () => {
  const pageOne = {
    count: 30,
    next: 'http://testserver/api/v1/ledger/?page=2',
    previous: null,
    results: [ENTRY_A],
  }
  const pageTwo = {
    count: 30,
    next: null,
    previous: 'http://testserver/api/v1/ledger/?page=1',
    results: [ENTRY_B],
  }

  test('previous is disabled on the first page, next moves forward and back', async () => {
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/balance/': () => jsonResponse({ balance: 15 }),
        'GET /api/v1/ledger/?page=1': () => jsonResponse(pageOne),
        'GET /api/v1/ledger/?page=2': () => jsonResponse(pageTwo),
      }),
    )
    renderScreen()

    await waitFor(() => expect(screen.getByText('Chore credit')).toBeDefined())
    const previousButton = screen.getByRole('button', { name: 'Previous page' })
    const nextButton = screen.getByRole('button', { name: 'Next page' })
    expect(previousButton.hasAttribute('disabled')).toBe(true)
    expect(nextButton.hasAttribute('disabled')).toBe(false)

    fireEvent.click(nextButton)

    await waitFor(() => expect(screen.getByText('Reward debit')).toBeDefined())
    expect(screen.getByText('Page 2')).toBeDefined()
    expect(screen.getByRole('button', { name: 'Next page' }).hasAttribute('disabled')).toBe(
      true,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Previous page' }))

    await waitFor(() => expect(screen.getByText('Chore credit')).toBeDefined())
    expect(screen.getByText('Page 1')).toBeDefined()
  })

  test('an invalid page (404) offers a control back to page 1, which then loads', async () => {
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/balance/': () => jsonResponse({ balance: 15 }),
        'GET /api/v1/ledger/?page=1': () => jsonResponse(pageOne),
        'GET /api/v1/ledger/?page=2': () => jsonResponse({ detail: 'Invalid page.' }, 404),
      }),
    )
    renderScreen()

    await waitFor(() => expect(screen.getByText('Chore credit')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))

    const retry = await screen.findByRole('button', { name: 'Go to page 1' })
    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe(CONNECTION_MESSAGE),
    )

    fireEvent.click(retry)

    await waitFor(() => expect(screen.getByText('Chore credit')).toBeDefined())
    expect(screen.getByText('Page 1')).toBeDefined()
  })
})

describe('keyboard operation', () => {
  test('pagination controls are real, focusable buttons that a click reaches', async () => {
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/balance/': () => jsonResponse({ balance: 15 }),
        'GET /api/v1/ledger/?page=1': () =>
          jsonResponse({
            count: 30,
            next: 'http://testserver/api/v1/ledger/?page=2',
            previous: null,
            results: [ENTRY_A],
          }),
        'GET /api/v1/ledger/?page=2': () =>
          jsonResponse({
            count: 30,
            next: null,
            previous: 'http://testserver/api/v1/ledger/?page=1',
            results: [ENTRY_B],
          }),
      }),
    )
    renderScreen()

    const nextButton = await screen.findByRole('button', { name: 'Next page' })
    expect(nextButton.tagName).toBe('BUTTON')
    nextButton.focus()
    expect(document.activeElement).toBe(nextButton)
    fireEvent.click(nextButton)

    await waitFor(() => expect(screen.getByText('Reward debit')).toBeDefined())

    const previousButton = screen.getByRole('button', { name: 'Previous page' })
    expect(previousButton.tagName).toBe('BUTTON')
    expect(previousButton.hasAttribute('disabled')).toBe(false)
  })
})
