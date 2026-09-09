# Chorum-murohc

A household chores-and-rewards web app for two parents and their children.
Children submit the chores they have done, a parent approves each one with a
PIN, and the points land in a ledger that buys rewards and grows a creature.

It runs on one small machine - a home server, a spare laptop, a cheap VPS -
from one `docker compose` command. It is built for one household on its own
network, not for the internet.

## What it does today

Everything below is implemented, tested, and driven end to end in a real
browser by the journeys in `browser_journeys/`.

- **Accounts.** A parent creates every account in the household, parent or
  child, and can rename, deactivate, reactivate or delete one. The household
  always keeps at least one active parent.
- **Chore pool.** Parents keep a pool of chores, each with a fixed point
  value. Every chore is always available to every child; nothing is
  scheduled and nothing disappears when it is claimed.
- **Submission and approval.** A child marks a chore done and submits it. A
  parent approves or rejects it with their four-to-ten-digit PIN, either on
  the child's device or from their own queue on their own device. Five wrong
  PINs lock that parent out for fifteen minutes.
- **Points.** An approved chore credits the child's ledger. The ledger is
  append-only: entries are never edited or deleted, and every credit and
  debit carries an idempotency key, so a retry cannot pay twice.
- **Interest.** Unspent points earn 2 percent once a week, floored to whole
  points and capped at 20 points per accrual. `manage.py accrue_interest` is
  the only thing that credits it, and it always takes an explicit date.
- **Rewards.** Parents define the reward catalogue themselves - what it is
  called, what it costs. A child redeems from it when the balance covers it;
  a parent fulfils or cancels the request, and the ledger shows the exact
  effect.
- **Levels.** Ten levels, from lifetime points earned: 50, 150, 300, 500,
  750, 1050, 1400, 1800, 2250, 2750. Spending never demotes anyone.
- **Creatures.** Seven original creature lines with four forms each. A child
  picks a line once, at first sign-in, and keeps it. Forms are revealed at
  levels 1, 4, 7 and 10; the ones still to come show as silhouettes with the
  level that reveals them.
- **Oversight.** Parents see every child's balance and level on one overview
  screen, and the household's activity history on another.

Parent screens: Overview, Approvals, Chore pool, Reward requests, Household,
Activity, Approval PIN. Child screens: Chores, Points, Rewards, Levels,
Creature.

## Run it

You need Docker Engine with the Compose plugin. Nothing else: Python, Node
and the database all live inside the containers.

```shell
git clone https://github.com/alexisdacquay/chorum-murohc.git
cd chorum-murohc
docker compose up -d --build
```

That builds the interface and the application image, starts PostgreSQL with a
volume of its own, generates a session signing key into a second volume,
applies the migrations, and serves the whole thing on
<http://localhost:8000/>. Both containers restart with the machine.

### Create the first parent

The database starts empty, so nobody can sign in yet. This command asks for
the household name, the first parent's username, and a password twice. It
takes no default password and prints nothing back.

```shell
docker compose run --rm app python manage.py bootstrap_household
```

```
Household name: Ridgeway House
Parent username: alexis
Password:
Confirm password:
Bootstrap completed.
```

The password must satisfy Django's own validators: at least eight
characters, not entirely numeric, not a common password, and not too close
to the username.

Running it again is safe. With the same answers it changes nothing and says
`Bootstrap already completed; no changes made.` With different answers, once
the household exists, it refuses with `Bootstrap could not be completed.` and
writes nothing.

### Add a child

Open <http://localhost:8000/>, sign in as the parent you just created, and
go to **Household**:

1. **Add member**, then a username, a password, and the role **Child**.
2. Give the child that username and password. They sign in on their own
   device, at the same address, and pick their creature line the first time.

The same screen adds the second parent. Every account in the household is
created here.

### Set your approval PIN

Approving a chore needs a PIN, not just a session, so each parent sets their
own on the **Approval PIN** screen: four to ten digits, confirmed with the
account password. Until a parent has one, they cannot approve anything.

### Let the rest of the household in

Out of the box the application answers on `127.0.0.1` only, so nothing but
this machine can reach it. To let the family's devices in, publish it on the
network and tell Django the address they will type:

```shell
CHORUM_BIND=0.0.0.0 CHORUM_HOSTS=localhost,127.0.0.1,192.168.1.20 docker compose up -d
```

That is plain HTTP on your own network, which is what a household on its own
LAN should expect. Do not put it on the public internet like this. If you
want it reachable from outside the house, terminate TLS in a reverse proxy in
front of it and start it with `CHORUM_HTTPS=true`, which turns on Secure
cookies, the redirect to HTTPS, and HSTS together.

### Accrue the weekly interest

Interest is not a background thread; one command applies it, and it is safe
to run twice for the same date. Run it once a week from the host's cron,
shortly after the Sunday 00:00 UTC week boundary:

```
5 0 * * 0 cd /path/to/chorum-murohc && docker compose exec -T app \
  python manage.py accrue_interest --date "$(date -u -d yesterday +\%Y-\%m-\%d)"
```

`_docs/interest-schedule.md` has the rest: dry runs, one household at a time,
a missed week, and how to turn it off.

### Everyday operations

```shell
docker compose logs -f app                 # what the server is doing
docker compose ps                          # both containers and their health
docker compose stop                        # stop the household
docker compose up -d                       # start it again
git pull && docker compose up -d --build   # update to a newer version
docker compose exec app python manage.py changepassword alexis
```

There is no self-service password reset: a forgotten password is reset with
`changepassword` by whoever runs the machine.

## Backup and restore

The points and the history are the only things in here that cannot be made
again, and they all live in PostgreSQL. One command dumps everything:

```shell
docker compose exec -T database pg_dump --clean --if-exists -U chorum_murohc chorum_murohc > chorum-backup.sql
```

One command puts it back. Stop the application first so nothing is writing
while the tables are replaced; the dump drops and recreates each one, so
restoring over a running household is safe to repeat:

```shell
docker compose stop app
docker compose exec -T database psql -U chorum_murohc -d chorum_murohc < chorum-backup.sql
docker compose start app
```

Keep the dump somewhere off this machine. It contains password and PIN
hashes, so treat it like the household's keys.

The `state` volume holds one more thing worth keeping: the generated session
signing key. Losing it costs everyone their signed-in session and nothing
else - they sign in again.

## Configuration

Settings are read from the process environment. Django does not load `.env`
files in this project. The compose file sets everything the container needs;
these are the ones worth changing, and each has a `CHORUM_*` shortcut you can
put in front of `docker compose up -d`.

| Shortcut | Sets | Default | What it is for |
| --- | --- | --- | --- |
| `CHORUM_BIND` | the published address | `127.0.0.1` | `0.0.0.0` to let the household's devices reach it |
| `CHORUM_PORT` | the published port | `8000` | another port on the host |
| `CHORUM_HOSTS` | `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | every name or address the family will type, comma separated |
| `CHORUM_HTTPS` | `DJANGO_HTTPS` | `false` | `true` when a TLS proxy sits in front |
| `CHORUM_DB_PASSWORD` | the database password | a fixed local value | set it before the first start if you want your own |

The database publishes no port at all: the application container on the
compose network is the only thing that can reach it.

The full set of variables the settings module reads, for anyone deploying it
some other way:

| Variable | Accepted format | Development default | Production requirement |
| --- | --- | --- | --- |
| `DJANGO_ENVIRONMENT` | `development` or `production`; whitespace and case are normalised | `development` | Set to `production`; empty or unknown is rejected |
| `DJANGO_SECRET_KEY` | Any non-blank value, used exactly as supplied | `django-insecure-local-development-only` | Required, unless `DJANGO_SECRET_KEY_FILE` supplies it |
| `DJANGO_SECRET_KEY_FILE` | Path to a file holding the key; surrounding whitespace is stripped. `DJANGO_SECRET_KEY` wins if both are set | unset | How the container does it: the entrypoint generates the file into the state volume on the first start |
| `DJANGO_DEBUG` | True: `1`, `true`, `yes`, `on`; false: `0`, `false`, `no`, `off` | `True` | Defaults to `False`; a true value is always rejected |
| `DJANGO_HTTPS` | Same true and false values as `DJANGO_DEBUG` | `False` | Defaults to `True`. Secure cookies, the HTTPS redirect and HSTS, all together |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hosts; empty entries and `*` are rejected | `localhost`, `127.0.0.1`, `[::1]`, `testserver` | At least one non-wildcard host |
| `DJANGO_DB_ENGINE` | `sqlite` or `postgresql` | `sqlite` | Must be `postgresql` |
| `DJANGO_DB_NAME` | SQLite: `:memory:`, an absolute path, or a path under the project root. PostgreSQL: the database name | `<project-root>/db.sqlite3` | Required |
| `DJANGO_DB_USER`, `DJANGO_DB_PASSWORD`, `DJANGO_DB_HOST`, `DJANGO_DB_PORT` | Any non-blank value; the port is 1 to 65535 | Must be absent with SQLite | All four required |
| `DJANGO_DB_TARGET` | The isolated-test grammar below | Only when development selects PostgreSQL | Forbidden |

Supplying a PostgreSQL-only variable while SQLite is selected is an error
rather than being silently ignored.

### What `DJANGO_HTTPS=false` costs

A Secure cookie is never sent over plain HTTP, so a household reached at
`http://192.168.1.20:8000` must have this off or nobody could sign in. It is
a real downgrade and the deployment check says so: with it off,
`manage.py check --deploy` reports W004, W008, W012 and W016 - no HSTS, no
redirect to HTTPS, and neither cookie marked Secure. On a home network,
behind the house's own router, that is the honest trade. With
`CHORUM_HTTPS=true` and a proxy holding the certificate, the same check has
nothing to report but the one W021 this project silences on purpose.

## Development

### What runs where

- `chorum_murohc/` - Django. One package per domain: `identity`, `chores`,
  `submissions`, `ledger`, `rewards`, `progression`, `creatures`, `interest`,
  `audit`. `chorum_murohc/api/` is the only HTTP layer.
- `config/` - settings, URLs, and `config/spa.py`, which serves the API, the
  admin and the built interface from one origin. Session cookies and CSRF
  only work when they share one.
- `frontend/` - React, TypeScript, Vite, Tailwind.
- `docker/`, `Dockerfile`, `compose.yaml` - how it runs.
- `_docs/` - the plan, the design, the backlog and the product policies.

The public name has a hyphen; Python packages cannot, so the importable
package is `chorum_murohc`.

### Prerequisites

Python 3.13 or later, [uv](https://docs.astral.sh/uv/), Node.js 24.15.0 and
pnpm 11.19.0.

### The two gates

Both green, or no merge. CI reports them as `Backend` and `Frontend`.

```shell
uv sync --locked
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked python manage.py check
uv run --locked python manage.py makemigrations --check --dry-run
uv run --locked pytest
```

```shell
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend test
pnpm --dir frontend build
```

With no database variables set, the backend gate uses a local SQLite file and
needs no service. That is convenient, not CI parity; CI runs the same
commands against PostgreSQL. A third workflow, `Dependency audit`, scans both
lockfiles for known vulnerabilities every Monday and on every pull request.

### Running it without Docker

```shell
uv run --locked python manage.py migrate
pnpm --dir frontend dev
uv run --locked python manage.py runserver
```

Vite serves the interface on <http://localhost:5173/> and proxies `/api` to
Django on port 8000, so the two still share an origin from the browser's
point of view. To run the built interface the way the container does, build
it first and use the same server the container uses:

```shell
pnpm --dir frontend build
uv run --locked python manage.py serve --port 8000
```

### Browser journeys

Five household journeys and two audits, driven in headless Chrome against
the real API and the real build, on one origin. They need a build and a
browser, so they are a local gate rather than a CI check:

```shell
pnpm --dir frontend build
python3 -m browser_journeys.run_journeys .
```

`browser_journeys/README.md` has the journey list and the isolation contract.

### Isolated PostgreSQL tests

A PostgreSQL development or test run fails closed around one explicitly
named target. Every character must match one of these grammars exactly;
whitespace, uppercase, other punctuation and missing tokens are rejected.

| Lineage | Exact target grammar | Required host |
| --- | --- | --- |
| Local task | `task_tNNN_<worker-token>` - three digits, then 8-16 lowercase letters or digits | `127.0.0.1` |
| CI job | `ci_<run-id>_<attempt>_<job-token>` | `postgres` |

For a target `<target>`, nothing is chosen independently: the base database
and the restricted role are both `chorum_murohc_<target>`, the disposable
test database is `test_chorum_murohc_<target>`, and the password is a
test-only secret injected through the environment, never written in a file or
a command argument.

Local runs use one fresh container from the approved immutable image
`postgres:17.11-alpine@sha256:18cfe3ef5e6815560c98237d6216d1e5119702fb0f3894c8785dd58b8bbe5d73`,
bound to `127.0.0.1` on a Docker-selected port, with transient storage and no
repository or secret mount. The approval is recorded in
[issue #5](https://github.com/alexisdacquay/chorum-murohc/issues/5#issuecomment-5559116428).
Before Django is given a credential, a preflight proves the target, the
derived names, the owner, the four role flags
(`NOSUPERUSER CREATEDB NOCREATEROLE NOREPLICATION`), the empty base schema
and the absent test database, and refuses if any of them is wrong. Afterwards
the test database must be gone and the base schema still empty; then remove
that one recorded container by its exact name, never by prefix or prune.
`.github/workflows/ci.yml` owns the same guard for CI, including how its
credentials are derived and rotated inside the job.

## What this deployment is not

Said plainly, because the alternative is finding out later:

- **One process.** The application is a threaded standard-library WSGI
  server, sized for a family on one machine, and nothing here starts more
  than one worker today. That is a sizing choice rather than a forced one:
  the login abuse control used to be a reason it could not change, since it
  counted attempts in local memory and a second worker would have multiplied
  the allowance, but its counters now live in PostgreSQL and are shared
  across any number of processes
  ([#128](https://github.com/alexisdacquay/chorum-murohc/issues/128)).
- **No TLS of its own.** Certificates belong to a reverse proxy in front of
  it. See `DJANGO_HTTPS` above.
- **The Content-Security-Policy does not reach the interface document.**
  `config/middleware.py` sends `default-src 'self'` on Django's own
  responses; the built interface, served by `config/spa.py`, does not carry
  it. Driving the real build under that policy in a browser blocks two things
  the interface does today - the `data:` favicon Vite inlines, and an inline
  `<style>` element that appears when a dialog opens - so switching it on
  would silently drop styles. `_docs/audit-security.md` records it for S-01's
  owner.
- **No self-service password reset**
  ([#129](https://github.com/alexisdacquay/chorum-murohc/issues/129)) and no
  way to switch between households in one session
  ([#130](https://github.com/alexisdacquay/chorum-murohc/issues/130)).
- **One household.** The data model has households, but the product is built
  and tested for one family on one machine.
- **Not tamper-proof.** Household isolation and the append-only ledger are
  enforced in the application, not by the database. Whoever holds the
  database holds the points.

## Documentation

- [Contributor map](AGENTS.md) - layout, the two gates, and the house rules
- [Project plan](_docs/plan.md) - current product scope and requirements
- [Design](_docs/design.md) - selected architecture and implementation track
- [Backlog](_docs/tasks.md) - self-contained implementation tasks
- [Testing guidelines](_docs/testing-guidelines.md) - what to test and where
- [Design system](_docs/design-system.md) - interface tokens and component rules
- [Dependency approvals](_docs/dependency-approvals.md) - package-change register
- [Approval authentication](_docs/approval-authentication.md) - parent PIN policy
- [Interest policy](_docs/interest-policy.md) - the weekly rule and its arithmetic
- [Interest schedule](_docs/interest-schedule.md) - the cron line and recovery
- [Creature catalogue policy](_docs/creature-catalogue-policy.md) - the seven lines
- [Retention policy](_docs/retention-policy.md) - deactivate, edit and delete rules
- [Roadmap](_docs/roadmap.md) - ideas intentionally deferred beyond the current scope
- [Browser journeys](browser_journeys/README.md) - the end-to-end harness
- [Accessibility audit](_docs/audit-accessibility.md) - WCAG 2.2 AA findings
- [Security audit](_docs/audit-security.md) - security findings and residual risks
- [Plan verification](_docs/plan-verification.md) - requirement-by-requirement go or no-go
