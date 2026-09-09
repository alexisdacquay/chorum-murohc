/**
 * The create and edit form for one household member, shared by both because
 * the two differ only in which request they send, which fields they show,
 * and what their title says - the same shape `chore-form-dialog.tsx` uses
 * for a chore.
 *
 * Only create sets a password here: an edit that could quietly change
 * someone else's password would undercut the proof
 * `reset-member-password-dialog.tsx` requires for exactly that action
 * (issue #129), so this form's edit mode never sends one. It also never
 * touches the caller's own account - `household-screen.tsx` hides every
 * action, this dialog included, on the caller's own row.
 *
 * Validated twice: locally first, so an obviously bad value never leaves the
 * browser, and again by the server, whose taken-username and password-
 * strength checks cannot be done locally at all. A local failure and a
 * server failure land on the same field in the same way.
 */

import { useEffect, useId, useRef, useState, type FormEvent } from 'react'

import { useMutation } from '@tanstack/react-query'

import {
  MemberRequestError,
  createMember,
  ensureCsrfToken,
  updateMember,
  type Member,
  type MemberRole,
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

export const USERNAME_REQUIRED_MESSAGE = 'Enter a username.'
export const PASSWORD_REQUIRED_MESSAGE = 'Enter a password.'

const DEFAULT_ROLE: MemberRole = 'child'

const validateUsername = (raw: string): string | null =>
  raw.trim() === '' ? USERNAME_REQUIRED_MESSAGE : null

interface FieldErrors {
  username?: string
  password?: string
  role?: string
}

export interface MemberFormDialogProps {
  /** The member being edited. Ignored, and may be omitted, in create mode. */
  member?: Member
  mode: 'create' | 'edit'
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Called with the saved member once the request succeeds. */
  onSaved: (member: Member) => void
}

export function MemberFormDialog({
  member,
  mode,
  onOpenChange,
  onSaved,
  open,
}: MemberFormDialogProps) {
  const usernameField = useRef<HTMLInputElement>(null)
  const passwordField = useRef<HTMLInputElement>(null)
  const usernameId = useId()
  const passwordId = useId()
  const roleId = useId()
  const usernameMessageId = useId()
  const passwordMessageId = useId()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<MemberRole>(DEFAULT_ROLE)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)

  // Every open, including a switch from one member to another, starts from a
  // clean form: the previous member's values, and any previous failure or
  // password entry, never leak into the next.
  useEffect(() => {
    if (!open) {
      return
    }
    setUsername(mode === 'edit' && member ? member.username : '')
    setPassword('')
    setRole(mode === 'edit' && member ? member.role : DEFAULT_ROLE)
    setFieldErrors({})
    setFormError(null)
  }, [open, mode, member])

  const mutation = useMutation({
    mutationFn: async (values: {
      username: string
      password: string
      role: MemberRole
    }) => {
      const csrfToken = await ensureCsrfToken()
      return mode === 'create'
        ? createMember({
            csrfToken,
            username: values.username,
            password: values.password,
            role: values.role,
          })
        : updateMember({
            csrfToken,
            id: (member as Member).id,
            username: values.username,
            role: values.role,
          })
    },
    onSuccess: (saved) => onSaved(saved),
    onError: (error) => {
      if (error instanceof MemberRequestError && error.kind === 'validation') {
        const next: FieldErrors = {}
        if (error.fieldErrors.username) {
          next.username = error.fieldErrors.username
        }
        if (error.fieldErrors.password) {
          next.password = error.fieldErrors.password
        }
        if (error.fieldErrors.role) {
          next.role = error.fieldErrors.role
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

    const usernameError = validateUsername(username)
    const passwordError =
      mode === 'create' && password === '' ? PASSWORD_REQUIRED_MESSAGE : null

    if (usernameError !== null || passwordError !== null) {
      setFieldErrors({
        ...(usernameError !== null ? { username: usernameError } : {}),
        ...(passwordError !== null ? { password: passwordError } : {}),
      })
      setFormError(null)
      ;(usernameError !== null ? usernameField : passwordField).current?.focus()
      return
    }

    setFieldErrors({})
    setFormError(null)
    mutation.mutate({ username: username.trim(), password, role })
  }

  const title = mode === 'create' ? 'Add household member' : 'Edit household member'
  const submitLabel = mutation.isPending
    ? mode === 'create'
      ? 'Adding...'
      : 'Saving...'
    : mode === 'create'
      ? 'Add member'
      : 'Save changes'

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            A parent account can manage the household. A child account can
            complete chores and spend points.
          </DialogDescription>
        </DialogHeader>
        <form className="chore-form" noValidate onSubmit={submit}>
          <div className="chore-form-field">
            <label className="auth-label" htmlFor={usernameId}>
              Username
            </label>
            <Input
              aria-describedby={usernameMessageId}
              aria-invalid={fieldErrors.username !== undefined ? 'true' : undefined}
              autoComplete="username"
              id={usernameId}
              onChange={(event) => setUsername(event.target.value)}
              ref={usernameField}
              value={username}
            />
            <FormMessage id={usernameMessageId} role="alert" tone="error">
              {fieldErrors.username ?? ''}
            </FormMessage>
          </div>
          {mode === 'create' ? (
            <div className="chore-form-field">
              <label className="auth-label" htmlFor={passwordId}>
                Password
              </label>
              <Input
                aria-describedby={passwordMessageId}
                aria-invalid={fieldErrors.password !== undefined ? 'true' : undefined}
                autoComplete="new-password"
                id={passwordId}
                onChange={(event) => setPassword(event.target.value)}
                ref={passwordField}
                type="password"
                value={password}
              />
              <FormMessage id={passwordMessageId} role="alert" tone="error">
                {fieldErrors.password ?? ''}
              </FormMessage>
            </div>
          ) : null}
          <div className="chore-form-field">
            <label className="auth-label" htmlFor={roleId}>
              Role
            </label>
            <select
              className="ui-input"
              id={roleId}
              onChange={(event) => setRole(event.target.value as MemberRole)}
              value={role}
            >
              <option value="child">Child</option>
              <option value="parent">Parent</option>
            </select>
            <FormMessage role="alert" tone="error">
              {fieldErrors.role ?? ''}
            </FormMessage>
          </div>
          <FormMessage role="alert" tone="error">
            {formError ?? ''}
          </FormMessage>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="secondary">
                Cancel
              </Button>
            </DialogClose>
            <Button
              aria-busy={mutation.isPending || undefined}
              disabled={mutation.isPending}
              type="submit"
            >
              {submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
