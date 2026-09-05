# Chorum-murohc — Design v1

> **Status:** Selected planning direction; not yet implemented.

## Design Goals

- Deliver a modern, polished, mobile-first user interface.
- Keep product behaviour modular so that it can be designed, implemented,
  tested, troubleshot, and evolved in bounded areas.
- Begin with a manageable local architecture while preserving a clear path to
  containerised, distributed, production-grade operation.
- Avoid premature microservices and introduce operational complexity only when
  scale or reliability requirements justify it.

## Architecture

Chorum-murohc will use a monorepo containing two principal applications:

1. A React frontend that provides the user interface.
2. A Django backend that exposes the application API and owns business rules,
   authentication, and persistent data.

The backend will begin as a modular monolith. Domain boundaries will be kept
explicit so that independently scalable services can be extracted later if a
demonstrated need arises.

The initial deployment should keep the frontend and backend on the same origin.
This permits Django session authentication and CSRF protection without adding
unnecessary token-management or cross-origin complexity.

## Selected Technology Track

| Area | Selected technology | Purpose |
| --- | --- | --- |
| Backend language | Python 3.13 | Primary implementation language |
| Backend framework | Django 5.2 LTS | Application framework, authentication, administration, and business logic |
| API | Django REST Framework | Versioned HTTP API for the frontend |
| Database | PostgreSQL | Durable transactional system of record |
| Frontend language | TypeScript | Safer, maintainable browser application code |
| Frontend framework | React | Component-based user interface |
| Frontend tooling | Vite | Development server and production builds |
| Styling and components | Tailwind CSS and shadcn/ui | Modern, consistent, accessible visual system |
| Animation | Motion | Point rewards, creature evolution, and interface transitions |
| Server-state management | TanStack Query | API requests, caching, and synchronisation |
| Forms and validation | React Hook Form and Zod | Form state and client-side validation |
| Authentication | Django sessions with CSRF protection | Secure same-origin browser authentication |
| Python packages | uv | Python environments, dependencies, and locking |
| Frontend packages | pnpm | JavaScript and TypeScript dependency management |
| Backend testing | pytest and pytest-django | Unit and integration testing |
| Frontend testing | Vitest and Testing Library | Component and interaction testing |
| End-to-end testing | Playwright | Browser-level workflow testing |

SQLite may remain useful for very early local experiments, but PostgreSQL is
the selected implementation database so that development and production
behaviour do not diverge unnecessarily.

## Approved Backend Boundaries

The repository and public product remain **Chorum-murohc**. The Python
distribution remains `chorum-murohc`, and all importable product packages use
the valid Python namespace `chorum_murohc`. The backend is not a standalone
`chores` project, and the nested chores app does not replace the existing root
app.

`config` is the Django composition root. It owns settings, root URLs, ASGI, and
WSGI only; it may register every app but owns no product models or migrations.
The existing `chorum_murohc` app remains installed as the Chorum-murohc
compatibility/root app and package namespace. It imports no domain
implementation and owns no product models or product migrations.

The following packages are the approved backend boundaries. The tasks in the
final column own future model and migration changes for that app; this boundary
task creates only the eight nested app shells and their empty migrations
packages.

| Package / Django app | Responsibility | Future model and migration owner |
| --- | --- | --- |
| `config` | Django composition root: settings, root URLs, ASGI, and WSGI only | No product models or migrations |
| `chorum_murohc` | Existing installed Chorum-murohc compatibility/root app and package namespace | No product models or product migrations |
| `chorum_murohc.identity` | Users, households, memberships, and parent PIN persistence | T006, T007, and T030 |
| `chorum_murohc.audit` | Append-only audit events | T008 |
| `chorum_murohc.chores` | Reusable household chore definitions | T034 |
| `chorum_murohc.submissions` | Completion submissions and approval state | T041 and later submission-schema changes |
| `chorum_murohc.ledger` | Immutable point transactions | T038 and later ledger-schema changes |
| `chorum_murohc.rewards` | Reward-redemption records | T056 and later reward-schema changes |
| `chorum_murohc.progression` | Per-child level state | T062 and later progression-schema changes |
| `chorum_murohc.creatures` | Creature catalogue, forms, and selection state | T069 and later creature-schema changes |

Python dependencies between product apps must follow this acyclic direction
map:

| Importing package | Product packages it may import |
| --- | --- |
| `chorum_murohc` root | None |
| `chorum_murohc.audit` | None |
| `chorum_murohc.identity` | `audit` |
| `chorum_murohc.chores` | `audit` |
| `chorum_murohc.ledger` | `audit` |
| `chorum_murohc.submissions` | `identity`, `chores`, `ledger`, `audit` |
| `chorum_murohc.rewards` | `identity`, `ledger`, `audit` |
| `chorum_murohc.progression` | `identity`, `ledger`, `audit` |
| `chorum_murohc.creatures` | `identity`, `progression`, `audit` |

Reverse or undeclared product-package imports are forbidden. Cross-app model
references use Django lazy string references or `settings.AUTH_USER_MODEL`,
with migration dependencies declared only when the owning model task adds a
migration.

The frontend should follow the same domain boundaries for screens, components,
API clients, and tests. Shared UI primitives should remain separate from
product-specific features.

## Data and Security Principles

- Create the custom Django user model before business database migrations.
- Record points in an auditable transaction ledger rather than relying only on
  a mutable balance.
- Use database transactions for approvals, spending, interest, and levelling.
- Represent points and rates with integer or decimal arithmetic, never floats.
- Store parent PINs as secure hashes and rate-limit failed attempts.
- Keep credentials outside version control and inject production secrets at
  runtime.

## Deferred Technology

Go and Rust are not part of the present implementation track. They may later be
introduced behind stable interfaces when measurement demonstrates a suitable
need: Go for concurrent network services or workers, and Rust for CPU-intensive
or unusually safety-critical components.

The suggested operational additions and production evolution are recorded
separately from product features in the [long-term roadmap](roadmap.md).
