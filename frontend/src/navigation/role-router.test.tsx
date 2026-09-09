import { act, fireEvent, render, screen, within } from '@testing-library/react'
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  test,
  vi,
  type MockInstance,
} from 'vitest'

import {
  ROUTE_TABLE,
  RoleRouter,
  SIGNED_OUT_SESSION,
  resolveRoute,
  resolveViewerRole,
  type SessionSnapshot,
} from './role-router'

const PARENT_LABELS = [
  'Overview',
  'Approvals',
  'Chore pool',
  'Reward requests',
  'Household',
  'Activity',
  'Approval PIN',
  'Change password',
]
const CHILD_LABELS = ['Chores', 'Points', 'Rewards', 'Levels', 'Creature']

const signedIn = (role: unknown): Record<string, unknown> => ({
  is_authenticated: true,
  user: { id: 7, username: 'test-user' },
  household: { id: 3, name: 'Test household' },
  role,
})

const parent = signedIn('parent')
const child = signedIn('child')

let pushState: MockInstance
let replaceState: MockInstance

const goTo = (url: string) => window.history.replaceState(null, '', url)

const renderAt = (url: string, props: Parameters<typeof RoleRouter>[0]) => {
  goTo(url)
  pushState.mockClear()
  replaceState.mockClear()
  return render(<RoleRouter {...props} />)
}

const linkNames = () =>
  screen
    .queryAllByRole('navigation')
    .flatMap((navigation) =>
      within(navigation)
        .getAllByRole('link')
        .map((link) => link.textContent),
    )

beforeEach(() => {
  goTo('/')
  pushState = vi.spyOn(window.history, 'pushState')
  replaceState = vi.spyOn(window.history, 'replaceState')
})

afterEach(() => {
  vi.restoreAllMocks()
  window.history.replaceState(null, '', '/')
})

describe('resolveViewerRole', () => {
  test('accepts only an authenticated, housed, supported role', () => {
    expect(resolveViewerRole(parent)).toBe('parent')
    expect(resolveViewerRole(child)).toBe('child')
  })

  test('fails closed for every other reported state', () => {
    const cases: Array<[string, unknown]> = [
      ['signed out', SIGNED_OUT_SESSION],
      ['missing body', null],
      ['undefined body', undefined],
      ['non-object body', 'parent'],
      ['array body', []],
      ['inactive or unauthenticated user', { ...signedIn('parent'), is_authenticated: false }],
      ['authenticated flag as a string', { ...signedIn('parent'), is_authenticated: 'true' }],
      ['missing user', { ...signedIn('parent'), user: null }],
      ['no resolved household', { ...signedIn('parent'), household: null }],
      ['missing role', signedIn(null)],
      ['unsupported role', signedIn('supervisor')],
      ['role of the wrong type', signedIn(1)],
      ['empty object', {}],
    ]

    for (const [name, value] of cases) {
      expect(resolveViewerRole(value), name).toBeNull()
    }
  })
})

describe('resolveRoute', () => {
  test('sends every path to the signed-out destination without a role', () => {
    for (const path of ['/', '/sign-in', '/household', '/chores/', '/nope']) {
      expect(resolveRoute(path, null)).toEqual({
        view: 'sign-in',
        canonicalPath: '/sign-in',
        entry: null,
        contentKey: 'sign-in',
      })
    }
  })

  test('resolves the approved table for each role', () => {
    for (const entry of ROUTE_TABLE) {
      expect(resolveRoute(entry.path, entry.role)).toEqual({
        view: 'screen',
        canonicalPath: entry.path,
        entry,
        contentKey: entry.path,
      })
    }
  })

  test('rewrites the root and a trailing slash, and rejects other spellings', () => {
    expect(resolveRoute('/', 'parent').canonicalPath).toBe('/overview')
    expect(resolveRoute('/', 'child').canonicalPath).toBe('/chores')
    expect(resolveRoute('/chores/', 'child')).toMatchObject({
      view: 'screen',
      canonicalPath: '/chores',
    })
    expect(resolveRoute('/CHORES', 'child')).toMatchObject({
      view: 'not-found',
      canonicalPath: '/CHORES',
    })
    expect(resolveRoute('/chores//', 'child')).toMatchObject({
      view: 'not-found',
      canonicalPath: '/chores//',
    })
  })

  test('gives one identical answer for an unknown and a cross-role path', () => {
    const unknown = resolveRoute('/nope', 'parent')

    expect(unknown.view).toBe('not-found')
    expect(resolveRoute('/rewards', 'parent').view).toBe('not-found')
    expect(resolveRoute('/approvals', 'child').view).toBe('not-found')
    expect(resolveRoute('/rewards', 'parent').contentKey).toBe(
      unknown.contentKey,
    )
  })

  test('sends a viewer who already has a role off the signed-out path', () => {
    expect(resolveRoute('/sign-in', 'parent')).toMatchObject({
      view: 'screen',
      canonicalPath: '/overview',
    })
    expect(resolveRoute('/sign-in/', 'child')).toMatchObject({
      view: 'screen',
      canonicalPath: '/chores',
    })
  })
})

describe('RoleRouter signed-out and fail-closed states', () => {
  test('replaces a protected path with the signed-out destination', () => {
    renderAt('/household', { currentUser: SIGNED_OUT_SESSION })

    expect(window.location.pathname).toBe('/sign-in')
    expect(replaceState).toHaveBeenCalledWith(null, '', '/sign-in')
    expect(pushState).not.toHaveBeenCalled()
    expect(screen.queryByRole('navigation')).toBeNull()
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      'Sign in',
    )
    for (const label of [...PARENT_LABELS, ...CHILD_LABELS]) {
      expect(screen.queryByText(label)).toBeNull()
    }
  })

  test('replaces the site root with the signed-out destination', () => {
    renderAt('/', { currentUser: SIGNED_OUT_SESSION })

    expect(window.location.pathname).toBe('/sign-in')
    expect(screen.queryByRole('navigation')).toBeNull()
  })

  test('shows the same result for every fail-closed report', () => {
    const failClosed: unknown[] = [
      SIGNED_OUT_SESSION,
      { ...signedIn('parent'), is_authenticated: false },
      { ...signedIn('parent'), household: null },
      signedIn(null),
      signedIn('supervisor-9000'),
      null,
      'parent',
    ]
    const rendered = failClosed.map((currentUser) => {
      const view = renderAt('/overview', { currentUser })
      const markup = view.container.innerHTML
      const pathname = window.location.pathname
      view.unmount()
      return { markup, pathname }
    })

    for (const result of rendered) {
      expect(result.pathname).toBe('/sign-in')
      expect(result.markup).toBe(rendered[0].markup)
      expect(result.markup).not.toContain('supervisor-9000')
      expect(result.markup).not.toContain('test-user')
      expect(result.markup).not.toContain('Test household')
    }
  })

  test('shows the shell loading state and nothing else while the session loads', () => {
    renderAt('/', { currentUser: undefined, isLoading: true })

    expect(screen.getByRole('status').textContent).toContain('Loading')
    expect(screen.getByRole('main').getAttribute('aria-busy')).toBe('true')
    expect(screen.queryByRole('navigation')).toBeNull()
    expect(screen.queryByRole('heading', { level: 1 })).toBeNull()
  })

  test('leaves a directly loaded route alone while the session is still pending, then opens it (A-03)', () => {
    goTo('/points')
    pushState.mockClear()
    replaceState.mockClear()
    const { rerender } = render(
      <RoleRouter currentUser={undefined} isLoading />,
    )

    // The bug: role is unresolved while loading, so every path looks
    // signed-out. Acting on that before the session settles would rewrite
    // a bookmark, refresh, or shared link to /sign-in and lose it for
    // good, even though the viewer turns out to be allowed on it.
    expect(window.location.pathname).toBe('/points')
    expect(replaceState).not.toHaveBeenCalled()

    rerender(<RoleRouter currentUser={child} isLoading={false} />)

    expect(window.location.pathname).toBe('/points')
    expect(replaceState).not.toHaveBeenCalled()
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      'Points',
    )
  })
})

describe('RoleRouter allowed roles', () => {
  test('gives a parent exactly the parent entries in order from the parent start', () => {
    renderAt('/', { currentUser: parent })

    expect(window.location.pathname).toBe('/overview')
    expect(linkNames()).toEqual(PARENT_LABELS)
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      'Overview',
    )
    for (const label of CHILD_LABELS) {
      expect(screen.queryByRole('link', { name: label })).toBeNull()
    }
  })

  test('gives a child exactly the child entries in order from the child start', () => {
    renderAt('/', { currentUser: child })

    expect(window.location.pathname).toBe('/chores')
    expect(linkNames()).toEqual(CHILD_LABELS)
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Chores')
    for (const label of PARENT_LABELS) {
      expect(screen.queryByRole('link', { name: label })).toBeNull()
    }
  })

  test('marks exactly one entry as the current page', () => {
    renderAt('/points', { currentUser: child })

    const current = screen
      .getAllByRole('link')
      .filter((link) => link.getAttribute('aria-current') === 'page')

    expect(current).toHaveLength(1)
    expect(current[0].textContent).toBe('Points')
    expect(current[0].getAttribute('href')).toBe('/points')
  })

  test('shows every approved destination as a neutral placeholder', () => {
    for (const entry of ROUTE_TABLE) {
      const view = renderAt(entry.path, {
        currentUser: signedIn(entry.role),
      })

      expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
        entry.label,
      )
      expect(screen.getByRole('main').textContent).toBe(
        `${entry.label}This screen is not built yet.`,
      )
      view.unmount()
    }
  })
})

describe('RoleRouter denied and unknown paths', () => {
  test('answers a cross-role path exactly as it answers an unknown path', () => {
    const denied = renderAt('/rewards', { currentUser: parent })
    const deniedMain = screen.getByRole('main').innerHTML
    const deniedPath = window.location.pathname
    denied.unmount()

    const unknown = renderAt('/nope', { currentUser: parent })
    const unknownMain = screen.getByRole('main').innerHTML

    expect(deniedPath).toBe('/rewards')
    expect(window.location.pathname).toBe('/nope')
    expect(deniedMain).toBe(unknownMain)
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      'Page not found',
    )
    expect(screen.getByRole('main').textContent).not.toContain('nope')
    expect(screen.getByRole('link', { name: 'Go to Overview' })).toBeDefined()
    unknown.unmount()

    renderAt('/approvals', { currentUser: child })
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      'Page not found',
    )
    expect(screen.getByRole('link', { name: 'Go to Chores' })).toBeDefined()
    expect(
      screen
        .getAllByRole('link')
        .filter((link) => link.hasAttribute('aria-current')),
    ).toHaveLength(0)
  })

  test('canonicalises a trailing slash and rejects a different case', () => {
    const canonical = renderAt('/chores/', { currentUser: child })

    expect(window.location.pathname).toBe('/chores')
    expect(replaceState).toHaveBeenCalledWith(null, '', '/chores')
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Chores')
    canonical.unmount()

    renderAt('/CHORES', { currentUser: child })
    expect(window.location.pathname).toBe('/CHORES')
    expect(replaceState).not.toHaveBeenCalled()
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      'Page not found',
    )
  })

  test('ignores a query string and a fragment entirely', () => {
    renderAt('/chores?next=/household#x', { currentUser: child })

    expect(window.location.pathname).toBe('/chores')
    expect(window.location.search).toBe('?next=/household')
    expect(window.location.hash).toBe('#x')
    expect(replaceState).not.toHaveBeenCalled()
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Chores')
    expect(document.body.innerHTML).not.toContain('next=')
    expect(document.body.innerHTML).not.toContain('#x')
    expect(screen.queryByRole('link', { name: 'Household' })).toBeNull()
  })

  test('drops a query string when it rewrites a fail-closed URL', () => {
    renderAt('/household?next=/activity', { currentUser: SIGNED_OUT_SESSION })

    expect(replaceState).toHaveBeenCalledWith(null, '', '/sign-in')
    expect(window.location.pathname).toBe('/sign-in')
    expect(window.location.search).toBe('')
  })
})

describe('RoleRouter history and focus', () => {
  test('pushes one entry, moves the current marker, and focuses main once', () => {
    renderAt('/overview', { currentUser: parent })

    const main = screen.getByRole('main')
    const focusMain = vi.spyOn(main, 'focus')

    fireEvent.click(screen.getByRole('link', { name: 'Approvals' }))

    expect(pushState).toHaveBeenCalledExactlyOnceWith(null, '', '/approvals')
    expect(replaceState).not.toHaveBeenCalled()
    expect(window.location.pathname).toBe('/approvals')
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      'Approvals',
    )
    expect(
      screen
        .getByRole('link', { name: 'Approvals' })
        .getAttribute('aria-current'),
    ).toBe('page')
    expect(
      screen
        .getByRole('link', { name: 'Overview' })
        .getAttribute('aria-current'),
    ).toBeNull()
    expect(focusMain).toHaveBeenCalledOnce()
    expect(screen.getByRole('main')).toBe(main)
  })

  test('prevents the document reload an ordinary activation would cause', () => {
    renderAt('/overview', { currentUser: parent })

    const activation = fireEvent.click(
      screen.getByRole('link', { name: 'Household' }),
    )

    expect(activation).toBe(false)
  })

  test('adds no entry and moves no focus when the current route is activated', () => {
    renderAt('/overview', { currentUser: parent })

    const focusMain = vi.spyOn(screen.getByRole('main'), 'focus')
    const activation = fireEvent.click(
      screen.getByRole('link', { name: 'Overview' }),
    )

    expect(activation).toBe(false)
    expect(pushState).not.toHaveBeenCalled()
    expect(replaceState).not.toHaveBeenCalled()
    expect(window.location.pathname).toBe('/overview')
    expect(focusMain).not.toHaveBeenCalled()
  })

  test('resolves the table again on back and forward, focusing main once each', async () => {
    renderAt('/overview', { currentUser: parent })

    const focusMain = vi.spyOn(screen.getByRole('main'), 'focus')

    fireEvent.click(screen.getByRole('link', { name: 'Activity' }))
    expect(window.location.pathname).toBe('/activity')
    expect(focusMain).toHaveBeenCalledOnce()

    await act(async () => {
      window.history.back()
      await new Promise((resolve) => setTimeout(resolve, 50))
    })
    expect(window.location.pathname).toBe('/overview')
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      'Overview',
    )
    expect(
      screen
        .getByRole('link', { name: 'Overview' })
        .getAttribute('aria-current'),
    ).toBe('page')
    expect(focusMain).toHaveBeenCalledTimes(2)

    await act(async () => {
      window.history.forward()
      await new Promise((resolve) => setTimeout(resolve, 50))
    })
    expect(window.location.pathname).toBe('/activity')
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      'Activity',
    )
    expect(focusMain).toHaveBeenCalledTimes(3)
  })

  test('leaves modified, non-primary, targeted, download, and external activation native', () => {
    renderAt('/overview', { currentUser: parent })

    // A document-level listener records whether the router prevented the
    // activation and then stops jsdom attempting a real navigation, so the
    // native cases are observed without leaving the test document.
    const intercepted: boolean[] = []
    const record = (event: Event) => {
      intercepted.push(event.defaultPrevented)
      event.preventDefault()
    }

    document.addEventListener('click', record)
    try {
      const link = screen.getByRole('link', { name: 'Approvals' })

      for (const init of [
        { metaKey: true },
        { ctrlKey: true },
        { shiftKey: true },
        { altKey: true },
        { button: 1 },
      ]) {
        fireEvent.click(link, init)
      }

      link.setAttribute('target', '_blank')
      fireEvent.click(link)
      link.removeAttribute('target')

      link.setAttribute('download', '')
      fireEvent.click(link)
      link.removeAttribute('download')

      link.setAttribute('href', 'https://example.invalid/approvals')
      fireEvent.click(link)
      link.setAttribute('href', '/approvals')

      // A plain activation of the same link proves the recording listener is
      // not what kept the other seven native.
      fireEvent.click(link)
    } finally {
      document.removeEventListener('click', record)
    }

    expect(intercepted).toEqual([
      false,
      false,
      false,
      false,
      false,
      false,
      false,
      false,
      true,
    ])
    expect(pushState).toHaveBeenCalledExactlyOnceWith(null, '', '/approvals')
    expect(window.location.pathname).toBe('/approvals')
  })

  test('recovers from a not-found path through the offered start link', () => {
    renderAt('/nope', { currentUser: child })

    fireEvent.click(screen.getByRole('link', { name: 'Go to Chores' }))

    expect(pushState).toHaveBeenCalledExactlyOnceWith(null, '', '/chores')
    expect(window.location.pathname).toBe('/chores')
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Chores')
  })
})

describe('RoleRouter role and session changes', () => {
  test('removes the previous links and content in the same render', () => {
    goTo('/overview')
    const { rerender } = render(<RoleRouter currentUser={parent} />)

    expect(linkNames()).toEqual(PARENT_LABELS)

    rerender(<RoleRouter currentUser={child} />)

    expect(screen.queryByRole('link', { name: 'Overview' })).toBeNull()
    expect(linkNames()).toEqual(CHILD_LABELS)
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      'Page not found',
    )
  })

  test('drops to the signed-out state when a membership disappears', () => {
    goTo('/overview')
    const { rerender } = render(<RoleRouter currentUser={parent} />)

    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      'Overview',
    )

    rerender(<RoleRouter currentUser={SIGNED_OUT_SESSION} />)

    expect(screen.queryByRole('navigation')).toBeNull()
    for (const label of PARENT_LABELS) {
      expect(screen.queryByText(label)).toBeNull()
    }
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      'Sign in',
    )
    expect(window.location.pathname).toBe('/sign-in')
  })

  test('keeps the shell contract: one banner, one main, skip link first', () => {
    const { container } = renderAt('/overview', { currentUser: parent })

    const skipLink = screen.getByRole('link', { name: 'Skip to main content' })

    expect(container.children[0]).toBe(skipLink)
    expect(screen.getAllByRole('banner')).toHaveLength(1)
    expect(container.querySelectorAll('main')).toHaveLength(1)
    expect(screen.getAllByRole('navigation')).toHaveLength(1)
    expect(document.activeElement).toBe(document.body)

    const banner = screen.getByRole('banner')
    const navigation = screen.getByRole('navigation')
    const focusable = [
      skipLink,
      ...within(navigation).getAllByRole('link'),
    ]

    expect(banner.contains(navigation)).toBe(true)
    for (const element of focusable) {
      element.focus()
      expect(document.activeElement).toBe(element)
    }

    fireEvent.click(skipLink)
    expect(document.activeElement).toBe(screen.getByRole('main'))
  })
})

describe('RoleRouter composition slots', () => {
  test('shows the supplied sign-in screen instead of its own panel', () => {
    renderAt('/household', {
      currentUser: SIGNED_OUT_SESSION,
      signInScreen: <p>Supplied sign-in screen</p>,
    })

    expect(window.location.pathname).toBe('/sign-in')
    expect(screen.getByText('Supplied sign-in screen')).toBeDefined()
    expect(screen.queryByText('This screen is not built yet.')).toBeNull()
  })

  test('rewrites a role-resolved viewer away from the signed-out path', () => {
    renderAt('/sign-in', {
      currentUser: parent,
      signInScreen: <p>Supplied sign-in screen</p>,
    })

    expect(window.location.pathname).toBe('/overview')
    expect(replaceState).toHaveBeenCalledWith(null, '', '/overview')
    expect(screen.queryByText('Supplied sign-in screen')).toBeNull()
    expect(screen.queryByText('Page not found')).toBeNull()
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      'Overview',
    )
  })

  test('renders a supplied screen for its exact path only, placeholder elsewhere', () => {
    const built = renderAt('/chore-pool', {
      currentUser: parent,
      screens: { '/chore-pool': <p>Built chore pool screen</p> },
    })

    expect(screen.getByText('Built chore pool screen')).toBeDefined()
    expect(screen.queryByText('This screen is not built yet.')).toBeNull()
    built.unmount()

    renderAt('/household', {
      currentUser: parent,
      screens: { '/chore-pool': <p>Built chore pool screen</p> },
    })
    expect(screen.queryByText('Built chore pool screen')).toBeNull()
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      'Household',
    )
  })

  test('shows the session control in the banner only once a role resolves', () => {
    const control = <button type="button">Supplied session control</button>

    const signedOut = renderAt('/sign-in', {
      currentUser: SIGNED_OUT_SESSION,
      sessionControl: control,
    })
    expect(
      screen.queryByRole('button', { name: 'Supplied session control' }),
    ).toBeNull()
    signedOut.unmount()

    const loading = renderAt('/', {
      currentUser: undefined,
      isLoading: true,
      sessionControl: control,
    })
    expect(
      screen.queryByRole('button', { name: 'Supplied session control' }),
    ).toBeNull()
    loading.unmount()

    renderAt('/overview', { currentUser: parent, sessionControl: control })
    const supplied = screen.getByRole('button', {
      name: 'Supplied session control',
    })

    expect(screen.getByRole('banner').contains(supplied)).toBe(true)
    expect(screen.getByRole('main').contains(supplied)).toBe(false)
  })
})

describe('the approved route table', () => {
  test('holds exactly the approved literal paths, labels, and order', () => {
    expect(
      ROUTE_TABLE.map((entry) => [entry.role, entry.path, entry.label]),
    ).toEqual([
      ['parent', '/overview', 'Overview'],
      ['parent', '/approvals', 'Approvals'],
      ['parent', '/chore-pool', 'Chore pool'],
      ['parent', '/reward-requests', 'Reward requests'],
      ['parent', '/household', 'Household'],
      ['parent', '/activity', 'Activity'],
      ['parent', '/approval-pin', 'Approval PIN'],
      ['parent', '/change-password', 'Change password'],
      ['child', '/chores', 'Chores'],
      ['child', '/points', 'Points'],
      ['child', '/rewards', 'Rewards'],
      ['child', '/levels', 'Levels'],
      ['child', '/creature', 'Creature'],
    ])
  })

  test('carries no dynamic, nested, or wildcard path', () => {
    for (const entry of ROUTE_TABLE) {
      expect(entry.path).toMatch(/^\/[a-z][a-z-]*[a-z]$/)
    }
  })

  test('mirrors the exact signed-out body of the session endpoint', () => {
    const signedOut: SessionSnapshot = SIGNED_OUT_SESSION

    expect(signedOut).toEqual({
      is_authenticated: false,
      user: null,
      household: null,
      role: null,
    })
  })
})
