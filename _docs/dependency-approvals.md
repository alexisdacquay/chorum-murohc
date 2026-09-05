# Dependency Approval Register

No entry in this document grants approval by itself. A direct dependency may be
added only after the product owner approves its package name, purpose, ecosystem,
and compatible version range. Record that decision here and link the approving
issue or discussion before changing a manifest or lockfile.

The selected stack in `_docs/design.md` records technical intent. It is not a
blanket installation approval.

## Planned approval gates

| Gate | Earliest task | Proposed purpose | Status |
| --- | --- | --- | --- |
| DA-01 | T001 | `pytest` and `pytest-django` baseline | Approved |
| DA-02 | T003 | One Python formatter and linter | Approved |
| DA-03 | T005 | PostgreSQL driver | Pending exact proposal and approval |
| DA-04 | T010 | Django REST Framework | Pending exact proposal and approval |
| DA-05 | T011 | React, TypeScript, Vite, Vitest, and Testing Library foundation | Pending exact proposal and approval |
| DA-06 | T012 | Tailwind CSS | Pending exact proposal and approval |
| DA-07 | T013 | shadcn/ui and required Radix primitives | Pending exact proposal and approval |
| DA-08 | T016 | TanStack Query | Pending exact proposal and approval |
| DA-09 | T028 | React Hook Form and Zod | Pending exact proposal and approval |
| DA-10 | T083 | Motion, only if CSS is demonstrably insufficient | Conditional; pending exact proposal and approval |
| DA-11 | T088 | Playwright | Pending exact proposal and approval |

### DA-01 — Approved

- Direct package(s): `pytest`, `pytest-django`
- Ecosystem and manifest: Python, `pyproject.toml` and generated `uv.lock`
- Purpose: establish the canonical locked pytest baseline
- Permitted version range(s): `pytest>=9.1.1,<10.0`, `pytest-django>=4.14.0,<5.0`
- Approved by: alexisdacquay
- Approval date: 2026-09-05
- Evidence link: https://github.com/alexisdacquay/chorum-murohc/issues/1#issuecomment-5555010370
- Owning task: T001

### DA-02 — Approved

- Direct package(s): `ruff`
- Ecosystem and manifest: Python, `pyproject.toml` and generated `uv.lock`
- Purpose: provide one locked backend formatter and linter for reproducible formatting and lint checks
- Permitted version range(s): `ruff>=0.16.6,<0.17.0`
- Approved by: alexisdacquay
- Approval date: 2026-09-06
- Evidence link: https://github.com/alexisdacquay/chorum-murohc/issues/3#issuecomment-5555495792
- Owning task: T003

## Approval record template

```markdown
### <gate> — <status>

- Direct package(s):
- Ecosystem and manifest:
- Purpose:
- Permitted version range(s):
- Approved by:
- Approval date:
- Evidence link:
- Owning task:
```

Transitive packages are accepted only through the generated, reviewed lockfile.
Adding, replacing, or making a major-version change to a direct dependency needs
a new approval record.

Valid states are Pending, Approved, Rejected, and Superseded. The approving
human and evidence must be named, and an agent cannot approve its own proposal.
This register is itself a shared file owned by the integration owner.
