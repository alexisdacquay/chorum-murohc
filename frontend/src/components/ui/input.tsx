import { forwardRef, type InputHTMLAttributes } from 'react'

import { cn } from '../../lib/utils'

export interface InputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  /**
   * Only the two types a current screen needs. `password` keeps the value out
   * of the rendered document; nothing here ever reveals it as text.
   */
  type?: 'text' | 'password'
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
