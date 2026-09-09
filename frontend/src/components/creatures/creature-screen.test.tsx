import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { createQueryClient } from '../../api/query-client'
import { CreatureScreen } from './creature-screen'
import {
  ALREADY_CHOSEN_MESSAGE,
  CONNECTION_MESSAGE,
  PERMISSION_MESSAGE,
} from './creature-messages'

const TEST_CSRF_TOKEN = 'test-csrf-token'

const form = (index: number, unlockLevel: number, unlocked: boolean) => ({
  index,
  name: `Form ${index}`,
  alt_text: `A drawing of dragon form ${index} with wings.`,
  unlock_level: unlockLevel,
  asset_path: `/creatures/dragon/form-${index}.svg`,
  unlocked,
})

const FORMS = [
  form(1, 1, true),
  form(2, 4, true),
  form(3, 7, false),
  form(4, 10, false),
]

const CHOSEN = {
  level: 5,
  max_level: 10,
  line: {
    slug: 'dragon',
    name: 'Dragon',
    description: 'A scaled hoarder who grows wings.',
  },
  current_form: FORMS[1],
  forms: FORMS,
}

const UNCHOSEN = {
  level: 0,
  max_level: 10,
  line: null,
  current_form: null,
  forms: [],
}

const JUST_CHOSEN = {
  ...UNCHOSEN,
  line: CHOSEN.line,
  forms: FORMS.map((entry) => ({ ...entry, unlocked: false })),
}

const LINES = {
  lines: [
    {
      slug: 'dragon',
      name: 'Dragon',
      description: 'A scaled hoarder who grows wings.',
      preview: {
        index: 1,
        name: 'Hatchling',
        alt_text: 'A small green dragon hatchling sitting up.',
        unlock_level: 1,
        asset_path: '/creatures/dragon/form-1.svg',
      },
    },
    {
      slug: 'golem',
      name: 'Golem',
      description: 'A figure of stone and clay.',
      preview: {
        index: 1,
        name: 'Pebble',
        alt_text: 'A small round stone golem with two bright eyes.',
        unlock_level: 1,
        asset_path: '/creatures/golem/form-1.svg',
      },
    },
  ],
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

const renderScreen = () =>
  render(
    <QueryClientProvider client={createQueryClient()}>
      <CreatureScreen />
    </QueryClientProvider>,
  )

/** Route every request by path and method, with a table of handlers. */
const route = (handlers: Record<string, (init?: RequestInit) => Response>) =>
  vi.fn(async (input: string, init?: RequestInit) => {
    const key = `${init?.method ?? 'GET'} ${input}`
    const handler = handlers[key]
    if (handler) {
      return handler(init)
    }
    if (input === '/api/v1/creature/') {
      return jsonResponse(CHOSEN)
    }
    if (input === '/api/v1/creature/lines/') {
      return jsonResponse(LINES)
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

describe('loading and failing', () => {
  test('shows a loading status before the creature arrives', async () => {
    fetchSpy.mockImplementation(route({}))
    renderScreen()

    expect(screen.getByRole('status').textContent).toContain('Loading')

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Form 2' })).toBeDefined(),
    )
  })

  test('shows one recoverable message and retries when the read fails', async () => {
    fetchSpy.mockImplementation(
      route({ 'GET /api/v1/creature/': () => jsonResponse({}, 500) }),
    )
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe(CONNECTION_MESSAGE),
    )

    fetchSpy.mockImplementation(route({}))
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Form 2' })).toBeDefined(),
    )
  })

  test('names the permission failure separately from a connection failure', async () => {
    fetchSpy.mockImplementation(
      route({ 'GET /api/v1/creature/': () => jsonResponse({ detail: 'no' }, 403) }),
    )
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe(PERMISSION_MESSAGE),
    )
  })
})

describe('the gallery, once a creature is chosen', () => {
  test('shows the current form, the level and every form in order', async () => {
    fetchSpy.mockImplementation(route({}))
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Form 2' })).toBeDefined(),
    )
    expect(screen.getByText(/Level 5 of 10/)).toBeDefined()
    expect(screen.getByText('Next form at level 7.')).toBeDefined()

    const tiles = within(screen.getByRole('list')).getAllByRole('listitem')
    expect(tiles).toHaveLength(4)
    expect(tiles[0].textContent).toContain('Form 1')
    expect(tiles[2].textContent).toContain('Locked until level 7')
    expect(tiles[3].textContent).toContain('Locked until level 10')
  })

  test('describes unlocked drawings and leaves locked ones undescribed', async () => {
    fetchSpy.mockImplementation(route({}))
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Form 2' })).toBeDefined(),
    )

    // Two unlocked tiles plus the large current drawing carry a description.
    const described = screen.getAllByRole('img')
    expect(described).toHaveLength(3)
    for (const image of described) {
      expect(image.getAttribute('alt')).toMatch(/^A drawing of dragon form/)
    }
    // The two locked drawings are silhouettes with no accessible name, so a
    // screen reader is told the level instead of the shape.
    expect(document.querySelectorAll('img[alt=""]')).toHaveLength(2)
  })

  test('tells a child who has chosen but not levelled what to reach for', async () => {
    fetchSpy.mockImplementation(
      route({ 'GET /api/v1/creature/': () => jsonResponse(JUST_CHOSEN) }),
    )
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Dragon' })).toBeDefined(),
    )
    expect(
      screen.getByText('Your dragon appears at level 1. You are level 0.'),
    ).toBeDefined()
    expect(screen.queryByText(/^Form /)).toBeNull()
  })

  test('says so at the last form instead of naming a next one', async () => {
    const finished = {
      ...CHOSEN,
      level: 10,
      current_form: form(4, 10, true),
      forms: FORMS.map((entry) => ({ ...entry, unlocked: true })),
    }
    fetchSpy.mockImplementation(
      route({ 'GET /api/v1/creature/': () => jsonResponse(finished) }),
    )
    renderScreen()

    await waitFor(() =>
      expect(
        screen.getByText('This is the last form. Your creature is fully grown.'),
      ).toBeDefined(),
    )
  })
})

describe('the chooser, before a creature is chosen', () => {
  const renderChooser = async (handlers: Parameters<typeof route>[0] = {}) => {
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/creature/': () => jsonResponse(UNCHOSEN),
        ...handlers,
      }),
    )
    renderScreen()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Dragon/ })).toBeDefined(),
    )
  }

  test('offers every line with its preview and description', async () => {
    await renderChooser()

    expect(screen.getByRole('heading', { name: 'Choose your creature' })).toBeDefined()
    const options = screen.getAllByRole('button')
    expect(options.map((option) => option.textContent)).toEqual([
      'DragonA scaled hoarder who grows wings.',
      'GolemA figure of stone and clay.',
    ])
    expect(
      screen.getByAltText('A small green dragon hatchling sitting up.'),
    ).toBeDefined()
  })

  test('confirms before saving, and cancelling saves nothing', async () => {
    await renderChooser()

    fireEvent.click(screen.getByRole('button', { name: /Golem/ }))

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/cannot swap it/)).toBeDefined()

    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(
      fetchSpy.mock.calls.filter((call) => call[1]?.method === 'POST'),
    ).toHaveLength(0)
  })

  test('saves the confirmed line and shows the creature it returns', async () => {
    await renderChooser({
      'POST /api/v1/creature/': () => jsonResponse(JUST_CHOSEN, 201),
    })

    fireEvent.click(screen.getByRole('button', { name: /Dragon/ }))
    fireEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', {
        name: 'Yes, choose this one',
      }),
    )

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Dragon' })).toBeDefined(),
    )
    const post = fetchSpy.mock.calls.find((call) => call[1]?.method === 'POST')
    expect(post?.[1]?.body).toBe(JSON.stringify({ line: 'dragon' }))
    expect(
      (post?.[1]?.headers as Record<string, string>)['X-CSRFToken'],
    ).toBe(TEST_CSRF_TOKEN)
  })

  test('keeps the dialog open with one message when saving fails', async () => {
    await renderChooser({
      'POST /api/v1/creature/': () => jsonResponse({}, 500),
    })

    fireEvent.click(screen.getByRole('button', { name: /Dragon/ }))
    fireEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', {
        name: 'Yes, choose this one',
      }),
    )

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe(CONNECTION_MESSAGE),
    )
    expect(screen.getByRole('dialog')).toBeDefined()
  })

  test('explains a creature saved elsewhere rather than looking broken', async () => {
    await renderChooser({
      'POST /api/v1/creature/': () => jsonResponse({ detail: 'no' }, 409),
    })

    fireEvent.click(screen.getByRole('button', { name: /Dragon/ }))
    fireEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', {
        name: 'Yes, choose this one',
      }),
    )

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe(ALREADY_CHOSEN_MESSAGE),
    )
  })

  test('recovers when the line list itself cannot be read', async () => {
    fetchSpy.mockImplementation(
      route({
        'GET /api/v1/creature/': () => jsonResponse(UNCHOSEN),
        'GET /api/v1/creature/lines/': () => jsonResponse({}, 500),
      }),
    )
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe(CONNECTION_MESSAGE),
    )

    fetchSpy.mockImplementation(
      route({ 'GET /api/v1/creature/': () => jsonResponse(UNCHOSEN) }),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Dragon/ })).toBeDefined(),
    )
  })

  test('every option is reachable and activatable from the keyboard', async () => {
    await renderChooser({
      'POST /api/v1/creature/': () => jsonResponse(JUST_CHOSEN, 201),
    })

    const option = screen.getByRole('button', { name: /Golem/ })
    option.focus()
    expect(document.activeElement).toBe(option)

    fireEvent.keyDown(option, { key: 'Enter' })
    fireEvent.click(option)

    expect(await screen.findByRole('dialog')).toBeDefined()
  })
})
