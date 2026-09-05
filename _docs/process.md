# Development Process

This process applies whenever work is performed by one developer, several
developers, or delegated coding agents. Safety and a reproducible handoff take
priority over maximising concurrency.

## Roles

- PM - grooms a task before anyone implements it, follows `_docs/team/pm.md`

## Unit of work

- `main` is the integration branch. Each implementation task is one GitHub
  issue with one assignee, one branch, one pull request, and one dedicated
  worktree.
- "One issue at a time" means one active implementation issue per worker. More
  than one worker may proceed only when their issues are Ready and their
  ownership does not overlap.
- Backlog task IDs are stable references, not a promise of numerical execution.
  The dependencies in `_docs/task-dependencies.md` determine what can start.
- Do not combine unrelated tasks in one branch or pull request. Record newly
  discovered work as a separate issue.
- A task resolved as not applicable satisfies its dependants only when the issue
  records the governing policy decision, acceptance evidence, and integration
  owner approval. An abandoned or merely closed issue does not.

## Ready gate

Create the issue from `.github/ISSUE_TEMPLATE/implementation-task.md`. An issue
is Ready only when all of the following are true:

- the Goal, Description, acceptance criteria, verification, workstream, and
  ownership fields are complete;
- every dependency is merged into the integration branch, rather than merely
  completed on another worker's branch;
- required policy and product decisions have recorded approval;
- required API, data, or asset contracts are merged;
- every proposed dependency addition has recorded approval in
  `_docs/dependency-approvals.md`;
- the integration branch passes its current checks; and
- ownership of every shared path is assigned to one issue.

If any item is missing, keep the issue Blocked. Do not ask a worker to infer the
missing contract.

T001 has one explicit bootstrap exception: its incoming integration check is
`uv run --locked python manage.py test chorum_murohc`, because pytest is not
installed yet. Its outgoing acceptance check is `uv run --locked pytest`. After
T001 merges, pytest is the canonical backend test command and the bootstrap
exception expires.

## Branch and worktree isolation

- Use a dedicated worktree and branch for every issue. Codex branches use
  `codex/<task-id>-<short-slug>`.
- The orchestrator creates or removes worktrees serially. Before writing, the
  worker verifies and records the repository path, worktree path, branch, base
  commit, and clean working-tree status.
- Never assign two write-capable workers to the same worktree or let feature
  workers edit the integration checkout.
- When delegated agents share one checkout, allow only one writer; other agents
  must be read-only reviewers unless they have explicitly isolated worktrees.
- In a shared checkout, read-only means no installs, tests, formatters, builds,
  generators, migrations, or commands that may create caches or files. A
  reviewer who must run verification receives another isolated worktree.
- Start from the latest verified integration commit and record that base commit
  in the issue.
- Before each commit, inspect the working tree and stage only files owned by the
  issue. Never commit another worker's changes.
- Keep commits small and related to the issue. Never reset, delete, overwrite,
  or absorb unrelated work to resolve a conflict.
- Never commit or push directly to `main`, and never force-push it. Issue
  assignment authorises pushing only the declared feature branch and opening or
  updating its pull request.

## Shared-file ownership

Only one active issue at a time may own any of these shared hotspots:

- `pyproject.toml` and `uv.lock`;
- frontend dependency manifests and lockfiles;
- Django root settings, app registration, and root URL configuration;
- migrations within the same Django app;
- the frontend router, build configuration, and application shell;
- global design tokens and shared UI primitives;
- CI configuration;
- any aggregate creature catalogue or manifest; and
- `_docs/dependency-approvals.md` and `_docs/requirements-evidence.md`.

The issue must declare shared ownership before work starts. If an unplanned
shared-file change becomes necessary, stop and obtain ownership from the
integration owner. Prefer domain-owned URL modules, services, tests, frontend
feature directories, and per-lineage creature manifests.

## Django migrations and databases

- Task T002 must define Django app boundaries, allowed dependencies, and
  migration ownership before product models are added.
- Assign only one migration writer per Django app at a time. Cross-app schema
  changes are integrated serially.
- Create a migration only after predecessor migrations for that app are merged.
  Keep a model change and its schema migration in the same issue.
- Use a PostgreSQL database isolated to the worktree or CI run. Never share a
  mutable development database between workers.
- Use the explicit task-scoped database configuration established by T005, not
  a database URL inherited incidentally from a shell or secret file. Before any
  `migrate`, `flush`, `loaddata`, schema, or destructive data command, verify the
  non-secret host and database name match the task or CI isolation convention.
  If the target cannot be proven isolated, stop.
- Use a restricted task-local database user, an explicit local or CI host, and a
  unique database-name suffix derived from the worktree or CI run. Never source
  `.env` or inherit an unchecked database URL for database operations.
- Never run migration, load, flush, drop, or destructive test setup against a
  shared, staging, or production database from a delegated task.
- Do not apply feature migrations to a persistent shared database before merge.
- Verify migrations from an empty PostgreSQL database and from the latest
  merged schema.
- Resolve conflicts from the integration branch deliberately. Never edit a
  migration dependency merely to silence an error.
- The custom user model is an exclusive foundation gate and must land before
  persistent business migrations.

## Dependencies and lockfiles

- Do not add a dependency without the approval required by `AGENTS.md`.
- Approval identifies the direct package, purpose, ecosystem, and acceptable
  version range. A selected technology in `_docs/design.md` is not by itself
  permission to install a package.
- Only the issue owning the applicable manifest and lockfile may change them.
- Commit the manifest and regenerated lockfile together. Never edit a lockfile
  manually or hide dependency changes inside unrelated feature work.
- Non-owner verification uses immutable installs and runs, including
  `uv sync --locked`, `uv run --locked ...`, and future
  `pnpm install --frozen-lockfile`. Only the approved manifest owner may
  regenerate a lockfile.

## Integration and merge order

A designated integration owner keeps the integration branch green and merges
one pull request at a time in this order when changes depend on one another:

1. approved policies and contracts;
2. approved dependencies and shared configuration;
3. models and migrations;
4. domain services;
5. APIs;
6. interfaces;
7. end-to-end verification and audits.

Independent domains may use parallel lanes only after their shared foundations
are merged. UI work may start only against a merged contract; do not guess an
API shape from another unmerged branch.

After a shared configuration, migration, or lockfile merge, rerun all currently
available checks before integrating another dependent issue. Never merge a
failing or incompletely verified branch.

After each merge, the integration owner alone updates
`_docs/requirements-evidence.md` from the pull request's requirement IDs and
evidence. Feature branches report evidence but do not compete to edit the shared
matrix.

Repository settings such as branch protection, required checks, deployment
credentials, or force-push rules are external mutations. An agent may recommend
them but must not change them without explicit authorisation. Until protections
are enabled, work remains single-writer and the integration owner enforces the
same checks manually. Parallel write-capable delegation begins only after T017
is green and an authorised human enables required checks and protection against
direct and force pushes to `main`.

T017 pins third-party GitHub Actions to reviewed full commit SHAs, grants the
minimum workflow permissions, avoids `pull_request_target`, and exposes no
secrets to untrusted pull requests.

## Testing

- Follow `_docs/testing-guidelines.md`.
- Run the narrowest relevant test first and then the whole affected suite.
- Database-dependent tests use isolated PostgreSQL after Task T005 establishes
  the database test foundation.
- A retry does not turn a flaky test into a pass.
- Every acceptance criterion needs recorded automated or manual evidence.
- UI work also records the keyboard, reduced-motion, mobile, and desktop checks
  required by `_docs/design-system.md`.
- Before CI exists, the integration owner reproduces required checks locally.
  Once CI exists, its required checks must pass before merge.
- If a required check cannot run, the issue remains open or Blocked and records
  the reason.

## Secrets and sensitive data

- Never read, print, copy, commit, or attach `.env` contents.
- Do not copy secret files into worktrees. Use approved local credential storage
  and runtime environment injection.
- Example configuration contains variable names and safe placeholders only.
- Never place tokens, passwords, PINs, cookies, or personal data in command
  arguments, issues, logs, fixtures, screenshots, or test output.
- Inspect the proposed diff for credentials and personal data before handoff.
- If exposure is suspected, stop, notify the owner, revoke or rotate the
  credential, and coordinate any history repair before continuing.

## External and host actions

Issue assignment authorises repository-local changes plus pushing the declared
feature branch and opening or updating its pull request. It does not authorise:

- host scheduler or service changes, global installs, or unrelated filesystem
  changes;
- GitHub repository settings or branch-protection changes;
- deployments, cloud resources, external databases, or paid APIs; or
- uploading data, generating media through an external provider, publishing,
  or messaging third parties.

Each such action needs a separate recorded approval naming the approver,
service or host, data exposure, expected cost, rollback, and exact scope. Prefer
a repository-owned simulation or documented command when that proves the task
without the external mutation.

## Approval states and authorities

- Approval states are Pending, Approved, Rejected, or Superseded.
- The issue names the human authorised to approve product behaviour,
  dependencies, security risk, external actions, and rights or licensing as
  applicable. An agent cannot approve its own proposal.
- Product preference does not substitute for security acceptance or rights and
  legal clearance. A Rejected or Superseded decision cannot satisfy a Ready
  gate.

## Failure and escalation

Stop and mark the issue Blocked when:

- a dependency, policy, contract, or approval is missing;
- a proposed dependency has not been approved;
- shared ownership conflicts;
- the baseline or an upstream dependency is failing;
- an unexpected migration conflict appears;
- unrelated changes overlap the task;
- security, privacy, licensing, destructive action, or external-system mutation
  needs a human decision; or
- satisfying the issue would materially expand its scope.

Do not repeat an unchanged failing operation. After two materially different
diagnostic attempts, record sanitised evidence and escalate. Never invent a
policy, weaken a test, or silently broaden the task to obtain a pass.

## Handoff evidence

Before handoff, the worker records:

- the issue, branch, base commit, and head commit;
- a concise implementation summary and changed-file list;
- shared hotspots changed and their ownership approval;
- the completed acceptance-criteria checklist;
- dependency and product-decision approvals;
- migrations and database verification, when applicable;
- commands run, results, and required manual checks;
- known risks, deliberately untested behaviour, and follow-up issues;
- confirmation that the worktree is clean and no secrets were included; and
- the pushed branch and linked pull request.

The integration owner reviews the complete diff, checks scope and ownership,
repeats risk-proportionate verification, and merges only when the evidence is
complete.
