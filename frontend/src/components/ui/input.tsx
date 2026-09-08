import { forwardRef, type InputHTMLAttributes } from 'react'

import { cn } from '../../lib/utils'

export interface InputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  type?: 'text'
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, type = 'text', ...props }, ref) => (
    <input
      className={cn('ui-input', className)}
      ref={ref}
      type={type}
      {...props}
    />
  ),
)

Input.displayName = 'Input'
