import { cva, type VariantProps } from 'class-variance-authority'
import { forwardRef, type HTMLAttributes } from 'react'

import { cn } from '../../lib/utils'

const formMessageVariants = cva('form-message', {
  variants: {
    tone: {
      help: 'form-message-help',
      error: 'form-message-error',
      success: 'form-message-success',
    },
  },
  defaultVariants: {
    tone: 'help',
  },
})

export interface FormMessageProps
  extends HTMLAttributes<HTMLParagraphElement>,
    VariantProps<typeof formMessageVariants> {}

export const FormMessage = forwardRef<HTMLParagraphElement, FormMessageProps>(
  ({ className, tone, ...props }, ref) => (
    <p
      className={cn(formMessageVariants({ tone }), className)}
      ref={ref}
      {...props}
    />
  ),
)

FormMessage.displayName = 'FormMessage'
