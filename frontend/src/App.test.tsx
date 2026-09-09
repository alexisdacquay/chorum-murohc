/// <reference types="node" />

import { readFileSync } from 'node:fs'

import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import App from './App'
import { createQueryClient } from './api/query-client'
import { CONNECTION_MESSAGE } from './components/auth/sign-in-form'
import { inlineFavicon } from '../vite.config'

// Synthetic values only. Nothing here is a real account or a real token.
const TEST_CSRF_TOKEN = 'test-csrf-token'
const TEST_USERNAME = 'test-parent'
const TEST_PASSWORD = 'test-only-password'

const PARENT_LABELS = [
  'Overview',
  'Approvals',
  'Chore pool',
  'Reward requests',
  'Household',
  'Activity',
  'Approval PIN',
]
const CHILD_LABELS = ['Chores', 'Points', 'Rewards', 'Levels', 'Creature']

const SIGNED_OUT = {
  is_authenticated: false,
  user: null,
  household: null,
  role: null,
}
const PARENT = {
  is_authenticated: true,
  user: { id: 7, username: TEST_USERNAME },
  household: { id: 3, name: 'Test household' },
  role: 'parent',
}
const CHILD = { ...PARENT, user: { id: 8, username: 'test-child' }, role: 'child' }
const EMPTY_OVERVIEW = { children: [], parents: [], pending_total: 0 }

let fetchSpy: ReturnType<typeof vi.fn>

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

const renderApp = () =>
  render(
    <QueryClientProvider client={createQueryClient()}>
      <App />
    </QueryClientProvider>,
  )

/** Ids are generated per render, so they are normalised before comparison. */
const withoutGeneratedIds = (markup: string) =>
  markup.replace(/(id|for|aria-describedby)="[^"]*"/g, '$1="generated"')

const linkNames = () =>
  screen
    .queryAllByRole('navigation')
    .flatMap((navigation) =>
      within(navigation)
        .getAllByRole('link')
        .map((link) => link.textContent),
    )

const signInForm = () =>
  screen.getByRole('heading', { level: 1, name: 'Sign in' }).parentElement
    ?.querySelector('form') as HTMLFormElement

const sessionCalls = () =>
  fetchSpy.mock.calls.filter((call) => call[0] === '/api/v1/auth/session/')

beforeEach(() => {
  window.history.replaceState(null, '', '/')
  clearCookies()
  document.cookie = `csrftoken=${TEST_CSRF_TOKEN}`
  fetchSpy = vi.fn(() => new Promise<Response>(() => undefined))
  vi.stubGlobal('fetch', fetchSpy)
})

afterEach(() => {
  vi.unstubAllGlobals()
  clearCookies()
  window.history.replaceState(null, '', '/')
})

const readSource = (path: string) =>
  readFileSync(new URL(path, import.meta.url), 'utf8')

const parseThemeTokens = (stylesheet: string) => {
  const theme = stylesheet.match(/@theme\s*\{([\s\S]*?)\}/)?.[1] ?? ''

  return Object.fromEntries(
    [...theme.matchAll(/--([a-z0-9*-]+):\s*([^;]+);/g)].map(
      ([, name, value]) => [name, value.trim().replace(/\s+/g, ' ')],
    ),
  )
}

const relativeLuminance = (hex: string) => {
  const channels = hex
    .slice(1)
    .match(/.{2}/g)
    ?.map((channel) => Number.parseInt(channel, 16) / 255)

  if (!channels || channels.length !== 3) {
    throw new Error(`Invalid test colour: ${hex}`)
  }

  const linearChannels = channels.map((channel) =>
    channel <= 0.04045
      ? channel / 12.92
      : ((channel + 0.055) / 1.055) ** 2.4,
  )

  return (
    0.2126 * linearChannels[0] +
    0.7152 * linearChannels[1] +
    0.0722 * linearChannels[2]
  )
}

const contrastRatio = (first: string, second: string) => {
  const lighter = Math.max(
    relativeLuminance(first),
    relativeLuminance(second),
  )
  const darker = Math.min(
    relativeLuminance(first),
    relativeLuminance(second),
  )

  return (lighter + 0.05) / (darker + 0.05)
}

describe('the current session on load', () => {
  test('asks the session endpoint once, same-origin, and shows only loading', () => {
    renderApp()

    expect(fetchSpy).toHaveBeenCalledExactlyOnceWith('/api/v1/auth/session/', {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      method: 'GET',
      signal: expect.any(AbortSignal),
    })
    expect(screen.getByRole('status').textContent).toContain('Loading')
    expect(screen.getByRole('main').getAttribute('aria-busy')).toBe('true')
    expect(screen.queryByRole('navigation')).toBeNull()
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Sign in' })).toBeNull()
    expect(screen.queryByRole('heading', { level: 1 })).toBeNull()
  })

  test('lands a parent on the parent start path with the five parent items', async () => {
    fetchSpy.mockResolvedValue(jsonResponse(PARENT))
    renderApp()

    await waitFor(() => expect(linkNames()).toEqual(PARENT_LABELS))
    expect(window.location.pathname).toBe('/overview')
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      'Overview',
    )
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeDefined()
    expect(screen.queryByLabelText('Password')).toBeNull()
  })

  test('lands a child on the child start path with the five child items', async () => {
    fetchSpy.mockResolvedValue(jsonResponse(CHILD))
    renderApp()

    await waitFor(() => expect(linkNames()).toEqual(CHILD_LABELS))
    expect(window.location.pathname).toBe('/chores')
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Chores')
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeDefined()
  })

  test('rewrites an already-authenticated visitor away from the sign-in path', async () => {
    window.history.replaceState(null, '', '/sign-in')
    fetchSpy.mockResolvedValue(jsonResponse(PARENT))
    renderApp()

    await waitFor(() => expect(window.location.pathname).toBe('/overview'))
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      'Overview',
    )
    expect(screen.queryByLabelText('Username')).toBeNull()
    expect(screen.queryByText('Page not found')).toBeNull()
  })

  test.each([
    ['a signed-out body', SIGNED_OUT],
    ['a malformed body', { is_authenticated: true }],
    ['a null household', { ...PARENT, household: null }],
    ['an unsupported role', { ...PARENT, role: 'supervisor-9000' }],
  ])('shows the one sign-in screen for %s', async (_name, body) => {
    fetchSpy.mockResolvedValue(jsonResponse(body))
    renderApp()

    await waitFor(() => expect(screen.getByLabelText('Username')).toBeDefined())
    expect(window.location.pathname).toBe('/sign-in')
    expect(screen.queryByRole('navigation')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull()
    expect(document.body.textContent).not.toContain('supervisor-9000')
    expect(document.body.textContent).not.toContain('Test household')
    expect(document.body.textContent).not.toContain(TEST_USERNAME)
  })

  test('renders one identical form whether the session is refused or unreachable', async () => {
    const forms: string[] = []

    for (const body of [
      SIGNED_OUT,
      { is_authenticated: true },
      { ...PARENT, household: null },
      { ...PARENT, role: 'supervisor-9000' },
    ]) {
      fetchSpy.mockResolvedValue(jsonResponse(body))
      const view = renderApp()

      await waitFor(() => expect(screen.getByLabelText('Username')).toBeDefined())
      forms.push(withoutGeneratedIds(signInForm().outerHTML))
      view.unmount()
    }

    fetchSpy.mockRejectedValue(new Error('offline'))
    renderApp()
    await waitFor(() => expect(screen.getByLabelText('Username')).toBeDefined())
    forms.push(withoutGeneratedIds(signInForm().outerHTML))

    expect(new Set(forms).size).toBe(1)
  })

  test('offers one recoverable notice with a working retry, and no stuck spinner', async () => {
    fetchSpy.mockRejectedValueOnce(new Error('offline'))
    fetchSpy.mockResolvedValue(jsonResponse(PARENT))
    renderApp()

    await waitFor(() => expect(screen.getByLabelText('Username')).toBeDefined())
    // The spinner is gone, and one recoverable notice took its place.
    expect(screen.getByRole('status').textContent).toContain(CONNECTION_MESSAGE)
    expect(screen.getByRole('status').textContent).not.toContain('Loading')
    expect(screen.getByRole('main').getAttribute('aria-busy')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))

    await waitFor(() => expect(linkNames()).toEqual(PARENT_LABELS))
    expect(sessionCalls()).toHaveLength(2)
    expect(window.location.pathname).toBe('/overview')
  })
})

describe('the sign-in and sign-out journey', () => {
  test('signs a parent in from the form and moves focus to main', async () => {
    fetchSpy.mockImplementation(async (input: string) => {
      if (input === '/api/v1/auth/login/') {
        return jsonResponse(PARENT)
      }
      if (input === '/api/v1/overview/') {
        return jsonResponse(EMPTY_OVERVIEW)
      }
      return jsonResponse(SIGNED_OUT)
    })
    renderApp()

    await waitFor(() => expect(screen.getByLabelText('Username')).toBeDefined())
    fireEvent.change(screen.getByLabelText('Username'), {
      target: { value: TEST_USERNAME },
    })
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: TEST_PASSWORD },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(linkNames()).toEqual(PARENT_LABELS))
    expect(window.location.pathname).toBe('/overview')
    expect(document.activeElement).toBe(screen.getByRole('main'))
    // The login body became the session: one session read, one login post,
    // then the landing overview screen's own read of its own household data.
    await waitFor(() =>
      expect(fetchSpy.mock.calls.map((call) => call[0])).toEqual([
        '/api/v1/auth/session/',
        '/api/v1/auth/login/',
        '/api/v1/overview/',
      ]),
    )
    expect(document.body.textContent).not.toContain(TEST_PASSWORD)
    expect(window.localStorage.length).toBe(0)
    expect(window.sessionStorage.length).toBe(0)
  })

  test('signs a parent out again and removes the navigation', async () => {
    fetchSpy.mockImplementation(async (input: string) =>
      input === '/api/v1/auth/logout/'
        ? new Response(null, { status: 204 })
        : jsonResponse(PARENT),
    )
    renderApp()

    await waitFor(() => expect(linkNames()).toEqual(PARENT_LABELS))
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))

    await waitFor(() => expect(window.location.pathname).toBe('/sign-in'))
    expect(screen.queryByRole('navigation')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull()
    expect(screen.getByLabelText('Username')).toBeDefined()
  })

  test('treats an expired session on sign-out as an ordinary sign-out', async () => {
    fetchSpy.mockImplementation(async (input: string) =>
      input === '/api/v1/auth/logout/'
        ? new Response(null, { status: 403 })
        : jsonResponse(PARENT),
    )
    renderApp()

    await waitFor(() => expect(linkNames()).toEqual(PARENT_LABELS))
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))

    await waitFor(() => expect(window.location.pathname).toBe('/sign-in'))
    expect(screen.queryByRole('alert')?.textContent ?? '').toBe('')
    expect(screen.queryByRole('navigation')).toBeNull()
  })

  test('leaves a viewer where they were when sign-out cannot be reached', async () => {
    fetchSpy.mockImplementation(async (input: string) => {
      if (input === '/api/v1/auth/logout/') {
        throw new Error('offline')
      }
      if (input === '/api/v1/overview/') {
        return jsonResponse(EMPTY_OVERVIEW)
      }
      return jsonResponse(PARENT)
    })
    renderApp()

    await waitFor(() => expect(linkNames()).toEqual(PARENT_LABELS))
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toContain(
        'We could not sign you out',
      ),
    )
    expect(window.location.pathname).toBe('/overview')
    expect(linkNames()).toEqual(PARENT_LABELS)
  })
})

describe('the chore pool screen', () => {
  test('a parent who follows the Chore pool link reaches the built screen', async () => {
    fetchSpy.mockImplementation(async (input: string) =>
      input === '/api/v1/chores/' ? jsonResponse([]) : jsonResponse(PARENT),
    )
    renderApp()

    await waitFor(() => expect(linkNames()).toEqual(PARENT_LABELS))
    fireEvent.click(screen.getByRole('link', { name: 'Chore pool' }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Add chore' })).toBeDefined(),
    )
    expect(window.location.pathname).toBe('/chore-pool')
    expect(screen.queryByText('This screen is not built yet.')).toBeNull()
  })
})

describe('the overview screen and its quick links', () => {
  test('a parent lands on the overview and its quick link reaches chore pool without a reload', async () => {
    fetchSpy.mockImplementation(async (input: string) => {
      if (input === '/api/v1/overview/') {
        return jsonResponse(EMPTY_OVERVIEW)
      }
      if (input === '/api/v1/chores/') {
        return jsonResponse([])
      }
      return jsonResponse(PARENT)
    })
    renderApp()

    await waitFor(() =>
      expect(screen.getByText(/No children in this household yet/)).toBeDefined(),
    )
    const quickLink = screen.getByRole('link', { name: 'Manage chores' })
    expect(quickLink.getAttribute('href')).toBe('/chore-pool')

    fireEvent.click(quickLink)

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Add chore' })).toBeDefined(),
    )
    expect(window.location.pathname).toBe('/chore-pool')
    // Reached through the app's own history push, not a full navigation:
    // the parent nav (present only once the app has mounted) is still there.
    expect(linkNames()).toEqual(PARENT_LABELS)
  })
})

describe('the approval PIN screen', () => {
  test('a parent who follows the Approval PIN link reaches the built screen', async () => {
    fetchSpy.mockResolvedValue(jsonResponse(PARENT))
    renderApp()

    await waitFor(() => expect(linkNames()).toEqual(PARENT_LABELS))
    fireEvent.click(screen.getByRole('link', { name: 'Approval PIN' }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Save PIN' })).toBeDefined(),
    )
    expect(window.location.pathname).toBe('/approval-pin')
    expect(screen.queryByText('This screen is not built yet.')).toBeNull()
  })
})

describe('the composition root itself', () => {
  test('derives no identity, role, or authority from the browser', () => {
    const appSource = readSource('./App.tsx')

    for (const forbidden of [
      /document\.cookie/,
      /localStorage/,
      /sessionStorage/,
      /['"]parent['"]/,
      /['"]child['"]/,
      /location\.search/,
      /URLSearchParams/,
      /SIGNED_OUT_SESSION/,
    ]) {
      expect(appSource).not.toMatch(forbidden)
    }
    expect(appSource).toContain('sessionQueryKey')
  })
})

describe('semantic token source', () => {
  test('inlines a favicon in the generated entry document', () => {
    expect(inlineFavicon()).toEqual([
      {
        tag: 'link',
        attrs: { rel: 'icon', href: 'data:,' },
        injectTo: 'head-prepend',
      },
    ])
  })

  test('declares the exact approved token values once', () => {
    const tokens = parseThemeTokens(readSource('./styles.css'))

    expect(tokens).toEqual({
      'color-*': 'initial',
      'color-surface': '#ffffff',
      'color-surface-muted': '#f1f5f9',
      'color-foreground': '#0f172a',
      'color-foreground-muted': '#475569',
      'color-accent': '#1d4ed8',
      'color-accent-hover': '#1e40af',
      'color-on-accent': '#ffffff',
      'color-success': '#166534',
      'color-warning': '#92400e',
      'color-danger': '#b91c1c',
      'color-border': '#64748b',
      'color-focus': '#2563eb',
      'font-sans':
        'ui-sans-serif, system-ui, sans-serif, "Apple Color Emoji", "Segoe UI Emoji"',
      'font-weight-normal': '400',
      'font-weight-medium': '500',
      'font-weight-bold': '700',
      'text-sm': '0.875rem',
      'text-sm--line-height': '1.25rem',
      'text-body': '1rem',
      'text-body--line-height': '1.5rem',
      'text-lead': '1.125rem',
      'text-lead--line-height': '1.75rem',
      'text-heading-2': '1.5rem',
      'text-heading-2--line-height': '2rem',
      'text-heading-1': '1.875rem',
      'text-heading-1--line-height': '2.25rem',
      'spacing-1': '0.25rem',
      'spacing-2': '0.5rem',
      'spacing-3': '0.75rem',
      'spacing-4': '1rem',
      'spacing-6': '1.5rem',
      'spacing-8': '2rem',
      'spacing-12': '3rem',
      'radius-sm': '0.375rem',
      'radius-md': '0.75rem',
      'radius-lg': '1rem',
      'shadow-sm': '0 1px 2px rgb(15 23 42 / 0.08)',
      'shadow-md': '0 8px 24px rgb(15 23 42 / 0.12)',
      'focus-ring-width': '3px',
      'focus-ring-offset': '2px',
      'duration-fast': '120ms',
      'duration-normal': '200ms',
      'ease-standard': 'cubic-bezier(0, 0, 0.2, 1)',
    })
  })

  test('meets every recorded text and non-text contrast ratio', () => {
    const tokens = parseThemeTokens(readSource('./styles.css'))
    const colour = (name: string) => String(tokens[`color-${name}`])
    const pairs = [
      ['foreground', 'surface', 4.5, 17.85],
      ['foreground-muted', 'surface', 4.5, 7.58],
      ['foreground-muted', 'surface-muted', 4.5, 6.92],
      ['on-accent', 'accent', 4.5, 6.7],
      ['on-accent', 'accent-hover', 4.5, 8.72],
      ['success', 'surface', 4.5, 7.13],
      ['warning', 'surface', 4.5, 7.09],
      ['danger', 'surface', 4.5, 6.47],
      ['border', 'surface', 3, 4.76],
      ['focus', 'surface', 3, 5.17],
      ['accent', 'surface-muted', 4.5, 6.12],
      ['accent-hover', 'surface-muted', 4.5, 7.96],
      ['foreground', 'surface-muted', 4.5, 16.3],
    ] as const

    for (const [foreground, background, threshold, recorded] of pairs) {
      const ratio = contrastRatio(colour(foreground), colour(background))

      expect(ratio).toBeGreaterThanOrEqual(threshold)
      expect(Number(ratio.toFixed(2))).toBeGreaterThanOrEqual(recorded)
    }
  })

  test('defines accessible focus, target, and reduced-motion rules', () => {
    const stylesheet = readSource('./styles.css')

    expect(stylesheet).toMatch(
      /\.ui-button\s*\{[\s\S]*?min-block-size:\s*var\(--spacing-12\);[\s\S]*?min-inline-size:\s*var\(--spacing-12\);/,
    )
    expect(stylesheet).toMatch(
      /\.skip-link:focus-visible,[\s\S]*?\.primary-navigation-link:focus-visible,\s*\.page-panel-link:focus-visible\s*\{\s*outline:\s*var\(--focus-ring-width\) solid var\(--color-focus\);\s*outline-offset:\s*var\(--focus-ring-offset\);/,
    )
    expect(stylesheet).not.toMatch(/outline:\s*(?:0|none)/)
    expect(stylesheet).toMatch(/\.ui-button-primary:hover\s*\{/)
    expect(stylesheet).toMatch(/\.ui-button-primary:active\s*\{/)
    expect(stylesheet).toMatch(
      /\.ui-button\s*\{[\s\S]*?transition:[^;]*var\(--duration-fast\)/,
    )
    expect(stylesheet).toMatch(
      /@media\s*\(prefers-reduced-motion:\s*reduce\)[\s\S]*?scroll-behavior:\s*auto[^}]*\}[\s\S]*?animation-duration:\s*0\.01ms !important;[\s\S]*?animation-iteration-count:\s*1 !important;[\s\S]*?transition-duration:\s*0\.01ms !important;/,
    )
  })

  test('gives the sign-in screen full-width, reachable, motion-free controls', () => {
    const stylesheet = readSource('./styles.css')

    expect(stylesheet).toMatch(
      /\.auth-panel\s*\{[\s\S]*?max-inline-size:\s*calc\(var\(--spacing-12\) \* 10\);/,
    )
    expect(stylesheet).toMatch(
      /\.auth-form\s*\{[\s\S]*?inline-size:\s*100%;\s*min-inline-size:\s*0;/,
    )
    expect(stylesheet).toMatch(
      /\.auth-field\s*\{[\s\S]*?inline-size:\s*100%;\s*min-inline-size:\s*0;/,
    )
    expect(stylesheet).toMatch(
      /\.ui-input\s*\{[\s\S]*?min-block-size:\s*var\(--spacing-12\);/,
    )
    expect(stylesheet).toMatch(
      /\.shell-session-actions\s*\{[\s\S]*?min-inline-size:\s*0;/,
    )
    // No state on these screens is carried by motion, so nothing to reduce.
    expect(stylesheet).not.toMatch(/@keyframes|animation-name|animation:/)
  })

  test('gives navigation links a reachable target and a non-colour current cue', () => {
    const stylesheet = readSource('./styles.css')

    expect(stylesheet).toMatch(
      /\.primary-navigation-link,\s*\.page-panel-link\s*\{[\s\S]*?min-block-size:\s*var\(--spacing-12\);\s*min-inline-size:\s*var\(--spacing-12\);/,
    )
    expect(stylesheet).toMatch(
      /\.primary-navigation-link,\s*\.page-panel-link\s*\{[\s\S]*?overflow-wrap:\s*anywhere;/,
    )
    expect(stylesheet).toMatch(
      /\.primary-navigation-list\s*\{[\s\S]*?flex-wrap:\s*wrap;/,
    )
    expect(stylesheet).toMatch(/\.primary-navigation-link:hover,/)
    expect(stylesheet).toMatch(/\.primary-navigation-link:active,/)

    const current = stylesheet.match(
      /\.primary-navigation-link\[aria-current='page'\]\s*\{([\s\S]*?)\}/,
    )?.[1]

    expect(current).toMatch(/border-block-end-color:/)
    expect(current).toMatch(/font-weight:\s*var\(--font-weight-bold\);/)
    expect(current).toMatch(/text-decoration:\s*none;/)
  })

  test('wires one global stylesheet and one first-party Tailwind plugin', () => {
    const mainSource = readSource('./main.tsx')
    const appSource = readSource('./App.tsx')
    const viteSource = readSource('../vite.config.ts')
    const stylesheetImports = [
      ...mainSource.matchAll(/import\s+['"]([^'"]+\.css)['"]/g),
    ].map((match) => match[1])

    expect(stylesheetImports).toEqual(['./styles.css'])
    expect(appSource).not.toMatch(/\.css['"]/)
    expect(appSource).not.toMatch(/className=[^\n]*\[[^\]]+\]/)
    expect(appSource).not.toMatch(/#[0-9a-f]{3,8}|\b(?:rgb|hsl)a?\(/i)
    expect(viteSource.match(/from '@tailwindcss\/vite'/g)).toHaveLength(1)
    expect(viteSource.match(/tailwindcss\(\)/g)).toHaveLength(1)
    expect(viteSource).toContain(
      'plugins: [react(), tailwindcss(), inlineFaviconPlugin]',
    )
    expect(viteSource).toContain("environment: 'jsdom'")
    expect(viteSource).toContain("setupFiles: './src/test/setup.ts'")
  })
})
