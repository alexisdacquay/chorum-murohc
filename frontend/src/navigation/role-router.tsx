/**
 * Role-aware navigation over the approved literal route table (issue #15).
 *
 * Route visibility is usability, never authorisation. Invariant 10 of the
 * merged permission matrix in `_docs/design.md` is explicit: a frontend
 * route, hidden control, disabled button, cached query result, or local
 * browser state is never an authorisation control. Hiding a parent link from
 * a child is a convenience; every API enforces its own matrix row itself.
 *
 * The current-user value comes from `GET /api/v1/auth/session/` (T027) and
 * crosses a trust boundary, so this module validates it at runtime instead of
 * trusting a static type. Anything that is not an authenticated, active user
 * with one resolved household and a supported role fails closed to the
 * signed-out destination, and none of those cases is distinguishable from
 * another.
 *
 * This module owns URL and role resolution only. It is not a router
 * framework: no nested routes, no loaders, no lazy registry, no plugin API.
 */

import {
  useCallback,
  useEffect,
  useState,
  type MouseEvent,
  type ReactNode,
} from 'react'

import { ApplicationShell } from '../components/layout/application-shell'
import { RoleNavigation } from '../components/navigation/role-navigation'

/** The two roles the session contract can report. Anything else fails closed. */
export type NavigationRole = 'parent' | 'child'

/**
 * The exact body of `GET /api/v1/auth/session/`. `api/session.ts` validates a
 * real response against it; the router still validates whatever it actually
 * receives, because a caller could pass anything.
 */
export interface SessionSnapshot {
  is_authenticated: boolean
  user: { id: number; username: string } | null
  household: { id: number; name: string } | null
  role: string | null
}

/** The one signed-out body the session endpoint returns. */
export const SIGNED_OUT_SESSION: SessionSnapshot = {
  is_authenticated: false,
  user: null,
  household: null,
  role: null,
}

export interface RouteEntry {
  path: string
  label: string
  role: NavigationRole
}

/** The signed-out destination and the single fail-closed landing place. */
const SIGN_IN_PATH = '/sign-in'

/**
 * The product-approved route table, in approved order within each role.
 * Screen owners, recorded here rather than in the interface: /overview #85,
 * /approvals #48, /chore-pool #37, /household #24, /activity #87, /chores
 * #36, /points #49, /rewards #58, /levels #65, /creature #83, /sign-in #28,
 * /approval-pin #30, /change-password #129.
 * /reward-requests is the one addition issue #55 makes: the parent side of
 * the merged rewards feature (fulfil, cancel, and catalogue management) has
 * no earlier route to extend, and cannot share child-only `/rewards`, since
 * every path in this table maps to exactly one role. Its label is "Reward
 * requests" rather than "Rewards": every other entry gives its nav label and
 * screen heading the same words, and the child's own `/rewards` link already
 * owns the shorter name in the same navigation vocabulary.
 */
export const ROUTE_TABLE: readonly RouteEntry[] = [
  { path: '/overview', label: 'Overview', role: 'parent' },
  { path: '/approvals', label: 'Approvals', role: 'parent' },
  { path: '/chore-pool', label: 'Chore pool', role: 'parent' },
  { path: '/reward-requests', label: 'Reward requests', role: 'parent' },
  { path: '/household', label: 'Household', role: 'parent' },
  { path: '/activity', label: 'Activity', role: 'parent' },
  { path: '/approval-pin', label: 'Approval PIN', role: 'parent' },
  { path: '/change-password', label: 'Change password', role: 'parent' },
  { path: '/chores', label: 'Chores', role: 'child' },
  { path: '/points', label: 'Points', role: 'child' },
  { path: '/rewards', label: 'Rewards', role: 'child' },
  { path: '/levels', label: 'Levels', role: 'child' },
  { path: '/creature', label: 'Creature', role: 'child' },
]

/** Every literal path the application answers, including the signed-out one. */
const TABLE_PATHS = new Set<string>([
  SIGN_IN_PATH,
  ...ROUTE_TABLE.map((entry) => entry.path),
])

const START_PATH: Record<NavigationRole, string> = {
  parent: '/overview',
  child: '/chores',
}

const NOT_FOUND_CONTENT_KEY = 'not-found'
const SIGN_IN_CONTENT_KEY = 'sign-in'
const LOADING_CONTENT_KEY = 'loading'

/** The one sentence every unbuilt destination shows. */
const PLACEHOLDER_COPY = 'This screen is not built yet.'

export type RouteView = 'sign-in' | 'screen' | 'not-found'

export interface RouteResolution {
  /** Which of the three panels to render. */
  view: RouteView
  /** The pathname the URL should carry; a rewrite is due when it differs. */
  canonicalPath: string
  /** The approved table entry when the viewer may see this screen. */
  entry: RouteEntry | null
  /**
   * The shell content key. It is built from literals only, so no
   * user-controlled URL text is ever stored or compared as content identity.
   */
  contentKey: string
}

/**
 * Reduce an untrusted session body to a role, or to `null`.
 *
 * `null` covers signed out, an inactive account, a missing or malformed body,
 * no resolved household, several unresolved candidate households, a stale or
 * deleted membership, and any role outside `parent` and `child`. They all
 * behave identically on purpose.
 */
export function resolveViewerRole(currentUser: unknown): NavigationRole | null {
  if (typeof currentUser !== 'object' || currentUser === null) {
    return null
  }

  const snapshot = currentUser as Record<string, unknown>

  if (snapshot.is_authenticated !== true) {
    return null
  }
  if (typeof snapshot.user !== 'object' || snapshot.user === null) {
    return null
  }
  if (typeof snapshot.household !== 'object' || snapshot.household === null) {
    return null
  }

  return snapshot.role === 'parent' || snapshot.role === 'child'
    ? snapshot.role
    : null
}

/** The entries one viewer may see, in the approved order. */
function navigationEntriesFor(role: NavigationRole | null) {
  return role === null
    ? []
    : ROUTE_TABLE.filter((entry) => entry.role === role)
}

/** The one entry a viewer of this role starts on. */
function startEntryFor(role: NavigationRole): RouteEntry {
  const entry = ROUTE_TABLE.find((row) => row.path === START_PATH[role])

  if (entry === undefined) {
    throw new Error('The route table has no start entry for this role')
  }
  return entry
}

const screenResolution = (entry: RouteEntry): RouteResolution => ({
  view: 'screen',
  canonicalPath: entry.path,
  entry,
  contentKey: entry.path,
})

/**
 * Resolve one pathname for one viewer. Pure, and independent of `window`.
 *
 * Query strings and fragments never reach this function: the caller passes a
 * pathname only, so they cannot select a route or change a role, and any
 * rewrite is written as the canonical pathname alone.
 */
export function resolveRoute(
  pathname: string,
  role: NavigationRole | null,
): RouteResolution {
  if (role === null) {
    // Fail closed to one destination. Every path behaves the same, so no
    // route can be probed and no role-specific label can appear.
    return {
      view: 'sign-in',
      canonicalPath: SIGN_IN_PATH,
      entry: null,
      contentKey: SIGN_IN_CONTENT_KEY,
    }
  }

  if (pathname === '/') {
    return screenResolution(startEntryFor(role))
  }

  // A trailing slash canonicalises only when the slashless form is a real
  // table path. Every other spelling, a different case included, is unknown.
  const slashless =
    pathname.length > 1 && pathname.endsWith('/')
      ? pathname.slice(0, -1)
      : pathname
  const candidate =
    slashless !== pathname && TABLE_PATHS.has(slashless) ? slashless : pathname

  // A viewer who already has a role has no business on the signed-out
  // destination, and must not be shown the form or a not-found panel there.
  if (candidate === SIGN_IN_PATH) {
    return screenResolution(startEntryFor(role))
  }

  const entry = ROUTE_TABLE.find((row) => row.path === candidate)
  if (entry !== undefined && entry.role === role) {
    return screenResolution(entry)
  }

  // An unknown path and the other role's path give one identical panel at the
  // requested URL.
  return {
    view: 'not-found',
    canonicalPath: candidate,
    entry: null,
    contentKey: NOT_FOUND_CONTENT_KEY,
  }
}

export interface RoleRouterProps {
  /**
   * The session body, exactly as the endpoint returns it. Typed `unknown`
   * because it is untrusted input that this module validates.
   */
  currentUser: unknown
  /** True while the caller is still fetching the session body. */
  isLoading?: boolean
  /**
   * Built screens, keyed by their exact approved route path. A path with no
   * entry here still shows the neutral placeholder, so an unbuilt
   * destination needs no change anywhere in this module. Screen ownership
   * for this build is recorded next to `ROUTE_TABLE` above.
   */
  screens?: Partial<Record<string, ReactNode>>
  /**
   * The screen shown at the signed-out destination. The router keeps its own
   * neutral panel when the composition root supplies none.
   */
  signInScreen?: ReactNode
  /**
   * A control rendered in the banner beside the navigation, and only while a
   * role is resolved. Hiding it is usability, never authorisation.
   */
  sessionControl?: ReactNode
}

function PlaceholderScreen({ heading }: { heading: string }) {
  return (
    <div className="page-panel">
      <h1 className="page-panel-title">{heading}</h1>
      <p className="page-panel-copy">{PLACEHOLDER_COPY}</p>
    </div>
  )
}

export function RoleRouter({
  currentUser,
  isLoading = false,
  screens = {},
  sessionControl,
  signInScreen,
}: RoleRouterProps) {
  const role = resolveViewerRole(currentUser)
  const [pathname, setPathname] = useState(() => window.location.pathname)

  useEffect(() => {
    const readLocation = () => setPathname(window.location.pathname)

    window.addEventListener('popstate', readLocation)
    return () => window.removeEventListener('popstate', readLocation)
  }, [])

  const resolution = resolveRoute(pathname, role)
  const { canonicalPath } = resolution
  const needsRewrite = canonicalPath !== pathname

  useEffect(() => {
    // The session request has not settled, so `role` is provisionally
    // `null` and every path resolves to the signed-out destination. Acting
    // on that now would rewrite the requested URL to /sign-in before the
    // real role is known, permanently losing a bookmark, a refresh, or a
    // shared link the moment the session resolves to a role that was
    // allowed to see it all along (issue #159, A-03). Wait for the real
    // answer; the effect re-runs once it arrives.
    if (isLoading || !needsRewrite) {
      return
    }

    // Fail-closed and canonical corrections replace the entry; only a link
    // activation pushes one.
    window.history.replaceState(null, '', canonicalPath)
    setPathname(canonicalPath)
  }, [canonicalPath, isLoading, needsRewrite])

  const navigate = useCallback((event: MouseEvent<HTMLAnchorElement>) => {
    if (event.defaultPrevented || event.button !== 0) {
      return
    }
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return
    }

    const link = event.currentTarget
    const linkTarget = link.getAttribute('target')

    if (link.hasAttribute('download')) {
      return
    }
    if (linkTarget !== null && linkTarget !== '_self') {
      return
    }
    if (link.origin !== window.location.origin) {
      return
    }

    event.preventDefault()

    // Re-activating the current route must not add a history entry or move
    // focus again.
    if (link.pathname === window.location.pathname) {
      return
    }

    window.history.pushState(null, '', link.pathname)
    setPathname(link.pathname)
  }, [])

  const entries = isLoading ? [] : navigationEntriesFor(role)
  const navigation =
    entries.length > 0 ? (
      <>
        <RoleNavigation
          currentPath={resolution.entry?.path ?? null}
          entries={entries}
          onNavigate={navigate}
        />
        {sessionControl}
      </>
    ) : undefined

  // While the session is loading the shell shows its own loading state, so no
  // placeholder content is built at all.
  let content = null
  if (isLoading) {
    content = null
  } else if (resolution.view === 'sign-in') {
    content = signInScreen ?? <PlaceholderScreen heading="Sign in" />
  } else if (resolution.entry !== null) {
    content = screens[resolution.entry.path] ?? (
      <PlaceholderScreen heading={resolution.entry.label} />
    )
  } else if (role !== null) {
    // One panel for an unknown path and for the other role's path, so no
    // route can be probed. It never echoes the requested URL.
    const start = startEntryFor(role)

    content = (
      <div className="page-panel">
        <h1 className="page-panel-title">Page not found</h1>
        <p className="page-panel-copy">We could not find that page.</p>
        <a className="page-panel-link" href={start.path} onClick={navigate}>
          Go to {start.label}
        </a>
      </div>
    )
  }

  return (
    <ApplicationShell
      contentKey={isLoading ? LOADING_CONTENT_KEY : resolution.contentKey}
      isLoading={isLoading}
      navigation={navigation}
    >
      {content}
    </ApplicationShell>
  )
}
