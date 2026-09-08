import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { createQueryClient } from '../../api/query-client'
import { HealthStatus } from './health-status'

const clients: ReturnType<typeof createQueryClient>[] = []

const validResponse = () =>
  new Response(JSON.stringify({ status: 'ok' }), {
    headers: { 'Content-Type': 'application/json' },
    status: 200,
  })

const renderStatus = () => {
  const client = createQueryClient()
  clients.push(client)
  return render(
    <QueryClientProvider client={client}>
      <HealthStatus />
    </QueryClientProvider>,
  )
}

beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
afterEach(() => {
  for (const client of clients.splice(0)) client.clear()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('HealthStatus', () => {
  test('shows polite loading then the bounded success copy without moving focus', async () => {
    const existingFocus = document.createElement('button')
    existingFocus.textContent = 'Existing focus'
    document.body.append(existingFocus)
    existingFocus.focus()
    let resolveRequest: ((response: Response) => void) | undefined
    vi.mocked(fetch).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveRequest = resolve
        }),
    )

    renderStatus()

    expect(screen.getByRole('status').textContent).toBe('Checking service…')
    expect(document.activeElement).toBe(existingFocus)

    resolveRequest?.(validResponse())
    await waitFor(() =>
      expect(screen.getByRole('status').textContent).toBe('Service available.'),
    )
    expect(document.activeElement).toBe(existingFocus)
    expect(screen.queryByText(/status|api|health|host|version/i)).toBeNull()
    existingFocus.remove()
  })

  test('renders one generic private alert for request and contract failures', async () => {
    vi.mocked(fetch).mockRejectedValue(new Error('internal-only-detail'))

    const { container } = renderStatus()
    const alert = await screen.findByRole('alert')

    expect(screen.getAllByRole('alert')).toHaveLength(1)
    expect(
      screen.getByRole('heading', { name: 'Service unavailable' }),
    ).toBeDefined()
    expect(
      screen.getByText('We could not check the service. Try again.'),
    ).toBeDefined()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeDefined()
    expect(container.innerHTML).not.toContain('internal-only-detail')
    expect(alert.textContent).not.toContain('/api/')
    expect(fetch).toHaveBeenCalledOnce()
  })

  test('permits exactly one manual retry and disables repeat activation', async () => {
    let resolveRetry: ((response: Response) => void) | undefined
    vi.mocked(fetch)
      .mockRejectedValueOnce(new Error('first failure'))
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveRetry = resolve
          }),
      )

    renderStatus()
    const retry = await screen.findByRole('button', { name: 'Try again' })
    expect(fetch).toHaveBeenCalledOnce()

    retry.focus()
    fireEvent.click(retry)
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))

    const checking = screen.getByRole('button', { name: 'Checking…' })
    expect(checking.getAttribute('aria-disabled')).toBe('true')
    expect(checking.getAttribute('aria-busy')).toBe('true')
    expect(screen.getByRole('status').textContent).toBe('Checking service…')
    expect(document.activeElement).toBe(checking)
    fireEvent.click(checking)
    expect(fetch).toHaveBeenCalledTimes(2)

    resolveRetry?.(validResponse())
    await waitFor(() =>
      expect(screen.getByRole('status').textContent).toBe('Service available.'),
    )
  })

  test('returns to the identical alert when a manual retry fails', async () => {
    vi.mocked(fetch)
      .mockRejectedValueOnce(new Error('first failure'))
      .mockRejectedValueOnce(new Error('second failure'))

    renderStatus()
    fireEvent.click(await screen.findByRole('button', { name: 'Try again' }))

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    expect(screen.getAllByRole('alert')).toHaveLength(1)
    expect(
      screen.getByText('We could not check the service. Try again.'),
    ).toBeDefined()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeDefined()
  })

  test('aborts an active request on unmount without retry or console warning', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    let requestSignal: AbortSignal | undefined
    vi.mocked(fetch).mockImplementation(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          requestSignal = init?.signal ?? undefined
          requestSignal?.addEventListener('abort', () =>
            reject(new DOMException('Aborted', 'AbortError')),
          )
        }),
    )

    const { unmount } = renderStatus()
    await waitFor(() => expect(requestSignal).toBeDefined())
    unmount()

    await waitFor(() => expect(requestSignal?.aborted).toBe(true))
    expect(fetch).toHaveBeenCalledOnce()
    expect(consoleError).not.toHaveBeenCalled()
  })
})
