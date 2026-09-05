# Design System Guidelines

Chorum-murohc should feel modern, playful, and rewarding while remaining clear
for both children and parents. Design mobile-first and preserve accessibility
when adding visual polish or animation.

## Technology

- Use Tailwind CSS for layout and semantic design tokens.
- Use shadcn/ui and its Radix primitives when an existing component meets the
  interaction need.
- Use Motion only when CSS cannot express the required transition clearly.
- Do not add a UI dependency without asking, as required by `AGENTS.md`.

## Tokens

- Define colours, typography, spacing, radii, elevation, focus, and motion as
  semantic tokens rather than scattering literal values through components.
- Name tokens by purpose, such as surface, text, accent, success, warning, and
  danger, rather than by a specific colour.
- Use one spacing and type scale across parent and child views; vary emphasis
  through composition, not unrelated systems.
- Do not invent final brand colours or fonts until they are approved.

## Components

- Reuse an existing native, shadcn/ui, or project component before creating a
  new abstraction.
- Add only the states required by a current screen. Avoid wrappers, variants,
  and configuration intended solely for possible future use.
- Every interactive component must define default, hover, focus, active,
  disabled, loading, error, and success behaviour where applicable.
- Keep parent and child experiences consistent while adjusting language,
  density, and emphasis for their different tasks.

## Responsive behaviour

- Start with the narrowest supported screen and enhance layouts as space grows.
- Avoid horizontal scrolling for normal content and keep primary actions within
  easy reach on touch devices.
- Verify long names, large text, empty data, validation messages, and on-screen
  keyboards rather than reviewing only ideal content.

## Accessibility

- Target WCAG 2.2 AA colour contrast, focus visibility, semantics, labels, and
  touch-target sizes.
- All workflows must work with a keyboard and expose useful accessible names.
- Respect `prefers-reduced-motion`; animation must never be required to
  understand a state change.
- Provide useful alternative text for creature imagery and avoid conveying
  status through colour alone.

## Motion and feedback

- Use motion to explain cause and effect, especially point awards, level
  changes, and creature evolution, rather than as continuous decoration.
- Keep transitions short, interruptible, and safe when a request fails or is
  retried.
- Always provide explicit loading, empty, success, and recoverable error states
  with compact, actionable language.

## UI task workflow

- Read the issue, `_docs/plan.md`, and the relevant API contract before editing
  a screen.
- Reuse existing tokens and components, implement the smallest complete state
  set, and inspect it at mobile and desktop widths.
- Run the focused component tests and complete a keyboard and reduced-motion
  check before closing the issue.
