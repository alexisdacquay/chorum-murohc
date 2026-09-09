/**
 * The "Sign out" control in the banner.
 *
 * It is rendered by the router only once a role has resolved, so a signed-out
 * viewer never sees it. Hiding it is a convenience, not a control: the
 * endpoint is authenticated and CSRF protected on its own (invariant 10).
 *
 * A 403 means the session had already ended between page load and the click.
 * That is not a failure the viewer can act on, so it lands exactly where a
 * 204 lands and shows no error. Only an unreachable service leaves the
 * viewer where they were, with one compact recoverable message.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { SessionRequestError, ensureCsrfToken, logout } from '../../api/session'
import { replaceSession } from '../../api/query-client'
import { SIGNED_OUT_SESSION } from '../../navigation/role-router'
import { Button } from '../ui/button'
import { FormMessage } from '../ui/form-message'

export const SIGN_OUT_FAILED_MESSAGE =
  'We could not sign you out. Check your connection and try again.'

export function SignOutButton() {
  const queryClient = useQueryClient()
  const [hasFailed, setHasFailed] = useState(false)

  const signOut = useMutation({
    mutationFn: async () => {
      const csrfToken = await ensureCsrfToken()

      await logout({ csrfToken })
    },
    onSuccess: () => {
      setHasFailed(false)
      // Every cached screen belongs to this account and household; the next
      // sign-in, on this device or another account's, must not see any of
      // it flash by before its own fetch replaces it.
      replaceSession(queryClient, SIGNED_OUT_SESSION)
    },
    onError: (error) => {
      if (
        error instanceof SessionRequestError &&
        error.failure === 'forbidden'
      ) {
        setHasFailed(false)
        replaceSession(queryClient, SIGNED_OUT_SESSION)
        return
      }
      setHasFailed(true)
    },
  })

  return (
    <div className="shell-session-actions">
      <Button
        aria-busy={signOut.isPending || undefined}
        disabled={signOut.isPending}
        onClick={() => signOut.mutate()}
        variant="secondary"
      >
        {signOut.isPending ? 'Signing out...' : 'Sign out'}
      </Button>
      {hasFailed ? (
        <FormMessage role="alert" tone="error">
          {SIGN_OUT_FAILED_MESSAGE}
        </FormMessage>
      ) : null}
    </div>
  )
}
