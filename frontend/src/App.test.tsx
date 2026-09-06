import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'

import App from './App'

test('shows the Chorum-murohc heading', () => {
  render(<App />)

  const heading = screen.getByRole('heading', {
    level: 1,
    name: 'Chorum-murohc',
  })

  expect(heading).toBeDefined()
})
