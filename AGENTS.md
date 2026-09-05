Commands

- `uv sync --locked` - install exactly the locked dependencies
- `uv run --locked pytest` - run the whole suite
- `uv run --locked pytest chorum_murohc/tests.py` - the baseline test file after T001
- `uv run --locked ruff format --check .` - verify Python formatting
- `uv run --locked ruff check .` - verify Python linting

Documents

- `_docs/process.md` - how work is organized
- `_docs/task-dependencies.md` - readiness gates and safe parallel workstreams
- `_docs/dependency-approvals.md` - approvals required before adding packages
- `_docs/requirements-evidence.md` - integration-owned plan coverage and proof
- Before writing tests, read `_docs/testing-guidelines.md`
- For anything touching the UI, read `_docs/design-system.md`

Rules

- Python dependencies are added in `pyproject.toml`; frontend dependencies go
  in the frontend manifest once it exists. Do not add any dependency without
  asking and recording approval in `_docs/dependency-approvals.md`.
- Do not begin implementation unless the GitHub issue satisfies the Ready gate
  in `_docs/process.md` and all dependencies are merged.
- A write-capable worker must have an isolated branch and worktree. If agents
  share a checkout, only one may write and the others are read-only reviewers.
- Non-owners install only from lockfiles. They must not regenerate or update a
  dependency lockfile.
