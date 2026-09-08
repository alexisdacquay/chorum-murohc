import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { createQueryClient } from '../../api/query-client'
import { ParentRewardsScreen } from './parent-rewards-screen'

const TEST_CSRF_TOKEN = 'test-csrf-token'

const PENDING_REDEMPTION = {
  id: 9,
  child_id: 3,
  child_username: 'kid',
  reward_name: 'Screen time',
  reward_points: 15,
  status: 'pending' as const,
  created_at: '2026-09-01T00:00:00Z',
  decided_at: null,
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
      <ParentRewardsScreen />
    </QueryClientProvider>,
  )
}

const respondByPath = (routes: Record<string, () => Response>) =>
  vi.fn((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()
    for (const [prefix, build] of Object.entries(routes)) {
      if (url.startsWith(prefix)) {
        return Promise.resolve(build())
      }
    }
    return Promise.resolve(jsonResponse({}, 404))
  })

beforeEach(() => {
  clearCookies()
  document.cookie = `csrftoken=${TEST_CSRF_TOKEN}`
})

afterEach(() => {
  vi.unstubAllGlobals()
  clearCookies()
})

describe('the request queue', () => {
  test('shows a pending request and the empty catalogue side by side', async () => {
    fetchSpy = respondByPath({
      '/api/v1/redemptions/': () => jsonResponse([PENDING_REDEMPTION]),
      '/api/v1/rewards/': () => jsonResponse([]),
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 3, name: 'Screen time' })).toBeDefined(),
    )
    expect(screen.getByText(/kid - 15 points - Pending/)).toBeDefined()
    await waitFor(() =>
      expect(screen.getByText('No active rewards. Add one, or show inactive rewards to see what is hidden.')).toBeDefined(),
    )
  })

  test('shows the empty-queue copy when nothing is pending', async () => {
    fetchSpy = respondByPath({
      '/api/v1/redemptions/': () => jsonResponse([]),
      '/api/v1/rewards/': () => jsonResponse([]),
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() =>
      expect(screen.getByText('No reward requests yet.')).toBeDefined(),
    )
  })

  test('fulfilling a request marks it fulfilled and removes its buttons', async () => {
    let status: 'pending' | 'fulfilled' = 'pending'
    fetchSpy = respondByPath({
      '/api/v1/redemptions/9/fulfil/': () => {
        status = 'fulfilled'
        return jsonResponse({ ...PENDING_REDEMPTION, status, decided_at: '2026-09-02T00:00:00Z' })
      },
      '/api/v1/redemptions/': () =>
        jsonResponse([{ ...PENDING_REDEMPTION, status }]),
      '/api/v1/rewards/': () => jsonResponse([]),
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Fulfil Screen time for kid' }),
      ).toBeDefined(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Fulfil Screen time for kid' }))

    await waitFor(() => expect(screen.getByText(/Fulfilled/)).toBeDefined())
    expect(
      screen.queryByRole('button', { name: 'Fulfil Screen time for kid' }),
    ).toBeNull()
  })

  test('cancelling a request refunds it and shows a recoverable error on failure', async () => {
    fetchSpy = respondByPath({
      '/api/v1/redemptions/9/cancel/': () => jsonResponse({ detail: 'nope' }, 404),
      '/api/v1/redemptions/': () => jsonResponse([PENDING_REDEMPTION]),
      '/api/v1/rewards/': () => jsonResponse([]),
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Cancel Screen time for kid' }),
      ).toBeDefined(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Cancel Screen time for kid' }))

    await waitFor(() =>
      expect(
        screen.getByText(/That request could not be found/),
      ).toBeDefined(),
    )
  })
})

describe('the catalogue', () => {
  test('adds a reward through the form dialog', async () => {
    let created = false
    fetchSpy = respondByPath({
      '/api/v1/redemptions/': () => jsonResponse([]),
      '/api/v1/rewards/': () =>
        jsonResponse(created ? [{ id: 1, name: 'Movie night', points: 200, is_active: true, created_at: 'x', updated_at: 'x' }] : []),
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() =>
      expect(screen.getByText('No active rewards. Add one, or show inactive rewards to see what is hidden.')).toBeDefined(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Add reward' }))

    const dialog = await screen.findByRole('dialog', { name: 'Add reward' })
    fireEvent.change(within(dialog).getByLabelText('Name'), {
      target: { value: 'Movie night' },
    })
    fireEvent.change(within(dialog).getByLabelText('Points'), {
      target: { value: '200' },
    })
    fetchSpy.mockImplementationOnce((_input: RequestInfo | URL, init?: RequestInit) => {
      created = true
      expect(init?.method).toBe('POST')
      return Promise.resolve(
        jsonResponse(
          { id: 1, name: 'Movie night', points: 200, is_active: true, created_at: 'x', updated_at: 'x' },
          201,
        ),
      )
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add reward' }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 3, name: 'Movie night' })).toBeDefined(),
    )
  })
})
