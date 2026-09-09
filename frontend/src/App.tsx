import { useQuery } from '@tanstack/react-query'

import { fetchSession, sessionQueryKey } from './api/session'
import { ParentApprovalsScreen } from './components/approvals/parent-approvals-screen'
import { AuditHistoryScreen } from './components/audit/audit-history-screen'
import { SignInForm } from './components/auth/sign-in-form'
import { SignOutButton } from './components/auth/sign-out-button'
import { ChildChoreScreen } from './components/chores/child-chore-screen'
import { ChorePoolScreen } from './components/chores/chore-pool-screen'
import { CreatureScreen } from './components/creatures/creature-screen'
import { HouseholdScreen } from './components/members/household-screen'
import { ParentOverviewScreen } from './components/overview/parent-overview-screen'
import { PointsDashboardScreen } from './components/points/points-dashboard-screen'
import { LevelsScreen } from './components/progression/levels-screen'
import { ChildRewardsScreen } from './components/rewards/child-rewards-screen'
import { ParentRewardsScreen } from './components/rewards/parent-rewards-screen'
import { PasswordSettingsScreen } from './components/settings/password-settings-screen'
import { PinSettingsScreen } from './components/settings/pin-settings-screen'
import { RoleRouter } from './navigation/role-router'

// Screens built so far, keyed by their approved route path (issue #37 owns
// `/chore-pool`, issue #36 owns `/chores`, issue #21 owns `/household`, issue
// #30 owns `/approval-pin`; issue #55 owns `/rewards` and
// `/reward-requests`; issue #61 owns `/levels`; issue #49 owns `/points`;
// issue #66 owns `/creature`; issue #44 owns `/approvals`; issue #84 owns
// `/overview` and `/activity`; issue 129 owns `/change-password`). Every
// other approved path still falls back to the router's own neutral
// placeholder.
const SCREENS = {
  '/activity': <AuditHistoryScreen />,
  '/approvals': <ParentApprovalsScreen />,
  '/chore-pool': <ChorePoolScreen />,
  '/chores': <ChildChoreScreen />,
  '/household': <HouseholdScreen />,
  '/overview': <ParentOverviewScreen />,
  '/approval-pin': <PinSettingsScreen />,
  '/change-password': <PasswordSettingsScreen />,
  '/points': <PointsDashboardScreen />,
  '/rewards': <ChildRewardsScreen />,
  '/reward-requests': <ParentRewardsScreen />,
  '/levels': <LevelsScreen />,
  '/creature': <CreatureScreen />,
}

/**
 * The composition root.
 *
 * It asks `GET /api/v1/auth/session/` once who the caller is and hands that
 * answer, untouched, to the router. It decides no role of its own: it holds
 * no identity literal, reads no cookie, no URL and no browser storage, and
 * every authority decision stays with the server.
 *
 * A request that has not answered yet shows the shell loading state, so
 * neither navigation nor the sign-in form can flash first. A request that
 * failed shows the sign-in screen with one recoverable notice, exactly as a
 * signed-out answer does, because a viewer who cannot be identified is not
 * signed in.
 */
export default function App() {
  const session = useQuery({
    queryKey: sessionQueryKey,
    queryFn: ({ signal }) => fetchSession({ signal }),
  })

  return (
    <RoleRouter
      currentUser={session.data}
      isLoading={session.isPending}
      screens={SCREENS}
      sessionControl={<SignOutButton />}
      signInScreen={
        <SignInForm
          isRetryingSession={session.isFetching}
          isSessionUnavailable={session.isError}
          onRetrySession={() => {
            void session.refetch()
          }}
        />
      }
    />
  )
}
