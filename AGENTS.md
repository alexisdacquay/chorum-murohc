# Chorum-murohc

A family chores-and-rewards web app for two parents and their children. Children
submit completed chores, a parent approves with a PIN, points land in a ledger
and buy rewards and creature progression.

## Where the code lives

- `chorum_murohc/` - Django. One package per domain: `identity`, `chores`,
  `submissions`, `ledger`, `rewards`, `progression`, `creatures`, `audit`.
  `chorum_murohc/api/` is the only HTTP layer; no domain package imports it.
- `config/` - Django settings, URLs, and `spa.py`, the one-origin WSGI
  composition the container serves. `frontend/` - React, TypeScript, Vite,
  Tailwind. `Dockerfile`, `compose.yaml`, `docker/` - how it runs; `README.md`
  is the runbook.
- `_docs/` - `plan.md` scope, `design.md` architecture, `tasks.md` backlog,
  `design-system.md` UI, `testing-guidelines.md` tests, `roadmap.md` deferred,
  and the approval, retention and dependency product policies.

## The two gates

    uv sync --locked
    uv run --locked ruff format --check . && uv run --locked ruff check .
    uv run --locked python manage.py check
    uv run --locked python manage.py makemigrations --check --dry-run
    uv run --locked pytest

    pnpm --dir frontend install --frozen-lockfile
    pnpm --dir frontend test && pnpm --dir frontend build

CI runs these as the Backend and Frontend checks. Both green, or no merge.

## House rules

- One issue per feature, one branch, one pull request. No grooming, no
  readiness gate, no separate reviewer, no handover document. You design it,
  build it, test it and land it; the gates are the only check.
- Simplest thing that works and is tested. Prefer the boring solution.
- You own every file you need to touch. There is no file-ownership contract. If
  a merged test blocks a legitimate change, fix that test and say so in the PR.
- Backend and frontend ship in one branch and one pull request, with their tests.
- Ask before adding a dependency; record it in `_docs/dependency-approvals.md`.
- Plain ASCII everywhere. No third-party characters, brands or assets.
