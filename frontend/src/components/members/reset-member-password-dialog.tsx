/**
 * Reset one household member's password (issue #129).
 *
 * Separate from `member-form-dialog.tsx` on purpose: setting someone else's
 * password needs its own proof, stronger than "the caller is a parent of
 * this household" - the acting parent's own PIN or their own account
 * password, entered here, in the same request. Exactly one of the two: the
 * form will not let both through, matching
 * `chorum_murohc/api/members.py`'s `MemberPasswordResetSerializer`.
 *
 * A wrong PIN here is charged to the acting parent's own PIN lockout, the
 * same one `approval-pin` uses, so this form shows that failure with the
 * same generic wording the server sends rather than inventing its own.
 */

import { useEffect, useId, useRef, useState, type FormEvent } from 'react'

import { useMutation } from '@tanstack/react-query'

import {
  MemberRequestError,
  ensureCsrfToken,
  resetMemberPassword,
  type Member,
} from '../../api/members'
import { Button } from '../ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog'
import { FormMessage } from '../ui/form-message'
import { Input } from '../ui/input'
import { GENERIC_VALIDATION_MESSAGE, describeMemberFailure } from './member-messages'

export const PROOF_REQUIRED_MESSAGE =
  'Enter your PIN or your account password, not both.'
export const NEW_PASSWORD_REQUIRED_MESSAGE = 'Enter a new password.'
export const CONFIRM_REQUIRED_MESSAGE = 'Enter the new password again.'
export const CONFIRM_MISMATCH_MESSAGE = 'Both passwords must match.'

interface FieldErrors {
  proof?: string
  new_password?: string
  confirm?: string
}

export interface ResetMemberPasswordDialogProps {
  member: Member
  open: boolean
  onOpenChange: (open: boolean) => void
  onReset: () => void
}

export function ResetMemberPasswordDialog({
  member,
  onOpenChange,
  onReset,
  open,
}: ResetMemberPasswordDialogProps) {
  const pinField = useRef<HTMLInputElement>(null)
  const passwordField = useRef<HTMLInputElement>(null)
  const newPasswordField = useRef<HTMLInputElement>(null)
  const confirmField = useRef<HTMLInputElement>(null)
  const pinId = useId()
  const passwordId = useId()
  const newPasswordId = useId()
  const confirmId = useId()
  const proofMessageId = useId()
  const newPasswordMessageId = useId()
  const confirmMessageId = useId()

  const [pin, setPin] = useState('')
  const [password, setPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)

  // Every open starts from a clean form: a previous target's typed secrets
  // never leak into the next one's dialog.
  useEffect(() => {
    if (!open) {
      return
    }
    setPin('')
    setPassword('')
    setNewPassword('')
    setConfirmPassword('')
    setFieldErrors({})
    setFormError(null)
  }, [open])

  const clearSecrets = () => {
    setPin('')
    setPassword('')
    setNewPassword('')
    setConfirmPassword('')
  }

  const mutation = useMutation({
    mutationFn: async (values: {
      pin: string
      password: string
      newPassword: string
    }) => {
      const csrfToken = await ensureCsrfToken()
      return resetMemberPassword({
        csrfToken,
        id: member.id,
        newPassword: values.newPassword,
        ...(values.pin === '' ? { password: values.password } : { pin: values.pin }),
      })
    },
    onSuccess: () => {
      clearSecrets()
      onReset()
    },
    onError: (error) => {
      clearSecrets()
      if (error instanceof MemberRequestError && error.kind === 'validation') {
        const next: FieldErrors = {}
        if (error.fieldErrors.new_password) {
          next.new_password = error.fieldErrors.new_password
        }
        if (Object.keys(next).length > 0) {
          setFieldErrors(next)
          setFormError(null)
          return
        }
        setFieldErrors({})
        setFormError(error.detail ?? GENERIC_VALIDATION_MESSAGE)
        return
      }
      setFieldErrors({})
      setFormError(describeMemberFailure(error))
    },
  })

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    if (mutation.isPending) {
      return
    }

    const proofError =
      (pin === '') === (password === '') ? PROOF_REQUIRED_MESSAGE : null
    const newPasswordError =
      newPassword === '' ? NEW_PASSWORD_REQUIRED_MESSAGE : null
    const confirmError =
      newPasswordError !== null
        ? null
        : confirmPassword === ''
          ? CONFIRM_REQUIRED_MESSAGE
          : confirmPassword !== newPassword
            ? CONFIRM_MISMATCH_MESSAGE
            : null

    if (proofError !== null || newPasswordError !== null || confirmError !== null) {
      setFieldErrors({
        ...(proofError !== null ? { proof: proofError } : {}),
        ...(newPasswordError !== null ? { new_password: newPasswordError } : {}),
        ...(confirmError !== null ? { confirm: confirmError } : {}),
      })
      setFormError(null)
      ;(proofError !== null
        ? pin === ''
          ? passwordField
          : pinField
        : newPasswordError !== null
          ? newPasswordField
          : confirmField
      ).current?.focus()
      return
    }

    setFieldErrors({})
    setFormError(null)
    mutation.mutate({ pin, password, newPassword })
  }

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Reset password for &quot;{member.username}&quot;</DialogTitle>
          <DialogDescription>
            Prove it is really you with your own PIN or your own account
            password, then set the new password for this account.
          </DialogDescription>
        </DialogHeader>
        <form className="chore-form" noValidate onSubmit={submit}>
          <div className="chore-form-field">
            <label className="auth-label" htmlFor={pinId}>
              Your PIN
            </label>
            <Input
              aria-describedby={proofMessageId}
              aria-invalid={fieldErrors.proof !== undefined ? 'true' : undefined}
              autoComplete="off"
              id={pinId}
              inputMode="numeric"
              onChange={(event) => setPin(event.target.value)}
              ref={pinField}
              type="password"
              value={pin}
            />
          </div>
          <div className="chore-form-field">
            <label className="auth-label" htmlFor={passwordId}>
              Or your account password
            </label>
            <Input
              aria-describedby={proofMessageId}
              aria-invalid={fieldErrors.proof !== undefined ? 'true' : undefined}
              autoComplete="current-password"
              id={passwordId}
              onChange={(event) => setPassword(event.target.value)}
              ref={passwordField}
              type="password"
              value={password}
            />
            <FormMessage id={proofMessageId} role="alert" tone="error">
              {fieldErrors.proof ?? ''}
            </FormMessage>
          </div>
          <div className="chore-form-field">
            <label className="auth-label" htmlFor={newPasswordId}>
              New password
            </label>
            <Input
              aria-describedby={newPasswordMessageId}
              aria-invalid={fieldErrors.new_password !== undefined ? 'true' : undefined}
              autoComplete="new-password"
              id={newPasswordId}
              onChange={(event) => setNewPassword(event.target.value)}
              ref={newPasswordField}
              type="password"
              value={newPassword}
            />
            <FormMessage id={newPasswordMessageId} role="alert" tone="error">
              {fieldErrors.new_password ?? ''}
            </FormMessage>
          </div>
          <div className="chore-form-field">
            <label className="auth-label" htmlFor={confirmId}>
              Confirm new password
            </label>
            <Input
              aria-describedby={confirmMessageId}
              aria-invalid={fieldErrors.confirm !== undefined ? 'true' : undefined}
              autoComplete="new-password"
              id={confirmId}
              onChange={(event) => setConfirmPassword(event.target.value)}
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
          <DialogFooter>
            <DialogClose asChild>
              <Button disabled={mutation.isPending} type="button" variant="secondary">
                Cancel
              </Button>
            </DialogClose>
            <Button
              aria-busy={mutation.isPending || undefined}
              disabled={mutation.isPending}
              type="submit"
            >
              {mutation.isPending ? 'Resetting...' : 'Reset password'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
