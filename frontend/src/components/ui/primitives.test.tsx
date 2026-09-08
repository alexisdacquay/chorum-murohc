import { createRef } from 'react'

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { Button } from './button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from './card'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
  DialogTrigger,
} from './dialog'
import { FormMessage } from './form-message'
import { Input } from './input'

const renderDialog = () =>
  render(
    <div>
      <Button>Background action</Button>
      <Dialog>
        <DialogTrigger asChild>
          <Button>Open dialog</Button>
        </DialogTrigger>
        <DialogContent>
          <DialogTitle>Reference dialog</DialogTitle>
          <DialogDescription>
            This description explains the modal.
          </DialogDescription>
          <p>Ordinary dialog content.</p>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="secondary">Close</Button>
            </DialogClose>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>,
  )

describe('Button', () => {
  test('forwards native behaviour, props, ref, and bounded states', () => {
    const onPrimary = vi.fn()
    const onDisabled = vi.fn()
    const onBusy = vi.fn()
    const ref = createRef<HTMLButtonElement>()

    render(
      <div>
        <Button
          aria-label="Primary control"
          data-proof="forwarded"
          onClick={onPrimary}
          ref={ref}
        >
          Primary
        </Button>
        <Button variant="secondary">Secondary</Button>
        <Button disabled onClick={onDisabled}>
          Disabled
        </Button>
        <Button aria-busy="true" disabled onClick={onBusy}>
          Saving…
        </Button>
      </div>,
    )

    const primary = screen.getByRole('button', { name: 'Primary control' })
    const disabled = screen.getByRole('button', { name: 'Disabled' })
    const busy = screen.getByRole('button', { name: 'Saving…' })

    expect(primary).toHaveProperty('type', 'button')
    expect(primary.getAttribute('data-proof')).toBe('forwarded')
    expect(ref.current).toBe(primary)
    expect(screen.getByRole('button', { name: 'Secondary' })).toBeDefined()
    expect(disabled).toHaveProperty('disabled', true)
    expect(busy).toHaveProperty('disabled', true)
    expect(busy.getAttribute('aria-busy')).toBe('true')

    fireEvent.click(primary)
    fireEvent.click(disabled)
    fireEvent.click(busy)

    expect(onPrimary).toHaveBeenCalledOnce()
    expect(onDisabled).not.toHaveBeenCalled()
    expect(onBusy).not.toHaveBeenCalled()
  })

  test('composes one interactive child without losing its name or handlers', () => {
    const slotHandler = vi.fn()
    const childHandler = vi.fn()

    render(
      <Button asChild onClick={slotHandler} variant="secondary">
        <button onClick={childHandler} type="button">
          Composed action
        </button>
      </Button>,
    )

    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(1)
    expect(buttons[0].textContent).toBe('Composed action')

    fireEvent.click(buttons[0])
    expect(childHandler).toHaveBeenCalledOnce()
    expect(slotHandler).toHaveBeenCalledOnce()
  })
})

describe('Input and FormMessage', () => {
  test('keeps native labels, associations, state, handlers, and refs', () => {
    const onChange = vi.fn()
    const ref = createRef<HTMLInputElement>()

    render(
      <div>
        <label htmlFor="reference-code">Reference code</label>
        <Input
          aria-describedby="reference-error"
          aria-invalid="true"
          data-proof="forwarded"
          defaultValue="Initial"
          id="reference-code"
          onChange={onChange}
          ref={ref}
        />
        <FormMessage id="reference-error" role="alert" tone="error">
          Error: Enter a valid reference code.
        </FormMessage>
        <label htmlFor="disabled-input">Disabled example</label>
        <Input disabled id="disabled-input" />
        <label htmlFor="secret-input">Password example</label>
        <Input
          autoComplete="current-password"
          id="secret-input"
          type="password"
        />
        <FormMessage tone="help">Helpful guidance.</FormMessage>
        <FormMessage role="status" tone="success">
          Success: The value is ready.
        </FormMessage>
      </div>,
    )

    const input = screen.getByRole('textbox', { name: 'Reference code' })
    const disabled = screen.getByRole('textbox', { name: 'Disabled example' })

    expect(input).toHaveProperty('type', 'text')
    expect(input.getAttribute('aria-invalid')).toBe('true')
    expect(input.getAttribute('aria-describedby')).toBe('reference-error')
    expect(input.getAttribute('data-proof')).toBe('forwarded')
    expect(ref.current).toBe(input)
    expect(screen.getByRole('alert').textContent).toMatch(/^Error:/)
    expect(screen.getByRole('status').textContent).toMatch(/^Success:/)
    expect(screen.getByText('Helpful guidance.').getAttribute('role')).toBeNull()
    expect(disabled).toHaveProperty('disabled', true)

    // A password field is masked, so it is not a textbox and its value is
    // never exposed as document text.
    const secret = screen.getByLabelText('Password example')

    expect(secret).toHaveProperty('type', 'password')
    expect(secret.getAttribute('autocomplete')).toBe('current-password')
    expect(screen.queryByRole('textbox', { name: 'Password example' })).toBeNull()
    fireEvent.change(secret, { target: { value: 'test-only-password' } })
    expect(document.body.textContent).not.toContain('test-only-password')

    fireEvent.change(input, { target: { value: 'Changed' } })
    expect(onChange).toHaveBeenCalledOnce()
    expect(input).toHaveProperty('value', 'Changed')
  })
})

describe('Card', () => {
  test('preserves supplied content without adding interactive or landmark semantics', () => {
    const ref = createRef<HTMLDivElement>()
    const { container } = render(
      <Card aria-labelledby="card-heading" data-proof="forwarded" ref={ref}>
        <CardHeader>
          <CardTitle>
            <h2 id="card-heading">Reference card</h2>
          </CardTitle>
          <CardDescription>A supplied description.</CardDescription>
        </CardHeader>
        <CardContent>Supplied content.</CardContent>
        <CardFooter>Supplied footer.</CardFooter>
      </Card>,
    )

    expect(screen.getByRole('heading', { name: 'Reference card' })).toBeDefined()
    expect(screen.getByText('A supplied description.')).toBeDefined()
    expect(screen.getByText('Supplied content.')).toBeDefined()
    expect(screen.getByText('Supplied footer.')).toBeDefined()
    expect(screen.queryByRole('button')).toBeNull()
    expect(screen.queryByRole('link')).toBeNull()
    expect(container.querySelector('article')).toBeNull()
    expect(ref.current?.getAttribute('data-proof')).toBe('forwarded')
    expect(ref.current?.getAttribute('aria-labelledby')).toBe('card-heading')
  })
})

describe('Dialog', () => {
  test('opens one named modal, moves focus inside, and hides background controls', async () => {
    renderDialog()

    fireEvent.click(screen.getByRole('button', { name: 'Open dialog' }))

    const dialog = await screen.findByRole('dialog', {
      name: 'Reference dialog',
      description: 'This description explains the modal.',
    })
    expect(screen.getAllByRole('dialog')).toHaveLength(1)
    expect(dialog.textContent).toContain('Ordinary dialog content.')
    expect(screen.queryByRole('button', { name: 'Background action' })).toBeNull()

    const close = screen.getByRole('button', { name: 'Close' })
    await waitFor(() => expect(document.activeElement).toBe(close))
  })

  test('dismisses with Escape and visible close, restoring the trigger each time', async () => {
    renderDialog()
    const trigger = screen.getByRole('button', { name: 'Open dialog' })

    fireEvent.click(trigger)
    await screen.findByRole('dialog', { name: 'Reference dialog' })
    fireEvent.keyDown(document, { key: 'Escape' })

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(trigger))

    fireEvent.click(trigger)
    await screen.findByRole('dialog', { name: 'Reference dialog' })
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(trigger))
  })
})
