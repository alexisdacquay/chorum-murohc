/**
 * The creature chooser (issue #66).
 *
 * A child picks their line at first sign-in, after their account exists, so
 * account creation never waits on this. The choice is write-once on the
 * server and a creature is meant to be lived with, so the pick is confirmed
 * before it is sent rather than saved on the first tap.
 *
 * Every preview is an original drawing committed to this repository and
 * served from the same origin; the client never loads an image from anywhere
 * else. A drawing that fails to load leaves the name and the description,
 * which are the parts a child needs to choose.
 */

import { useState } from 'react'

import { useMutation, useQuery } from '@tanstack/react-query'

import {
  CREATURE_LINES_QUERY_KEY,
  chooseCreatureLine,
  ensureCsrfToken,
  fetchCreatureLines,
  type Creature,
  type CreatureLineSummary,
} from '../../api/creatures'
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
import { describeCreatureFailure } from './creature-messages'

export interface CreatureChooserProps {
  /** Called with the creature the server saved, once a pick succeeds. */
  onChosen: (creature: Creature) => void
}

export function CreatureChooser({ onChosen }: CreatureChooserProps) {
  const [pending, setPending] = useState<CreatureLineSummary | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  const lines = useQuery({
    queryKey: CREATURE_LINES_QUERY_KEY,
    queryFn: ({ signal }) => fetchCreatureLines({ signal }),
  })

  const save = useMutation({
    mutationFn: async (line: string) => {
      const csrfToken = await ensureCsrfToken()
      return chooseCreatureLine({ csrfToken, line })
    },
    onSuccess: (creature) => {
      setSaveError(null)
      setPending(null)
      onChosen(creature)
    },
    onError: (error) => setSaveError(describeCreatureFailure(error)),
  })

  if (lines.isPending) {
    return (
      <p aria-live="polite" className="creature-status" role="status">
        Loading creatures...
      </p>
    )
  }

  if (lines.isError) {
    return (
      <div className="creature-error">
        <FormMessage role="alert" tone="error">
          {describeCreatureFailure(lines.error)}
        </FormMessage>
        <Button onClick={() => void lines.refetch()} variant="secondary">
          Try again
        </Button>
      </div>
    )
  }

  return (
    <div className="creature-chooser">
      <p className="creature-chooser-intro">
        Pick one to look after. It grows into a new form at levels 1, 4, 7 and 10,
        and it stays yours.
      </p>
      <ul className="creature-chooser-list">
        {lines.data.map((line) => (
          <li key={line.slug}>
            <button
              className="creature-chooser-option"
              disabled={save.isPending}
              onClick={() => {
                setSaveError(null)
                setPending(line)
              }}
              type="button"
            >
              <img
                alt={line.preview.alt_text}
                className="creature-drawing creature-drawing-preview"
                src={line.preview.asset_path}
              />
              <span className="creature-chooser-name">{line.name}</span>
              <span className="creature-chooser-description">{line.description}</span>
            </button>
          </li>
        ))}
      </ul>
      <Dialog
        onOpenChange={(open) => {
          if (!open && !save.isPending) {
            setPending(null)
          }
        }}
        open={pending !== null}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Choose the {pending?.name ?? 'creature'}?</DialogTitle>
            <DialogDescription>
              This is the creature you keep. You cannot swap it for another one
              later.
            </DialogDescription>
          </DialogHeader>
          <FormMessage role="alert" tone="error">
            {saveError ?? ''}
          </FormMessage>
          <DialogFooter>
            <DialogClose asChild>
              <Button disabled={save.isPending} type="button" variant="secondary">
                Cancel
              </Button>
            </DialogClose>
            <Button
              aria-busy={save.isPending || undefined}
              disabled={save.isPending || pending === null}
              onClick={() => {
                if (pending !== null) {
                  save.mutate(pending.slug)
                }
              }}
              type="button"
            >
              {save.isPending ? 'Saving...' : 'Yes, choose this one'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
