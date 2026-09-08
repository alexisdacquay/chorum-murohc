import { RoleRouter, SIGNED_OUT_SESSION } from './navigation/role-router'

/**
 * The committed application shows the signed-out state and nothing else.
 *
 * #28 connects the live session, at which point this component will pass the
 * fetched `GET /api/v1/auth/session/` body to the router. Until then there is
 * deliberately no identity, no role, no role switch, no request, and no
 * cookie or browser-storage read here.
 */
export default function App() {
  return <RoleRouter currentUser={SIGNED_OUT_SESSION} />
}
