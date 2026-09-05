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
| DA-01 | T001 | `pytest` and `pytest-django` baseline | Pending exact proposal and approval |
| DA-02 | T003 | One Python formatter and linter | Pending exact proposal and approval |
| DA-03 | T005 | PostgreSQL driver | Pending exact proposal and approval |
| DA-04 | T010 | Django REST Framework | Pending exact proposal and approval |
| DA-05 | T011 | React, TypeScript, Vite, Vitest, and Testing Library foundation | Pending exact proposal and approval |
| DA-06 | T012 | Tailwind CSS | Pending exact proposal and approval |
| DA-07 | T013 | shadcn/ui and required Radix primitives | Pending exact proposal and approval |
| DA-08 | T016 | TanStack Query | Pending exact proposal and approval |
| DA-09 | T028 | React Hook Form and Zod | Pending exact proposal and approval |
| DA-10 | T083 | Motion, only if CSS is demonstrably insufficient | Conditional; pending exact proposal and approval |
| DA-11 | T088 | Playwright | Pending exact proposal and approval |

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
