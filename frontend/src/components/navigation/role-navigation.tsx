/**
 * The primary navigation list.
 *
 * Presentational only: it renders entries that have already been filtered for
 * the viewer. It decides no permission, reads no cookie or storage, fetches
 * nothing, and never derives a role from a username, a URL, the DOM, or a
 * label. Route visibility is usability, not authorisation.
 */

import type { MouseEvent } from 'react'

export interface RoleNavigationEntry {
  path: string
  label: string
}

export interface RoleNavigationProps {
  /** Already-filtered entries, in the order they must appear. */
  entries: readonly RoleNavigationEntry[]
  /** The entry that is currently open, or `null` when none is. */
  currentPath: string | null
  onNavigate: (event: MouseEvent<HTMLAnchorElement>) => void
}

export function RoleNavigation({
  currentPath,
  entries,
  onNavigate,
}: RoleNavigationProps) {
  if (entries.length === 0) {
    return null
  }

  return (
    <nav aria-label="Primary navigation" className="primary-navigation">
      <ul className="primary-navigation-list">
        {entries.map((entry) => (
          <li key={entry.path}>
            <a
              aria-current={entry.path === currentPath ? 'page' : undefined}
              className="primary-navigation-link"
              href={entry.path}
              onClick={onNavigate}
            >
              {entry.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  )
}
