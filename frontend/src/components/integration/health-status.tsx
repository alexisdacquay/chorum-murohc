import { useQuery } from '@tanstack/react-query'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'

import { fetchHealth, healthQueryKey } from '../../api/health'
import { Button } from '../ui/button'

export function HealthStatus() {
  const [isManualRetry, setIsManualRetry] = useState(false)
  const isMounted = useRef(true)
  const manageRetryFocus = useRef(false)
  const retryButton = useRef<HTMLButtonElement>(null)
  const retryInFlight = useRef(false)
  const status = useRef<HTMLParagraphElement>(null)
  const health = useQuery({
    queryFn: fetchHealth,
    queryKey: healthQueryKey,
  })

  useEffect(() => {
    isMounted.current = true
    return () => {
      isMounted.current = false
    }
  }, [])

  useLayoutEffect(() => {
    if (!manageRetryFocus.current) return

    if (isManualRetry) {
      status.current?.focus()
      return
    }

    if (health.isError) {
      retryButton.current?.focus()
      manageRetryFocus.current = false
      return
    }

    if (health.isSuccess) {
      status.current?.focus()
      manageRetryFocus.current = false
    }
  }, [health.isError, health.isSuccess, isManualRetry])

  const retry = () => {
    if (retryInFlight.current) return

    retryInFlight.current = true
    manageRetryFocus.current = document.activeElement === retryButton.current
    setIsManualRetry(true)
    void health.refetch().finally(() => {
      retryInFlight.current = false
      if (isMounted.current) setIsManualRetry(false)
    })
  }

  const showError = health.isError || isManualRetry
  const statusText = isManualRetry
    ? 'Checking service…'
    : health.isSuccess
      ? 'Service available.'
      : health.isError
        ? undefined
        : 'Checking service…'

  return (
    <div className="health-status">
      {showError ? (
        <div className="health-error" role="alert">
          <h3>Service unavailable</h3>
          <p>We could not check the service. Try again.</p>
          <Button
            aria-busy={isManualRetry ? 'true' : undefined}
            disabled={isManualRetry}
            onClick={retry}
            ref={retryButton}
          >
            {isManualRetry ? 'Checking…' : 'Try again'}
          </Button>
        </div>
      ) : null}
      <p
        className="health-status-message"
        hidden={statusText === undefined}
        ref={status}
        role="status"
        tabIndex={-1}
      >
        {statusText}
      </p>
    </div>
  )
}
