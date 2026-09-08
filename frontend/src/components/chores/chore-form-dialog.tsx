/**
 * The create and edit form for one chore, shared by both because the two
 * differ only in which request they send and what their title says.
 *
 * Validated twice, like `sign-in-form.tsx`: locally first, so an obviously
 * bad value never leaves the browser, and again by the server, whose
 * duplicate-name check cannot be done locally at all. A local failure and a
 * server failure land on the same field in the same way.
 */

import { useEffect, useId, useRef, useState, type FormEvent } from 'react'

import { useMutation } from '@tanstack/react-query'

import {
  ChoreRequestError,
  createChore,
  ensureCsrfToken,
  updateChore,
  type Chore,
} from '../../api/chores'
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
import { GENERIC_VALIDATION_MESSAGE, describeChoreFailure } from './chore-messages'

export const CHORE_NAME_MAX_LENGTH = 100
export const CHORE_POINTS_MIN = 1
export const CHORE_POINTS_MAX = 2147483647

export const NAME_REQUIRED_MESSAGE = 'Enter a name for this chore.'
export const NAME_TOO_LONG_MESSAGE = `Keep the name to ${CHORE_NAME_MAX_LENGTH} characters or fewer.`
export const POINTS_REQUIRED_MESSAGE = 'Enter how many points this chore is worth.'
export const POINTS_NOT_A_NUMBER_MESSAGE = 'Points must be a whole number.'
export const POINTS_TOO_LOW_MESSAGE = `Points must be at least ${CHORE_POINTS_MIN}.`
export const POINTS_TOO_HIGH_MESSAGE = `Points must be ${CHORE_POINTS_MAX} or less.`

const validateName = (raw: string): string | null => {
  const trimmed = raw.trim()
  if (trimmed === '') {
    return NAME_REQUIRED_MESSAGE
  }
  if (trimmed.length > CHORE_NAME_MAX_LENGTH) {
    return NAME_TOO_LONG_MESSAGE
  }
  return null
}

const validatePoints = (raw: string): string | null => {
  const trimmed = raw.trim()
  if (trimmed === '') {
    return POINTS_REQUIRED_MESSAGE
  }
  if (!/^\d+$/.test(trimmed)) {
    return POINTS_NOT_A_NUMBER_MESSAGE
  }
  const value = Number(trimmed)
  if (value < CHORE_POINTS_MIN) {
    return POINTS_TOO_LOW_MESSAGE
  }
  if (value > CHORE_POINTS_MAX) {
    return POINTS_TOO_HIGH_MESSAGE
  }
  return null
}

interface FieldErrors {
  name?: string
  points?: string
}

export interface ChoreFormDialogProps {
  /** The chore being edited. Ignored, and may be omitted, in create mode. */
  chore?: Chore
  mode: 'create' | 'edit'
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Called with the saved chore once the request succeeds. */
  onSaved: (chore: Chore) => void
}

export function ChoreFormDialog({
  chore,
  mode,
  onOpenChange,
  onSaved,
  open,
}: ChoreFormDialogProps) {
  const nameField = useRef<HTMLInputElement>(null)
  const pointsField = useRef<HTMLInputElement>(null)
  const nameId = useId()
  const pointsId = useId()
  const nameMessageId = useId()
  const pointsMessageId = useId()

  const [name, setName] = useState('')
  const [points, setPoints] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)

  // Every open, including a switch from one chore to another, starts from a
  // clean form: the previous chore's values and any previous failure never
  // leak into the next.
  useEffect(() => {
    if (!open) {
      return
    }
    setName(mode === 'edit' && chore ? chore.name : '')
    setPoints(mode === 'edit' && chore ? String(chore.points) : '')
    setFieldErrors({})
    setFormError(null)
  }, [open, mode, chore])

  const mutation = useMutation({
    mutationFn: async (values: { name: string; points: number }) => {
      const csrfToken = await ensureCsrfToken()
      return mode === 'create'
        ? createChore({ csrfToken, name: values.name, points: values.points })
        : updateChore({
            csrfToken,
            id: (chore as Chore).id,
            name: values.name,
            points: values.points,
          })
    },
    onSuccess: (saved) => onSaved(saved),
    onError: (error) => {
      if (error instanceof ChoreRequestError && error.kind === 'validation') {
        const next: FieldErrors = {}
        if (error.fieldErrors.name) {
          next.name = error.fieldErrors.name
        }
        if (error.fieldErrors.points) {
          next.points = error.fieldErrors.points
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
      setFormError(describeChoreFailure(error))
    },
  })

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    if (mutation.isPending) {
      return
    }

    const nameError = validateName(name)
    const pointsError = validatePoints(points)

    if (nameError !== null || pointsError !== null) {
      setFieldErrors({
        ...(nameError !== null ? { name: nameError } : {}),
        ...(pointsError !== null ? { points: pointsError } : {}),
      })
      setFormError(null)
      ;(nameError !== null ? nameField : pointsField).current?.focus()
      return
    }

    setFieldErrors({})
    setFormError(null)
    mutation.mutate({ name: name.trim(), points: Number(points.trim()) })
  }

  const title = mode === 'create' ? 'Add chore' : 'Edit chore'
  const submitLabel = mutation.isPending
    ? mode === 'create'
      ? 'Adding...'
      : 'Saving...'
    : mode === 'create'
      ? 'Add chore'
      : 'Save changes'

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            Chores award points to a child once completed and approved.
          </DialogDescription>
        </DialogHeader>
        <form className="chore-form" noValidate onSubmit={submit}>
          <div className="chore-form-field">
            <label className="auth-label" htmlFor={nameId}>
              Name
            </label>
            <Input
              aria-describedby={nameMessageId}
              aria-invalid={fieldErrors.name !== undefined ? 'true' : undefined}
              id={nameId}
              maxLength={CHORE_NAME_MAX_LENGTH}
              onChange={(event) => setName(event.target.value)}
              ref={nameField}
              value={name}
            />
            <FormMessage id={nameMessageId} role="alert" tone="error">
              {fieldErrors.name ?? ''}
            </FormMessage>
          </div>
          <div className="chore-form-field">
            <label className="auth-label" htmlFor={pointsId}>
              Points
            </label>
            <Input
              aria-describedby={pointsMessageId}
              aria-invalid={fieldErrors.points !== undefined ? 'true' : undefined}
              id={pointsId}
              inputMode="numeric"
              onChange={(event) => setPoints(event.target.value)}
              ref={pointsField}
              value={points}
            />
            <FormMessage id={pointsMessageId} role="alert" tone="error">
              {fieldErrors.points ?? ''}
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
