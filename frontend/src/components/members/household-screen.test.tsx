import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { createQueryClient } from '../../api/query-client'
import {
  PASSWORD_REQUIRED_MESSAGE,
  USERNAME_REQUIRED_MESSAGE,
} from './member-form-dialog'
import { NOT_FOUND_MESSAGE, PERMISSION_MESSAGE } from './member-messages'
import { HouseholdScreen } from './household-screen'

const TEST_CSRF_TOKEN = 'test-csrf-token'

const SESSION = {
  is_authenticated: true,
  user: { id: 1, username: 'parent-one' },
  household: { id: 1, name: 'Synthetic Household' },
  role: 'parent',
}

const PARENT_ONE = {
  id: 1,
  username: 'parent-one',
  role: 'parent',
  is_active: true,
  date_joined: '2026-09-01T00:00:00Z',
}
const CHILD_A = {
  id: 2,
  username: 'kid-a',
  role: 'child',
  is_active: true,
  date_joined: '2026-09-01T00:00:00Z',
}
const CHILD_B = {
  id: 3,
  username: 'kid-b',
  role: 'child',
  is_active: false,
  date_joined: '2026-09-01T00:00:00Z',
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
      <HouseholdScreen />
    </QueryClientProvider>,
  )
}

/** Route every request by method and path, session always resolved. */
const withSession = (
  handler: (input: string, init?: RequestInit) => Promise<Response> | Response,
) =>
  vi.fn(async (input: string, init?: RequestInit) => {
    if (input === '/api/v1/auth/session/') {
      return jsonResponse(SESSION)
    }
    return handler(input, init)
  })

beforeEach(() => {
  clearCookies()
  document.cookie = `csrftoken=${TEST_CSRF_TOKEN}`
})

afterEach(() => {
  vi.unstubAllGlobals()
  clearCookies()
})

describe('loading the directory', () => {
  test('shows loading, then active members with role and no self controls', async () => {
    fetchSpy = withSession(() => jsonResponse([PARENT_ONE, CHILD_A]))
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    expect(screen.getByRole('status').textContent).toContain('Loading')

    await waitFor(() =>
      expect(
        screen.getByRole('heading', { level: 2, name: 'kid-a' }),
      ).toBeDefined(),
    )
    expect(screen.getByText('Child')).toBeDefined()
    expect(screen.getByText('Parent - You')).toBeDefined()
    expect(screen.queryByRole('button', { name: 'Edit parent-one' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Edit kid-a' })).toBeDefined()
  })

  test('shows an empty-state sentence instead of an empty list', async () => {
    fetchSpy = withSession(() => jsonResponse([PARENT_ONE]))
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() =>
      expect(screen.getByText(/No other active household members/)).toBeDefined(),
    )
  })

  test('the inactive toggle widens the list and labels the inactive one', async () => {
    fetchSpy = withSession((input) =>
      input.includes('include_inactive=true')
        ? jsonResponse([PARENT_ONE, CHILD_A, CHILD_B])
        : jsonResponse([PARENT_ONE, CHILD_A]),
    )
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() => expect(screen.getByText('kid-a')).toBeDefined())
    fireEvent.click(screen.getByRole('checkbox', { name: 'Show inactive members' }))

    await waitFor(() => expect(screen.getByText('kid-b')).toBeDefined())
    expect(screen.getByText('Child - Inactive')).toBeDefined()
  })

  test('offers a working retry when the list request fails', async () => {
    let calls = 0
    fetchSpy = withSession(() => {
      calls += 1
      if (calls === 1) {
        throw new Error('offline')
      }
      return jsonResponse([PARENT_ONE])
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toContain(
        'We could not reach Chorum-murohc',
      ),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Add member' })).toBeDefined(),
    )
  })

  test('shows the fixed permission sentence for a 403, never server text', async () => {
    fetchSpy = withSession(() => jsonResponse({ detail: 'nope' }, 403))
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toBe(PERMISSION_MESSAGE),
    )
    expect(document.body.textContent).not.toContain('nope')
  })
})

describe('adding a member', () => {
  test('refuses an empty submission locally, with no request sent', async () => {
    fetchSpy = withSession(() => jsonResponse([PARENT_ONE]))
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Add member' })).toBeDefined(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Add member' }))
    const dialog = await screen.findByRole('dialog', { name: 'Add household member' })

    const postCallsBefore = fetchSpy.mock.calls.filter(
      (call) => call[1]?.method === 'POST',
    ).length
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add member' }))

    expect(within(dialog).getByText(USERNAME_REQUIRED_MESSAGE)).toBeDefined()
    expect(within(dialog).getByText(PASSWORD_REQUIRED_MESSAGE)).toBeDefined()
    expect(document.activeElement).toBe(within(dialog).getByLabelText('Username'))
    expect(
      fetchSpy.mock.calls.filter((call) => call[1]?.method === 'POST').length,
    ).toBe(postCallsBefore)
  })

  test('creates a member with the chosen role and shows it in the refreshed list', async () => {
    fetchSpy = withSession((input, init) => {
      if (input === '/api/v1/household-members/' && init?.method === 'POST') {
        return jsonResponse(
          { ...CHILD_A, id: 9, username: 'new-kid', role: 'child' },
          201,
        )
      }
      if (input === '/api/v1/household-members/') {
        const priorGets = fetchSpy.mock.calls.filter(
          (call) =>
            call[0] === '/api/v1/household-members/' && call[1]?.method === 'GET',
        ).length
        return jsonResponse(
          priorGets <= 1
            ? [PARENT_ONE]
            : [PARENT_ONE, { ...CHILD_A, id: 9, username: 'new-kid' }],
        )
      }
      return jsonResponse({}, 404)
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Add member' })).toBeDefined(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Add member' }))
    const dialog = await screen.findByRole('dialog', { name: 'Add household member' })

    fireEvent.change(within(dialog).getByLabelText('Username'), {
      target: { value: 'new-kid' },
    })
    fireEvent.change(within(dialog).getByLabelText('Password'), {
      target: { value: 'a genuinely unusual passphrase 42' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add member' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(screen.getByText('new-kid')).toBeDefined())

    const [, postInit] = fetchSpy.mock.calls.find(
      (call) => call[0] === '/api/v1/household-members/' && call[1]?.method === 'POST',
    )!
    expect(JSON.parse(postInit.body as string)).toEqual({
      username: 'new-kid',
      password: 'a genuinely unusual passphrase 42',
      role: 'child',
    })
    expect(postInit.headers['X-CSRFToken']).toBe(TEST_CSRF_TOKEN)
  })

  test('shows the server duplicate-username message on its own field', async () => {
    fetchSpy = withSession((input, init) => {
      if (input === '/api/v1/household-members/' && init?.method === 'POST') {
        return jsonResponse(
          { username: ['A user with that username already exists.'] },
          400,
        )
      }
      return jsonResponse([PARENT_ONE])
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Add member' })).toBeDefined(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Add member' }))
    const dialog = await screen.findByRole('dialog', { name: 'Add household member' })

    fireEvent.change(within(dialog).getByLabelText('Username'), {
      target: { value: 'parent-one' },
    })
    fireEvent.change(within(dialog).getByLabelText('Password'), {
      target: { value: 'a genuinely unusual passphrase 42' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add member' }))

    await waitFor(() =>
      expect(
        within(dialog).getByText('A user with that username already exists.'),
      ).toBeDefined(),
    )
    expect(screen.getByRole('dialog')).toBeDefined()
  })

  test('Escape closes the dialog and sends no request', async () => {
    fetchSpy = withSession(() => jsonResponse([PARENT_ONE]))
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Add member' })).toBeDefined(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Add member' }))
    await screen.findByRole('dialog', { name: 'Add household member' })

    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())

    expect(
      fetchSpy.mock.calls.some((call) => call[1]?.method === 'POST'),
    ).toBe(false)
  })
})

describe('editing a member', () => {
  test('prefills the form and a blank password leaves it unchanged', async () => {
    fetchSpy = withSession((input, init) => {
      if (input === '/api/v1/household-members/2/' && init?.method === 'PATCH') {
        return jsonResponse({ ...CHILD_A, role: 'parent' })
      }
      return jsonResponse([PARENT_ONE, CHILD_A])
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() => expect(screen.getByText('kid-a')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Edit kid-a' }))

    const dialog = await screen.findByRole('dialog', { name: 'Edit household member' })
    expect(within(dialog).getByLabelText('Username')).toHaveProperty('value', 'kid-a')
    expect(within(dialog).getByLabelText('New password')).toHaveProperty('value', '')
    expect(within(dialog).getByLabelText('Role')).toHaveProperty('value', 'child')

    fireEvent.change(within(dialog).getByLabelText('Role'), {
      target: { value: 'parent' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    const [, patchInit] = fetchSpy.mock.calls.find(
      (call) => call[0] === '/api/v1/household-members/2/' && call[1]?.method === 'PATCH',
    )!
    expect(JSON.parse(patchInit.body as string)).toEqual({
      username: 'kid-a',
      role: 'parent',
    })
  })

  test('a member removed by someone else shows one recoverable notice', async () => {
    fetchSpy = withSession((input, init) => {
      if (input === '/api/v1/household-members/2/' && init?.method === 'PATCH') {
        return jsonResponse({}, 404)
      }
      return jsonResponse([PARENT_ONE, CHILD_A])
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() => expect(screen.getByText('kid-a')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Edit kid-a' }))
    const dialog = await screen.findByRole('dialog', { name: 'Edit household member' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(within(dialog).getByText(NOT_FOUND_MESSAGE)).toBeDefined(),
    )
  })

  test('the last-active-parent business message is shown verbatim, not as a field error', async () => {
    fetchSpy = withSession((input, init) => {
      if (input === '/api/v1/household-members/2/' && init?.method === 'PATCH') {
        return jsonResponse(
          { detail: 'The household must keep at least one active parent.' },
          400,
        )
      }
      return jsonResponse([PARENT_ONE, CHILD_A])
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() => expect(screen.getByText('kid-a')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Edit kid-a' }))
    const dialog = await screen.findByRole('dialog', { name: 'Edit household member' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(
        within(dialog).getByText(
          'The household must keep at least one active parent.',
        ),
      ).toBeDefined(),
    )
  })
})

describe('deactivating and reactivating', () => {
  test('one click each way, no confirmation', async () => {
    fetchSpy = withSession((input, init) => {
      if (
        input === '/api/v1/household-members/2/deactivate/' &&
        init?.method === 'POST'
      ) {
        return jsonResponse({ ...CHILD_A, is_active: false })
      }
      return jsonResponse([PARENT_ONE, CHILD_A])
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() => expect(screen.getByText('kid-a')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Deactivate kid-a' }))

    await waitFor(() =>
      expect(
        fetchSpy.mock.calls.some(
          (call) => call[0] === '/api/v1/household-members/2/deactivate/',
        ),
      ).toBe(true),
    )
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})

describe('deleting a member', () => {
  test('the consequence text names points, level and creature for a child', async () => {
    fetchSpy = withSession(() => jsonResponse([PARENT_ONE, CHILD_A]))
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() => expect(screen.getByText('kid-a')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Delete kid-a' }))
    const dialog = await screen.findByRole('dialog')

    expect(dialog.textContent).toContain('points, level and creature')
    expect(dialog.textContent).toContain('cannot be undone')
  })

  test('cancel sends no request and keeps the member', async () => {
    fetchSpy = withSession(() => jsonResponse([PARENT_ONE, CHILD_A]))
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() => expect(screen.getByText('kid-a')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Delete kid-a' }))
    const dialog = await screen.findByRole('dialog')

    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(
      fetchSpy.mock.calls.some((call) => call[1]?.method === 'DELETE'),
    ).toBe(false)
    expect(screen.getByText('kid-a')).toBeDefined()
  })

  test('confirming removes the member from the list', async () => {
    fetchSpy = withSession((input, init) => {
      if (
        input === '/api/v1/household-members/2/' &&
        init?.method === 'DELETE'
      ) {
        return new Response(null, { status: 204 })
      }
      const stillThere = !fetchSpy.mock.calls.some(
        (call) =>
          call[0] === '/api/v1/household-members/2/' && call[1]?.method === 'DELETE',
      )
      return jsonResponse(stillThere ? [PARENT_ONE, CHILD_A] : [PARENT_ONE])
    })
    vi.stubGlobal('fetch', fetchSpy)
    renderScreen()

    await waitFor(() => expect(screen.getByText('kid-a')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: 'Delete kid-a' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete account' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(screen.queryByText('kid-a')).toBeNull())
  })
})
