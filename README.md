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

- Python
- Django
- [uv](https://docs.astral.sh/uv/) for Python project and dependency management

## Documentation

- [Project plan](_docs/plan.md) — current product scope and requirements
- [Roadmap](docs/roadmap-v1.md) — ideas intentionally deferred beyond the current scope

## Local development

### Prerequisites

- Python 3.13 or later
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

### Setup

Install the locked dependencies and prepare the local database:

```shell
uv sync
uv run python manage.py migrate
```

Start the development server:

```shell
uv run python manage.py runserver
```

Then open <http://127.0.0.1:8000/>.

### Checks and tests

```shell
uv run python manage.py check
uv run python manage.py test
```

## Project structure

- `config/` — project-wide Django settings and URL routing
- `chorum_murohc/` — the main Chorum-murohc Django app
- `_docs/plan.md` — current product plan and requirements
- `manage.py` — command-line entry point for Django tasks

The public project and app name uses a hyphen. Python package names cannot use
hyphens, so the app's importable code folder uses `chorum_murohc` instead.

## Configuration and security

The generated settings are suitable for local development only. Before a
deployment, set `DJANGO_SECRET_KEY` and review Django's `DEBUG` and
`ALLOWED_HOSTS` settings.

Do not commit credentials or local configuration. `.env` is excluded from
version control.
