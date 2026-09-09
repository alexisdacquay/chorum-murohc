import { QueryClient } from '@tanstack/react-query'

import { sessionQueryKey, type SessionSnapshot } from './session'

export const createQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        refetchOnReconnect: false,
        refetchOnWindowFocus: false,
        retry: false,
      },
    },
  })

/**
 * Write a fresh session into the cache and drop every other cached query:
 * every screen's own data belongs to the account and household the caller
 * just left, on login, logout, and switching households alike (issue #130).
 *
 * Order matters, and `queryClient.clear()` is deliberately not used here.
 * `App`'s own session query is always mounted, so clearing it first - even
 * for one tick before this call's own `setQueryData` - makes react-query
 * treat it as freshly mounted with no data and refetch `auth/session/` on
 * its own, racing the answer this call is about to write. Setting the new
 * data directly has no such observer-on-itself to race; only the other
 * queries, which this caller does want gone, are removed.
 */
export const replaceSession = (
  queryClient: QueryClient,
  snapshot: SessionSnapshot,
): void => {
  queryClient.setQueryData(sessionQueryKey, snapshot)
  queryClient.removeQueries({
    predicate: (query) => query.queryKey[0] !== sessionQueryKey[0],
  })
}
