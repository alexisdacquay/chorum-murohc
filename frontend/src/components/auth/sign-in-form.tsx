/**
 * The sign-in screen shown at `/sign-in`.
 *
 * It owns two fields, one message and one submit control. Route visibility is
 * usability, never authorisation (invariant 10): this form asks the server
 * who the caller is and shows whatever the server says. It derives no role
 * from a username, a URL, a cookie or the DOM, and it writes nothing to
 * `localStorage` or `sessionStorage`.
 *
 * The interface maps an HTTP outcome to its own fixed copy and never renders
 * the server's `detail` (invariant 13). Every credential failure - a wrong
 * password, an unknown username, a disabled account, and a locally refused
 * empty field - shows one identical sentence, so nothing here reveals whether
 * an account exists. The submitted username is never echoed back, and the
 * password is never placed in a message, a URL or the document.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useId, useRef, useState, type FormEvent } from 'react'

import {
  SessionRequestError,
  ensureCsrfToken,
  login,
  sessionQueryKey,
} from '../../api/session'
import { Button } from '../ui/button'
import { FormMessage } from '../ui/form-message'
import { Input } from '../ui/input'

/** One sentence for every way a sign-in can be refused. */
export const SIGN_IN_FAILED_MESSAGE =
  'We could not sign you in. Check your username and password and try again.'

/**
 * The throttle counts failures per client address and never per submitted
 * username, so naming it discloses nothing about any account. There is
 * deliberately no countdown and no wait time.
 */
export const SIGN_IN_THROTTLED_MESSAGE =
  'Too many sign-in attempts from this device. Wait a few minutes and try again.'

/** Unreachable, not JSON, an unexpected status, or a rejected CSRF token. */
export const CONNECTION_MESSAGE =
  'We could not reach Chorum-murohc. Check your connection and try again.'

interface FormFailure {
  message: string
  /** Whether the two credential fields are the thing at fault. */
  marksFields: boolean
}

const CREDENTIAL_FAILURE: FormFailure = {
  message: SIGN_IN_FAILED_MESSAGE,
  marksFields: true,
}
const THROTTLE_FAILURE: FormFailure = {
  message: SIGN_IN_THROTTLED_MESSAGE,
  marksFields: false,
}
const CONNECTION_FAILURE: FormFailure = {
  message: CONNECTION_MESSAGE,
  marksFields: false,
}

export interface SignInFormProps {
  /** True when the current-session request itself failed. */
  isSessionUnavailable?: boolean
  /** True while that request is being retried. */
  isRetryingSession?: boolean
  /** Run that request again. Shown as "Try again" beside the notice. */
  onRetrySession?: () => void
}

export function SignInForm({
  isRetryingSession = false,
  isSessionUnavailable = false,
  onRetrySession,
}: SignInFormProps) {
  const queryClient = useQueryClient()
  const usernameField = useRef<HTMLInputElement>(null)
  const passwordField = useRef<HTMLInputElement>(null)
  const usernameId = useId()
  const passwordId = useId()
  const messageId = useId()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [failure, setFailure] = useState<FormFailure | null>(null)

  const signIn = useMutation({
    mutationFn: async (credentials: { username: string; password: string }) => {
      const csrfToken = await ensureCsrfToken()

      return login({ ...credentials, csrfToken })
    },
    onSuccess: (session) => {
      // The login body is the session, so nothing is fetched again. The
      // router sees a resolved role on this render and replaces the URL with
      // the role start path.
      setPassword('')
      setFailure(null)
      queryClient.setQueryData(sessionQueryKey, session)
    },
    onError: (error) => {
      // The password is never kept across a round trip that failed.
      setPassword('')

      const kind =
        error instanceof SessionRequestError ? error.failure : 'unavailable'

      if (kind === 'forbidden') {
        // The token was rejected. Ask the session endpoint for a fresh one
        // once, and never resubmit the credentials on the viewer's behalf.
        void queryClient.refetchQueries({ queryKey: sessionQueryKey })
      }
      setFailure(
        kind === 'credentials'
          ? CREDENTIAL_FAILURE
          : kind === 'throttled'
            ? THROTTLE_FAILURE
            : CONNECTION_FAILURE,
      )
    },
  })

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    // A second Enter or click while the first attempt is in flight is
    // ignored, so one submission is one POST.
    if (signIn.isPending) {
      return
    }

    if (username === '' || password === '') {
      // Refused locally, with the same sentence a server refusal shows, and
      // no request at all.
      setFailure(CREDENTIAL_FAILURE)
      const firstEmpty = username === '' ? usernameField : passwordField
      firstEmpty.current?.focus()
      return
    }

    setFailure(null)
    signIn.mutate({ username, password })
  }

  const invalid = failure?.marksFields === true ? 'true' : undefined

  return (
    <div className="page-panel auth-panel">
      <h1 className="page-panel-title">Sign in</h1>
      {isSessionUnavailable ? (
        <div className="auth-notice" role="status">
          <FormMessage tone="error">{CONNECTION_MESSAGE}</FormMessage>
          <Button
            aria-busy={isRetryingSession || undefined}
            disabled={isRetryingSession}
            onClick={onRetrySession}
            variant="secondary"
          >
            {isRetryingSession ? 'Trying again...' : 'Try again'}
          </Button>
        </div>
      ) : null}
      <form className="auth-form" noValidate onSubmit={submit}>
        <div className="auth-field">
          <label className="auth-label" htmlFor={usernameId}>
            Username
          </label>
          <Input
            aria-describedby={messageId}
            aria-invalid={invalid}
            autoComplete="username"
            id={usernameId}
            name="username"
            onChange={(event) => setUsername(event.target.value)}
            ref={usernameField}
            required
            value={username}
          />
        </div>
        <div className="auth-field">
          <label className="auth-label" htmlFor={passwordId}>
            Password
          </label>
          <Input
            aria-describedby={messageId}
            aria-invalid={invalid}
            autoComplete="current-password"
            id={passwordId}
            name="password"
            onChange={(event) => setPassword(event.target.value)}
            ref={passwordField}
            required
            type="password"
            value={password}
          />
        </div>
        <FormMessage id={messageId} role="alert" tone="error">
          {failure?.message ?? ''}
        </FormMessage>
        <Button
          aria-busy={signIn.isPending || undefined}
          disabled={signIn.isPending}
          type="submit"
        >
          {signIn.isPending ? 'Signing in...' : 'Sign in'}
        </Button>
      </form>
    </div>
  )
}
