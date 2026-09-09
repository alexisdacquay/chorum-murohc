/**
 * The mutation behind every household switch (issue #130), shared by the
 * banner switcher and the post-login picker so the one security-sensitive
 * step - replacing every cached query before the new household's data can
 * arrive - only has one implementation to keep correct.
 *
 * Selecting a household re-derives the role from that membership alone
 * (`chorum_murohc.api.session.resolve_active_membership` never unions
 * roles), but the browser also holds its own cache of the previous
 * household's screens. `replaceSession` drops all of it before the fresh
 * session is written back in: every mounted screen sees its query go from
 * cached-and-stale to absent-and-refetching in one render, never from one
 * household's data straight to another's.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { replaceSession } from '../../api/query-client'
import { ensureCsrfToken, selectHousehold } from '../../api/session'

export function useHouseholdSwitch() {
  const queryClient = useQueryClient()
  const [hasFailed, setHasFailed] = useState(false)

  const mutation = useMutation({
    mutationFn: async (householdId: number) => {
      const csrfToken = await ensureCsrfToken()
      return selectHousehold({ csrfToken, householdId })
    },
    onSuccess: (session) => {
      setHasFailed(false)
      replaceSession(queryClient, session)
    },
    onError: () => {
      setHasFailed(true)
    },
  })

  return {
    switchHousehold: (householdId: number) => mutation.mutate(householdId),
    isPending: mutation.isPending,
    hasFailed,
  }
}
