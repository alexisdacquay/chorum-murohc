import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { createQueryClient } from '../../api/query-client'
import { ChildRewardsScreen } from './child-rewards-screen'

const TEST_CSRF_TOKEN = 'test-csrf-token'

const SCREEN_TIME = { id: 1, name: 'Screen time', points: 15 }
const MOVIE_NIGHT = { id: 2, name: 'Movie night', points: 200 }

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
      <ChildRewardsScreen />
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

describe('loading and listing', () => {
  test('shows loading, then the balance and the active rewards', async () => {
    fetchSpy = respondByPath({
      '/api/v1/balance/': () => jsonResponse({ balance: 20 }),
      '/api/v1/rewards/': () => jsonResponse([SCREEN_TIME, MOVIE_NIGHT]),
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    expect(screen.getByRole('status').textContent).toContain('Loading')

    await waitFor(() =>
      expect(
        screen.getByRole('heading', { level: 2, name: 'Screen time' }),
      ).toBeDefined(),
    )
    expect(screen.getByTestId('rewards-balance').textContent).toContain('20')
    expect(screen.getByText('15 points')).toBeDefined()
    expect(screen.getByRole('heading', { level: 2, name: 'Movie night' })).toBeDefined()
  })

  test('shows the empty-catalogue copy when there are no rewards', async () => {
    fetchSpy = respondByPath({
      '/api/v1/balance/': () => jsonResponse({ balance: 0 }),
      '/api/v1/rewards/': () => jsonResponse([]),
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() =>
      expect(screen.getByText('No rewards yet. Ask a parent to add one.')).toBeDefined(),
    )
  })

  test('shows a recoverable error and can retry', async () => {
    fetchSpy = respondByPath({
      '/api/v1/balance/': () => jsonResponse({ balance: 20 }),
      '/api/v1/rewards/': () => jsonResponse({ detail: 'nope' }, 403),
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() =>
      expect(
        screen.getByText(/You do not have permission to manage rewards/),
      ).toBeDefined(),
    )
    expect(screen.getByRole('button', { name: 'Try again' })).toBeDefined()
  })
})

describe('redeeming', () => {
  test('confirming a redemption debits the balance and shows the pending state', async () => {
    let redeemed = false
    fetchSpy = respondByPath({
      '/api/v1/balance/': () => jsonResponse({ balance: redeemed ? 5 : 20 }),
      '/api/v1/rewards/': () => jsonResponse([SCREEN_TIME]),
      '/api/v1/redemptions/': () => {
        redeemed = true
        return jsonResponse(
          {
            id: 9,
            reward_name: 'Screen time',
            reward_points: 15,
            status: 'pending',
            created_at: '2026-09-01T00:00:00Z',
            decided_at: null,
          },
          201,
        )
      },
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Redeem Screen time' })).toBeDefined(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Redeem Screen time' }))

    const dialog = await screen.findByRole('dialog', { name: 'Redeem "Screen time"?' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Redeem' }))

    await waitFor(() =>
      expect(
        screen.getByText(/Requested "Screen time". A parent will hand it over soon\./),
      ).toBeDefined(),
    )
    await waitFor(() =>
      expect(screen.getByTestId('rewards-balance').textContent).toContain('5'),
    )
  })

  test('an unaffordable reward disables the confirm button with a compact explanation', async () => {
    fetchSpy = respondByPath({
      '/api/v1/balance/': () => jsonResponse({ balance: 5 }),
      '/api/v1/rewards/': () => jsonResponse([SCREEN_TIME]),
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Redeem Screen time' })).toBeDefined(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Redeem Screen time' }))

    await waitFor(() =>
      expect(screen.getByText(/which is not enough yet/)).toBeDefined(),
    )
    const confirmButton = screen.getByRole('button', {
      name: 'Redeem',
    }) as HTMLButtonElement
    expect(confirmButton.disabled).toBe(true)
  })

  test('a server-refused redemption shows its message and does not close the dialog', async () => {
    fetchSpy = respondByPath({
      '/api/v1/balance/': () => jsonResponse({ balance: 20 }),
      '/api/v1/rewards/': () => jsonResponse([SCREEN_TIME]),
      '/api/v1/redemptions/': () =>
        jsonResponse({ reward: ['Not enough points for this reward.'] }, 400),
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Redeem Screen time' })).toBeDefined(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Redeem Screen time' }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Redeem' })).toBeDefined(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Redeem' }))

    await waitFor(() =>
      expect(screen.getByText('Not enough points for this reward.')).toBeDefined(),
    )
    expect(screen.getByRole('dialog', { name: 'Redeem "Screen time"?' })).toBeDefined()
  })
})
