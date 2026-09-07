import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import type { HtmlTagDescriptor, Plugin } from 'vite'
import { defineConfig } from 'vitest/config'

export const inlineFavicon = (): HtmlTagDescriptor[] => [
  {
    tag: 'link',
    attrs: { rel: 'icon', href: 'data:,' },
    injectTo: 'head-prepend',
  },
]

const inlineFaviconPlugin: Plugin = {
  name: 'inline-favicon',
  transformIndexHtml: inlineFavicon,
}

export default defineConfig({
  plugins: [react(), tailwindcss(), inlineFaviconPlugin],
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
  },
})
