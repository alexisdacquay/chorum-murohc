import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import {
  CREATURE_LINES_QUERY_KEY,
  CREATURE_QUERY_KEY,
  CreatureRequestError,
  chooseCreatureLine,
  fetchCreature,
  fetchCreatureLines,
  isCreature,
  isCreatureLineList,
} from './creatures'

const TEST_CSRF_TOKEN = 'test-csrf-token'

const FORM = {
  index: 1,
  name: 'Hatchling',
  alt_text: 'A small green dragon hatchling sitting up.',
  unlock_level: 1,
  asset_path: '/creatures/dragon/form-1.svg',
  unlocked: true,
}

const LOCKED_FORM = {
  ...FORM,
  index: 2,
  name: 'Fledgling',
  unlock_level: 4,
  asset_path: '/creatures/dragon/form-2.svg',
  unlocked: false,
}

const CREATURE = {
  level: 1,
  max_level: 10,
  line: {
    slug: 'dragon',
    name: 'Dragon',
    description: 'A scaled hoarder.',
  },
  current_form: FORM,
  forms: [FORM, LOCKED_FORM],
}

const UNCHOSEN = {
  level: 0,
  max_level: 10,
  line: null,
  current_form: null,
  forms: [],
}

const { unlocked: _unlocked, ...PREVIEW } = FORM

const LINE_LIST = {
  lines: [
    {
      slug: 'dragon',
      name: 'Dragon',
      description: 'A scaled hoarder.',
      preview: PREVIEW,
    },
  ],
}

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status,
  })

beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
afterEach(() => vi.unstubAllGlobals())

describe('query keys', () => {
  test('are stable literals', () => {
    expect(CREATURE_QUERY_KEY).toEqual(['creature'])
    expect(CREATURE_LINES_QUERY_KEY).toEqual(['creature-lines'])
  })
})

describe('isCreature', () => {
  test('accepts a chosen creature with its forms', () => {
    expect(isCreature(CREATURE)).toBe(true)
  })

  test('accepts a child who has not chosen yet', () => {
    expect(isCreature(UNCHOSEN)).toBe(true)
  })

  test('accepts a chosen line whose first form is not reached', () => {
    expect(
      isCreature({ ...CREATURE, level: 0, current_form: null }),
    ).toBe(true)
  })

  test.each([
    ['a missing field', { ...CREATURE, max_level: undefined }],
    ['an extra field', { ...CREATURE, lifetime_points: 50 }],
    ['a fractional level', { ...CREATURE, level: 1.5 }],
    ['a negative level', { ...CREATURE, level: -1 }],
    ['a line with no forms', { ...CREATURE, forms: [] }],
    ['forms with no line', { ...UNCHOSEN, forms: [FORM] }],
    ['a form missing its unlocked flag', { ...CREATURE, forms: [PREVIEW] }],
    ['an empty alt text', { ...CREATURE, forms: [{ ...FORM, alt_text: '   ' }] }],
    ['null', null],
    ['an array', [CREATURE]],
  ])('rejects %s', (_name, value) => {
    expect(isCreature(value)).toBe(false)
  })

  test.each([
    ['an absolute url', 'https://example.invalid/form-1.svg'],
    ['a protocol-relative url', '//example.invalid/form-1.svg'],
    ['a javascript url', 'javascript:alert(1)'],
    ['a data url', 'data:image/svg+xml,<svg/>'],
    ['a traversal', '/creatures/../../etc/passwd'],
    ['another directory', '/uploads/dragon/form-1.svg'],
  ])('rejects %s as an asset path', (_name, path) => {
    expect(isCreature({ ...CREATURE, forms: [{ ...FORM, asset_path: path }] })).toBe(
      false,
    )
  })
})

describe('isCreatureLineList', () => {
  test('accepts a list of lines with previews', () => {
    expect(isCreatureLineList(LINE_LIST)).toBe(true)
  })

  test.each([
    ['an empty list', { lines: [] }],
    ['a preview carrying an unlocked flag', { lines: [{ ...LINE_LIST.lines[0], preview: FORM }] }],
    ['a missing preview', { lines: [{ slug: 'dragon', name: 'Dragon', description: 'x' }] }],
    ['a bare array', [LINE_LIST.lines[0]]],
    ['null', null],
  ])('rejects %s', (_name, value) => {
    expect(isCreatureLineList(value)).toBe(false)
  })
})

describe('fetchCreature', () => {
  test('reads the callers own creature', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(CREATURE))

    await expect(fetchCreature()).resolves.toEqual(CREATURE)
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe('/api/v1/creature/')
  })

  test('maps a 403 to forbidden', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: 'no' }, 403))

    await expect(fetchCreature()).rejects.toMatchObject({ kind: 'forbidden' })
  })

  test('maps an unexpected shape to unavailable', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ level: 1 }))

    await expect(fetchCreature()).rejects.toMatchObject({ kind: 'unavailable' })
  })

  test('maps a network failure to unavailable', async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError('offline'))

    await expect(fetchCreature()).rejects.toBeInstanceOf(CreatureRequestError)
  })
})

describe('fetchCreatureLines', () => {
  test('returns the lines a child may pick from', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(LINE_LIST))

    await expect(fetchCreatureLines()).resolves.toEqual(LINE_LIST.lines)
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe('/api/v1/creature/lines/')
  })

  test('maps a 403 to forbidden', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: 'no' }, 403))

    await expect(fetchCreatureLines()).rejects.toMatchObject({ kind: 'forbidden' })
  })
})

describe('chooseCreatureLine', () => {
  test('posts the slug with the csrf header', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(CREATURE, 201))

    await chooseCreatureLine({ csrfToken: TEST_CSRF_TOKEN, line: 'dragon' })

    const [path, init] = vi.mocked(fetch).mock.calls[0]
    expect(path).toBe('/api/v1/creature/')
    expect(init?.method).toBe('POST')
    expect(init?.body).toBe(JSON.stringify({ line: 'dragon' }))
    expect(
      (init?.headers as Record<string, string>)['X-CSRFToken'],
    ).toBe(TEST_CSRF_TOKEN)
  })

  test('accepts the 200 a repeated choice returns', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(CREATURE, 200))

    await expect(
      chooseCreatureLine({ csrfToken: TEST_CSRF_TOKEN, line: 'dragon' }),
    ).resolves.toEqual(CREATURE)
  })

  test('maps a 409 to already-chosen', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: 'no' }, 409))

    await expect(
      chooseCreatureLine({ csrfToken: TEST_CSRF_TOKEN, line: 'golem' }),
    ).rejects.toMatchObject({ kind: 'already-chosen' })
  })

  test('maps a validation failure to unavailable', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ line: ['bad'] }, 400))

    await expect(
      chooseCreatureLine({ csrfToken: TEST_CSRF_TOKEN, line: 'nope' }),
    ).rejects.toMatchObject({ kind: 'unavailable' })
  })
})
