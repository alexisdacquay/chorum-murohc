import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { AuditRequestError, auditEventsQueryKey, fetchAuditEvents } from './audit'

const EVENT = {
  id: 9,
  actor: 2,
  action: 'chore.create',
  target_type: 'chore',
  target_id: '4',
  created_at: '2026-09-06T12:00:00Z',
  context: { chore_name: 'Wash dishes' },
}

const PAGE = { count: 1, next: null, previous: null, results: [EVENT] }

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })

beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
afterEach(() => vi.unstubAllGlobals())

describe('auditEventsQueryKey', () => {
  test('is stable and distinguishes page and filters', () => {
    expect(auditEventsQueryKey(1, {})).toEqual(['audit', 1, {}])
    expect(auditEventsQueryKey(1, { actor: 2 })).not.toEqual(
      auditEventsQueryKey(1, {}),
    )
    expect(auditEventsQueryKey(2, {})).not.toEqual(auditEventsQueryKey(1, {}))
  })
})

describe('fetchAuditEvents', () => {
  test('reads one page with no filters', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(PAGE))

    await expect(fetchAuditEvents({ page: 1, filters: {} })).resolves.toEqual({
      events: [EVENT],
      count: 1,
      hasNext: false,
      hasPrevious: false,
    })

    expect(fetch).toHaveBeenCalledWith('/api/v1/audit/?page=1', {
      credentials: 'same-origin',
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: undefined,
    })
  })

  test('sends every named filter and drops empty ones', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(PAGE))

    await fetchAuditEvents({
      page: 2,
      filters: { actor: 7, action: 'chore.create', dateFrom: '2026-09-01', dateTo: '' },
    })

    const [url] = vi.mocked(fetch).mock.calls[0]
    const params = new URLSearchParams(String(url).split('?')[1])
    expect(params.get('page')).toBe('2')
    expect(params.get('actor')).toBe('7')
    expect(params.get('action')).toBe('chore.create')
    expect(params.get('date_from')).toBe('2026-09-01')
    expect(params.has('date_to')).toBe(false)
  })

  test('a bad date range reads as a field validation error', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ date_to: ['date_from must not be later than date_to.'] }, 400),
    )

    const error = await fetchAuditEvents({ page: 1, filters: {} }).catch(
      (caught: unknown) => caught,
    )

    expect(error).toBeInstanceOf(AuditRequestError)
    expect((error as AuditRequestError).kind).toBe('validation')
    expect((error as AuditRequestError).fieldErrors).toEqual({
      date_to: 'date_from must not be later than date_to.',
    })
  })

  test('a child caller is refused', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: 'denied' }, 403))

    const error = await fetchAuditEvents({ page: 1, filters: {} }).catch(
      (caught: unknown) => caught,
    )

    expect(error).toBeInstanceOf(AuditRequestError)
    expect((error as AuditRequestError).kind).toBe('forbidden')
  })

  test.each([
    ['a network failure', () => Promise.reject(new Error('offline'))],
    ['a malformed body', () => Promise.resolve(jsonResponse({ count: 'many' }))],
    ['a non-JSON body', () => Promise.resolve(new Response('nope', { status: 200 }))],
  ])('%s is unavailable', async (_name, respond) => {
    vi.mocked(fetch).mockImplementation(respond)

    const error = await fetchAuditEvents({ page: 1, filters: {} }).catch(
      (caught: unknown) => caught,
    )

    expect(error).toBeInstanceOf(AuditRequestError)
    expect((error as AuditRequestError).kind).toBe('unavailable')
  })

  test('a redacted context value passes through unchanged', async () => {
    const redacted = { ...EVENT, context: { password: '[REDACTED]' } }
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ ...PAGE, results: [redacted] }),
    )

    const page = await fetchAuditEvents({ page: 1, filters: {} })

    expect(page.events[0].context).toEqual({ password: '[REDACTED]' })
  })

  test('a null actor (a system-recorded event) is accepted', async () => {
    const systemEvent = { ...EVENT, actor: null }
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ ...PAGE, results: [systemEvent] }),
    )

    const page = await fetchAuditEvents({ page: 1, filters: {} })

    expect(page.events[0].actor).toBeNull()
  })
})
