import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { forwardRef, type ButtonHTMLAttributes } from 'react'

import { cn } from '../../lib/utils'

const buttonVariants = cva('ui-button', {
  variants: {
    variant: {
      primary: 'ui-button-primary',
      secondary: 'ui-button-secondary',
    },
  },
  defaultVariants: {
    variant: 'primary',
  },
})

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ asChild = false, className, type, variant, ...props }, ref) => {
    const Component = asChild ? Slot : 'button'

    return (
      <Component
        className={cn(buttonVariants({ variant }), className)}
        ref={ref}
        type={asChild ? undefined : (type ?? 'button')}
        {...props}
      />
    )
  },
)

Button.displayName = 'Button'
