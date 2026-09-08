/// <reference types="node" />

import { readFileSync } from 'node:fs'

import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import App from './App'
import { createQueryClient } from './api/query-client'
import { inlineFavicon } from '../vite.config'

const clients: ReturnType<typeof createQueryClient>[] = []

const renderApp = () => {
  const client = createQueryClient()
  clients.push(client)
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  )
}

beforeEach(() =>
  vi.stubGlobal(
    'fetch',
    vi.fn(() => new Promise<Response>(() => undefined)),
  ),
)
afterEach(() => {
  for (const client of clients.splice(0)) client.clear()
  vi.unstubAllGlobals()
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

describe('visual-token reference page', () => {
  test('uses one main, one product heading, and labelled reference sections', () => {
    const { container } = renderApp()

    expect(container.querySelectorAll('main')).toHaveLength(1)
    expect(screen.getAllByRole('banner')).toHaveLength(1)
    expect(screen.queryByRole('navigation')).toBeNull()
    expect(
      screen.getByRole('link', { name: 'Skip to main content' }),
    ).toBeDefined()
    expect(
      screen.getAllByRole('heading', {
        level: 1,
        name: 'Chorum-murohc',
      }),
    ).toHaveLength(1)
    expect(screen.getByText(/visual-token reference/i)).toBeDefined()

    for (const name of [
      'Colours',
      'Typography',
      'Spacing and shape',
      'Interaction states',
      'Motion',
      'Shared interface primitives',
      'Service connection',
    ]) {
      expect(screen.getByRole('region', { name })).toBeDefined()
    }
  })

  test('visibly labels every token family and non-colour state', () => {
    renderApp()

    for (const label of [
      'surface',
      'surface-muted',
      'foreground',
      'foreground-muted',
      'accent',
      'accent-hover',
      'on-accent',
      'success',
      'warning',
      'danger',
      'border',
      'focus',
      'text-sm',
      'text-body',
      'text-lead',
      'text-heading-2',
      'text-heading-1',
      'spacing-1',
      'spacing-2',
      'spacing-3',
      'spacing-4',
      'spacing-6',
      'spacing-8',
      'spacing-12',
      'radius-sm',
      'radius-md',
      'radius-lg',
      'elevation-sm',
      'elevation-md',
    ]) {
      expect(screen.getByText(label, { exact: true })).toBeDefined()
    }

    expect(screen.getAllByText(/^Success:/).length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText(/^Warning:/)).toBeDefined()
    expect(screen.getByText(/^Danger:/)).toBeDefined()
    expect(screen.getByText(/decorative and finite/i)).toBeDefined()
  })

  test('uses shared native controls with enabled, disabled, and busy states', () => {
    renderApp()

    const primary = screen.getByRole('button', { name: 'Primary action' })
    const secondary = screen.getByRole('button', { name: 'Secondary action' })
    const disabled = screen.getByRole('button', { name: 'Disabled action' })
    const busy = screen.getByRole('button', { name: 'Saving…' })

    expect(primary).toHaveProperty('disabled', false)
    expect(secondary).toHaveProperty('disabled', false)
    expect(disabled).toHaveProperty('disabled', true)
    expect(busy).toHaveProperty('disabled', true)
    expect(busy.getAttribute('aria-busy')).toBe('true')

    primary.focus()
    expect(document.activeElement).toBe(primary)
    disabled.focus()
    expect(document.activeElement).toBe(primary)
  })

  test('renders labelled inputs, messages, card content, and a dialog trigger', () => {
    renderApp()

    expect(
      screen.getByRole('textbox', { name: 'Household display name' }),
    ).toBeDefined()
    const invalid = screen.getByRole('textbox', { name: 'Reference code' })
    expect(invalid.getAttribute('aria-invalid')).toBe('true')
    expect(invalid.getAttribute('aria-describedby')).toBe('reference-error')
    expect(
      screen.getByRole('textbox', { name: 'Disabled example' }),
    ).toHaveProperty('disabled', true)
    expect(screen.getByRole('alert').textContent).toMatch(/^Error:/)
    expect(
      screen
        .getByText('Success: Shared primitives are ready.')
        .closest('[role="status"]'),
    ).toBeDefined()
    expect(screen.getByRole('heading', { name: 'Composable card' })).toBeDefined()
    expect(screen.getByText('A quiet surface for grouped content.')).toBeDefined()
    expect(screen.getByRole('button', { name: 'Open reference dialog' })).toBeDefined()
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
    ] as const

    for (const [foreground, background, threshold, recorded] of pairs) {
      const ratio = contrastRatio(colour(foreground), colour(background))

      expect(ratio).toBeGreaterThanOrEqual(threshold)
      expect(Number(ratio.toFixed(2))).toBeGreaterThanOrEqual(recorded)
    }
  })

  test('defines accessible focus, target, motion, and reduced-motion rules', () => {
    const stylesheet = readSource('./styles.css')

    expect(stylesheet).toMatch(
      /\.ui-button\s*\{[\s\S]*?min-block-size:\s*var\(--spacing-12\);[\s\S]*?min-inline-size:\s*var\(--spacing-12\);/,
    )
    expect(stylesheet).toMatch(
      /\.ui-button:focus-visible,[\s\S]*?outline:\s*var\(--focus-ring-width\) solid var\(--color-focus\);[\s\S]*?outline-offset:\s*var\(--focus-ring-offset\);/,
    )
    expect(stylesheet).not.toMatch(/outline:\s*(?:0|none)/)
    expect(stylesheet).toMatch(/\.ui-button-primary:hover\s*\{/)
    expect(stylesheet).toMatch(/\.ui-button-primary:active\s*\{/)
    expect(stylesheet).toMatch(
      /\.motion-marker\s*\{[\s\S]*?animation:[^;]*var\(--duration-normal\)[^;]*3 alternate;/,
    )
    expect(stylesheet).toMatch(
      /\.ui-button\s*\{[\s\S]*?transition:[^;]*var\(--duration-fast\)/,
    )
    expect(stylesheet).toMatch(
      /@media\s*\(prefers-reduced-motion:\s*reduce\)[\s\S]*?scroll-behavior:\s*auto[^}]*\}[\s\S]*?animation-duration:\s*0\.01ms !important;[\s\S]*?animation-iteration-count:\s*1 !important;[\s\S]*?transition-duration:\s*0\.01ms !important;/,
    )
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
