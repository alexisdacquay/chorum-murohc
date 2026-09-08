import { fireEvent, render, screen, within } from '@testing-library/react'
import type { MouseEvent } from 'react'
import { describe, expect, test, vi } from 'vitest'

import { RoleNavigation } from './role-navigation'

const entries = [
  { path: '/chores', label: 'Chores' },
  { path: '/points', label: 'Points' },
  { path: '/rewards', label: 'Rewards' },
]

describe('RoleNavigation', () => {
  test('renders one labelled nav holding a list of native links in order', () => {
    render(
      <RoleNavigation
        currentPath="/points"
        entries={entries}
        onNavigate={() => undefined}
      />,
    )

    const navigation = screen.getByRole('navigation', {
      name: 'Primary navigation',
    })
    const list = within(navigation).getByRole('list')
    const links = within(list).getAllByRole('link')

    expect(screen.getAllByRole('navigation')).toHaveLength(1)
    expect(within(navigation).getAllByRole('list')).toHaveLength(1)
    expect(links.map((link) => link.textContent)).toEqual([
      'Chores',
      'Points',
      'Rewards',
    ])
    for (const link of links) {
      expect(link.tagName).toBe('A')
      expect(link.getAttribute('href')).toMatch(/^\/[a-z-]+$/)
      expect(link.parentElement?.tagName).toBe('LI')
      expect(link.hasAttribute('disabled')).toBe(false)
      expect(link.getAttribute('aria-disabled')).toBeNull()
      expect(link.querySelector('a, button, input')).toBeNull()
    }
    expect(navigation.querySelectorAll('[role]')).toHaveLength(0)
    expect(navigation.querySelectorAll('button')).toHaveLength(0)
  })

  test('marks only the current entry with aria-current', () => {
    render(
      <RoleNavigation
        currentPath="/points"
        entries={entries}
        onNavigate={() => undefined}
      />,
    )

    const current = screen.getAllByRole('link').filter(
      (link) => link.getAttribute('aria-current') === 'page',
    )

    expect(current).toHaveLength(1)
    expect(current[0].textContent).toBe('Points')
    expect(current[0].getAttribute('href')).toBe('/points')
    expect(
      screen.getByRole('link', { name: 'Chores' }).getAttribute('aria-current'),
    ).toBeNull()
  })

  test('marks nothing current when the viewer is not on a listed entry', () => {
    render(
      <RoleNavigation
        currentPath={null}
        entries={entries}
        onNavigate={() => undefined}
      />,
    )

    expect(
      screen
        .getAllByRole('link')
        .filter((link) => link.hasAttribute('aria-current')),
    ).toHaveLength(0)
  })

  test('renders no navigation landmark when there is nothing to show', () => {
    const { container } = render(
      <RoleNavigation
        currentPath={null}
        entries={[]}
        onNavigate={() => undefined}
      />,
    )

    expect(screen.queryByRole('navigation')).toBeNull()
    expect(container.innerHTML).toBe('')
  })

  test('hands every activation to its caller rather than deciding anything', () => {
    const activated: string[] = []
    const onNavigate = vi.fn((event: MouseEvent<HTMLAnchorElement>) => {
      event.preventDefault()
      activated.push(event.currentTarget.pathname)
    })
    render(
      <RoleNavigation
        currentPath="/chores"
        entries={entries}
        onNavigate={onNavigate}
      />,
    )

    fireEvent.click(screen.getByRole('link', { name: 'Rewards' }))
    expect(onNavigate).toHaveBeenCalledOnce()
    expect(activated).toEqual(['/rewards'])
  })
})
