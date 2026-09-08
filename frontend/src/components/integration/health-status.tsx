import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import { fetchHealth, healthQueryKey } from '../../api/health'
import { Button } from '../ui/button'

export function HealthStatus() {
  const [isManualRetry, setIsManualRetry] = useState(false)
  const isMounted = useRef(true)
  const retryInFlight = useRef(false)
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

  const retry = () => {
    if (retryInFlight.current) return

    retryInFlight.current = true
    setIsManualRetry(true)
    void health.refetch().finally(() => {
      retryInFlight.current = false
      if (isMounted.current) setIsManualRetry(false)
    })
  }

  if (health.isError || isManualRetry) {
    return (
      <div className="health-status">
        <div className="health-error" role="alert">
          <h3>Service unavailable</h3>
          <p>We could not check the service. Try again.</p>
          <Button
            aria-busy={health.isFetching ? 'true' : undefined}
            aria-disabled={health.isFetching ? 'true' : undefined}
            onClick={retry}
          >
            {health.isFetching ? 'Checking…' : 'Try again'}
          </Button>
        </div>
        {health.isFetching ? <p role="status">Checking service…</p> : null}
      </div>
    )
  }

  return (
    <p className="health-status-message" role="status">
      {health.isSuccess ? 'Service available.' : 'Checking service…'}
    </p>
  )
}
