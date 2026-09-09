/**
 * The parent password settings screen at `/change-password` (issue #129).
 *
 * A parent's self-service path to change their own account password,
 * matching `pin-settings-screen.tsx`'s shape: validated twice, locally first
 * so an obvious mismatch never leaves the browser, and again by the server,
 * whose current-password and strength checks cannot be done locally at all.
 *
 * A child with a forgotten password has no account password to prove here;
 * a parent resets it for them instead, from the household screen's own
 * "Reset password" action.
 *
 * Every secret field is cleared after a submission reaches the network,
 * success or failure alike, so no password sits in memory or the DOM any
 * longer than the one request needs.
 */

import { useId, useRef, useState, type FormEvent } from 'react'

import { useMutation } from '@tanstack/react-query'

import { PasswordChangeRequestError, changeOwnPassword, ensureCsrfToken } from '../../api/password'
import { Button } from '../ui/button'
import { FormMessage } from '../ui/form-message'
import { Input } from '../ui/input'

export const CURRENT_PASSWORD_REQUIRED_MESSAGE = 'Enter your current password.'
export const NEW_PASSWORD_REQUIRED_MESSAGE = 'Enter a new password.'
export const CONFIRM_REQUIRED_MESSAGE = 'Enter the new password again.'
export const CONFIRM_MISMATCH_MESSAGE = 'Both passwords must match.'
export const GENERIC_VALIDATION_MESSAGE = 'Check the details and try again.'
export const PERMISSION_MESSAGE =
  'You do not have permission to change this password. Refresh the page and try again.'
export const CONNECTION_MESSAGE =
  'We could not reach Chorum-murohc. Check your connection and try again.'
export const SUCCESS_MESSAGE = 'Your password has been changed.'

interface FieldErrors {
  current_password?: string
  new_password?: string
  confirm?: string
}

export function PasswordSettingsScreen() {
  const currentField = useRef<HTMLInputElement>(null)
  const newField = useRef<HTMLInputElement>(null)
  const confirmField = useRef<HTMLInputElement>(null)
  const currentId = useId()
  const newId = useId()
  const confirmId = useId()
  const currentMessageId = useId()
  const newMessageId = useId()
  const confirmMessageId = useId()

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [succeeded, setSucceeded] = useState(false)

  const clearSecrets = () => {
    setCurrentPassword('')
    setNewPassword('')
    setConfirmPassword('')
  }

  const onFieldChange = (setValue: (value: string) => void) => (value: string) => {
    setSucceeded(false)
    setValue(value)
  }

  const mutation = useMutation({
    mutationFn: async (values: { currentPassword: string; newPassword: string }) => {
      const csrfToken = await ensureCsrfToken()
      await changeOwnPassword({
        csrfToken,
        currentPassword: values.currentPassword,
        newPassword: values.newPassword,
      })
    },
    onSuccess: () => {
      clearSecrets()
      setFieldErrors({})
      setFormError(null)
      setSucceeded(true)
    },
    onError: (error) => {
      clearSecrets()
      setSucceeded(false)

      if (error instanceof PasswordChangeRequestError && error.kind === 'validation') {
        const next: FieldErrors = {}
        if (error.fieldErrors.current_password) {
          next.current_password = error.fieldErrors.current_password
        }
        if (error.fieldErrors.new_password) {
          next.new_password = error.fieldErrors.new_password
        }
        if (Object.keys(next).length > 0) {
          setFieldErrors(next)
          setFormError(null)
          return
        }
        setFieldErrors({})
        setFormError(GENERIC_VALIDATION_MESSAGE)
        return
      }

      setFieldErrors({})
      setFormError(
        error instanceof PasswordChangeRequestError && error.kind === 'forbidden'
          ? PERMISSION_MESSAGE
          : CONNECTION_MESSAGE,
      )
    },
  })

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    // A second Enter or click while the first attempt is in flight is
    // ignored, so one submission is one POST.
    if (mutation.isPending) {
      return
    }

    const currentError =
      currentPassword === '' ? CURRENT_PASSWORD_REQUIRED_MESSAGE : null
    const newError = newPassword === '' ? NEW_PASSWORD_REQUIRED_MESSAGE : null
    const confirmError =
      newError !== null
        ? null
        : confirmPassword === ''
          ? CONFIRM_REQUIRED_MESSAGE
          : confirmPassword !== newPassword
            ? CONFIRM_MISMATCH_MESSAGE
            : null

    if (currentError !== null || newError !== null || confirmError !== null) {
      setFieldErrors({
        ...(currentError !== null ? { current_password: currentError } : {}),
        ...(newError !== null ? { new_password: newError } : {}),
        ...(confirmError !== null ? { confirm: confirmError } : {}),
      })
      setFormError(null)
      setSucceeded(false)
      ;(
        currentError !== null
          ? currentField
          : newError !== null
            ? newField
            : confirmField
      ).current?.focus()
      return
    }

    setFieldErrors({})
    setFormError(null)
    mutation.mutate({ currentPassword, newPassword })
  }

  return (
    <div className="page-panel">
      <h1 className="page-panel-title">Change password</h1>
      <p className="page-panel-copy">
        Change your own account password. To reset a child&apos;s forgotten
        password instead, use Household and the member&apos;s own Reset
        password action.
      </p>
      <form className="auth-form" noValidate onSubmit={submit}>
        <div className="auth-field">
          <label className="auth-label" htmlFor={currentId}>
            Current password
          </label>
          <Input
            aria-describedby={currentMessageId}
            aria-invalid={fieldErrors.current_password !== undefined ? 'true' : undefined}
            autoComplete="current-password"
            id={currentId}
            onChange={(event) => onFieldChange(setCurrentPassword)(event.target.value)}
            ref={currentField}
            type="password"
            value={currentPassword}
          />
          <FormMessage id={currentMessageId} role="alert" tone="error">
            {fieldErrors.current_password ?? ''}
          </FormMessage>
        </div>
        <div className="auth-field">
          <label className="auth-label" htmlFor={newId}>
            New password
          </label>
          <Input
            aria-describedby={newMessageId}
            aria-invalid={fieldErrors.new_password !== undefined ? 'true' : undefined}
            autoComplete="new-password"
            id={newId}
            onChange={(event) => onFieldChange(setNewPassword)(event.target.value)}
            ref={newField}
            type="password"
            value={newPassword}
          />
          <FormMessage id={newMessageId} role="alert" tone="error">
            {fieldErrors.new_password ?? ''}
          </FormMessage>
        </div>
        <div className="auth-field">
          <label className="auth-label" htmlFor={confirmId}>
            Confirm new password
          </label>
          <Input
            aria-describedby={confirmMessageId}
            aria-invalid={fieldErrors.confirm !== undefined ? 'true' : undefined}
            autoComplete="new-password"
            id={confirmId}
            onChange={(event) => onFieldChange(setConfirmPassword)(event.target.value)}
            ref={confirmField}
            type="password"
            value={confirmPassword}
          />
          <FormMessage id={confirmMessageId} role="alert" tone="error">
            {fieldErrors.confirm ?? ''}
          </FormMessage>
        </div>
        <FormMessage role="alert" tone="error">
          {formError ?? ''}
        </FormMessage>
        {succeeded ? (
          <FormMessage role="status" tone="success">
            {SUCCESS_MESSAGE}
          </FormMessage>
        ) : null}
        <Button
          aria-busy={mutation.isPending || undefined}
          disabled={mutation.isPending}
          type="submit"
        >
          {mutation.isPending ? 'Saving...' : 'Change password'}
        </Button>
      </form>
    </div>
  )
}
