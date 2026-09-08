import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { ApplicationShell } from './application-shell'

afterEach(() => vi.restoreAllMocks())

const thrownDetail =
  'SyntheticError credential-marker request-payload personal-data-marker'

function FragileContent({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) {
    throw new Error(thrownDetail)
  }

  return <p>Recovered content</p>
}

describe('ShellBoundary', () => {
  test('focuses one generic alert without exposing thrown details', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)

    const { container } = render(
      <ApplicationShell contentKey="broken">
        <FragileContent shouldThrow />
      </ApplicationShell>,
    )
    const alert = await screen.findByRole('alert')

    expect(screen.getAllByRole('main')).toHaveLength(1)
    expect(screen.getByRole('banner')).toBeDefined()
    expect(screen.getByRole('link', { name: 'Skip to main content' })).toBeDefined()
    expect(
      screen.getByRole('heading', { name: 'Something went wrong' }),
    ).toBeDefined()
    expect(screen.getByText('We could not show this page. Try again.')).toBeDefined()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeDefined()
    await waitFor(() => expect(document.activeElement).toBe(alert))

    for (const forbidden of [
      thrownDetail,
      'SyntheticError',
      'credential-marker',
      'request-payload',
      'personal-data-marker',
    ]) {
      expect(container.innerHTML).not.toContain(forbidden)
      expect(alert.textContent).not.toContain(forbidden)
    }
  })

  test('recovers on retry and focuses main after successful content renders', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    let shouldThrow = true

    function MutableContent() {
      return <FragileContent shouldThrow={shouldThrow} />
    }

    render(
      <ApplicationShell contentKey="retry">
        <MutableContent />
      </ApplicationShell>,
    )
    const alert = await screen.findByRole('alert')
    await waitFor(() => expect(document.activeElement).toBe(alert))

    shouldThrow = false
    const retry = screen.getByRole('button', { name: 'Try again' })
    retry.focus()
    fireEvent.click(retry)

    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
    expect(screen.getByText('Recovered content')).toBeDefined()
    expect(document.activeElement).toBe(screen.getByRole('main'))
  })

  test('returns one focused fallback when retry fails again', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)

    render(
      <ApplicationShell contentKey="repeat-failure">
        <FragileContent shouldThrow />
      </ApplicationShell>,
    )
    const firstAlert = await screen.findByRole('alert')
    await waitFor(() => expect(document.activeElement).toBe(firstAlert))

    const retry = screen.getByRole('button', { name: 'Try again' })
    retry.focus()
    fireEvent.click(retry)

    await waitFor(() => {
      const alerts = screen.getAllByRole('alert')
      expect(alerts).toHaveLength(1)
      expect(document.activeElement).toBe(alerts[0])
    })
    expect(screen.getAllByRole('button', { name: 'Try again' })).toHaveLength(1)
  })

  test('clears a stale fallback when logical content changes', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const { rerender } = render(
      <ApplicationShell contentKey="broken">
        <FragileContent shouldThrow />
      </ApplicationShell>,
    )
    await screen.findByRole('alert')

    rerender(
      <ApplicationShell contentKey="working">
        <FragileContent shouldThrow={false} />
      </ApplicationShell>,
    )

    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
    expect(screen.getByText('Recovered content')).toBeDefined()
    expect(document.activeElement).toBe(screen.getByRole('main'))
  })
})
