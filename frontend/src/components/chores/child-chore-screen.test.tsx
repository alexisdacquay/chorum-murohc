import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { createQueryClient } from '../../api/query-client'
import { ChildChoreScreen } from './child-chore-screen'
import { NOT_FOUND_MESSAGE, PERMISSION_MESSAGE } from './submission-messages'

const TEST_CSRF_TOKEN = 'test-csrf-token'

const CHORE_A = { id: 1, name: 'Wash dishes', points: 10 }
const CHORE_B = { id: 2, name: 'Feed cat', points: 1 }

const SUBMISSION_A = {
  id: 91,
  chore: 1,
  chore_name: 'Wash dishes',
  chore_points: 10,
  note: '',
  status: 'pending' as const,
  created_at: '2026-09-01T00:00:00Z',
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
      <ChildChoreScreen />
    </QueryClientProvider>,
  )
}

/** Route every request by path and method, with a table of handlers. */
const route = (
  handlers: Record<string, (init?: RequestInit) => Response>,
) =>
  vi.fn(async (input: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    const key = `${method} ${input}`
    const handler = handlers[key]
    if (handler) {
      return handler(init)
    }
    if (input === '/api/v1/chores/') {
      return jsonResponse([CHORE_A])
    }
    if (input === '/api/v1/submissions/') {
      return jsonResponse([])
    }
    return jsonResponse({}, 404)
  })

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

describe('loading the browser', () => {
  test('shows loading, then cards with name and points only', async () => {
    fetchSpy.mockResolvedValue(jsonResponse([]))
    fetchSpy.mockImplementation(route({}))
    renderScreen()

    expect(screen.getByRole('status').textContent).toContain('Loading')

    await waitFor(() =>
      expect(
        screen.getByRole('heading', { level: 2, name: 'Wash dishes' }),
      ).toBeDefined(),
    )
    expect(screen.getByText('10 points')).toBeDefined()
    expect(screen.getByRole('button', { name: 'Mark Wash dishes as done' })).toBeDefined()
  })

  test('shows an empty-state sentence instead of an empty list', async () => {
    fetchSpy.mockImplementation(
      route({ 'GET /api/v1/chores/': () => jsonResponse([]) }),
    )
    renderScreen()

    await waitFor(() => expect(screen.getByText(/No chores yet/)).toBeDefined())
    expect(screen.queryByRole('list')).toBeNull()
  })

  test('a chore with a pending submission shows the badge, not a button', async () => {
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/chores/': () => jsonResponse([CHORE_A, CHORE_B]),
        'GET /api/v1/submissions/': () => jsonResponse([SUBMISSION_A]),
      }),
    )
    renderScreen()

    await waitFor(() => expect(screen.getByText('Wash dishes')).toBeDefined())
    expect(screen.getByText('Pending review')).toBeDefined()
    expect(
      screen.queryByRole('button', { name: 'Mark Wash dishes as done' }),
    ).toBeNull()
    expect(screen.getByRole('button', { name: 'Mark Feed cat as done' })).toBeDefined()
  })

  test('offers a working retry when the chore list fails', async () => {
    let attempts = 0
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/chores/': () => {
          attempts += 1
          if (attempts === 1) {
            throw new Error('offline')
          }
          return jsonResponse([CHORE_A])
        },
      }),
    )
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
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/chores/': () => jsonResponse({ detail: 'nope' }, 403),
      }),
    )
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe(PERMISSION_MESSAGE),
    )
    expect(document.body.textContent).not.toContain('nope')
  })
})

describe('marking a chore done', () => {
  test('cancel sends no request and the chore stays available', async () => {
    fetchSpy.mockImplementation(route({}))
    renderScreen()

    await waitFor(() => expect(screen.getByText('Wash dishes')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Mark Wash dishes as done' }))
    const dialog = await screen.findByRole('dialog')

    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(
      fetchSpy.mock.calls.some((call) => call[1]?.method === 'POST'),
    ).toBe(false)
    expect(screen.getByRole('button', { name: 'Mark Wash dishes as done' })).toBeDefined()
  })

  test('Escape closes the dialog and sends no request', async () => {
    fetchSpy.mockImplementation(route({}))
    renderScreen()

    await waitFor(() => expect(screen.getByText('Wash dishes')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Mark Wash dishes as done' }))
    await screen.findByRole('dialog')

    fireEvent.keyDown(document, { key: 'Escape' })

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(
      fetchSpy.mock.calls.some((call) => call[1]?.method === 'POST'),
    ).toBe(false)
  })

  test('confirming submits the note, shows success and the pending badge', async () => {
    fetchSpy.mockImplementation(
      route({
        'POST /api/v1/submissions/': (init) => {
          const body = JSON.parse(init!.body as string) as Record<string, unknown>
          return jsonResponse({ ...SUBMISSION_A, note: body.note }, 201)
        },
        'GET /api/v1/submissions/': () => {
          const alreadySubmitted = fetchSpy.mock.calls.some(
            (call) => call[0] === '/api/v1/submissions/' && call[1]?.method === 'POST',
          )
          return jsonResponse(alreadySubmitted ? [SUBMISSION_A] : [])
        },
      }),
    )
    renderScreen()

    await waitFor(() => expect(screen.getByText('Wash dishes')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Mark Wash dishes as done' }))
    const dialog = await screen.findByRole('dialog')

    fireEvent.change(within(dialog).getByLabelText('Add a note (optional)'), {
      target: { value: 'Left the mop out' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Mark as done' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() =>
      expect(screen.getByText(/marked as done/)).toBeDefined(),
    )
    await waitFor(() => expect(screen.getByText('Pending review')).toBeDefined())

    const [, postInit] = fetchSpy.mock.calls.find(
      (call) => call[0] === '/api/v1/submissions/' && call[1]?.method === 'POST',
    )!
    const sentBody = JSON.parse(postInit.body as string)
    expect(sentBody.chore).toBe(1)
    expect(sentBody.note).toBe('Left the mop out')
    expect(typeof sentBody.idempotency_key).toBe('string')
    expect(sentBody.idempotency_key.length).toBeGreaterThan(0)
    expect(postInit.headers['X-CSRFToken']).toBe(TEST_CSRF_TOKEN)
  })

  test('a duplicate-pending refusal shows the server detail on the dialog', async () => {
    fetchSpy.mockImplementation(
      route({
        'POST /api/v1/submissions/': () =>
          jsonResponse(
            { chore: ['You already have a pending submission for this chore.'] },
            400,
          ),
      }),
    )
    renderScreen()

    await waitFor(() => expect(screen.getByText('Wash dishes')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Mark Wash dishes as done' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Mark as done' }))

    await waitFor(() =>
      expect(
        within(dialog).getByText(
          'You already have a pending submission for this chore.',
        ),
      ).toBeDefined(),
    )
    expect(screen.getByRole('dialog')).toBeDefined()
  })

  test('a chore removed elsewhere shows the fixed not-found sentence', async () => {
    fetchSpy.mockImplementation(
      route({ 'POST /api/v1/submissions/': () => jsonResponse({}, 404) }),
    )
    renderScreen()

    await waitFor(() => expect(screen.getByText('Wash dishes')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Mark Wash dishes as done' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Mark as done' }))

    await waitFor(() =>
      expect(within(dialog).getByText(NOT_FOUND_MESSAGE)).toBeDefined(),
    )
  })

  test('retrying after a connection failure reuses the same idempotency key', async () => {
    let posts = 0
    fetchSpy.mockImplementation(
      route({
        'POST /api/v1/submissions/': (init) => {
          posts += 1
          if (posts === 1) {
            throw new Error('offline')
          }
          const body = JSON.parse(init!.body as string) as Record<string, unknown>
          keysSeen.push(body.idempotency_key as string)
          return jsonResponse(SUBMISSION_A, 201)
        },
      }),
    )
    const keysSeen: string[] = []
    renderScreen()

    await waitFor(() => expect(screen.getByText('Wash dishes')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Mark Wash dishes as done' }))
    const dialog = await screen.findByRole('dialog')

    fireEvent.click(within(dialog).getByRole('button', { name: 'Mark as done' }))
    await waitFor(() =>
      expect(within(dialog).getByRole('alert').textContent).toContain(
        'We could not reach Chorum-murohc',
      ),
    )

    fireEvent.click(within(dialog).getByRole('button', { name: 'Mark as done' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())

    const posted = fetchSpy.mock.calls.filter(
      (call) => call[0] === '/api/v1/submissions/' && call[1]?.method === 'POST',
    )
    expect(posted).toHaveLength(2)
    const firstKey = JSON.parse(posted[0][1]?.body as string).idempotency_key
    const secondKey = JSON.parse(posted[1][1]?.body as string).idempotency_key
    expect(firstKey).toBe(secondKey)
  })

  test('double-clicking confirm sends only one request', async () => {
    let posts = 0
    fetchSpy.mockImplementation(
      route({
        'POST /api/v1/submissions/': () => {
          posts += 1
          return jsonResponse(SUBMISSION_A, 201)
        },
      }),
    )
    renderScreen()

    await waitFor(() => expect(screen.getByText('Wash dishes')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Mark Wash dishes as done' }))
    const dialog = await screen.findByRole('dialog')
    const confirmButton = within(dialog).getByRole('button', { name: 'Mark as done' })

    fireEvent.click(confirmButton)
    fireEvent.click(confirmButton)

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(posts).toBe(1)
  })
})
