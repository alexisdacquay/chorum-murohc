/**
 * The creature API client (issue #66).
 *
 * Three calls over two routes under `/api/v1/`, child-only every way:
 *
 * - `fetchCreatureLines` reads the seven lines a child may pick from, in
 *   catalogue order, each with the drawing the chooser shows.
 * - `fetchCreature` reads the caller's own creature: their level, the line
 *   they picked (or `null` when they have not picked yet), the form they are
 *   on, and all four forms with an `unlocked` flag, so the gallery can
 *   silhouette what is still to come.
 * - `chooseCreatureLine` records the line the caller picked. It is
 *   write-once on the server: a repeat of the same line succeeds and changes
 *   nothing, and a different line is refused with `already-chosen`.
 *
 * Same-origin session authentication and CSRF only, matching `api/chores.ts`
 * and `api/progression.ts` exactly: `ensureCsrfToken` and the CSRF header
 * they export are reused here rather than duplicated. Every response crosses
 * a trust boundary, so a body is validated at runtime before it is trusted,
 * and an asset path is checked to be a local `/creatures/...` path before it
 * ever reaches an `img` element.
 */

import { CSRF_HEADER_NAME, ensureCsrfToken } from './session'

export interface CreatureForm {
  index: number
  name: string
  alt_text: string
  unlock_level: number
  asset_path: string
  unlocked: boolean
}

export type CreaturePreview = Omit<CreatureForm, 'unlocked'>

export interface CreatureLineSummary {
  slug: string
  name: string
  description: string
  preview: CreaturePreview
}

export interface CreatureLine {
  slug: string
  name: string
  description: string
}

export interface Creature {
  level: number
  max_level: number
  line: CreatureLine | null
  current_form: CreatureForm | null
  forms: CreatureForm[]
}

export const CREATURE_QUERY_KEY = ['creature'] as const
export const CREATURE_LINES_QUERY_KEY = ['creature-lines'] as const

/**
 * - `forbidden`: the caller is no longer an active child of this household.
 * - `already-chosen`: a different creature is already recorded for them.
 * - `unavailable`: unreachable, timed out, not JSON, or an unexpected status.
 */
export type CreatureFailureKind = 'forbidden' | 'already-chosen' | 'unavailable'

export class CreatureRequestError extends Error {
  readonly kind: CreatureFailureKind

  constructor(kind: CreatureFailureKind) {
    super(`Creature request failed: ${kind}`)
    this.name = 'CreatureRequestError'
    this.kind = kind
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const isJsonMediaType = (contentType: string | null) =>
  contentType !== null &&
  /^application\/(?:[a-z0-9!#$&^_.+-]+\+)?json(?:\s*;|$)/i.test(contentType)

const isNonNegativeInteger = (value: unknown): value is number =>
  typeof value === 'number' && Number.isInteger(value) && value >= 0

const isNonEmptyString = (value: unknown): value is string =>
  typeof value === 'string' && value.trim() !== ''

/**
 * A drawing this application serves itself, and nothing else.
 *
 * The path is written straight into an `img` source, so an absolute URL, a
 * protocol-relative one, a `javascript:` or `data:` value, or any traversal
 * out of the creature directory is rejected here rather than rendered. The
 * server has no business sending anything else, and if it ever does the
 * image is simply treated as missing.
 */
const isCreatureAssetPath = (value: unknown): value is string =>
  typeof value === 'string' && /^\/creatures\/[a-z]+\/form-[1-9]\.svg$/.test(value)

const hasExactKeys = (value: Record<string, unknown>, keys: readonly string[]) =>
  Object.keys(value).length === keys.length &&
  keys.every((key) => Object.hasOwn(value, key))

const PREVIEW_KEYS = [
  'index',
  'name',
  'alt_text',
  'unlock_level',
  'asset_path',
] as const

const FORM_KEYS = [...PREVIEW_KEYS, 'unlocked'] as const

const LINE_KEYS = ['slug', 'name', 'description'] as const

/** The five fields a preview and a form both carry, with the same rules. */
const hasDrawingFields = (value: Record<string, unknown>) =>
  isNonNegativeInteger(value.index) &&
  isNonEmptyString(value.name) &&
  isNonEmptyString(value.alt_text) &&
  isNonNegativeInteger(value.unlock_level) &&
  isCreatureAssetPath(value.asset_path)

const hasLineFields = (value: Record<string, unknown>) =>
  isNonEmptyString(value.slug) &&
  isNonEmptyString(value.name) &&
  isNonEmptyString(value.description)

const isPreview = (value: unknown): value is CreaturePreview =>
  isRecord(value) && hasExactKeys(value, PREVIEW_KEYS) && hasDrawingFields(value)

const isForm = (value: unknown): value is CreatureForm =>
  isRecord(value) &&
  hasExactKeys(value, FORM_KEYS) &&
  hasDrawingFields(value) &&
  typeof value.unlocked === 'boolean'

const isLine = (value: unknown): value is CreatureLine =>
  isRecord(value) && hasExactKeys(value, LINE_KEYS) && hasLineFields(value)

const isLineSummary = (value: unknown): value is CreatureLineSummary =>
  isRecord(value) &&
  hasExactKeys(value, [...LINE_KEYS, 'preview']) &&
  hasLineFields(value) &&
  isPreview(value.preview)

/** The exact body `GET creature/lines/` returns. */
export const isCreatureLineList = (
  value: unknown,
): value is { lines: CreatureLineSummary[] } =>
  isRecord(value) &&
  hasExactKeys(value, ['lines']) &&
  Array.isArray(value.lines) &&
  value.lines.length > 0 &&
  value.lines.every(isLineSummary)

/** The exact five-key body both creature routes return. */
export const isCreature = (value: unknown): value is Creature => {
  if (!isRecord(value) || !hasExactKeys(value, [
    'level',
    'max_level',
    'line',
    'current_form',
    'forms',
  ])) {
    return false
  }

  if (!isNonNegativeInteger(value.level) || !isNonNegativeInteger(value.max_level)) {
    return false
  }
  if (value.line !== null && !isLine(value.line)) {
    return false
  }
  if (value.current_form !== null && !isForm(value.current_form)) {
    return false
  }
  if (!Array.isArray(value.forms) || !value.forms.every(isForm)) {
    return false
  }

  // A line with no forms, or forms with no line, would leave the screen with
  // nothing coherent to draw.
  return value.line === null ? value.forms.length === 0 : value.forms.length > 0
}

const readJsonBody = async (response: Response): Promise<unknown> => {
  if (!isJsonMediaType(response.headers.get('Content-Type'))) {
    return undefined
  }
  try {
    return await response.json()
  } catch {
    return undefined
  }
}

const send = async (path: string, init: RequestInit): Promise<Response> => {
  try {
    return await fetch(path, { credentials: 'same-origin', ...init })
  } catch {
    // The reason is dropped: it can carry a URL or a platform diagnostic, and
    // the interface shows one fixed sentence either way.
    throw new CreatureRequestError('unavailable')
  }
}

const failureFor = (response: Response): CreatureFailureKind => {
  if (response.status === 403) {
    return 'forbidden'
  }
  return response.status === 409 ? 'already-chosen' : 'unavailable'
}

const readCreatureBody = async (
  response: Response,
  expectedStatuses: readonly number[],
): Promise<Creature> => {
  if (response.redirected) {
    throw new CreatureRequestError('unavailable')
  }
  if (!expectedStatuses.includes(response.status)) {
    throw new CreatureRequestError(failureFor(response))
  }
  const body = await readJsonBody(response)
  if (!isCreature(body)) {
    throw new CreatureRequestError('unavailable')
  }
  return body
}

/** `GET /api/v1/creature/lines/`: the lines a child may pick from. */
export const fetchCreatureLines = async ({
  signal,
}: { signal?: AbortSignal } = {}): Promise<CreatureLineSummary[]> => {
  const response = await send('/api/v1/creature/lines/', {
    method: 'GET',
    headers: { Accept: 'application/json' },
    signal,
  })

  if (response.redirected) {
    throw new CreatureRequestError('unavailable')
  }
  if (response.status !== 200) {
    throw new CreatureRequestError(failureFor(response))
  }
  const body = await readJsonBody(response)
  if (!isCreatureLineList(body)) {
    throw new CreatureRequestError('unavailable')
  }
  return body.lines
}

/** `GET /api/v1/creature/`: the caller's own creature. */
export const fetchCreature = async ({
  signal,
}: { signal?: AbortSignal } = {}): Promise<Creature> =>
  readCreatureBody(
    await send('/api/v1/creature/', {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal,
    }),
    [200],
  )

/**
 * `POST /api/v1/creature/`: pick a line.
 *
 * 201 the first time and 200 for a repeat of the same line; both return the
 * caller's creature. A different line answers 409 and surfaces as
 * `already-chosen`, which the screen recovers from by reloading.
 */
export const chooseCreatureLine = async ({
  csrfToken,
  line,
  signal,
}: {
  csrfToken: string
  line: string
  signal?: AbortSignal
}): Promise<Creature> =>
  readCreatureBody(
    await send('/api/v1/creature/', {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        [CSRF_HEADER_NAME]: csrfToken,
      },
      body: JSON.stringify({ line }),
      signal,
    }),
    [200, 201],
  )

export { ensureCsrfToken }
