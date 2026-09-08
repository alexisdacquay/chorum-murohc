import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { ApplicationShell } from './application-shell'

describe('ApplicationShell', () => {
  test('renders the skip link, banner, and one focusable main in document order', () => {
    const existingFocus = document.createElement('button')
    existingFocus.textContent = 'Existing focus'
    document.body.append(existingFocus)
    existingFocus.focus()

    const { container } = render(
      <ApplicationShell contentKey="reference">
        <button type="button">Content action</button>
      </ApplicationShell>,
    )

    const skipLink = screen.getByRole('link', { name: 'Skip to main content' })
    const banner = screen.getByRole('banner')
    const main = screen.getByRole('main')
    const productName = screen.getByText('Chorum-murohc')

    expect(document.activeElement).toBe(existingFocus)
    expect(container.children[0]).toBe(skipLink)
    expect(container.children[1]).toBe(banner)
    expect(container.children[2]).toBe(main)
    expect(container.querySelectorAll('main')).toHaveLength(1)
    expect(screen.queryByRole('navigation')).toBeNull()
    expect(productName.closest('a, button')).toBeNull()
    expect(main.id).toBe('main-content')
    expect(main.tabIndex).toBe(-1)

    fireEvent.click(skipLink)
    expect(document.activeElement).toBe(main)

    existingFocus.remove()
  })

  test('moves focus once for a distinct content key and not for other updates', () => {
    const { rerender } = render(
      <ApplicationShell contentKey="first">
        <button type="button">First content</button>
      </ApplicationShell>,
    )
    const main = screen.getByRole('main')
    const skipLink = screen.getByRole('link', { name: 'Skip to main content' })
    const focusMain = vi.spyOn(main, 'focus')

    skipLink.focus()
    rerender(
      <ApplicationShell contentKey="first">
        <button type="button">Updated content</button>
      </ApplicationShell>,
    )
    expect(document.activeElement).toBe(skipLink)
    expect(focusMain).not.toHaveBeenCalled()

    rerender(
      <ApplicationShell contentKey="first" isLoading>
        <button type="button">Updated content</button>
      </ApplicationShell>,
    )
    expect(document.activeElement).toBe(skipLink)
    expect(focusMain).not.toHaveBeenCalled()

    rerender(
      <ApplicationShell contentKey="second">
        <button type="button">Second content</button>
      </ApplicationShell>,
    )
    expect(document.activeElement).toBe(main)
    expect(focusMain).toHaveBeenCalledOnce()

    rerender(
      <ApplicationShell contentKey="second">
        <button type="button">Second content updated</button>
      </ApplicationShell>,
    )
    expect(focusMain).toHaveBeenCalledOnce()
  })

  test('keeps shell landmarks and focus while exposing polite loading state', () => {
    const existingFocus = document.createElement('button')
    existingFocus.textContent = 'Existing loading focus'
    document.body.append(existingFocus)
    existingFocus.focus()

    const { rerender } = render(
      <ApplicationShell contentKey="reference" isLoading>
        <p>Reference content</p>
      </ApplicationShell>,
    )
    const skipLink = screen.getByRole('link', { name: 'Skip to main content' })
    const main = screen.getByRole('main')

    expect(document.activeElement).toBe(existingFocus)
    skipLink.focus()
    expect(screen.getByRole('banner')).toBeDefined()
    expect(main.getAttribute('aria-busy')).toBe('true')
    expect(screen.getAllByRole('status')).toHaveLength(1)
    expect(screen.getByRole('status').textContent).toBe('Loading…')
    expect(screen.queryByText('Reference content')).toBeNull()
    expect(document.activeElement).toBe(skipLink)

    rerender(
      <ApplicationShell contentKey="reference">
        <p>Reference content</p>
      </ApplicationShell>,
    )
    expect(main.getAttribute('aria-busy')).toBeNull()
    expect(screen.queryByText('Loading…')).toBeNull()
    expect(screen.getByText('Reference content')).toBeDefined()
    expect(document.activeElement).toBe(skipLink)

    existingFocus.remove()
  })
})
