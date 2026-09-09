/**
 * The one-time level-up celebration (issue #61).
 *
 * "The level-up is shown to the child once, the first time they see it."
 * This dialog opens exactly when the server reports a `pending_level_up`,
 * and however it closes -- the button, Escape, or clicking the overlay --
 * that counts as having been shown, so `onDismiss` always acknowledges. If
 * the acknowledge request fails, the dialog stays open with a retry: the
 * level itself is never at risk (it is computed from the ledger, not spent
 * into), only the "already shown" marker, so it is safe to try again rather
 * than to silently drop it and risk a permanent write failure going unseen.
 */

import { Button } from '../ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog'
import { FormMessage } from '../ui/form-message'

export interface LevelUpCelebrationDialogProps {
  level: number
  maxLevel: number
  isAcknowledging: boolean
  error: string | null
  onDismiss: () => void
}

export function LevelUpCelebrationDialog({
  error,
  isAcknowledging,
  level,
  maxLevel,
  onDismiss,
}: LevelUpCelebrationDialogProps) {
  return (
    <Dialog onOpenChange={(open) => !open && onDismiss()} open>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Level up! You reached level {level}</DialogTitle>
          <DialogDescription>
            {level >= maxLevel
              ? 'You have reached the highest level there is.'
              : `Keep earning points to reach level ${level + 1}.`}
          </DialogDescription>
        </DialogHeader>
        <FormMessage role="alert" tone="error">
          {error ?? ''}
        </FormMessage>
        <DialogFooter>
          <Button
            aria-busy={isAcknowledging || undefined}
            disabled={isAcknowledging}
            onClick={onDismiss}
            type="button"
          >
            {isAcknowledging ? 'Saving...' : 'Nice!'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
