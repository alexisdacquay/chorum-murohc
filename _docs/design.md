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

## Modularity Direction

The product remains Chorum-murohc. Within it, Django modules should own bounded
areas of behaviour rather than allowing all models and rules to accumulate in
one package. Candidate boundaries include:

- Identity and households
- Chore definitions
- Completion and approval workflows
- Points ledger and interest
- Rewards
- Creatures and evolution
- Administration and audit history

These are proposed design boundaries, not final package names. Boundaries and
interfaces should be agreed before their implementation.

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
