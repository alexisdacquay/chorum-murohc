/**
 * A same-origin internal link, for a screen that links to a different
 * approved route (the overview dashboard's links to `/approvals`,
 * `/chore-pool`, `/household` and `/reward-requests`; the activity screen's
 * link back to `/overview`).
 *
 * `navigation/role-router.tsx` already listens for the browser's own
 * `popstate` event to know when the URL changed under it; this handler does
 * the same left-click, same-tab, same-origin guarding `RoleRouter`'s own
 * navigation links use, then pushes the new path and dispatches a
 * synthetic `popstate` so the router picks it up exactly as it would a
 * back-button press. That keeps this module a plain function `RoleRouter`
 * need not import or otherwise know about, rather than a second navigation
 * mechanism running alongside it.
 */

import type { MouseEvent } from 'react'

export function handleInternalLinkClick(event: MouseEvent<HTMLAnchorElement>) {
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

  if (link.pathname === window.location.pathname) {
    return
  }

  window.history.pushState(null, '', link.pathname)
  window.dispatchEvent(new PopStateEvent('popstate'))
}
