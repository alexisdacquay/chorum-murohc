/**
 * The parent PIN settings screen at `/approval-pin` (T032, issue #30).
 *
 * One form serves both setup and replacement, exactly as
 * `_docs/approval-authentication.md` treats them as one operation
 * ("Forgetting is the same operation as changing"): there is no separate
 * "do I already have a PIN?" read to choose between two layouts, and the
 * merged `POST /api/v1/auth/pin/` contract needs none either.
 *
 * Validated twice, like `chore-form-dialog.tsx`: locally first, so an
 * obviously bad value never leaves the browser, and again by the server,
 * whose current-password and weak-PIN checks cannot be done locally at all.
 * A local failure and a server failure land on the same field the same way.
 *
 * Both secret fields are cleared after every submission that reaches the
 * network, success or failure alike, so neither the account password nor
 * the PIN sits in memory or the DOM any longer than the one request needs.
 * A local validation failure that never left the browser leaves the fields
 * as the parent typed them, so a single typo does not cost the whole form.
 */

import { useId, useRef, useState, type FormEvent } from 'react'

import { useMutation } from '@tanstack/react-query'

import { PinRequestError, ensureCsrfToken, setOrReplacePin } from '../../api/pin'
import { Button } from '../ui/button'
import { FormMessage } from '../ui/form-message'
import { Input } from '../ui/input'

// Matches `PIN_MIN_LENGTH` / `PIN_MAX_LENGTH` in `chorum_murohc/identity/services.py`.
export const PIN_MIN_LENGTH = 4
export const PIN_MAX_LENGTH = 10

export const CURRENT_PASSWORD_REQUIRED_MESSAGE =
  'Enter your current account password.'
export const PIN_REQUIRED_MESSAGE = 'Enter a new PIN.'
export const PIN_FORMAT_MESSAGE = `PIN must be ${PIN_MIN_LENGTH} to ${PIN_MAX_LENGTH} digits, numbers only.`
export const PIN_CONFIRM_REQUIRED_MESSAGE = 'Enter the new PIN again.'
export const PIN_CONFIRM_MISMATCH_MESSAGE = 'Both PINs must match.'
export const GENERIC_VALIDATION_MESSAGE = 'Check the details and try again.'
export const PERMISSION_MESSAGE =
  'You do not have permission to manage this PIN. Refresh the page and try again.'
export const CONNECTION_MESSAGE =
  'We could not reach Chorum-murohc. Check your connection and try again.'
export const SUCCESS_MESSAGE = 'Your approval PIN has been saved.'

const validatePassword = (raw: string): string | null =>
  raw === '' ? CURRENT_PASSWORD_REQUIRED_MESSAGE : null

const validatePin = (raw: string): string | null => {
  if (raw === '') {
    return PIN_REQUIRED_MESSAGE
  }
  if (!/^\d+$/.test(raw) || raw.length < PIN_MIN_LENGTH || raw.length > PIN_MAX_LENGTH) {
    return PIN_FORMAT_MESSAGE
  }
  return null
}

const validateConfirmation = (pin: string, confirmation: string): string | null => {
  if (confirmation === '') {
    return PIN_CONFIRM_REQUIRED_MESSAGE
  }
  if (confirmation !== pin) {
    return PIN_CONFIRM_MISMATCH_MESSAGE
  }
  return null
}

interface FieldErrors {
  current_password?: string
  pin?: string
  confirm?: string
}

export function PinSettingsScreen() {
  const passwordField = useRef<HTMLInputElement>(null)
  const pinField = useRef<HTMLInputElement>(null)
  const confirmField = useRef<HTMLInputElement>(null)
  const passwordId = useId()
  const pinId = useId()
  const confirmId = useId()
  const passwordMessageId = useId()
  const pinMessageId = useId()
  const confirmMessageId = useId()

  const [currentPassword, setCurrentPassword] = useState('')
  const [pin, setPin] = useState('')
  const [confirmPin, setConfirmPin] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [succeeded, setSucceeded] = useState(false)

  const clearSecrets = () => {
    setCurrentPassword('')
    setPin('')
    setConfirmPin('')
  }

  const onFieldChange = (setValue: (value: string) => void) => (value: string) => {
    setSucceeded(false)
    setValue(value)
  }

  const mutation = useMutation({
    mutationFn: async (values: { currentPassword: string; pin: string }) => {
      const csrfToken = await ensureCsrfToken()
      await setOrReplacePin({
        csrfToken,
        currentPassword: values.currentPassword,
        pin: values.pin,
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

      if (error instanceof PinRequestError && error.kind === 'validation') {
        const next: FieldErrors = {}
        if (error.fieldErrors.current_password) {
          next.current_password = error.fieldErrors.current_password
        }
        if (error.fieldErrors.pin) {
          next.pin = error.fieldErrors.pin
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
        error instanceof PinRequestError && error.kind === 'forbidden'
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

    const passwordError = validatePassword(currentPassword)
    const pinError = validatePin(pin)
    const confirmError =
      pinError === null ? validateConfirmation(pin, confirmPin) : null

    if (passwordError !== null || pinError !== null || confirmError !== null) {
      setFieldErrors({
        ...(passwordError !== null ? { current_password: passwordError } : {}),
        ...(pinError !== null ? { pin: pinError } : {}),
        ...(confirmError !== null ? { confirm: confirmError } : {}),
      })
      setFormError(null)
      setSucceeded(false)
      ;(
        passwordError !== null
          ? passwordField
          : pinError !== null
            ? pinField
            : confirmField
      ).current?.focus()
      return
    }

    setFieldErrors({})
    setFormError(null)
    mutation.mutate({ currentPassword, pin })
  }

  return (
    <div className="page-panel">
      <h1 className="page-panel-title">Approval PIN</h1>
      <p className="page-panel-copy">
        This PIN authorises an approval on a child&apos;s device. It never
        expires; save a new one here whenever you want to change it or you
        have forgotten it.
      </p>
      <form className="auth-form" noValidate onSubmit={submit}>
        <div className="auth-field">
          <label className="auth-label" htmlFor={passwordId}>
            Current account password
          </label>
          <Input
            aria-describedby={passwordMessageId}
            aria-invalid={fieldErrors.current_password !== undefined ? 'true' : undefined}
            autoComplete="current-password"
            id={passwordId}
            onChange={(event) =>
              onFieldChange(setCurrentPassword)(event.target.value)
            }
            ref={passwordField}
            type="password"
            value={currentPassword}
          />
          <FormMessage id={passwordMessageId} role="alert" tone="error">
            {fieldErrors.current_password ?? ''}
          </FormMessage>
        </div>
        <div className="auth-field">
          <label className="auth-label" htmlFor={pinId}>
            New PIN
          </label>
          <Input
            aria-describedby={pinMessageId}
            aria-invalid={fieldErrors.pin !== undefined ? 'true' : undefined}
            autoComplete="off"
            id={pinId}
            inputMode="numeric"
            maxLength={PIN_MAX_LENGTH}
            onChange={(event) => onFieldChange(setPin)(event.target.value)}
            ref={pinField}
            type="password"
            value={pin}
          />
          <FormMessage id={pinMessageId} role="alert" tone="error">
            {fieldErrors.pin ?? ''}
          </FormMessage>
        </div>
        <div className="auth-field">
          <label className="auth-label" htmlFor={confirmId}>
            Confirm new PIN
          </label>
          <Input
            aria-describedby={confirmMessageId}
            aria-invalid={fieldErrors.confirm !== undefined ? 'true' : undefined}
            autoComplete="off"
            id={confirmId}
            inputMode="numeric"
            maxLength={PIN_MAX_LENGTH}
            onChange={(event) => onFieldChange(setConfirmPin)(event.target.value)}
            ref={confirmField}
            type="password"
            value={confirmPin}
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
          {mutation.isPending ? 'Saving...' : 'Save PIN'}
        </Button>
      </form>
    </div>
  )
}
