# Chorum-murohc — Implementation Backlog

This backlog covers the current product scope in `_docs/plan.md` and the
selected implementation track in `_docs/design.md`. Long-term product and
technical possibilities remain in `_docs/roadmap.md` until the product owner
promotes them into the current scope.

Each entry is a source brief for one GitHub issue; Task 1 is referenced as T001,
Task 2 as T002, and so on. Before delegation, the orchestrator must add the
workstream, merged dependencies, owned paths,
acceptance criteria, and verification required by `_docs/process.md`; the source
brief alone is not Ready. Task IDs are stable references, while
`_docs/task-dependencies.md` controls execution order.

Tasks are intended for one focused engineering session except the explicitly
approved one-task-per-creature-lineage work. Those lineage tasks remain one
issue each but may use resumable checkpoint commits under one owner.

Implementation work follows two additional rules:

- Read the affected flow before changing it, reuse existing or native
  facilities, avoid speculative abstractions and dependencies, and leave the
  smallest runnable test that proves non-trivial behaviour.
- Keep control flow deterministic, persist business state needed for recovery,
  return compact actionable errors, cap retries, and stop for an explicit human
  decision when a named prerequisite policy is absent.

## 1. Set up an empty project with a passing test

**Goal**: Verify and stabilise the existing empty Chorum-murohc project baseline.

**Description**: Treat the current Django 5.2 project, registered `chorum_murohc` app, uv lockfile, and app-registration test as the required empty scaffold; do not recreate them. First prove the incoming baseline with `uv run --locked python manage.py test chorum_murohc`; after obtaining and recording DA-01 approval for exact compatible `pytest` and `pytest-django` ranges, establish and document `uv run --locked pytest` as the outgoing canonical command and finish with a clean passing test and no product models or features.

## 2. Establish the initial backend boundaries

**Goal**: Define the minimum module boundaries needed to keep the Django backend maintainable.

**Description**: Amend `_docs/design.md` with actual Django app or package names, allowed dependency directions, model and migration ownership, and the role of the existing `chorum_murohc` package. After approval, create and register only the empty app/package shells with focused registration and dependency-boundary checks so later schema tasks do not compete for root settings; do not add product models or speculative framework layers.

## 3. Add backend formatting and linting commands

**Goal**: Make backend formatting and linting reproducible alongside the established test command.

**Description**: After obtaining and recording DA-02 approval, configure one formatter and linter, reusing a single tool where it covers both jobs and leaving the Task 1 pytest baseline unchanged. Document and run the smallest command set that checks the existing scaffold, and do not add coverage gates or plugins without a current requirement.

## 4. Configure runtime-based Django settings

**Goal**: Keep secrets and environment-specific values out of tracked source code.

**Description**: Make Django read its secret key, debug flag, allowed hosts, and database connection from runtime configuration while retaining explicitly documented safe local defaults. Add focused settings tests for parsing and missing production-critical values without introducing a settings framework unless Django and the standard library are insufficient.

## 5. Establish the isolated PostgreSQL test foundation

**Goal**: Make database-dependent development and tests use isolated PostgreSQL before product schemas are added.

**Description**: After obtaining and recording DA-03 approval for the PostgreSQL driver, connect through the Task 4 settings contract and establish an explicit task-or-CI database naming and target guard that rejects ambient, shared, staging, and production targets. Prove the empty scaffold can create and discard its isolated test database without adding product models, reading a secret file, or applying feature migrations to a persistent environment.

## 6. Create the custom user model before business migrations

**Goal**: Establish the Chorum-murohc user model before any persistent business schema is migrated.

**Description**: In the identity app selected by Task 2, add a minimal custom Django user model that preserves username and password authentication and leaves household roles to membership records. Configure `AUTH_USER_MODEL`, create its initial migration, and test ordinary-user and superuser creation against isolated PostgreSQL without applying it to a persistent shared database.

## 7. Model households and memberships

**Goal**: Represent configurable households containing parent and child members.

**Description**: Add household and membership models linked to the custom user model, with parent and child roles and a database constraint preventing duplicate membership. Create migrations compatible with the custom-user migration, then prove a fresh isolated PostgreSQL database and the full backend tests support both a two-parent/two-child household and a differently sized household.

## 8. Add the minimal audit-event foundation

**Goal**: Provide one durable record format for sensitive mutations before those mutations are implemented.

**Description**: Add an append-only audit event containing household, optional actor, action, target reference, timestamp, and redacted structured context, with no generic event framework. Test creation, stable ordering, immutability through application APIs, and the ability to represent bootstrap actions without an existing actor.

## 9. Bootstrap the first household and parent

**Goal**: Provide a secure path from an empty database to the first authorised parent account.

**Description**: Add one idempotent Django management command that creates the first household and parent using explicit interactive or environment-provided inputs. Refuse unsafe defaults, avoid logging credentials, emit the audit event defined by the current schema, and test first run, repeat run, and invalid input.

## 10. Create the versioned API baseline

**Goal**: Establish a stable Django REST Framework entry point.

**Description**: Add Django REST Framework and expose a versioned `/api/v1/` namespace with one small health or metadata response using DRF's native response and error behaviour. Test the response status and shape without adding custom envelopes, pagination, schema tooling, or product behaviour.

## 11. Scaffold the React frontend with a passing test

**Goal**: Establish the smallest working React and TypeScript frontend.

**Description**: Create a Vite React application in a dedicated frontend directory using pnpm and the versions selected in `_docs/design.md`. Render a minimal Chorum-murohc screen and leave one passing Vitest and Testing Library smoke test plus documented install and test commands.

## 12. Define the visual tokens

**Goal**: Give the modern interface a small, consistent visual vocabulary.

**Description**: Configure Tailwind CSS and define only the initial colours, typography, spacing, radii, elevation, focus, and motion tokens needed by the application shell and authentication screens. Demonstrate the tokens on one static reference page and test colour contrast and reduced-motion defaults.

## 13. Add the first shared interface primitives

**Goal**: Reuse accessible controls required by the first interactive screens.

**Description**: Add shadcn/ui primitives for button, text input, form message, card, and dialog only, keeping their native Radix behaviour and the visual tokens from the design system. Render each state on the reference page and add focused accessibility and interaction tests without creating wrappers that have only one caller.

## 14. Build the responsive application shell

**Goal**: Provide the shared page frame for authenticated and unauthenticated screens.

**Description**: Build a mobile-first shell with a header, main content region, loading boundary, and error boundary using the established tokens and primitives. Test responsive layout, landmark semantics, keyboard focus restoration, loading, and compact actionable error presentation without adding product navigation.

## 15. Add role-aware navigation

**Goal**: Show parent and child users only the navigation appropriate to their role.

**Description**: Extend the application shell with a small route map using browser and React facilities already present, without adding a routing dependency, and distinct parent, child, and signed-out navigation states driven by the merged current-user contract. Test active routes, keyboard use, narrow screens, unknown roles, and signed-out behaviour; stop for dependency approval if native routing proves insufficient.

## 16. Connect the frontend and API on one origin

**Goal**: Let React call Django without CORS or token-authentication machinery.

**Description**: Configure Vite's development proxy and the production path so the frontend reaches `/api/v1/` on the Django origin, then use TanStack Query for one typed health request. Test success, loading, a compact server error, and cookie forwarding; do not add JWT, CORS, or a custom API client framework.

## 17. Add baseline continuous integration

**Goal**: Run the current backend and frontend checks on every proposed change.

**Description**: Configure CI to install immutable uv and pnpm lockfiles and run only the documented formatting, linting, test, and frontend build commands that currently exist. Pin third-party actions to reviewed full commit SHAs, grant minimum permissions, avoid `pull_request_target`, use a restricted ephemeral PostgreSQL service, expose no credentials to untrusted changes, and document matching local commands; parallel writers remain blocked until an authorised human enables the required checks and protects `main`.

## 18. Define trust boundaries and the permission matrix

**Goal**: Approve parent and child authority before role-sensitive code is built.

**Description**: Add a concise threat model and permission matrix to `_docs/design.md` covering sessions, household isolation, account administration, chores, submissions, approvals and PINs, ledger mutations, rewards, levels, creatures, audit views, and sensitive logs. Record assets, actors, trust boundaries, abuse cases, and the owner of each mitigation, then obtain product-owner and security approval without implementing permissions in this task.

## 19. Implement the household-role permission primitive

**Goal**: Give later DRF endpoints one tested implementation of the approved access-control foundation.

**Description**: Implement only the minimum reusable household-role permission primitive defined by Task 18, without embedding endpoint-specific policy in it. Test allow, deny, unauthenticated, disabled-user, unknown-role, and cross-household cases; every later endpoint remains responsible for testing its own permission-matrix row.

## 20. Decide deletion and retention behaviour

**Goal**: Reconcile the product's delete actions with ledger, approval, and audit history.

**Description**: Record in `_docs/retention-policy.md` whether users and chores are hard-deleted, deactivated, anonymised, or protected once referenced, including who may act and what remains visible. Obtain product-owner approval before account or chore mutation endpoints are implemented; if approval is absent, stop rather than invent behaviour.

## 21. Create the household account directory API

**Goal**: Let parents list household accounts and create one account safely.

**Description**: Using the retention, onboarding, and permission contracts, add parent-only list and create endpoints with password handling, initial role assignment, household isolation, child denial, and audit events. If the approved onboarding path selects a creature during account creation, reuse the merged selection service and validated catalogue rather than duplicating it; test both ordinary and last-parent household shapes without adding edit or removal operations.

## 22. Create household account and role update operations

**Goal**: Let parents edit an existing household account and assign its approved role.

**Description**: Add parent-only edit and role-change operations to the merged account API contract, preserving household isolation, password safety, and at least one active parent. Test validation, stale or foreign users, child denial, last-parent protection, and exact audit effects without implementing removal or deactivation.

## 23. Create household account removal operations

**Goal**: Apply the approved user-retention decision through a bounded parent-only API operation.

**Description**: Add only the approved remove, deactivate, anonymise, or protect operation from `_docs/retention-policy.md`, reusing the account permission and audit contracts. Test referenced and unreferenced users, self-action, last-parent protection, household isolation, idempotent retry, and retained history without silently hard-deleting protected records.

## 24. Build the household account directory interface

**Goal**: Let parents view household accounts and create one through an accessible interface.

**Description**: Build parent-only list, empty, create, validation, success, and recoverable-error states against the directory API using the approved form tools. If onboarding occurs during account creation, reuse the merged chooser component and its actor rules; test keyboard use, duplicate activation, loading, narrow screens, and no edit or removal controls.

## 25. Build household account and role editing

**Goal**: Let parents edit an existing account and its role without exposing removal behaviour.

**Description**: Add edit and role-change states against the merged update API, reusing account forms and confirmation patterns without duplicating password or permission logic. Test validation, last-parent feedback, stale data, failure recovery, keyboard use, and narrow screens.

## 26. Build household account removal and deactivation

**Goal**: Let parents perform the approved retention action with clear consequences.

**Description**: Add only the approved removal, deactivation, anonymisation, or protected-state interaction from the account API, with explicit consequence text and destructive confirmation. Test cancellation, referenced records, self-action, last-parent protection, repeated activation, API failure, keyboard use, and narrow screens.

## 27. Implement session authentication endpoints

**Goal**: Support secure browser login, session inspection, and logout through Django.

**Description**: Add CSRF-aware endpoints that use Django's native session authentication and return the minimal current-user and household-role data required by navigation. Test valid and invalid credentials, CSRF enforcement, disabled users, logout, unauthenticated inspection, and compact errors without introducing JWTs.

## 28. Build the login and logout experience

**Goal**: Let household members enter and leave Chorum-murohc accessibly.

**Description**: After obtaining and recording DA-09 approval, build login, current-session loading, invalid-credential, disabled-account, and logout flows against the session API using the approved form and validation tools. Route parents and children to their role-appropriate start views and test keyboard, narrow-screen, loading, error, and successful-session states.

## 29. Decide parent identity and PIN approval rules

**Goal**: Define how a specific approving adult is identified and attributed on both approval paths.

**Description**: Record in `_docs/approval-authentication.md` whether the child-device flow selects a parent before PIN entry or requires household-unique PINs, plus PIN length, retry, lockout, recovery, and audit attribution rules. Obtain product-owner and security approval before PIN storage or approval implementation; the decision must cover multiple parents and must not weaken the plan's PIN requirement.

## 30. Store and verify parent PINs securely

**Goal**: Implement the approved PIN contract without storing readable PIN values.

**Description**: Using `_docs/approval-authentication.md`, add the minimum model fields and service needed to set, replace, and verify a parent's PIN with Django's password-hashing facilities. Never return or log the PIN, emit audit events for setup and replacement, and test correct, incorrect, missing, changed, and cross-household cases.

## 31. Create parent PIN management operations

**Goal**: Let an authenticated parent securely set and replace their own approval PIN.

**Description**: Add CSRF-aware PIN setup and replacement API operations following `_docs/approval-authentication.md`, requiring current credentials or the approved recovery check and never returning a stored PIN value. Test validation, success, failure, permissions, household isolation, audit emission, and compact secret-safe errors without adding a settings screen.

## 32. Build the parent PIN management interface

**Goal**: Give each parent an accessible settings screen for creating and replacing their PIN.

**Description**: Build protected PIN setup, replacement, credential or recovery confirmation, success, and recoverable-error states against the merged PIN API. Clear secrets after use and test keyboard use, narrow screens, validation, repeat submission, expiry or logout, and that no stored PIN is displayed.

## 33. Enforce PIN attempt limits

**Goal**: Apply the approved lockout rules to PIN verification without obscuring the approving parent.

**Description**: Implement the retry and lockout policy from `_docs/approval-authentication.md` on top of the merged PIN operations, using the smallest state needed and Django's existing cache or database facilities. Test the exact threshold, reset conditions, concurrent failures, successful recovery, compact client errors, audit-safe logging, and no leakage of whether another parent's PIN matched.

## 34. Model the reusable chore pool

**Goal**: Store household chores and their parent-controlled point values.

**Description**: Using `_docs/retention-policy.md`, add a household-owned chore with name, positive integer point value, active or deletion state, and audit timestamps, but no scheduling or claiming fields. Test database constraints, household isolation, duplicate-name policy, point validation, and the approved retention behaviour once referenced.

## 35. Create the chore-pool API

**Goal**: Let children view active chores and parents manage household chore definitions.

**Description**: Add household-scoped DRF endpoints for listing active chores and parent-only creation, editing, and approved removal or deactivation, relying on native DRF serializers and the permission matrix. Test ordering, validation, household isolation, parent and child access, retention rules, and an audit event for each mutation.

## 36. Build the child chore browser

**Goal**: Present available chores as an engaging mobile-first selection screen.

**Description**: Build responsive chore cards showing only the name and point value returned by the child-visible chore endpoint. Test loading, empty, compact error, retry, touch, keyboard, and narrow-screen states without adding parent editing or submission behaviour.

## 37. Build parent chore management

**Goal**: Let parents create, edit, and remove or deactivate chores through the modern interface.

**Description**: Build parent-only list and form states against the chore-management API and the approved retention policy, reusing existing cards, dialogs, and form controls. Test validation, destructive confirmation, API failure, permissions, keyboard use, and narrow-screen behaviour without duplicating Django admin.

## 38. Create the immutable points ledger

**Goal**: Make every balance change traceable and resistant to accidental rewriting.

**Description**: Add append-only ledger entries with household, user, signed integer amount, reason, source reference, timestamp, and idempotency key, using database constraints instead of a generic ledger framework. Test credits, debits, duplicate rejection, deterministic ordering, household isolation, and prohibition of update or deletion through application services.

## 39. Expose balances and ledger history

**Goal**: Provide balances derived from the ledger as the single source of truth.

**Description**: Add a household-scoped balance service and DRF endpoints for the authorised user's balance and paginated ledger history using DRF's native pagination. Test positive, negative and zero totals, permissions, household isolation, reason labels, ordering, and compact pagination errors.

## 40. Define child completion attestation

**Goal**: State what a child asserts when submitting a chore without photo proof.

**Description**: Record in `_docs/completion-attestation.md` that the current-scope submission is an explicit child assertion that the work is complete and that the server cannot independently prove physical completion. Specify confirmation wording, duplicate policy, and parent rejection behaviour, and obtain product-owner approval before the submission endpoint is built.

## 41. Model chore completion submissions

**Goal**: Persist a child's completion assertion and its review state.

**Description**: Using `_docs/completion-attestation.md`, add a submission linked to household, child, and chore with pending, approved, and rejected states and decision attribution. Enforce valid transitions and test duplicate policy, immutable chore name and point snapshots, household isolation, timestamps, and state constraints.

## 42. Implement the chore-submission API

**Goal**: Let a child attest that an active chore has been completed and request review.

**Description**: Add a child-only DRF endpoint that creates a pending submission exactly as specified in `_docs/completion-attestation.md` and emits an audit event. Test confirmation input, inactive or foreign chores, duplicate policy, child ownership, forbidden parent submission, idempotent retry, and compact validation errors.

## 43. Build the child submission interaction

**Goal**: Let children confirm and submit completed work without accidental repeats.

**Description**: Extend the child chore browser with the approved attestation wording, a confirmation dialog, and success and pending-review states against the submission API. Test cancellation, double activation, loading, retry, validation failure, keyboard and touch operation, and narrow screens.

## 44. Create the pending-approvals API

**Goal**: Give parents a bounded household queue of submissions awaiting decision.

**Description**: Add a parent-only endpoint returning pending submissions with child, chore snapshot, point value, and submission time using native DRF pagination. Test permission denial, household isolation, stable ordering, empty results, page boundaries, and no leakage of other household data.

## 45. Implement atomic approval and rejection

**Goal**: Decide each pending submission once and credit points only on approval.

**Description**: Using `_docs/approval-authentication.md`, lock the pending submission, identify and verify the approving parent, append one idempotent ledger credit on approval, record rejection without credit, and emit an audit event in one database transaction. Test both device paths at the service boundary, concurrent decisions, retry, invalid or locked PIN, stale state, rollback, actor attribution, and unchanged balance after rejection.

## 46. Expose approval and rejection through the API

**Goal**: Provide one mutation endpoint for both parent approval contexts.

**Description**: Add one DRF endpoint that accepts approve or reject, delegates all state and ledger work to the atomic approval service, and follows `_docs/approval-authentication.md` for parent identity and PIN input. Test child-device and parent-device requests, CSRF, roles, household isolation, invalid and locked PINs, stale decisions, idempotent retry, compact errors, and exact response state.

## 47. Build child-device parent approval

**Goal**: Let a parent decide a just-submitted chore safely on the child's device.

**Description**: Build only the child-device decision dialog specified by `_docs/approval-authentication.md`, including parent identification, protected PIN entry, approve, reject, success, lockout, and retry states against the approval API. Test that the child cannot bypass PIN verification, the approving adult is attributed, secrets are cleared, and keyboard, touch, and narrow-screen interactions work.

## 48. Build the parent's approval queue

**Goal**: Let a parent review and decide pending submissions from their own authenticated device.

**Description**: Build the paginated queue and parent-device decision flow against the pending and approval APIs, following `_docs/approval-authentication.md` for any required PIN re-verification. Test empty, loading, stale, concurrent-decision, approve, reject, lockout, compact error, keyboard, and narrow-screen states.

## 49. Build the points dashboard

**Goal**: Show users a trustworthy balance and understandable transaction history.

**Description**: Build role-appropriate balance cards and paginated ledger history against the balance API, with clear labels for chore credits and later transaction reasons. Test positive, negative and zero balances, empty history, loading, retry, permissions, pagination, keyboard use, and narrow screens.

## 50. Finalise the interest policy

**Goal**: Turn the proposed monthly rate, daily accrual, and level bonus into exact arithmetic rules.

**Description**: Using the approved levels and maximum from `_docs/levelling-policy.md`, record in `_docs/interest-policy.md` whether accrual compounds daily, how monthly rates convert to daily rates, how the 20% base and 30% per-level bonus combine, which balance and time zone apply, and how rounding and missed days work. Include approved worked examples for level 0 and level 10 and obtain product-owner approval before calculator implementation.

## 51. Implement the interest calculator

**Goal**: Calculate one day's interest deterministically from the approved policy.

**Description**: Implement `_docs/interest-policy.md` as a pure integer or decimal function with no database access or floating-point arithmetic. Test every worked example plus zero and negative balances, level boundaries, dates, rounding, and any cap or maximum defined by the policy.

## 52. Persist one day's interest idempotently

**Goal**: Append at most one correct interest ledger entry per user and accrual date.

**Description**: Add a transactional service that reads the eligible ledger balance and persisted current level from the approved progression model, calls the calculator, and writes a uniquely keyed interest entry for a supplied date. Test repeat calls, concurrent calls, zero interest, multiple households, partial failure rollback, time-zone boundaries, and audit attribution.

## 53. Expose daily interest as a management command

**Goal**: Provide one deterministic operational entry point for due interest accrual.

**Description**: Add a Django management command that accepts an explicit accrual date, invokes the idempotent accrual service for eligible users, and reports compact counts and failures without sensitive data. Test dry run, one household, all households, invalid date, partial failure, repeat execution, and a non-zero exit for unrecovered errors.

## 54. Schedule daily interest with the native scheduler

**Goal**: Make daily accrual actually run in the current local deployment model.

**Description**: Add repository-owned documentation and the smallest cron-compatible invocation for the interest command at the policy's defined time zone, including locking and log location. Verify it in an isolated controlled environment and document disable, manual retry, and missed-run recovery without adding Redis or Celery; do not install or alter a host scheduler without separate explicit authorisation.

## 55. Decide reward redemption and fulfilment

**Goal**: Define how point spending becomes game time or pocket money in the household.

**Description**: Record in `_docs/reward-policy.md` whether redemption debits immediately or after parent approval, how parents fulfil or cancel off-app rewards, and how quantities, reversals, and audit history work for one minute per point and £5 per 200 points. Obtain product-owner approval before reward services or screens are built.

## 56. Implement reward redemption transactions

**Goal**: Apply the approved reward policy without overspending or losing audit history.

**Description**: Using `_docs/reward-policy.md`, add the minimum records and atomic service needed to request or redeem game time and pocket money and append the corresponding ledger debit at the approved transition. Test exact conversion, insufficient funds, concurrent requests, idempotent retry, cancellation or reversal policy, permissions, household isolation, and audit events.

## 57. Create the reward API

**Goal**: Expose the child reward initiation and status operations authorised by the approved policy.

**Description**: Add child-scoped DRF endpoints to initiate a reward and read its status under `_docs/reward-policy.md`, reusing the reward service rather than duplicating balance logic. Test child permissions, parent denial on these child operations, validation, household isolation, insufficient funds, idempotency, status visibility, and compact errors; leave fulfil, reject, cancel, and reverse mutations to the separate parent API task.

## 58. Build the child rewards screen

**Goal**: Let children understand costs and initiate the approved spending flow safely.

**Description**: Build game-time and pocket-money options with current balance, exact conversion, confirmation, success, pending or fulfilled state as defined by `_docs/reward-policy.md`, and insufficient-funds feedback. Test repeat prevention, loading, error, keyboard, touch, and narrow-screen behaviour against the reward API.

## 59. Create parent reward fulfilment operations

**Goal**: Expose only the parent reward transitions required by the approved policy.

**Description**: Add the parent DRF operations explicitly required by `_docs/reward-policy.md`; if the approved policy requires no parent transition, close this task as not applicable without adding code. Test every allowed transition, stale and duplicate actions, exact ledger effect, audit emission, permissions, household isolation, idempotency, and compact errors.

## 60. Build parent reward fulfilment

**Goal**: Let parents perform the approved reward transitions through an accessible interface.

**Description**: Build only the parent controls and states exposed by the parent reward API; if `_docs/reward-policy.md` requires no parent transition, close this task as not applicable without adding code. Test loading, empty, fulfil, reject, cancel or reverse states as applicable, stale responses, duplicate activation, keyboard use, and narrow screens.

## 61. Finalise the levelling policy

**Goal**: Define every level cost and its relationship to creature forms.

**Description**: Record in `_docs/levelling-policy.md` the exact escalation formula beginning at 500 then 510 points, rounding, maximum level within the planned 30–40 range, insufficient-funds behaviour, and mapping from levels to the approximately 35 ordered form indices. Do not assume one form per level; include a complete cost and mapping table and obtain product-owner approval before implementation.

## 62. Model the child's progression state

**Goal**: Persist one constrained current level for each child before levelling or interest uses it.

**Description**: In the progression app selected by Task 2, add the minimum user-linked current-level state, initial value, maximum constraint, and migration required by the approved levelling policy. Test creation, role and household ownership, invalid levels, deterministic lookup, and migration behaviour against isolated PostgreSQL without adding ledger mutations or API operations.

## 63. Implement the level-up transaction

**Goal**: Spend points and advance one level atomically under the approved policy.

**Description**: Using the merged progression model and `_docs/levelling-policy.md`, add an atomic service that checks the ledger balance and maximum level, appends one idempotent debit, increments the level, and emits an audit event. Test first and final levels, insufficient funds, concurrent requests, repeat calls, rollback, exact cost, and household ownership without changing the progression schema.

## 64. Create the level-up API

**Goal**: Expose the current level, next cost, eligibility, and level-up action to the child.

**Description**: Add child-scoped DRF read and mutation endpoints backed only by the approved level service and `_docs/levelling-policy.md`. Test permissions, current and maximum levels, insufficient balance, stale requests, idempotency, exact response values, and compact errors.

## 65. Build the level-up interface

**Goal**: Make the cost and consequence of levelling clear before points are spent.

**Description**: Build current-level, next-cost, affordability, confirmation, success, maximum-level, and error states against the level API without implementing creature animation. Test repeat prevention, balance refresh, keyboard, touch, reduced motion, loading, and narrow screens.

## 66. Establish creature-lineage rights clearance

**Goal**: Prevent unlicensed third-party characters or assets from entering the product.

**Description**: Record in `_docs/creature-catalogue-policy.md` each proposed creature line, its documented rights or legal clearance, any required licence or proposed original replacement, permitted asset sources, and evidence to retain for every image. Product-owner preference is not legal permission: block each lineage until the rights authority records approval, and require an approved `_docs/plan.md` scope amendment before replacing any named lineage with an original alternative.

## 67. Decide when admin-created children choose a creature

**Goal**: Reconcile admin-created accounts with the plan's requirement that children choose at signup.

**Description**: Record in `_docs/onboarding-policy.md` whether selection occurs during account creation, first login, or a separate parent-assisted step; name the chooser, acting role, service, endpoint, UI owner, incomplete state, and repeat-selection rule. The current plan says the child chooses at signup, so any outcome changing the chooser or timing also requires an approved `_docs/plan.md` amendment before implementation; do not build speculative alternatives.

## 68. Specify creature assets and provenance

**Goal**: Define a consistent, auditable format with an exact ordered form count per approved creature line.

**Description**: Extend `_docs/creature-catalogue-policy.md` with the exact approved form count, dimensions, format, file-size limits, naming, form order, accessibility text, progression, provenance, and acceptance checks, plus separate manifests per lineage. Before producing or uploading media, record the storage and provider decision, approved reference data, retention and privacy terms, expected cost, rollback, and rights status; keep level mapping in `_docs/levelling-policy.md` and do not edit a shared aggregate from lineage tasks.

## 69. Model creature lines and forms

**Goal**: Store the approved creature catalogue and its ordered level-linked forms.

**Description**: Using the approved catalogue and asset specification, add shared creature-line and form records with stable identifiers, form index, display metadata, asset reference, provenance reference, and active state. Test ordering, duplicate form indices, missing required metadata, activation, and the rule that catalogue records are not household-owned.

## 70. Produce images for creature lineage 1

**Goal**: Add the complete approved image evolution for creature lineage 1.

**Description**: Using the approved lineage 1 entry, frozen asset contract, and catalogue validator, create the exact required form-index images in the lineage 1 directory with accessible descriptions and provenance in its own manifest. Run validation at checkpoints and on the completed gradual visual sequence; do not edit an aggregate manifest, and stop unless lineage 1 has recorded rights clearance.

## 71. Produce images for creature lineage 2

**Goal**: Add the complete approved image evolution for creature lineage 2.

**Description**: Using the approved lineage 2 entry, frozen asset contract, and catalogue validator, create the exact required form-index images in the lineage 2 directory with accessible descriptions and provenance in its own manifest. Run validation at checkpoints and on the completed gradual visual sequence; do not edit an aggregate manifest, and stop unless lineage 2 has recorded rights clearance.

## 72. Produce images for creature lineage 3

**Goal**: Add the complete approved image evolution for creature lineage 3.

**Description**: Using the approved lineage 3 entry, frozen asset contract, and catalogue validator, create the exact required form-index images in the lineage 3 directory with accessible descriptions and provenance in its own manifest. Run validation at checkpoints and on the completed gradual visual sequence; do not edit an aggregate manifest, and stop unless lineage 3 has recorded rights clearance.

## 73. Produce images for creature lineage 4

**Goal**: Add the complete approved image evolution for creature lineage 4.

**Description**: Using the approved lineage 4 entry, frozen asset contract, and catalogue validator, create the exact required form-index images in the lineage 4 directory with accessible descriptions and provenance in its own manifest. Run validation at checkpoints and on the completed gradual visual sequence; do not edit an aggregate manifest, and stop unless lineage 4 has recorded rights clearance.

## 74. Produce images for creature lineage 5

**Goal**: Add the complete approved image evolution for creature lineage 5.

**Description**: Using the approved lineage 5 entry, frozen asset contract, and catalogue validator, create the exact required form-index images in the lineage 5 directory with accessible descriptions and provenance in its own manifest. Run validation at checkpoints and on the completed gradual visual sequence; do not edit an aggregate manifest, and stop unless lineage 5 has recorded rights clearance.

## 75. Produce images for creature lineage 6

**Goal**: Add the complete approved image evolution for creature lineage 6.

**Description**: Using the approved lineage 6 entry, frozen asset contract, and catalogue validator, create the exact required form-index images in the lineage 6 directory with accessible descriptions and provenance in its own manifest. Run validation at checkpoints and on the completed gradual visual sequence; do not edit an aggregate manifest, and stop unless lineage 6 has recorded rights clearance.

## 76. Produce images for creature lineage 7

**Goal**: Add the complete approved image evolution for creature lineage 7.

**Description**: Using the approved lineage 7 entry, frozen asset contract, and catalogue validator, create the exact required form-index images in the lineage 7 directory with accessible descriptions and provenance in its own manifest. Run validation at checkpoints and on the completed gradual visual sequence; do not edit an aggregate manifest, and stop unless lineage 7 has recorded rights clearance.

## 77. Create the creature catalogue validator

**Goal**: Reject invalid lineage assets and manifests before expensive catalogue production proceeds.

**Description**: Before lineage production, add the smallest automated validator and representative valid and invalid fixtures for the frozen per-lineage manifest contract and `_docs/levelling-policy.md`. Check exact form counts, identifiers, files, dimensions, size limits, metadata, provenance, rights state, and level mappings, and report missing, extra, or unmapped items compactly without building a general asset framework.

## 78. Validate and load the complete creature catalogue

**Goal**: Prove the seven lineages form one valid catalogue and populate its records reproducibly.

**Description**: Run the T077 validator across every lineage, including cross-line identifier and level-mapping checks, then add one idempotent Django management command that refuses any invalid catalogue before creating or updating its records. Test initial load, changed metadata, repeated load, missing or extra entries, invalid rights evidence, and deactivation without deleting referenced history.

## 79. Implement initial creature selection

**Goal**: Save one approved creature line through the authorised onboarding actor and path.

**Description**: Using `_docs/onboarding-policy.md` and the loaded catalogue, add one reusable selection service. Add a standalone DRF operation only when the approved path occurs after account creation; for creation-time selection, expose no duplicate endpoint and let T021 call the service from its account-create operation. Test incomplete onboarding, unavailable lines, acting for another child, household isolation, repeat attempts, permissions, and audit emission.

## 80. Build the creature chooser

**Goal**: Let the authorised actor choose a creature line through the approved onboarding flow.

**Description**: Build one reusable responsive chooser component. If selection occurs after account creation, this task owns its screen and route; for creation-time selection, it owns only the component and T024 embeds it in the account form. Show approved previews, accessible names, confirmation, loading, error, and incomplete states, and test the approved chooser and actor, persistence, repeat behaviour, keyboard, touch, reduced motion, missing previews, and narrow screens.

## 81. Calculate creature evolution state

**Goal**: Resolve the current and previously unlocked forms from a child's level.

**Description**: Using `_docs/levelling-policy.md` and the database catalogue loaded from the validated manifest, add a pure service that returns the current form and ordered unlocked history without database writes. Test every mapping boundary, no selection, incomplete catalogue, maximum level, inactive line, and deterministic ordering.

## 82. Expose creature evolution state

**Goal**: Give the authenticated child a stable API representation of their progression.

**Description**: Add a child-scoped DRF endpoint backed by the evolution service that returns the selected line, current form, and unlocked form history with display and asset metadata. Test permissions, household isolation, incomplete onboarding, missing catalogue data, stable ordering, and compact errors.

## 83. Build the creature evolution gallery

**Goal**: Make progression visually rewarding while preserving accessibility and performance.

**Description**: Build the current-creature view and unlocked-history gallery against the evolution API, using CSS for transitions unless a documented gap justifies and obtains DA-10 approval for Motion. Test locked and missing forms, image loading failure, keyboard and touch navigation, reduced motion, accessible alternatives, and narrow screens.

## 84. Create the parent overview API

**Goal**: Give parents one bounded summary of household users, balances, levels, and pending work.

**Description**: Add a parent-only DRF endpoint that composes current household, ledger, level, creature, and pending-submission queries without creating a duplicate reporting data model. Test household isolation, empty and partial data, stable ordering, query count, child denial, and compact errors.

## 85. Build the parent overview dashboard

**Goal**: Present the household summary and direct parents to existing management flows.

**Description**: Build a responsive dashboard against the parent overview API with users, balances, levels, creatures, and pending counts, linking to the existing account, chore, approval, and reward screens. Test loading, empty, partial, error, retry, keyboard, and narrow-screen states without duplicating those management interfaces.

## 86. Expose the audit trail to parents

**Goal**: Let authorised parents review sensitive actions in their own household.

**Description**: Add a read-only parent DRF endpoint over the audit-event schema with native pagination and only the filters required for actor, action, and date. Test immutability, redaction, household isolation, child denial, stable ordering, filter validation, and compact errors.

## 87. Build the audit-history interface

**Goal**: Make household audit events understandable without exposing secrets.

**Description**: Build a parent-only paginated audit view with actor, action, target, time, and safe context from the audit API. Test redaction, empty, loading, filter, error, retry, keyboard, and narrow-screen states without offering edit or delete controls.

## 88. Establish the browser-test harness

**Goal**: Give critical household journeys one isolated and reproducible Playwright foundation.

**Description**: After obtaining and recording DA-11 approval, configure Playwright server lifecycle, browser setup, base URL, isolated test-data creation and cleanup, secret-safe diagnostics, and one non-product smoke test, then add the harness to CI. Keep product journeys out of this task and prove parallel or repeated runs cannot share mutable users, households, databases, or credentials.

## 89. Test child submission and child-device approval

**Goal**: Protect the path from child attestation through a parent's decision on the child's device.

**Description**: Add one Playwright suite covering child login, chore selection, attestation, pending state, parent identification, PIN failure, approval credit, and rejection without credit on the child device using isolated data. Keep diagnostics compact and free of credentials and PIN values, and do not cover the separate parent queue.

## 90. Test parent-queue approval and rejection

**Goal**: Protect approval decisions made from a parent's authenticated device.

**Description**: Add one Playwright suite covering parent login, the pending queue, required PIN re-verification, approval credit, rejection without credit, stale decisions, and empty state using isolated data. Keep diagnostics compact and free of credentials and PIN values, and do not repeat the child-submission setup through the UI.

## 91. Test the reward journey

**Goal**: Protect point spending and any approved parent fulfilment transitions end to end.

**Description**: Add one Playwright suite based on `_docs/reward-policy.md` covering login, available balance, supported conversion, insufficient funds, successful redemption, and every required parent state. Use isolated data and verify exact ledger effects, audit history, retry behaviour, and secret-free diagnostics.

## 92. Test creature onboarding and selection

**Goal**: Protect the approved chooser, actor, and route to an initial creature choice.

**Description**: Add one Playwright suite using `_docs/onboarding-policy.md` and the validated catalogue to exercise the exact account-creation, first-login, or parent-assisted actor and path that was approved. Cover incomplete onboarding, available lines, confirmation, saved choice, repeat-selection rules, keyboard use, reduced motion, missing previews, and secret-free diagnostics without exercising level-up.

## 93. Test levelling and creature evolution

**Goal**: Protect the path from a known balance to a newly visible creature form.

**Description**: Add one Playwright suite using `_docs/levelling-policy.md` and a preselected creature to cover displayed cost, point debit, level change, current form, and unlocked history. Use isolated data and verify insufficient funds, maximum level, reduced motion, and secret-free diagnostics without repeating onboarding.

## 94. Audit current-scope accessibility

**Goal**: Produce a bounded WCAG 2.2 AA findings list for the implemented household journeys.

**Description**: In one working day, audit login, child chores, parent management, approvals, points, rewards, levelling, creature, dashboard, and audit screens with automated checks plus one representative keyboard and screen-reader pass. Do not fix findings in this task; record each reproducible issue as a separate session-sized backlog entry with severity, affected screen, expected behaviour, and verification method.

## 95. Audit current-scope security

**Goal**: Produce a bounded security findings list for the implemented trust boundaries.

**Description**: In one working day, independently inspect sessions and CSRF, role and household isolation, PIN handling, ledger mutations including scheduled interest, idempotency, secrets, logs, dependencies, CI, external-action boundaries, inputs, the audit interface, and browser security headers. Do not fix findings here; record each reproducible issue separately with severity, evidence, trust boundary, and regression-test expectation.

## 96. Verify the current product plan end to end

**Goal**: Produce an evidence-backed go or no-go decision for the current planned scope.

**Description**: Complete the integration-owned `_docs/requirements-evidence.md` matrix by tracing every requirement in `_docs/plan.md` to an implemented screen, API, model or approved policy and a runnable result, without pulling in roadmap features. Record gaps compactly, return no-go while any required evidence is missing, and create separate issues rather than implementing fixes inside this verification task.
