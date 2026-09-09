import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { createQueryClient } from '../../api/query-client'
import { ParentApprovalsScreen } from './parent-approvals-screen'

const TEST_CSRF_TOKEN = 'test-csrf-token'

const APPROVAL_A = {
  id: 9,
  child_id: 3,
  child_username: 'kid',
  chore: 1,
  chore_name: 'Dishes',
  chore_points: 5,
  note: 'Left the mop out',
  created_at: '2026-09-01T00:00:00Z',
}

const DECIDED_A = {
  id: 9,
  chore_name: 'Dishes',
  chore_points: 5,
  note: 'Left the mop out',
  status: 'approved' as const,
  rejection_reason: '',
  created_at: '2026-09-01T00:00:00Z',
  decided_at: '2026-09-01T01:00:00Z',
}

const page = (results: unknown[], next: string | null = null) => ({
  count: results.length,
  next,
  previous: null,
  results,
})

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
      <ParentApprovalsScreen />
    </QueryClientProvider>,
  )
}

const respondByPath = (routes: Record<string, (init?: RequestInit) => Response>) =>
  vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    for (const [prefix, build] of Object.entries(routes)) {
      if (url.startsWith(prefix)) {
        return Promise.resolve(build(init))
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

describe('the approvals list', () => {
  test('shows a pending approval with child, points and note', async () => {
    fetchSpy = respondByPath({
      '/api/v1/approvals/': () => jsonResponse(page([APPROVAL_A])),
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 3, name: 'Dishes' })).toBeDefined(),
    )
    expect(screen.getByText(/kid - 5 points - "Left the mop out"/)).toBeDefined()
  })

  test('shows the empty-queue copy when nothing is pending', async () => {
    fetchSpy = respondByPath({
      '/api/v1/approvals/': () => jsonResponse(page([])),
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() =>
      expect(screen.getByText('Nothing is waiting for a decision.')).toBeDefined(),
    )
  })

  test('offers a working retry on failure', async () => {
    let attempts = 0
    fetchSpy = respondByPath({
      '/api/v1/approvals/': () => {
        attempts += 1
        return attempts === 1 ? jsonResponse({}, 403) : jsonResponse(page([APPROVAL_A]))
      },
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toContain('permission'),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))

    await waitFor(() => expect(screen.getByText('Dishes')).toBeDefined())
  })

  test('a Load more button appends the next page', async () => {
    fetchSpy = respondByPath({
      '/api/v1/approvals/?page=2': () =>
        jsonResponse(page([{ ...APPROVAL_A, id: 10, chore_name: 'Trash' }])),
      '/api/v1/approvals/': () =>
        jsonResponse(page([APPROVAL_A], '/api/v1/approvals/?page=2')),
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() => expect(screen.getByText('Dishes')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Load more' }))

    await waitFor(() => expect(screen.getByText('Trash')).toBeDefined())
    expect(screen.getByText('Dishes')).toBeDefined()
  })
})

describe('deciding an approval', () => {
  test('approving asks for a PIN, then shows success and removes the item', async () => {
    let decided = false
    fetchSpy = respondByPath({
      '/api/v1/submissions/9/decide/': (init) => {
        decided = true
        const body = JSON.parse(init!.body as string) as Record<string, unknown>
        expect(body.decision).toBe('approve')
        expect(body.pin).toBe('3947')
        return jsonResponse(DECIDED_A)
      },
      '/api/v1/approvals/': () => jsonResponse(page(decided ? [] : [APPROVAL_A])),
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() => expect(screen.getByText('Dishes')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Approve Dishes for kid' }))
    const dialog = await screen.findByRole('dialog')

    fireEvent.change(within(dialog).getByLabelText('Your PIN'), {
      target: { value: '3947' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Approve' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(screen.getByText('Approved "Dishes".')).toBeDefined()
    await waitFor(() =>
      expect(
        screen.getByText('Nothing is waiting for a decision.'),
      ).toBeDefined(),
    )
  })

  test('rejecting sends the optional reason', async () => {
    fetchSpy = respondByPath({
      '/api/v1/submissions/9/decide/': (init) => {
        const body = JSON.parse(init!.body as string) as Record<string, unknown>
        expect(body.decision).toBe('reject')
        expect(body.reason).toBe('Not dry yet')
        return jsonResponse({ ...DECIDED_A, status: 'rejected', rejection_reason: body.reason })
      },
      '/api/v1/approvals/': () => jsonResponse(page([APPROVAL_A])),
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() => expect(screen.getByText('Dishes')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Reject Dishes for kid' }))
    const dialog = await screen.findByRole('dialog')

    fireEvent.change(within(dialog).getByLabelText('Your PIN'), {
      target: { value: '3947' },
    })
    fireEvent.change(within(dialog).getByLabelText('Reason (optional)'), {
      target: { value: 'Not dry yet' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reject' }))

    await waitFor(() => expect(screen.getByText('Rejected "Dishes".')).toBeDefined())
  })

  test('a submission already decided elsewhere shows the stale-state sentence', async () => {
    fetchSpy = respondByPath({
      '/api/v1/submissions/9/decide/': () => jsonResponse({ detail: 'Not found.' }, 404),
      '/api/v1/approvals/': () => jsonResponse(page([APPROVAL_A])),
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() => expect(screen.getByText('Dishes')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Approve Dishes for kid' }))
    const dialog = await screen.findByRole('dialog')

    fireEvent.change(within(dialog).getByLabelText('Your PIN'), {
      target: { value: '3947' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Approve' }))

    await waitFor(() =>
      expect(within(dialog).getByText(/no longer waiting for a decision/)).toBeDefined(),
    )
    expect(screen.getByRole('dialog')).toBeDefined()
  })

  test('a wrong PIN shows the server detail and keeps the dialog open', async () => {
    fetchSpy = respondByPath({
      '/api/v1/submissions/9/decide/': () =>
        jsonResponse({ pin: ['That PIN was not accepted.'] }, 400),
      '/api/v1/approvals/': () => jsonResponse(page([APPROVAL_A])),
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() => expect(screen.getByText('Dishes')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Approve Dishes for kid' }))
    const dialog = await screen.findByRole('dialog')

    fireEvent.change(within(dialog).getByLabelText('Your PIN'), {
      target: { value: '0000' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Approve' }))

    await waitFor(() =>
      expect(within(dialog).getByText('That PIN was not accepted.')).toBeDefined(),
    )
    expect(screen.getByRole('dialog')).toBeDefined()
    expect(within(dialog).getByLabelText('Your PIN')).toHaveProperty('value', '')
  })

  test('cancel closes the dialog and sends no decide request', async () => {
    fetchSpy = respondByPath({
      '/api/v1/approvals/': () => jsonResponse(page([APPROVAL_A])),
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() => expect(screen.getByText('Dishes')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Approve Dishes for kid' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(
      fetchSpy.mock.calls.some((call) => (call[1] as RequestInit | undefined)?.method === 'POST'),
    ).toBe(false)
  })
})
