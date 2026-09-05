# Testing Guidelines

Read the issue's acceptance criteria and the relevant production flow before
writing or changing tests.

## Principles

- Test observable behaviour, permissions, state transitions, and durable side
  effects rather than private implementation details.
- Use the smallest test layer that proves the behaviour: a unit test for pure
  logic, a Django or API test for backend integration, a component test for UI
  behaviour, and Playwright only for a critical cross-application journey.
- Every bug fix should include one focused regression test that fails for the
  root cause before the fix and passes afterwards.
- Keep tests deterministic. Control time, randomness, identifiers, and external
  responses; never call a live third-party service from the test suite.
- Prefer a few meaningful cases over repeated variations that do not protect a
  distinct risk.

## Backend

- Use pytest and pytest-django with PostgreSQL for database-dependent tests.
- Exercise database constraints and transaction boundaries where they enforce
  household isolation, ledger integrity, idempotency, or valid state changes.
- Test both allowed and forbidden requests for every role-sensitive endpoint.
- Assert exact ledger, audit, and workflow effects for approvals, spending,
  interest, and levelling.
- Never include real credentials, parent PINs, or production-derived personal
  data in fixtures or failure output.

## Frontend

- Use Vitest and Testing Library to interact with components as a user would,
  through accessible names and roles.
- Cover loading, empty, success, validation, permission, and recoverable error
  states required by the issue.
- Test keyboard behaviour and reduced-motion handling for interactive UI.
- Avoid snapshots for behaviour and avoid asserting Tailwind classes or
  component internals.

## End-to-end

- Use Playwright only for the bounded household journeys identified in the
  backlog.
- Give each test isolated data and make retries safe; a failed run must not
  corrupt another test or depend on execution order.
- Keep diagnostics compact and redact passwords, PINs, cookies, and sensitive
  image data.

## Before closing

- Re-read the acceptance criteria and confirm each criterion has direct test or
  inspection evidence.
- Run the narrowest relevant test first, then the whole affected suite.
- Record the commands run and any deliberately untested behaviour in the issue.
