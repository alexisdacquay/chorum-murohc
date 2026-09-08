/**
 * The create and edit form for one reward, shared by both, exactly as
 * `chore-form-dialog.tsx` shares one form between creating and editing a
 * chore. Validated twice: locally first, so an obviously bad value never
 * leaves the browser, and again by the server, whose duplicate-name check
 * cannot be done locally at all.
 */

import { useEffect, useId, useRef, useState, type FormEvent } from 'react'

import { useMutation } from '@tanstack/react-query'

import {
  RewardRequestError,
  createReward,
  ensureCsrfToken,
  updateReward,
  type Reward,
} from '../../api/rewards'
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
import { GENERIC_VALIDATION_MESSAGE, describeRewardFailure } from './reward-messages'

export const REWARD_NAME_MAX_LENGTH = 100
export const REWARD_POINTS_MIN = 1
export const REWARD_POINTS_MAX = 2147483647

export const NAME_REQUIRED_MESSAGE = 'Enter a name for this reward.'
export const NAME_TOO_LONG_MESSAGE = `Keep the name to ${REWARD_NAME_MAX_LENGTH} characters or fewer.`
export const POINTS_REQUIRED_MESSAGE = 'Enter how many points this reward costs.'
export const POINTS_NOT_A_NUMBER_MESSAGE = 'Points must be a whole number.'
export const POINTS_TOO_LOW_MESSAGE = `Points must be at least ${REWARD_POINTS_MIN}.`
export const POINTS_TOO_HIGH_MESSAGE = `Points must be ${REWARD_POINTS_MAX} or less.`

const validateName = (raw: string): string | null => {
  const trimmed = raw.trim()
  if (trimmed === '') {
    return NAME_REQUIRED_MESSAGE
  }
  if (trimmed.length > REWARD_NAME_MAX_LENGTH) {
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
  if (value < REWARD_POINTS_MIN) {
    return POINTS_TOO_LOW_MESSAGE
  }
  if (value > REWARD_POINTS_MAX) {
    return POINTS_TOO_HIGH_MESSAGE
  }
  return null
}

interface FieldErrors {
  name?: string
  points?: string
}

export interface RewardFormDialogProps {
  reward?: Reward
  mode: 'create' | 'edit'
  open: boolean
  onOpenChange: (open: boolean) => void
  onSaved: (reward: Reward) => void
}

export function RewardFormDialog({
  mode,
  onOpenChange,
  onSaved,
  open,
  reward,
}: RewardFormDialogProps) {
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

  useEffect(() => {
    if (!open) {
      return
    }
    setName(mode === 'edit' && reward ? reward.name : '')
    setPoints(mode === 'edit' && reward ? String(reward.points) : '')
    setFieldErrors({})
    setFormError(null)
  }, [open, mode, reward])

  const mutation = useMutation({
    mutationFn: async (values: { name: string; points: number }) => {
      const csrfToken = await ensureCsrfToken()
      return mode === 'create'
        ? createReward({ csrfToken, name: values.name, points: values.points })
        : updateReward({
            csrfToken,
            id: (reward as Reward).id,
            name: values.name,
            points: values.points,
          })
    },
    onSuccess: (saved) => onSaved(saved),
    onError: (error) => {
      if (error instanceof RewardRequestError && error.kind === 'validation') {
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
      setFormError(describeRewardFailure(error))
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

  const title = mode === 'create' ? 'Add reward' : 'Edit reward'
  const submitLabel = mutation.isPending
    ? mode === 'create'
      ? 'Adding...'
      : 'Saving...'
    : mode === 'create'
      ? 'Add reward'
      : 'Save changes'

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            A child spends points to request this reward. You hand it over or
            cancel the request afterwards.
          </DialogDescription>
        </DialogHeader>
        <form className="reward-form" noValidate onSubmit={submit}>
          <div className="reward-form-field">
            <label className="auth-label" htmlFor={nameId}>
              Name
            </label>
            <Input
              aria-describedby={nameMessageId}
              aria-invalid={fieldErrors.name !== undefined ? 'true' : undefined}
              id={nameId}
              maxLength={REWARD_NAME_MAX_LENGTH}
              onChange={(event) => setName(event.target.value)}
              ref={nameField}
              value={name}
            />
            <FormMessage id={nameMessageId} role="alert" tone="error">
              {fieldErrors.name ?? ''}
            </FormMessage>
          </div>
          <div className="reward-form-field">
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
