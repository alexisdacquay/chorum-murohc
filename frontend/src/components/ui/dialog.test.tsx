import { useState } from 'react'

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from './dialog'

/**
 * The pattern every conditionally-mounted dialog in the product uses:
 * `{target !== null ? <Dialog ...> : null}`. This is what actually
 * unmounts the whole `<Dialog>` the instant it closes, which is what broke
 * focus return in the first place (issue #159, A-01).
 */
function ConditionallyMountedDialog() {
  const [open, setOpen] = useState(false)

  return (
    <>
      <button onClick={() => setOpen(true)} type="button">
        Open
      </button>
      {open ? (
        <Dialog onOpenChange={(next) => !next && setOpen(false)} open={open}>
          <DialogContent>
            <DialogTitle>Example dialog</DialogTitle>
            <DialogDescription>Body text.</DialogDescription>
            <DialogClose asChild>
              <button type="button">Close</button>
            </DialogClose>
          </DialogContent>
        </Dialog>
      ) : null}
    </>
  )
}

/** The pattern `chore-form-dialog.tsx` and its siblings use: always mounted, `open` toggled. */
function AlwaysMountedDialog() {
  const [open, setOpen] = useState(false)

  return (
    <>
      <button onClick={() => setOpen(true)} type="button">
        Open
      </button>
      <Dialog onOpenChange={setOpen} open={open}>
        <DialogContent>
          <DialogTitle>Example dialog</DialogTitle>
          <DialogDescription>Body text.</DialogDescription>
          <DialogClose asChild>
            <button type="button">Close</button>
          </DialogClose>
        </DialogContent>
      </Dialog>
    </>
  )
}

describe('Dialog', () => {
  test('Escape returns focus to the trigger when the caller unmounts the dialog on close', async () => {
    render(<ConditionallyMountedDialog />)

    const trigger = screen.getByRole('button', { name: 'Open' })
    trigger.focus()
    fireEvent.click(trigger)
    await screen.findByRole('dialog')

    fireEvent.keyDown(document, { key: 'Escape' })

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(trigger))
  })

  test('the Close control returns focus to the trigger when the caller unmounts the dialog on close', async () => {
    render(<ConditionallyMountedDialog />)

    const trigger = screen.getByRole('button', { name: 'Open' })
    trigger.focus()
    fireEvent.click(trigger)
    await screen.findByRole('dialog')

    fireEvent.click(screen.getByRole('button', { name: 'Close' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(trigger))
  })

  test('Escape still returns focus to the trigger when the caller keeps the dialog mounted', async () => {
    render(<AlwaysMountedDialog />)

    const trigger = screen.getByRole('button', { name: 'Open' })
    trigger.focus()
    fireEvent.click(trigger)
    await screen.findByRole('dialog')

    fireEvent.keyDown(document, { key: 'Escape' })

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(trigger))
  })
})
