# Chorum-murohc — Implementation Backlog

This backlog covers the current product scope in `_docs/plan.md` and the
selected implementation track in `_docs/design.md`. Long-term product and
technical possibilities remain in `_docs/roadmap.md` until the product owner
promotes them into the current scope.

Each task is intended for one focused engineering session. A task assignee
should need only the task text, the named prerequisite artefacts, and the files
the task touches—not the descriptions of other backlog tasks.

Implementation work follows two additional rules:

- Read the affected flow before changing it, reuse existing or native
  facilities, avoid speculative abstractions and dependencies, and leave the
  smallest runnable test that proves non-trivial behaviour.
- Keep control flow deterministic, persist business state needed for recovery,
  return compact actionable errors, cap retries, and stop for an explicit human
  decision when a named prerequisite policy is absent.

## 1. Set up an empty project with a passing test

**Goal**: Verify and stabilise the existing empty Chorum-murohc project baseline.

**Description**: Treat the current Django 5.2 project, registered `chorum_murohc` app, uv lockfile, and app-registration test as the required empty scaffold; do not recreate them. Run the documented test command, fix only baseline failures, and finish with a clean passing test and no product models or features.

## 2. Record the initial backend boundaries

**Goal**: Define the minimum module boundaries needed to keep the Django backend maintainable.

**Description**: Amend `_docs/design.md` with responsibility and dependency rules for identity and households, chores and approvals, points and rewards, creatures, and auditing. Keep these as boundaries inside one modular monolith, avoid new framework layers, and record any provisional package names explicitly.

## 3. Add the backend quality commands

**Goal**: Make backend formatting, linting, and testing reproducible with one local command.

**Description**: Configure the selected pytest and pytest-django tools plus one formatter and linter, reusing a single tool where it covers both jobs. Document and run the smallest command set that checks the existing scaffold, and do not add coverage gates or plugins without a current requirement.

## 4. Configure runtime-based Django settings

**Goal**: Keep secrets and environment-specific values out of tracked source code.

**Description**: Make Django read its secret key, debug flag, allowed hosts, and database connection from runtime configuration while retaining explicitly documented safe local defaults. Add focused settings tests for parsing and missing production-critical values without introducing a settings framework unless Django and the standard library are insufficient.

## 5. Create the custom user model before database setup

**Goal**: Establish the Chorum-murohc user model before any persistent project database is migrated.

**Description**: Add a minimal custom Django user model that preserves username and password authentication and leaves household roles to membership records. Configure `AUTH_USER_MODEL`, create the app's initial migration, and test ordinary-user and superuser creation without applying migrations to a persistent shared database.

## 6. Model households and memberships

**Goal**: Represent configurable households containing parent and child members.

**Description**: Add household and membership models linked to the custom user model, with parent and child roles and a database constraint preventing duplicate membership. Put these models in an initial migration compatible with the custom-user migration and test both a two-parent/two-child household and a differently sized household.

## 7. Establish PostgreSQL and apply the initial migrations

**Goal**: Make PostgreSQL the implementation database after the custom user and household schema exist.

**Description**: Add the PostgreSQL driver, connect through the runtime settings contract, and apply the initial custom-user and household migrations to an isolated local database. Document setup and prove that migrations and backend tests pass against PostgreSQL rather than SQLite.

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

**Description**: Extend the application shell with a small route map and distinct parent, child, and signed-out navigation states driven by an explicit current-user shape. Test active routes, keyboard use, narrow screens, unknown roles, and signed-out behaviour without implementing authentication itself.

## 16. Connect the frontend and API on one origin

**Goal**: Let React call Django without CORS or token-authentication machinery.

**Description**: Configure Vite's development proxy and the production path so the frontend reaches `/api/v1/` on the Django origin, then use TanStack Query for one typed health request. Test success, loading, a compact server error, and cookie forwarding; do not add JWT, CORS, or a custom API client framework.

## 17. Add baseline continuous integration

**Goal**: Run the current backend and frontend checks on every proposed change.

**Description**: Configure CI to install the locked uv and pnpm dependencies and run only the documented formatting, linting, test, and frontend build commands that currently exist. Use an ephemeral PostgreSQL service, cache dependencies safely, expose no credentials, and document the matching local commands.

## 18. Define and enforce the permission matrix foundation

**Goal**: Record parent and child permissions before role-sensitive endpoints are built.

**Description**: Add a concise permission matrix to `_docs/design.md` for account administration, chore management, submissions, approvals, balances, rewards, levels, creatures, and audit views. Implement only the minimum reusable DRF household-role permission primitive and its own allow, deny, unauthenticated, and cross-household tests; every later endpoint must test its specific matrix row.

## 19. Decide deletion and retention behaviour

**Goal**: Reconcile the product's delete actions with ledger, approval, and audit history.

**Description**: Record in `_docs/retention-policy.md` whether users and chores are hard-deleted, deactivated, anonymised, or protected once referenced, including who may act and what remains visible. Obtain product-owner approval before account or chore mutation endpoints are implemented; if approval is absent, stop rather than invent behaviour.

## 20. Create the household account-administration API

**Goal**: Let parents manage household accounts under the approved retention policy.

**Description**: Using `_docs/retention-policy.md` and the permission matrix, add parent-only endpoints to list, create, edit, assign roles to, and remove or deactivate household users. Test validation, password handling, last-parent protection, household isolation, child denial, the approved retention behaviour, and an audit event for each mutation.

## 21. Build the household account-administration interface

**Goal**: Give parents a modern interface for managing household users and roles.

**Description**: Build parent-only list, create, edit, role-change, and approved removal/deactivation states against the account API contract, using React Hook Form and Zod for the forms. Test loading, empty, validation, destructive confirmation, API failure, keyboard use, and narrow-screen behaviour.

## 22. Implement session authentication endpoints

**Goal**: Support secure browser login, session inspection, and logout through Django.

**Description**: Add CSRF-aware endpoints that use Django's native session authentication and return the minimal current-user and household-role data required by navigation. Test valid and invalid credentials, CSRF enforcement, disabled users, logout, unauthenticated inspection, and compact errors without introducing JWTs.

## 23. Build the login and logout experience

**Goal**: Let household members enter and leave Chorum-murohc accessibly.

**Description**: Build login, current-session loading, invalid-credential, disabled-account, and logout flows against the session API, using the existing form primitives and validation tools. Route parents and children to their role-appropriate start views and test keyboard, narrow-screen, loading, error, and successful-session states.

## 24. Decide parent identity and PIN approval rules

**Goal**: Define how a specific approving adult is identified and attributed on both approval paths.

**Description**: Record in `_docs/approval-authentication.md` whether the child-device flow selects a parent before PIN entry or requires household-unique PINs, plus PIN length, retry, lockout, recovery, and audit attribution rules. Obtain product-owner approval before PIN storage or approval implementation; the decision must cover multiple parents and must not weaken the plan's PIN requirement.

## 25. Store and verify parent PINs securely

**Goal**: Implement the approved PIN contract without storing readable PIN values.

**Description**: Using `_docs/approval-authentication.md`, add the minimum model fields and service needed to set, replace, and verify a parent's PIN with Django's password-hashing facilities. Never return or log the PIN, emit audit events for setup and replacement, and test correct, incorrect, missing, changed, and cross-household cases.

## 26. Build parent PIN management

**Goal**: Let each parent securely create and replace their own approval PIN.

**Description**: Build authenticated PIN setup and replacement API operations and a parent settings screen following `_docs/approval-authentication.md`. Require current credentials or the approved recovery check, show no stored PIN value, and test validation, success, failure, CSRF, audit emission, and accessible form behaviour.

## 27. Enforce PIN attempt limits

**Goal**: Apply the approved lockout rules to PIN verification without obscuring the approving parent.

**Description**: Implement the retry and lockout policy from `_docs/approval-authentication.md` using the smallest state needed and Django's existing cache or database facilities. Test the exact threshold, reset conditions, concurrent failures, successful recovery, compact client errors, audit-safe logging, and no leakage of whether another parent's PIN matched.

## 28. Model the reusable chore pool

**Goal**: Store household chores and their parent-controlled point values.

**Description**: Using `_docs/retention-policy.md`, add a household-owned chore with name, positive integer point value, active or deletion state, and audit timestamps, but no scheduling or claiming fields. Test database constraints, household isolation, duplicate-name policy, point validation, and the approved retention behaviour once referenced.

## 29. Create the chore-pool API

**Goal**: Let children view active chores and parents manage household chore definitions.

**Description**: Add household-scoped DRF endpoints for listing active chores and parent-only creation, editing, and approved removal or deactivation, relying on native DRF serializers and the permission matrix. Test ordering, validation, household isolation, parent and child access, retention rules, and an audit event for each mutation.

## 30. Build the child chore browser

**Goal**: Present available chores as an engaging mobile-first selection screen.

**Description**: Build responsive chore cards showing only the name and point value returned by the child-visible chore endpoint. Test loading, empty, compact error, retry, touch, keyboard, and narrow-screen states without adding parent editing or submission behaviour.

## 31. Build parent chore management

**Goal**: Let parents create, edit, and remove or deactivate chores through the modern interface.

**Description**: Build parent-only list and form states against the chore-management API and the approved retention policy, reusing existing cards, dialogs, and form controls. Test validation, destructive confirmation, API failure, permissions, keyboard use, and narrow-screen behaviour without duplicating Django admin.

## 32. Create the immutable points ledger

**Goal**: Make every balance change traceable and resistant to accidental rewriting.

**Description**: Add append-only ledger entries with household, user, signed integer amount, reason, source reference, timestamp, and idempotency key, using database constraints instead of a generic ledger framework. Test credits, debits, duplicate rejection, deterministic ordering, household isolation, and prohibition of update or deletion through application services.

## 33. Expose balances and ledger history

**Goal**: Provide balances derived from the ledger as the single source of truth.

**Description**: Add a household-scoped balance service and DRF endpoints for the authorised user's balance and paginated ledger history using DRF's native pagination. Test positive, negative and zero totals, permissions, household isolation, reason labels, ordering, and compact pagination errors.

## 34. Define child completion attestation

**Goal**: State what a child asserts when submitting a chore without photo proof.

**Description**: Record in `_docs/completion-attestation.md` that the current-scope submission is an explicit child assertion that the work is complete and that the server cannot independently prove physical completion. Specify confirmation wording, duplicate policy, and parent rejection behaviour, and obtain product-owner approval before the submission endpoint is built.

## 35. Model chore completion submissions

**Goal**: Persist a child's completion assertion and its review state.

**Description**: Using `_docs/completion-attestation.md`, add a submission linked to household, child, and chore with pending, approved, and rejected states and decision attribution. Enforce valid transitions and test duplicate policy, immutable chore name and point snapshots, household isolation, timestamps, and state constraints.

## 36. Implement the chore-submission API

**Goal**: Let a child attest that an active chore has been completed and request review.

**Description**: Add a child-only DRF endpoint that creates a pending submission exactly as specified in `_docs/completion-attestation.md` and emits an audit event. Test confirmation input, inactive or foreign chores, duplicate policy, child ownership, forbidden parent submission, idempotent retry, and compact validation errors.

## 37. Build the child submission interaction

**Goal**: Let children confirm and submit completed work without accidental repeats.

**Description**: Extend the child chore browser with the approved attestation wording, a confirmation dialog, and success and pending-review states against the submission API. Test cancellation, double activation, loading, retry, validation failure, keyboard and touch operation, and narrow screens.

## 38. Create the pending-approvals API

**Goal**: Give parents a bounded household queue of submissions awaiting decision.

**Description**: Add a parent-only endpoint returning pending submissions with child, chore snapshot, point value, and submission time using native DRF pagination. Test permission denial, household isolation, stable ordering, empty results, page boundaries, and no leakage of other household data.

## 39. Implement atomic approval and rejection

**Goal**: Decide each pending submission once and credit points only on approval.

**Description**: Using `_docs/approval-authentication.md`, lock the pending submission, identify and verify the approving parent, append one idempotent ledger credit on approval, record rejection without credit, and emit an audit event in one database transaction. Test both device paths at the service boundary, concurrent decisions, retry, invalid or locked PIN, stale state, rollback, actor attribution, and unchanged balance after rejection.

## 40. Expose approval and rejection through the API

**Goal**: Provide one mutation endpoint for both parent approval contexts.

**Description**: Add one DRF endpoint that accepts approve or reject, delegates all state and ledger work to the atomic approval service, and follows `_docs/approval-authentication.md` for parent identity and PIN input. Test child-device and parent-device requests, CSRF, roles, household isolation, invalid and locked PINs, stale decisions, idempotent retry, compact errors, and exact response state.

## 41. Build child-device parent approval

**Goal**: Let a parent decide a just-submitted chore safely on the child's device.

**Description**: Build only the child-device decision dialog specified by `_docs/approval-authentication.md`, including parent identification, protected PIN entry, approve, reject, success, lockout, and retry states against the approval API. Test that the child cannot bypass PIN verification, the approving adult is attributed, secrets are cleared, and keyboard, touch, and narrow-screen interactions work.

## 42. Build the parent's approval queue

**Goal**: Let a parent review and decide pending submissions from their own authenticated device.

**Description**: Build the paginated queue and parent-device decision flow against the pending and approval APIs, following `_docs/approval-authentication.md` for any required PIN re-verification. Test empty, loading, stale, concurrent-decision, approve, reject, lockout, compact error, keyboard, and narrow-screen states.

## 43. Build the points dashboard

**Goal**: Show users a trustworthy balance and understandable transaction history.

**Description**: Build role-appropriate balance cards and paginated ledger history against the balance API, with clear labels for chore credits and later transaction reasons. Test positive, negative and zero balances, empty history, loading, retry, permissions, pagination, keyboard use, and narrow screens.

## 44. Finalise the interest policy

**Goal**: Turn the proposed monthly rate, daily accrual, and level bonus into exact arithmetic rules.

**Description**: Record in `_docs/interest-policy.md` whether accrual compounds daily, how monthly rates convert to daily rates, how the 20% base and 30% per-level bonus combine, which balance and time zone apply, and how rounding and missed days work. Include approved worked examples for level 0 and level 10 and obtain product-owner approval before calculator implementation.

## 45. Implement the interest calculator

**Goal**: Calculate one day's interest deterministically from the approved policy.

**Description**: Implement `_docs/interest-policy.md` as a pure integer or decimal function with no database access or floating-point arithmetic. Test every worked example plus zero and negative balances, level boundaries, dates, rounding, and any cap or maximum defined by the policy.

## 46. Persist one day's interest idempotently

**Goal**: Append at most one correct interest ledger entry per user and accrual date.

**Description**: Add a transactional service that reads the eligible ledger balance, calls the approved calculator, and writes a uniquely keyed interest entry for a supplied date. Test repeat calls, concurrent calls, zero interest, multiple households, partial failure rollback, time-zone boundaries, and audit attribution.

## 47. Expose daily interest as a management command

**Goal**: Provide one deterministic operational entry point for due interest accrual.

**Description**: Add a Django management command that accepts an explicit accrual date, invokes the idempotent accrual service for eligible users, and reports compact counts and failures without sensitive data. Test dry run, one household, all households, invalid date, partial failure, repeat execution, and a non-zero exit for unrecovered errors.

## 48. Schedule daily interest with the native scheduler

**Goal**: Make daily accrual actually run in the current local deployment model.

**Description**: Document and provide the smallest cron-based invocation for the interest management command at the household policy's defined time zone, including locking and log location. Verify one scheduled run in a controlled environment and document disable, manual retry, and missed-run recovery without adding Redis or Celery.

## 49. Decide reward redemption and fulfilment

**Goal**: Define how point spending becomes game time or pocket money in the household.

**Description**: Record in `_docs/reward-policy.md` whether redemption debits immediately or after parent approval, how parents fulfil or cancel off-app rewards, and how quantities, reversals, and audit history work for one minute per point and £5 per 200 points. Obtain product-owner approval before reward services or screens are built.

## 50. Implement reward redemption transactions

**Goal**: Apply the approved reward policy without overspending or losing audit history.

**Description**: Using `_docs/reward-policy.md`, add the minimum records and atomic service needed to request or redeem game time and pocket money and append the corresponding ledger debit at the approved transition. Test exact conversion, insufficient funds, concurrent requests, idempotent retry, cancellation or reversal policy, permissions, household isolation, and audit events.

## 51. Create the reward API

**Goal**: Expose the child reward initiation and status operations authorised by the approved policy.

**Description**: Add child-scoped DRF endpoints to initiate a reward and read its status under `_docs/reward-policy.md`, reusing the reward service rather than duplicating balance logic. Test child permissions, parent denial on these child operations, validation, household isolation, insufficient funds, idempotency, status visibility, and compact errors; leave fulfil, reject, cancel, and reverse mutations to the separate parent API task.

## 52. Build the child rewards screen

**Goal**: Let children understand costs and initiate the approved spending flow safely.

**Description**: Build game-time and pocket-money options with current balance, exact conversion, confirmation, success, pending or fulfilled state as defined by `_docs/reward-policy.md`, and insufficient-funds feedback. Test repeat prevention, loading, error, keyboard, touch, and narrow-screen behaviour against the reward API.

## 53. Create parent reward fulfilment operations

**Goal**: Expose only the parent reward transitions required by the approved policy.

**Description**: Add the parent DRF operations explicitly required by `_docs/reward-policy.md`; if the approved policy requires no parent transition, close this task as not applicable without adding code. Test every allowed transition, stale and duplicate actions, exact ledger effect, audit emission, permissions, household isolation, idempotency, and compact errors.

## 54. Build parent reward fulfilment

**Goal**: Let parents perform the approved reward transitions through an accessible interface.

**Description**: Build only the parent controls and states exposed by the parent reward API; if `_docs/reward-policy.md` requires no parent transition, close this task as not applicable without adding code. Test loading, empty, fulfil, reject, cancel or reverse states as applicable, stale responses, duplicate activation, keyboard use, and narrow screens.

## 55. Finalise the levelling policy

**Goal**: Define every level cost and its relationship to creature forms.

**Description**: Record in `_docs/levelling-policy.md` the exact escalation formula beginning at 500 then 510 points, rounding, maximum level within the planned 30–40 range, insufficient-funds behaviour, and mapping from levels to the approximately 35 ordered form indices. Do not assume one form per level; include a complete cost and mapping table and obtain product-owner approval before implementation.

## 56. Implement the level-up transaction

**Goal**: Spend points and advance one level atomically under the approved policy.

**Description**: Using `_docs/levelling-policy.md`, add an atomic service that checks the current ledger balance and maximum level, appends one idempotent debit, increments the level, and emits an audit event. Test the first and final levels, insufficient funds, concurrent requests, repeat calls, rollback, exact cost, and household ownership.

## 57. Create the level-up API

**Goal**: Expose the current level, next cost, eligibility, and level-up action to the child.

**Description**: Add child-scoped DRF read and mutation endpoints backed only by the approved level service and `_docs/levelling-policy.md`. Test permissions, current and maximum levels, insufficient balance, stale requests, idempotency, exact response values, and compact errors.

## 58. Build the level-up interface

**Goal**: Make the cost and consequence of levelling clear before points are spent.

**Description**: Build current-level, next-cost, affordability, confirmation, success, maximum-level, and error states against the level API without implementing creature animation. Test repeat prevention, balance refresh, keyboard, touch, reduced motion, loading, and narrow screens.

## 59. Obtain approval for the creature catalogue

**Goal**: Prevent unapproved third-party characters or assets from entering the product.

**Description**: Record in `_docs/creature-catalogue-policy.md` the product owner's approved creature lines, required licences or original replacements, permitted asset sources, and evidence to retain for every image. Treat legal review as external input, not an engineering conclusion, and block asset production until each line has an explicit approval state.

## 60. Decide when admin-created children choose a creature

**Goal**: Reconcile admin-created accounts with the plan's requirement that children choose at signup.

**Description**: Record in `_docs/onboarding-policy.md` whether selection occurs during account creation, first login, or a parent-assisted onboarding step, and whether an initial choice can be changed in current scope. Obtain product-owner approval and define the incomplete-onboarding user experience before selection endpoints or screens are built.

## 61. Specify creature assets and provenance

**Goal**: Define a consistent, auditable format for approximately 35 ordered form indices per approved creature line.

**Description**: Extend `_docs/creature-catalogue-policy.md` with dimensions, format, naming, form-index order, accessibility text, storage path, visual progression criteria, licence or generation provenance, and acceptance checks. Use one simple manifest format and existing image tools where possible; keep level-to-form mapping in `_docs/levelling-policy.md` and do not build an asset pipeline without a demonstrated repetitive need.

## 62. Model creature lines and forms

**Goal**: Store the approved creature catalogue and its ordered level-linked forms.

**Description**: Using the approved catalogue and asset specification, add shared creature-line and form records with stable identifiers, form index, display metadata, asset reference, provenance reference, and active state. Test ordering, duplicate form indices, missing required metadata, activation, and the rule that catalogue records are not household-owned.

## 63. Produce images for creature lineage 1

**Goal**: Add the complete approved image evolution for creature lineage 1.

**Description**: Using the approved lineage 1 entry and asset rules in `_docs/creature-catalogue-policy.md`, establish its visual reference and generate or import approximately 35 ordered form-index images with accessible descriptions and source, licence, or generation provenance recorded in the manifest. Verify format, dimensions, identifiers, catalogue references, and gradual visual continuity across the complete lineage; stop if lineage 1 is not approved.

## 64. Produce images for creature lineage 2

**Goal**: Add the complete approved image evolution for creature lineage 2.

**Description**: Using the approved lineage 2 entry and asset rules in `_docs/creature-catalogue-policy.md`, establish its visual reference and generate or import approximately 35 ordered form-index images with accessible descriptions and source, licence, or generation provenance recorded in the manifest. Verify format, dimensions, identifiers, catalogue references, and gradual visual continuity across the complete lineage; stop if lineage 2 is not approved.

## 65. Produce images for creature lineage 3

**Goal**: Add the complete approved image evolution for creature lineage 3.

**Description**: Using the approved lineage 3 entry and asset rules in `_docs/creature-catalogue-policy.md`, establish its visual reference and generate or import approximately 35 ordered form-index images with accessible descriptions and source, licence, or generation provenance recorded in the manifest. Verify format, dimensions, identifiers, catalogue references, and gradual visual continuity across the complete lineage; stop if lineage 3 is not approved.

## 66. Produce images for creature lineage 4

**Goal**: Add the complete approved image evolution for creature lineage 4.

**Description**: Using the approved lineage 4 entry and asset rules in `_docs/creature-catalogue-policy.md`, establish its visual reference and generate or import approximately 35 ordered form-index images with accessible descriptions and source, licence, or generation provenance recorded in the manifest. Verify format, dimensions, identifiers, catalogue references, and gradual visual continuity across the complete lineage; stop if lineage 4 is not approved.

## 67. Produce images for creature lineage 5

**Goal**: Add the complete approved image evolution for creature lineage 5.

**Description**: Using the approved lineage 5 entry and asset rules in `_docs/creature-catalogue-policy.md`, establish its visual reference and generate or import approximately 35 ordered form-index images with accessible descriptions and source, licence, or generation provenance recorded in the manifest. Verify format, dimensions, identifiers, catalogue references, and gradual visual continuity across the complete lineage; stop if lineage 5 is not approved.

## 68. Produce images for creature lineage 6

**Goal**: Add the complete approved image evolution for creature lineage 6.

**Description**: Using the approved lineage 6 entry and asset rules in `_docs/creature-catalogue-policy.md`, establish its visual reference and generate or import approximately 35 ordered form-index images with accessible descriptions and source, licence, or generation provenance recorded in the manifest. Verify format, dimensions, identifiers, catalogue references, and gradual visual continuity across the complete lineage; stop if lineage 6 is not approved.

## 69. Produce images for creature lineage 7

**Goal**: Add the complete approved image evolution for creature lineage 7.

**Description**: Using the approved lineage 7 entry and asset rules in `_docs/creature-catalogue-policy.md`, establish its visual reference and generate or import approximately 35 ordered form-index images with accessible descriptions and source, licence, or generation provenance recorded in the manifest. Verify format, dimensions, identifiers, catalogue references, and gradual visual continuity across the complete lineage; stop if lineage 7 is not approved.

## 70. Validate the complete creature catalogue

**Goal**: Prove that every approved form index and level mapping is complete and usable.

**Description**: Add the smallest automated check that reads the agreed manifest and `_docs/levelling-policy.md`, then confirms expected line and form-index counts, unique identifiers, files, metadata, provenance, licence state, and a valid form mapping for every permitted level. Run it against the complete catalogue and report missing, extra, or unmapped items compactly without creating a general asset framework.

## 71. Load the validated creature catalogue

**Goal**: Populate the creature-line and form records from the validated manifest reproducibly.

**Description**: Add one idempotent Django management command that refuses an invalid manifest, then creates or updates creature lines and ordered form-index records and applies the active or deactivation policy in `_docs/creature-catalogue-policy.md`. Test initial load, changed metadata, repeated load, invalid input, missing manifest entries, and deactivation without deleting referenced history.

## 72. Implement initial creature selection

**Goal**: Save one approved creature line for a child at the authorised onboarding point.

**Description**: Using `_docs/onboarding-policy.md` and the database catalogue loaded from the validated manifest, add a child-scoped selection service and DRF endpoints that list active lines and save the initial choice under the approved repeat-selection rule. Test incomplete onboarding, unavailable lines, another child, household isolation, repeat attempts, permissions, and audit emission.

## 73. Build the creature chooser

**Goal**: Let a child choose an approved creature line through the defined onboarding flow.

**Description**: Build a responsive visual chooser against the selection API, showing approved previews, accessible names, confirmation, loading, error, and incomplete-onboarding states from `_docs/onboarding-policy.md`. Test selection persistence, repeat behaviour, keyboard, touch, reduced motion, missing previews, and narrow screens.

## 74. Calculate creature evolution state

**Goal**: Resolve the current and previously unlocked forms from a child's level.

**Description**: Using `_docs/levelling-policy.md` and the database catalogue loaded from the validated manifest, add a pure service that returns the current form and ordered unlocked history without database writes. Test every mapping boundary, no selection, incomplete catalogue, maximum level, inactive line, and deterministic ordering.

## 75. Expose creature evolution state

**Goal**: Give the authenticated child a stable API representation of their progression.

**Description**: Add a child-scoped DRF endpoint backed by the evolution service that returns the selected line, current form, and unlocked form history with display and asset metadata. Test permissions, household isolation, incomplete onboarding, missing catalogue data, stable ordering, and compact errors.

## 76. Build the creature evolution gallery

**Goal**: Make progression visually rewarding while preserving accessibility and performance.

**Description**: Build the current-creature view and unlocked-history gallery against the evolution API, adding Motion only for point and form transitions that cannot be expressed adequately with CSS. Test locked and missing forms, image loading failure, keyboard and touch navigation, reduced motion, accessible alternatives, and narrow screens.

## 77. Create the parent overview API

**Goal**: Give parents one bounded summary of household users, balances, levels, and pending work.

**Description**: Add a parent-only DRF endpoint that composes current household, ledger, level, creature, and pending-submission queries without creating a duplicate reporting data model. Test household isolation, empty and partial data, stable ordering, query count, child denial, and compact errors.

## 78. Build the parent overview dashboard

**Goal**: Present the household summary and direct parents to existing management flows.

**Description**: Build a responsive dashboard against the parent overview API with users, balances, levels, creatures, and pending counts, linking to the existing account, chore, approval, and reward screens. Test loading, empty, partial, error, retry, keyboard, and narrow-screen states without duplicating those management interfaces.

## 79. Expose the audit trail to parents

**Goal**: Let authorised parents review sensitive actions in their own household.

**Description**: Add a read-only parent DRF endpoint over the audit-event schema with native pagination and only the filters required for actor, action, and date. Test immutability, redaction, household isolation, child denial, stable ordering, filter validation, and compact errors.

## 80. Build the audit-history interface

**Goal**: Make household audit events understandable without exposing secrets.

**Description**: Build a parent-only paginated audit view with actor, action, target, time, and safe context from the audit API. Test redaction, empty, loading, filter, error, retry, keyboard, and narrow-screen states without offering edit or delete controls.

## 81. Test child submission and child-device approval

**Goal**: Protect the path from child attestation through a parent's decision on the child's device.

**Description**: Add one Playwright suite covering child login, chore selection, attestation, pending state, parent identification, PIN failure, approval credit, and rejection without credit on the child device using isolated data. Keep diagnostics compact and free of credentials and PIN values, and do not cover the separate parent queue.

## 82. Test parent-queue approval and rejection

**Goal**: Protect approval decisions made from a parent's authenticated device.

**Description**: Add one Playwright suite covering parent login, the pending queue, required PIN re-verification, approval credit, rejection without credit, stale decisions, and empty state using isolated data. Keep diagnostics compact and free of credentials and PIN values, and do not repeat the child-submission setup through the UI.

## 83. Test the reward journey

**Goal**: Protect point spending and any approved parent fulfilment transitions end to end.

**Description**: Add one Playwright suite based on `_docs/reward-policy.md` covering login, available balance, supported conversion, insufficient funds, successful redemption, and every required parent state. Use isolated data and verify exact ledger effects, audit history, retry behaviour, and secret-free diagnostics.

## 84. Test creature onboarding and selection

**Goal**: Protect the child's approved route to an initial creature choice.

**Description**: Add one Playwright suite using `_docs/onboarding-policy.md` and the validated catalogue to cover incomplete onboarding, available lines, selection confirmation, saved choice, and the approved repeat-selection rule. Use isolated data and verify keyboard use, reduced motion, missing previews, and secret-free diagnostics without exercising level-up.

## 85. Test levelling and creature evolution

**Goal**: Protect the path from a known balance to a newly visible creature form.

**Description**: Add one Playwright suite using `_docs/levelling-policy.md` and a preselected creature to cover displayed cost, point debit, level change, current form, and unlocked history. Use isolated data and verify insufficient funds, maximum level, reduced motion, and secret-free diagnostics without repeating onboarding.

## 86. Audit current-scope accessibility

**Goal**: Produce a bounded WCAG 2.2 AA findings list for the implemented household journeys.

**Description**: In one time-boxed review, audit login, child chores, parent management, approvals, points, rewards, levelling, creature, dashboard, and audit screens with automated checks plus one representative keyboard and screen-reader pass. Do not fix findings in this task; record each reproducible issue as a separate session-sized backlog entry with severity, affected screen, expected behaviour, and verification method.

## 87. Audit current-scope security

**Goal**: Produce a bounded security findings list for the implemented trust boundaries.

**Description**: In one time-boxed review, inspect sessions and CSRF, role and household isolation, PIN handling, ledger mutations, idempotency, secrets, logs, dependencies, inputs, and browser security headers against the implemented flows. Do not fix findings in this task; record each reproducible issue as a separate session-sized backlog entry with severity, evidence, trust boundary, and regression-test expectation.

## 88. Verify the current product plan end to end

**Goal**: Produce an evidence-backed go or no-go decision for the current planned scope.

**Description**: Trace every requirement in `_docs/plan.md` to an implemented screen, API, model or approved policy and to a runnable verification result, without pulling in `_docs/roadmap.md` features. Record gaps and failures compactly, return no-go while any required evidence is missing, and avoid implementing unrelated fixes inside the verification task.
