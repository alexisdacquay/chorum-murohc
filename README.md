# Chorum-murohc

Chorum-murohc is a planned household chore-management web app that turns everyday
tasks into a rewarding experience for individuals, couples, and families.

Children complete chores to earn points, parents approve the work, and saved
points help creatures evolve over time. Points can also be exchanged for
agreed household rewards.

> **Project status:** Early development. The Django project and initial
> `chorum-murohc` app have been created; product features are not yet implemented.

## Planned features

- Parent-managed household accounts and roles
- A reusable pool of chores with configurable point values
- Parent approval of completed chores using a PIN
- Points for saving, spending, and creature progression
- Creature evolution with a visual history of earlier forms
- Household administration for users, chores, approvals, and balances

## Intended technology

- Python and Django REST Framework for the backend API
- React and TypeScript for the frontend
- PostgreSQL for persistent data
- Tailwind CSS and shadcn/ui for the interface
- [uv](https://docs.astral.sh/uv/) and pnpm for dependency management

## Documentation

- [Project plan](_docs/plan.md) — current product scope and requirements
- [Design](_docs/design.md) — selected architecture and implementation track
- [Backlog](_docs/tasks.md) — self-contained implementation tasks
- [Development process](_docs/process.md) — issue readiness, isolation, review, and handoff rules
- [Delegation map](_docs/task-dependencies.md) — dependencies and safe parallel workstreams
- [Dependency approvals](_docs/dependency-approvals.md) — package-change approval register
- [Requirements evidence](_docs/requirements-evidence.md) — current-plan coverage and verification ledger
- [Roadmap](_docs/roadmap.md) — ideas intentionally deferred beyond the current scope

## Local development

### Prerequisites

- Python 3.13 or later
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

### Setup

Install the locked dependencies and prepare the local database:

```shell
uv sync --locked
uv run --locked python manage.py migrate
```

Start the development server:

```shell
uv run --locked python manage.py runserver
```

Then open <http://127.0.0.1:8000/>.

### Checks and tests

```shell
uv run --locked python manage.py check
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked pytest
```

## Project structure

- `config/` — project-wide Django settings and URL routing
- `chorum_murohc/` — the main Chorum-murohc Django app
- `_docs/plan.md` — current product plan and requirements
- `manage.py` — command-line entry point for Django tasks

The public project and app name uses a hyphen. Python package names cannot use
hyphens, so the app's importable code folder uses `chorum_murohc` instead.

## Configuration and security

Settings are read from the process environment. Django does not load `.env`
files in this project, so a shell, process manager, container platform, or
deployment service must inject production values at runtime. Do not commit,
print, or pass real credentials in commands.

With none of the variables below set, the application starts in development
mode with safe local defaults. Variable names, formats, and production rules
are:

| Variable | Accepted format | Development default | Production requirement |
| --- | --- | --- | --- |
| `DJANGO_ENVIRONMENT` | `development` or `production`; surrounding whitespace and case are normalised | `development` | Set to `production`; an empty or unknown value is rejected |
| `DJANGO_SECRET_KEY` | Any non-blank value, used exactly as supplied | `django-insecure-local-development-only` | A non-blank runtime secret is required |
| `DJANGO_DEBUG` | True: `1`, `true`, `yes`, `on`; false: `0`, `false`, `no`, `off`; case-insensitive with surrounding whitespace ignored | `True` | Defaults to `False`; a true value is always rejected |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hosts; whitespace around each host is removed, order is preserved, and empty entries or `*` are rejected | `localhost`, `127.0.0.1`, `[::1]`, `testserver` | At least one non-wildcard host is required |
| `DJANGO_DB_ENGINE` | `sqlite` or `postgresql`; surrounding whitespace and case are normalised | `sqlite` | Must be explicitly set to `postgresql` |
| `DJANGO_DB_NAME` | For SQLite: `:memory:`, an absolute path, or a relative path placed beneath the project root. For PostgreSQL: any non-blank database name | `<project-root>/db.sqlite3` with SQLite | A non-blank PostgreSQL database name is required |
| `DJANGO_DB_USER` | Any non-blank value | Must be absent with SQLite | Required with PostgreSQL |
| `DJANGO_DB_PASSWORD` | Any non-blank value | Must be absent with SQLite | Required with PostgreSQL and injected as a secret |
| `DJANGO_DB_HOST` | Any non-blank value | Must be absent with SQLite | Required with PostgreSQL |
| `DJANGO_DB_PORT` | With PostgreSQL, ASCII decimal digits representing `1` through `65535`; leading zeroes are removed | Must be absent with SQLite | Required with PostgreSQL |

An explicitly blank SQLite database name is invalid. Supplying any
PostgreSQL-only user, password, host, or port variable while SQLite is selected
is also invalid instead of being silently ignored.

The production contract selects PostgreSQL, but this stage intentionally does
not install or import a PostgreSQL driver and does not open a connection. Task
T005 owns the approved driver, isolated task and CI database naming, Django
`TEST` configuration, connection checks, and database creation and disposal.

For local development, the fixed fallback values need no configuration. A
production platform should inject values such as
`DJANGO_SECRET_KEY=<inject-a-secret-at-runtime>` and
`DJANGO_DB_PASSWORD=<inject-a-password-at-runtime>` through its secret store;
the placeholders are not usable credentials.
