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

### Default SQLite setup

With no database variables set, install the locked dependencies and prepare the
default local SQLite database:

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
| `DJANGO_DB_TARGET` | Local: `task_tNNN_<worker-token>`. CI: `ci_<run-id>_<attempt>_<job-token>`. Exact grammar is below | Required only when development selects PostgreSQL; forbidden with SQLite | Forbidden; production has no explicit test target |
| `DJANGO_DB_NAME` | For SQLite: `:memory:`, an absolute path, or a relative path beneath the project root. For guarded PostgreSQL development: exactly `chorum_murohc_<DJANGO_DB_TARGET>` | `<project-root>/db.sqlite3` with SQLite | Any non-blank PostgreSQL database name is required |
| `DJANGO_DB_USER` | For guarded PostgreSQL development: exactly `chorum_murohc_<DJANGO_DB_TARGET>` | Must be absent with SQLite | Any non-blank PostgreSQL role is required |
| `DJANGO_DB_PASSWORD` | Any non-blank value | Must be absent with SQLite | Required with PostgreSQL and injected as a secret |
| `DJANGO_DB_HOST` | Guarded task target: exactly `127.0.0.1`; guarded CI target: exactly `postgres` | Must be absent with SQLite | Any non-blank PostgreSQL host is required |
| `DJANGO_DB_PORT` | With PostgreSQL, ASCII decimal digits representing `1` through `65535`; leading zeroes are removed | Must be absent with SQLite | Required with PostgreSQL |

An explicitly blank SQLite database name is invalid. Supplying any
PostgreSQL-only user, password, host, port, or target variable while SQLite is
selected is also invalid instead of being silently ignored. Production remains
a separately supplied PostgreSQL configuration: `DJANGO_DB_TARGET` is forbidden
there and Django receives no explicit task or CI test-database name.

For local development, the fixed fallback values need no configuration. A
production platform should inject values such as
`DJANGO_SECRET_KEY=<inject-a-secret-at-runtime>` and
`DJANGO_DB_PASSWORD=<inject-a-password-at-runtime>` through its secret store;
the placeholders are not usable credentials.

## Isolated PostgreSQL tests

PostgreSQL development and test runs fail closed around one explicitly named
worktree or CI target. The parser does not trim or normalise a target: every
character must match one of these ASCII grammars exactly.

| Lineage | Exact target grammar | Boundaries | Required host |
| --- | --- | --- | --- |
| Local task | `task_tNNN_<worker-token>` | `NNN` is exactly three ASCII digits; the token is 8–16 lowercase ASCII letters or digits | `127.0.0.1` |
| CI job | `ci_<run-id>_<attempt>_<job-token>` | Run ID is 1–20 ASCII digits; attempt is 1–3 ASCII digits; token is 8–16 lowercase ASCII letters or digits | `postgres` |

Whitespace, uppercase, Unicode, punctuation other than the fixed underscores,
missing uniqueness tokens, unknown prefixes, and oversized values are rejected.
Operational uniqueness is established by generating a new token for every
worktree, run, job, or shard and proving the derived test database is absent
before use.

For a target named `<target>`, the connection fields are derived rather than
chosen independently:

- base database and restricted role: `chorum_murohc_<target>`;
- disposable test database: `test_chorum_murohc_<target>`; and
- password: a generated test-only secret injected at runtime, never printed or
  placed in a command argument.

The longest permitted CI target is 44 ASCII bytes. Its base and role name are
58 bytes, and its test database is exactly PostgreSQL's 63-byte identifier
limit. There is no independent variable for the test-database name.

### Approved local verification boundary

T005 Engineer, QA, and post-merge verification may each use one fresh local
container from the official immutable image
`postgres:17.11-alpine@sha256:18cfe3ef5e6815560c98237d6216d1e5119702fb0f3894c8785dd58b8bbe5d73`.
The approval is limited to the local Docker `orbstack` context, an exact
run-labelled container, a Docker-selected port bound only to `127.0.0.1`,
transient storage, synthetic empty-scaffold data, and no repository or secret
mounts. The recorded approval is in
[issue #5](https://github.com/alexisdacquay/chorum-murohc/issues/5#issuecomment-5559116428).

The Django role must own the derived base database and have exactly these
relevant flags: `NOSUPERUSER CREATEDB NOCREATEROLE NOREPLICATION`. It may
connect to the isolated cluster's built-in `postgres` database so Django can
create and destroy the test database. Bootstrap authority and its generated
credential are never supplied to Django.

Before giving Django access, record and verify only this non-secret evidence:

- target, derived base database, derived test database, and derived role;
- allowed host and Docker-selected loopback port;
- exact container name, run label, immutable image digest, and PostgreSQL
  server version;
- base-database owner and the four restricted-role flags;
- the exact base database exists, its `public` schema has no application
  tables, and the derived test database does not exist.

The preflight guard must reject an unexpected host, name, image, label, owner,
role flag, existing test database, or non-empty base schema before Django
receives a credential. A negative preflight check uses a deliberately invalid
non-secret host, name, or role expectation and confirms that the guard stops
without creating or dropping anything.

Inject the six `DJANGO_DB_*` connection fields plus `DJANGO_DB_TARGET` into the
test process environment. Do not load a secret file. Run the smoke test and the
whole suite normally:

```shell
uv run --locked pytest -vv config/tests/test_postgresql.py
uv run --locked pytest
```

Do not add `--reuse-db`, `--create-db`, `--keepdb`, or any persistent test
service. Django creates only the exact derived test database, applies the
currently merged built-in migrations there, runs the tests, and destroys that
database on ordinary completion. Do not run product migrations against the
empty base database.

After the run, verify that the exact test database is absent and that the base
database's `public` schema is still empty. Then stop and remove only the exact
container name recorded during preflight; its transient cluster disappears
with it. Never select cleanup targets by prefix, wildcard, glob, broad SQL
predicate, or prune operation, and never remove a shared volume.

If a run is interrupted, first re-prove the container name, run label, image
digest, loopback host, target, all derived names, and role flags. Only then may
the one exact derived test database be removed. If any guard cannot be
re-proven, issue no database command: remove only the one exact ephemeral
container recorded for that run.

Persistent services, reused containers, public or LAN binds, external
databases, shared/staging/production data, and any other image or package are
outside this approval and require a newly groomed task and explicit approval.

### T006 handoff

Task T006 adds the custom user model and its first product migration without
weakening or rewriting this guard. Its local verifier must generate a unique
`task_t006_<worker-token>` target, where the token is 8–16 lowercase ASCII
letters or digits. It must use the exact derived base, role, and test names
above, prove the same preflight facts, and let Django apply the new migration
only inside the disposable test database. The base database remains an empty
lifecycle anchor; committed CI service integration belongs to T017 and uses
the `ci_...` grammar with the exact `postgres` alias.
