import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { createQueryClient } from '../../api/query-client'
import { LevelsScreen } from './levels-screen'
import { PERMISSION_MESSAGE } from './progression-messages'

const TEST_CSRF_TOKEN = 'test-csrf-token'

const BASE_PROGRESSION = {
  level: 3,
  max_level: 10,
  lifetime_points: 320,
  next_level_threshold: 500,
  points_to_next_level: 180,
  pending_level_up: null,
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
      <LevelsScreen />
    </QueryClientProvider>,
  )
}

/** Route every request by path and method, with a table of handlers. */
const route = (handlers: Record<string, (init?: RequestInit) => Response>) =>
  vi.fn(async (input: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    const key = `${method} ${input}`
    const handler = handlers[key]
    if (handler) {
      return handler(init)
    }
    if (input === '/api/v1/progression/') {
      return jsonResponse(BASE_PROGRESSION)
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

describe('loading and reading the level', () => {
  test('shows loading, then the level, progress and lifetime points', async () => {
    fetchSpy.mockImplementation(route({}))
    renderScreen()

    expect(screen.getByRole('status').textContent).toContain('Loading')

    await waitFor(() =>
      expect(
        screen.getByRole('heading', { level: 2, name: 'Level 3 of 10' }),
      ).toBeDefined(),
    )
    expect(screen.getByText('180 points to level 4')).toBeDefined()
    expect(screen.getByText('320 points earned in total')).toBeDefined()

    const bar = screen.getByRole('progressbar', {
      name: 'Progress toward level 4',
    }) as HTMLProgressElement
    expect(bar.max).toBe(500)
    expect(bar.value).toBe(320)
  })

  test('at the maximum level shows no progress bar', async () => {
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/progression/': () =>
          jsonResponse({
            ...BASE_PROGRESSION,
            level: 10,
            next_level_threshold: null,
            points_to_next_level: null,
          }),
      }),
    )
    renderScreen()

    await waitFor(() =>
      expect(
        screen.getByRole('heading', { level: 2, name: 'Level 10 of 10' }),
      ).toBeDefined(),
    )
    expect(screen.getByText(/reached the highest level/)).toBeDefined()
    expect(screen.queryByRole('progressbar')).toBeNull()
  })

  test('a level with exactly one point remaining uses the singular', async () => {
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/progression/': () =>
          jsonResponse({ ...BASE_PROGRESSION, points_to_next_level: 1 }),
      }),
    )
    renderScreen()

    await waitFor(() => expect(screen.getByText('1 point to level 4')).toBeDefined())
  })

  test('offers a working retry when the read fails', async () => {
    let attempts = 0
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/progression/': () => {
          attempts += 1
          if (attempts === 1) {
            throw new Error('offline')
          }
          return jsonResponse(BASE_PROGRESSION)
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

    await waitFor(() =>
      expect(
        screen.getByRole('heading', { level: 2, name: 'Level 3 of 10' }),
      ).toBeDefined(),
    )
  })

  test('shows the fixed permission sentence for a 403, never server text', async () => {
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/progression/': () => jsonResponse({ detail: 'nope' }, 403),
      }),
    )
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe(PERMISSION_MESSAGE),
    )
    expect(document.body.textContent).not.toContain('nope')
  })
})

describe('the level-up celebration', () => {
  test('opens automatically when a level-up is pending, and Nice! acknowledges it', async () => {
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/progression/': () =>
          jsonResponse({ ...BASE_PROGRESSION, pending_level_up: 3 }),
        'POST /api/v1/progression/acknowledge/': () =>
          jsonResponse({ ...BASE_PROGRESSION, pending_level_up: null }),
      }),
    )
    renderScreen()

    const dialog = await screen.findByRole('dialog', {
      name: 'Level up! You reached level 3',
    })
    expect(dialog).toBeDefined()

    fireEvent.click(screen.getByRole('button', { name: 'Nice!' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    const [, postInit] = fetchSpy.mock.calls.find(
      (call) =>
        call[0] === '/api/v1/progression/acknowledge/' && call[1]?.method === 'POST',
    )!
    expect((postInit.headers as Record<string, string>)['X-CSRFToken']).toBe(
      TEST_CSRF_TOKEN,
    )
  })

  test('does not open when nothing is pending', async () => {
    fetchSpy.mockImplementation(route({}))
    renderScreen()

    await waitFor(() =>
      expect(
        screen.getByRole('heading', { level: 2, name: 'Level 3 of 10' }),
      ).toBeDefined(),
    )
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  test('the highest level names no next level in the celebration', async () => {
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/progression/': () =>
          jsonResponse({
            ...BASE_PROGRESSION,
            level: 10,
            next_level_threshold: null,
            points_to_next_level: null,
            pending_level_up: 10,
          }),
      }),
    )
    renderScreen()

    await screen.findByRole('dialog', { name: 'Level up! You reached level 10' })
    expect(screen.getByText('You have reached the highest level there is.')).toBeDefined()
  })

  test('Escape also acknowledges, since it counts as having been shown', async () => {
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/progression/': () =>
          jsonResponse({ ...BASE_PROGRESSION, pending_level_up: 3 }),
        'POST /api/v1/progression/acknowledge/': () =>
          jsonResponse({ ...BASE_PROGRESSION, pending_level_up: null }),
      }),
    )
    renderScreen()

    await screen.findByRole('dialog')
    fireEvent.keyDown(document, { key: 'Escape' })

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(
      fetchSpy.mock.calls.some(
        (call) =>
          call[0] === '/api/v1/progression/acknowledge/' && call[1]?.method === 'POST',
      ),
    ).toBe(true)
  })

  test('an acknowledge failure keeps the dialog open with a retry', async () => {
    let attempts = 0
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/progression/': () =>
          jsonResponse({ ...BASE_PROGRESSION, pending_level_up: 3 }),
        'POST /api/v1/progression/acknowledge/': () => {
          attempts += 1
          if (attempts === 1) {
            return jsonResponse({ detail: 'nope' }, 403)
          }
          return jsonResponse({ ...BASE_PROGRESSION, pending_level_up: null })
        },
      }),
    )
    renderScreen()

    await screen.findByRole('dialog')
    fireEvent.click(screen.getByRole('button', { name: 'Nice!' }))

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe(PERMISSION_MESSAGE),
    )
    expect(screen.getByRole('dialog')).toBeDefined()

    fireEvent.click(screen.getByRole('button', { name: 'Nice!' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  })
})
