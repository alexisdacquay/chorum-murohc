import {
  useEffect,
  useRef,
  type MouseEvent,
  type ReactNode,
} from 'react'

import { ShellBoundary } from './shell-boundary'

export interface ApplicationShellProps {
  children: ReactNode
  contentKey: string
  isLoading?: boolean
  /**
   * Optional primary navigation, rendered in the banner after the product
   * name. Omitted or empty, the banner carries no navigation landmark.
   */
  navigation?: ReactNode
}

export function ApplicationShell({
  children,
  contentKey,
  isLoading = false,
  navigation,
}: ApplicationShellProps) {
  const mainRef = useRef<HTMLElement>(null)
  const previousContentKey = useRef(contentKey)

  useEffect(() => {
    if (previousContentKey.current !== contentKey) {
      previousContentKey.current = contentKey
      mainRef.current?.focus()
    }
  }, [contentKey])

  const focusMain = () => mainRef.current?.focus()
  const skipToMain = (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault()
    focusMain()
  }

  return (
    <>
      <a className="skip-link" href="#main-content" onClick={skipToMain}>
        Skip to main content
      </a>
      <header className="shell-header">
        <p className="shell-product-name">Chorum-murohc</p>
        {navigation}
      </header>
      <main
        aria-busy={isLoading || undefined}
        className="shell-main"
        id="main-content"
        ref={mainRef}
        tabIndex={-1}
      >
        {isLoading ? (
          <p aria-live="polite" className="shell-feedback" role="status">
            Loading…
          </p>
        ) : (
          <ShellBoundary contentKey={contentKey} onRecover={focusMain}>
            {children}
          </ShellBoundary>
        )}
      </main>
    </>
  )
}
