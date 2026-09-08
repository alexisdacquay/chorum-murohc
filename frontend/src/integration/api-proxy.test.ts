// @vitest-environment node

import { randomBytes } from 'node:crypto'
import { mkdtemp, rm } from 'node:fs/promises'
import { createServer as createHttpServer } from 'node:http'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  build,
  createServer as createViteServer,
  preview,
  type PreviewServer,
  type ViteDevServer,
} from 'vite'
import { describe, expect, test } from 'vitest'

const frontendRoot = fileURLToPath(new URL('../..', import.meta.url))
const configFile = join(frontendRoot, 'vite.config.ts')

const closeHttpServer = async (
  server: ReturnType<typeof createHttpServer>,
) => {
  server.closeAllConnections()
  await new Promise<void>((resolve, reject) =>
    server.close((error) => (error ? reject(error) : resolve())),
  )
}

describe('Vite API proxy', () => {
  test('forwards the exact request and in-memory Cookie in dev and preview', async () => {
    const cookieValue = `probe=${randomBytes(24).toString('hex')}`
    const observations: Array<Record<string, boolean>> = []
    const upstream = createHttpServer((request, response) => {
      observations.push({
        accept: request.headers.accept === 'application/json',
        cookie: request.headers.cookie === cookieValue,
        method: request.method === 'GET',
        path: request.url === '/api/v1/health/',
      })
      response.writeHead(200, { 'Content-Type': 'application/json' })
      response.end('{"status":"ok"}')
    })
    let devServer: ViteDevServer | undefined
    let previewServer: PreviewServer | undefined
    const buildDirectory = await mkdtemp(join(tmpdir(), 't016-proxy-'))

    try {
      await new Promise<void>((resolve, reject) => {
        upstream.once('error', reject)
        upstream.listen(8000, '127.0.0.1', () => {
          upstream.off('error', reject)
          resolve()
        })
      })

      devServer = await createViteServer({
        configFile,
        logLevel: 'silent',
        root: frontendRoot,
        server: { host: '127.0.0.1', port: 0, strictPort: true },
      })
      await devServer.listen()

      const devAddress = devServer.httpServer?.address()
      if (!devAddress || typeof devAddress === 'string') {
        throw new Error('Development proxy did not bind')
      }
      const devResponse = await fetch(
        `http://127.0.0.1:${devAddress.port}/api/v1/health/`,
        { headers: { Accept: 'application/json', Cookie: cookieValue } },
      )
      expect(devResponse.status).toBe(200)
      expect(devResponse.headers.has('Access-Control-Allow-Origin')).toBe(false)

      await build({
        build: { emptyOutDir: true, outDir: buildDirectory },
        configFile,
        logLevel: 'silent',
        root: frontendRoot,
      })
      previewServer = await preview({
        build: { outDir: buildDirectory },
        configFile,
        logLevel: 'silent',
        preview: { host: '127.0.0.1', port: 0, strictPort: true },
        root: frontendRoot,
      })
      const previewAddress = previewServer.httpServer.address()
      if (!previewAddress || typeof previewAddress === 'string') {
        throw new Error('Preview proxy did not bind')
      }
      const previewResponse = await fetch(
        `http://127.0.0.1:${previewAddress.port}/api/v1/health/`,
        { headers: { Accept: 'application/json', Cookie: cookieValue } },
      )
      expect(previewResponse.status).toBe(200)
      expect(previewResponse.headers.has('Access-Control-Allow-Origin')).toBe(
        false,
      )

      expect(observations).toEqual([
        { accept: true, cookie: true, method: true, path: true },
        { accept: true, cookie: true, method: true, path: true },
      ])
    } finally {
      await devServer?.close()
      await previewServer?.close()
      if (upstream.listening) await closeHttpServer(upstream)
      await rm(buildDirectory, { force: true, recursive: true })
    }
  })
})
