export interface HealthResponse {
  status: 'ok'
}

export const healthQueryKey = ['health'] as const

const isHealthResponse = (value: unknown): value is HealthResponse => {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false
  }

  const record = value as Record<string, unknown>
  return (
    Object.keys(record).length === 1 &&
    Object.hasOwn(record, 'status') &&
    record.status === 'ok'
  )
}

const isJsonMediaType = (contentType: string | null) =>
  contentType !== null &&
  /^application\/(?:[a-z0-9!#$&^_.+-]+\+)?json(?:\s*;|$)/i.test(contentType)

export const fetchHealth = async ({
  signal,
}: {
  signal: AbortSignal
}): Promise<HealthResponse> => {
  const response = await fetch('/api/v1/health/', {
    method: 'GET',
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
    signal,
  })

  if (
    response.redirected ||
    response.status !== 200 ||
    !isJsonMediaType(response.headers.get('Content-Type'))
  ) {
    throw new Error('Health request failed')
  }

  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new Error('Health request failed')
  }

  if (!isHealthResponse(body)) {
    throw new Error('Health request failed')
  }

  return body
}
