import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { createQueryClient } from '../../api/query-client'
import { ParentOverviewScreen } from './parent-overview-screen'
import { CONNECTION_MESSAGE, PERMISSION_MESSAGE } from './overview-messages'

const CHILD_A = {
  id: 5,
  username: 'avery',
  balance: 120,
  level: 3,
  max_level: 10,
  creature_line: 'Dragon',
  creature_form: 'Fledgling',
  pending_count: 2,
}

const CHILD_B = {
  id: 6,
  username: 'bailey',
  balance: 0,
  level: 0,
  max_level: 10,
  creature_line: null,
  creature_form: null,
  pending_count: 0,
}

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })

let fetchSpy: ReturnType<typeof vi.fn>

const renderScreen = () => {
  const queryClient = createQueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      <ParentOverviewScreen />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  fetchSpy = vi.fn()
  vi.stubGlobal('fetch', fetchSpy)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('loading and success', () => {
  test('shows loading, then an empty household', async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse({ children: [], parents: [{ id: 2, username: 'jordan' }], pending_total: 0 }),
    )
    renderScreen()

    expect(screen.getByRole('status').textContent).toContain('Loading')

    await waitFor(() =>
      expect(screen.getByText(/No children in this household yet/)).toBeDefined(),
    )
    expect(screen.getByText('Nothing pending')).toBeDefined()
    expect(screen.getByText(/jordan/)).toBeDefined()
  })

  test('renders each child balance, level, creature and pending state', async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse({
        children: [CHILD_A, CHILD_B],
        parents: [{ id: 2, username: 'jordan' }],
        pending_total: 2,
      }),
    )
    renderScreen()

    await waitFor(() => expect(screen.getByText('avery')).toBeDefined())

    const averyCard = screen.getByText('avery').closest('li') as HTMLElement
    expect(within(averyCard).getByText('120 points')).toBeDefined()
    expect(within(averyCard).getByText('3 of 10')).toBeDefined()
    expect(within(averyCard).getByText('Fledgling')).toBeDefined()
    expect(within(averyCard).getByText('2 pending decisions')).toBeDefined()

    // A child with no activity yet reads as its true zero and empty state,
    // not blank or hidden - the "partial data" case.
    const baileyCard = screen.getByText('bailey').closest('li') as HTMLElement
    expect(within(baileyCard).getByText('0 points')).toBeDefined()
    expect(within(baileyCard).getByText('0 of 10')).toBeDefined()
    expect(within(baileyCard).getByText('No creature chosen yet')).toBeDefined()
  })

  test('a household pending total is shown at the top', async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse({ children: [CHILD_A], parents: [], pending_total: 2 }),
    )
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('status').textContent).toBe('2 pending decisions'),
    )
  })
})

describe('error and retry', () => {
  test('a forbidden caller sees the permission sentence', async () => {
    fetchSpy.mockResolvedValue(jsonResponse({ detail: 'denied' }, 403))
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe(PERMISSION_MESSAGE),
    )
  })

  test('an unreachable request shows the connection sentence, with a working retry', async () => {
    let attempts = 0
    fetchSpy.mockImplementation(async () => {
      attempts += 1
      if (attempts === 1) {
        throw new Error('offline')
      }
      return jsonResponse({ children: [], parents: [], pending_total: 0 })
    })
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe(CONNECTION_MESSAGE),
    )

    const retryButton = screen.getByRole('button', { name: 'Try again' })
    expect(retryButton.tagName).toBe('BUTTON')
    fireEvent.click(retryButton)

    await waitFor(() =>
      expect(screen.getByText(/No children in this household yet/)).toBeDefined(),
    )
  })
})

describe('quick links to existing management screens', () => {
  test('links to approvals, chores, rewards, household and activity, distinct from the nav', async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse({ children: [], parents: [], pending_total: 0 }),
    )
    renderScreen()

    await waitFor(() =>
      expect(screen.getByText(/No children in this household yet/)).toBeDefined(),
    )

    for (const [name, href] of [
      ['Review approvals', '/approvals'],
      ['Manage chores', '/chore-pool'],
      ['Manage rewards', '/reward-requests'],
      ['Manage household', '/household'],
      ['View activity', '/activity'],
    ] as const) {
      const link = screen.getByRole('link', { name })
      expect(link.getAttribute('href')).toBe(href)
    }
  })

  test('a child with pending work links straight to approvals', async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse({ children: [CHILD_A], parents: [], pending_total: 2 }),
    )
    renderScreen()

    const link = await screen.findByRole('link', {
      name: "Review avery's pending work",
    })
    expect(link.getAttribute('href')).toBe('/approvals')
  })

  test('a child with nothing pending shows no per-child review link', async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse({ children: [CHILD_B], parents: [], pending_total: 0 }),
    )
    renderScreen()

    await waitFor(() => expect(screen.getByText('bailey')).toBeDefined())
    expect(
      screen.queryByRole('link', { name: "Review bailey's pending work" }),
    ).toBeNull()
  })
})

describe('keyboard operation', () => {
  test('a quick link is a real, focusable anchor', async () => {
    fetchSpy.mockResolvedValue(
      jsonResponse({ children: [], parents: [], pending_total: 0 }),
    )
    renderScreen()

    const link = await screen.findByRole('link', { name: 'Manage household' })
    expect(link.tagName).toBe('A')
    link.focus()
    expect(document.activeElement).toBe(link)
  })
})
