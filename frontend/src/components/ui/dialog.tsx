import * as DialogPrimitive from '@radix-ui/react-dialog'
import {
  forwardRef,
  useEffect,
  useRef,
  type ComponentPropsWithoutRef,
  type ElementRef,
  type HTMLAttributes,
} from 'react'

import { cn } from '../../lib/utils'

/**
 * Every dialog in the product is mounted through this one wrapper (issue
 * #159, A-01). Radix's own close-focus restoration
 * (`@radix-ui/react-dialog`'s `DialogContentModal`) only ever focuses
 * `context.triggerRef.current` - the DOM node under Radix's own
 * `<DialogTrigger>`. Nothing here renders one: every screen opens its
 * dialog from a plain button tied to its own local state instead, so that
 * ref is always null and Radix's restoration is a no-op on every dialog in
 * the product, not only the ones a screen unmounts on close. Fixing that
 * per screen would mean the same fix at every call site; fixing it here
 * means every dialog gets it, including ones not yet written.
 *
 * The wrapper remembers whatever was focused when the dialog opened and,
 * the moment Radix asks to close it for any reason - Escape, an outside
 * click, or a Close button - puts focus back there itself. That restore is
 * queued with `setTimeout`, not run inline: while the dialog is still
 * `trapped`, `FocusScope` keeps a document-level listener that yanks focus
 * straight back in the instant it sees it move outside the container, and
 * that trap only lifts once React processes this same close and unmounts
 * or relaxes it. Queuing past that point is exactly what Radix's own
 * (otherwise unusable, per above) restoration does too.
 */
export function Dialog({
  onOpenChange,
  open,
  ...props
}: ComponentPropsWithoutRef<typeof DialogPrimitive.Root>) {
  const previouslyFocused = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (open) {
      previouslyFocused.current =
        document.activeElement instanceof HTMLElement ? document.activeElement : null
    }
  }, [open])

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      const target = previouslyFocused.current
      window.setTimeout(() => {
        if (target !== null && document.body.contains(target)) {
          target.focus()
        }
      }, 0)
    }
    onOpenChange?.(next)
  }

  return <DialogPrimitive.Root onOpenChange={handleOpenChange} open={open} {...props} />
}
export const DialogTrigger = DialogPrimitive.Trigger
export const DialogPortal = DialogPrimitive.Portal
export const DialogClose = DialogPrimitive.Close

export const DialogOverlay = forwardRef<
  ElementRef<typeof DialogPrimitive.Overlay>,
  ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    className={cn('ui-dialog-overlay', className)}
    ref={ref}
    {...props}
  />
))
DialogOverlay.displayName = DialogPrimitive.Overlay.displayName

export const DialogContent = forwardRef<
  ElementRef<typeof DialogPrimitive.Content>,
  ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ children, className, ...props }, ref) => (
  <DialogPortal>
    <DialogOverlay />
    <DialogPrimitive.Content
      className={cn('ui-dialog-content', className)}
      ref={ref}
      {...props}
    >
      {children}
    </DialogPrimitive.Content>
  </DialogPortal>
))
DialogContent.displayName = DialogPrimitive.Content.displayName

export const DialogHeader = forwardRef<
  HTMLDivElement,
  HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div className={cn('ui-dialog-header', className)} ref={ref} {...props} />
))
DialogHeader.displayName = 'DialogHeader'

export const DialogTitle = forwardRef<
  ElementRef<typeof DialogPrimitive.Title>,
  ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    className={cn('ui-dialog-title', className)}
    ref={ref}
    {...props}
  />
))
DialogTitle.displayName = DialogPrimitive.Title.displayName

export const DialogDescription = forwardRef<
  ElementRef<typeof DialogPrimitive.Description>,
  ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    className={cn('ui-dialog-description', className)}
    ref={ref}
    {...props}
  />
))
DialogDescription.displayName = DialogPrimitive.Description.displayName

export const DialogFooter = forwardRef<
  HTMLDivElement,
  HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div className={cn('ui-dialog-footer', className)} ref={ref} {...props} />
))
DialogFooter.displayName = 'DialogFooter'
