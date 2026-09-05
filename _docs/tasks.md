# Chorum-murohc — Backlog

Each task is intended to fit within one focused implementation session. The
description supplies enough context and a completion condition for someone who
has not read the other tasks.

- Tasks 1–49 cover the current product scope and selected design.
- Tasks 50–56 translate the product-owner feature roadmap.
- Tasks 57–66 translate the coding-assistant technical evolution suggestions.

## 1. Set up an empty project with a passing test
Goal: Establish the smallest working Chorum-murohc project baseline.
Description: Create an empty Django 5.2 project with the `chorum_murohc` app registered and dependencies managed by uv. Add one meaningful smoke test and confirm the documented test command passes; if the scaffold already exists, verify it rather than recreating it.

## 2. Record the initial module boundaries
Goal: Define how the Django backend will remain modular as features are added.
Description: Add an architecture decision describing the proposed responsibility boundaries for identity, households, chores, approvals, points, rewards, creatures, and auditing. State the permitted dependency direction between these areas and identify which names remain provisional.

## 3. Add the backend quality toolchain
Goal: Make backend formatting, linting, testing, and coverage repeatable.
Description: Configure pytest, pytest-django, a Python formatter, a linter, and a coverage command for the Django backend. Add one documented command that runs all backend quality checks and ensure it passes on the empty project.

## 4. Configure environment-based Django settings
Goal: Separate local, test, and future production configuration safely.
Description: Make Django settings read database, secret, debug, and host configuration from the runtime environment without committing credentials. Preserve convenient local defaults where safe and add tests or checks for missing production-critical values.

## 5. Establish PostgreSQL as the implementation database
Goal: Run the Django backend against the selected PostgreSQL database.
Description: Add the PostgreSQL driver and configure Django to connect using environment-provided values. Document local database creation and prove that Django migrations and the backend test suite run against PostgreSQL.

## 6. Create the versioned API baseline
Goal: Establish a stable Django REST Framework entry point.
Description: Add Django REST Framework and expose a versioned `/api/v1/` namespace with a small health or metadata response. Test the response status and shape without adding product behaviour.

## 7. Define API response and error conventions
Goal: Give all frontend-facing endpoints a consistent contract.
Description: Document and implement standard response, validation-error, authentication-error, pagination, and date-time conventions for the API. Add focused tests demonstrating the conventions through representative endpoints.

## 8. Scaffold the React frontend with a passing test
Goal: Establish the smallest working React and TypeScript frontend.
Description: Create a Vite React application managed by pnpm in a dedicated frontend directory. Render a minimal Chorum-murohc screen and add one Vitest and Testing Library test that passes through a documented command.

## 9. Establish the visual design system
Goal: Create a consistent foundation for a modern, mobile-first interface.
Description: Configure Tailwind CSS and shadcn/ui, then define initial colour, typography, spacing, radius, elevation, and motion tokens. Build a small component showcase covering buttons, cards, inputs, status badges, dialogs, and loading states with accessible defaults.

## 10. Build the responsive application shell
Goal: Provide the shared layout and navigation used by product screens.
Description: Create a mobile-first shell with a header, navigation, content region, and distinct parent and child navigation states. Test keyboard navigation, responsive breakpoints, active-route feedback, and empty loading content.

## 11. Connect the frontend and backend on one origin
Goal: Let React call the Django API without unnecessary cross-origin complexity.
Description: Configure local development and the production build so frontend requests use the same origin as Django or a transparent development proxy. Demonstrate one typed request to the versioned API and verify CSRF-compatible cookie handling.

## 12. Add continuous integration for the empty applications
Goal: Detect backend and frontend regressions on every proposed change.
Description: Configure CI to install locked Python and frontend dependencies and run formatting, linting, backend tests, frontend tests, and build checks. Keep secrets out of CI configuration and document how to reproduce every check locally.

## 13. Create the custom user model
Goal: Establish a user model suitable for Chorum-murohc before business migrations grow.
Description: Add a custom Django user model that retains secure username and password authentication while allowing future product-specific fields. Configure it as the project user model, create its initial migration, and test user and superuser creation.

## 14. Model households and memberships
Goal: Represent configurable households containing adults and children.
Description: Add household and membership records with explicit parent and child roles and constraints that prevent duplicate membership. Test creation of the default two-adult, two-child arrangement as well as a differently sized household.

## 15. Enforce the parent and child permission matrix
Goal: Prevent children from performing parent-only operations.
Description: Define reusable backend permission rules for user administration, chore management, approvals, balance visibility, and child actions. Add tests that cover both allowed and forbidden behaviour for every role-sensitive operation.

## 16. Add household user administration
Goal: Let authorised parents create, edit, deactivate, and assign roles to household users.
Description: Expose parent-only operations for managing household accounts without allowing access across households. Test role changes, password setup, deactivation, validation errors, and unauthorised requests.

## 17. Implement session authentication endpoints
Goal: Support secure browser login and logout through Django sessions.
Description: Add CSRF-aware endpoints for session creation, session inspection, and logout without introducing JWTs. Test valid and invalid credentials, session expiry behaviour, CSRF enforcement, and disabled accounts.

## 18. Build the login and logout experience
Goal: Give household members a polished and accessible way to enter and leave the application.
Description: Create responsive login, validation, error, loading, and logout states against the session API. Route authenticated parents and children to their appropriate starting views and test the main interactions.

## 19. Store parent approval PINs securely
Goal: Allow parents to configure a PIN without storing it in readable form.
Description: Add parent PIN setup and replacement using an appropriate password-hashing mechanism and a minimum length of four digits. Ensure PIN values never appear in API responses, logs, admin listings, or database fields as plaintext.

## 20. Add rate-limited PIN verification
Goal: Verify parent approvals while resisting repeated PIN guessing.
Description: Create a narrowly scoped PIN-verification service with failed-attempt throttling and clear success, failure, and lockout results. Test correct PINs, incorrect PINs, lockout thresholds, recovery timing, and audit-safe logging.

## 21. Model the reusable chore pool
Goal: Store household chores and their parent-controlled point values.
Description: Add a chore definition with household ownership, name, fixed positive point value, active state, and audit timestamps. Do not add schedules or claiming behaviour, and test household isolation and validation constraints.

## 22. Add chore administration to Django admin
Goal: Give trusted administrators a basic operational interface for chore definitions.
Description: Register chore records with useful lists, filters, search, ordering, and safe edit fields in Django admin. Test that the registration loads correctly and does not expose records to unauthorised admin users.

## 23. Create the chore-pool API
Goal: Let children view chores while parents manage them.
Description: Add household-scoped endpoints for listing active chores and parent-only creation, editing, activation, and deactivation. Test role permissions, household isolation, ordering, duplicate names, and point-value validation.

## 24. Build the chore-pool interface
Goal: Present available chores as an engaging, mobile-first selection experience.
Description: Create responsive chore cards showing names and point values, with suitable loading, empty, error, parent-management, and child-selection states. Connect the screen to the chore API and test its primary interactions and role differences.

## 25. Create the immutable points ledger
Goal: Make every balance change traceable and resistant to accidental rewriting.
Description: Add append-only ledger entries with household, user, amount, reason, source reference, timestamp, and idempotency information. Add constraints and tests for credits, debits, duplicate prevention, and prohibition of direct mutation.

## 26. Expose balances and ledger history
Goal: Provide trustworthy balance information derived from ledger entries.
Description: Create household-scoped services and API endpoints that calculate current balances and return paginated transaction history. Test credits, debits, zero balances, household isolation, permissions, and deterministic ordering.

## 27. Model chore completion submissions
Goal: Record a child's claim that a selected chore has been completed.
Description: Add a submission linked to a child and chore with pending, approved, and rejected states plus relevant timestamps. Enforce valid state transitions and prevent a child from creating a submission on behalf of another user or household.

## 28. Implement chore submission
Goal: Allow a child to submit a completed chore for parent review.
Description: Add a child-only service and API endpoint that creates a pending submission from an active chore. Test invalid chores, cross-household access, duplicate requests, forbidden roles, and the rule that only completed work may be submitted.

## 29. Build the child completion flow
Goal: Let children select, confirm, and submit completed work confidently.
Description: Add a confirmation step to the chore interface and show clear success, validation, retry, and pending-review states. Prevent accidental double submission and test keyboard, touch, loading, and error interactions.

## 30. Create the pending-approvals API
Goal: Give parents a household-scoped queue of submissions requiring a decision.
Description: Add a parent-only endpoint that returns pending submissions with the child, chore, point value, and submission time. Test permissions, household isolation, pagination or bounded results, and stable ordering.

## 31. Implement atomic approval and rejection
Goal: Decide a submission exactly once and credit points only on approval.
Description: Add an atomic service that verifies the parent PIN, locks the pending submission, records the decision, and appends one ledger credit when approved. Test concurrent attempts, retries, rejection, invalid PINs, idempotency, and rollback on failure.

## 32. Build the parent approval experience
Goal: Let a parent approve or reject work from either the child's device or their own.
Description: Create a responsive pending queue and decision dialog with protected PIN entry, confirmation, loading, success, and failure states. Support both approval contexts through the same backend workflow and test the primary interactions.

## 33. Build the points dashboard
Goal: Show users their current points and understandable transaction history.
Description: Create role-appropriate balance cards and a paginated ledger view with clear reason labels for earning, spending, levelling, and interest. Test empty, loading, error, positive, negative, and restricted household views.

## 34. Finalise the interest policy
Goal: Turn the proposed interest rules into an unambiguous, testable specification.
Description: Decide whether daily accrual compounds, how monthly rates convert to daily rates, how level bonuses apply, how rounding works, and which balances and dates qualify. Record worked examples including level 0 and level 10, but do not implement the calculator in this task.

## 35. Implement the interest calculator
Goal: Calculate one user's interest deterministically from the approved policy.
Description: Implement the documented formula as a pure decimal or integer calculation with no database writes. Add boundary tests for dates, levels, zero and negative balances, rounding, and the worked policy examples.

## 36. Add idempotent daily interest accrual
Goal: Credit each eligible user once for each accrual date.
Description: Create a Django management command that calculates daily interest and appends uniquely keyed ledger entries inside transactions. Test repeated runs, partial failure and retry, multiple households, time-zone boundaries, and a dry-run mode.

## 37. Implement reward redemption
Goal: Spend points on game time or pocket money without allowing negative balances.
Description: Add an atomic redemption service for one minute of game time per point and £5 per 200 points, recording each debit in the ledger. Test insufficient funds, invalid quantities, concurrent spending, idempotency, permissions, and exact balance changes.

## 38. Build the rewards interface
Goal: Give children a clear and safe way to request supported rewards.
Description: Create game-time and pocket-money options with costs, available balance, confirmation, success, and insufficient-funds states. Connect the interface to redemption and test accidental repeat prevention and responsive interactions.

## 39. Implement the levelling policy and transaction
Goal: Let a child spend points to gain a level using a deterministic escalating cost.
Description: Specify the complete level-cost formula and maximum level, then implement one atomic level-up operation that debits the ledger and increments the level. Test the first levels, maximum level, insufficient balance, concurrent requests, idempotency, and rollback.

## 40. Resolve creature intellectual-property policy
Goal: Decide which creature names and images may safely ship with the product.
Description: Review the proposed Warhammer, Pikachu, Lego, and Playmobil lines and record whether licences, replacements, or original alternatives are required. Produce an approved catalogue policy and asset provenance requirements without generating images.

## 41. Model the approved creature catalogue
Goal: Represent creature lines and their ordered evolution forms.
Description: Add catalogue records for approved creature lines and level-linked forms with stable identifiers, display metadata, and asset references. Test ordering, missing forms, duplicate levels, activation, and the rule that catalogue data is shared safely across households.

## 42. Implement initial creature selection
Goal: Let each child choose one available creature line during onboarding.
Description: Add a child-scoped selection operation and a visual chooser showing approved creature previews and selection confirmation. Test unavailable lines, repeat selection rules, cross-user access, responsive interaction, and the saved selection.

## 43. Calculate and expose creature evolution state
Goal: Resolve the correct creature form from a child's current level.
Description: Add a deterministic service and API response that returns the current form and previously unlocked forms for the selected line. Test level boundaries, incomplete catalogues, maximum level, no selection, permissions, and stable ordering.

## 44. Build the creature evolution gallery
Goal: Make progression visually rewarding and let children revisit earlier forms.
Description: Create an animated current-creature view and an accessible gallery of unlocked historical forms using Motion with reduced-motion support. Test locked forms, missing images, loading, touch and keyboard navigation, and multiple screen sizes.

## 45. Build the parent overview dashboard
Goal: Give parents one view of household users, balances, levels, and pending work.
Description: Add a parent-only summary API and responsive dashboard using existing household, approval, ledger, and creature data. Test household isolation, empty states, partial data, loading, failures, and links to the corresponding management views.

## 46. Add the administrative audit trail
Goal: Make sensitive household actions attributable and reviewable.
Description: Record actor, action, target, time, and safe contextual metadata for user management, chore changes, approvals, PIN changes, spending, and levelling. Provide a parent-appropriate read view and test immutability, redaction, permissions, and household isolation.

## 47. Cover the core journey with browser tests
Goal: Protect the complete child-to-parent reward workflow.
Description: Add Playwright tests for login, chore selection, submission, parent approval, point credit, spending, levelling, and creature progression using isolated test data. Make failures reproducible locally and capture useful diagnostics without exposing secrets.

## 48. Complete an accessibility review
Goal: Ensure the core interface works for keyboard, screen-reader, low-vision, and reduced-motion users.
Description: Audit the login, chore, approval, points, rewards, and creature screens against WCAG 2.2 AA expectations. Fix or record every finding and add automated checks for regressions that tools can reliably detect.

## 49. Complete an application security review
Goal: Verify the MVP's authentication, authorisation, data handling, and browser protections.
Description: Review session and CSRF handling, household isolation, PIN throttling, secrets, logs, uploads, input validation, dependencies, and security headers. Add focused regression tests and document any accepted risk with an owner and follow-up condition.

## 50. Add before-and-after photo proof
Goal: Let children attach controlled evidence to a chore submission.
Description: Add validated before-and-after image uploads with size, type, ownership, retention, and access controls, then associate them with a pending submission. Test malicious files, missing pairs, cross-household access, removal, and accessible frontend upload states.

## 51. Validate photo metadata
Goal: Give parents a cautious signal about when and where submitted photos were created.
Description: Extract available date and location metadata without treating absence or client-controlled values as proof of validity. Present clear uncertainty, preserve privacy, and test stripped, malformed, contradictory, and valid metadata.

## 52. Add an AI photo-assessment boundary
Goal: Assess chore photos without coupling the core workflow to one AI provider.
Description: Define a provider-neutral assessment interface with explicit inputs, structured outputs, confidence, safety limits, timeouts, and failure behaviour. Implement one test double and contract tests before connecting any external model.

## 53. Add parent notification and optional auto-approval
Goal: Notify parents of AI assessments while keeping approval policy under parent control.
Description: Add notification records and per-household settings that default to manual approval and require explicit enablement for auto-approval. Test low confidence, provider failure, duplicate delivery, opt-out, auditability, and safeguards preventing an AI result from silently bypassing policy.

## 54. Allow a child to change creature line
Goal: Support a point-funded creature change while preserving financial and audit history.
Description: Finalise the cost and unlocked-form policy, then implement an atomic change that debits the ledger and records the old and new lines. Test insufficient funds, unavailable lines, repeat requests, permissions, idempotency, and history display.

## 55. Create the skill-tree framework
Goal: Provide a safe foundation for purchasable abilities without hard-coding them into unrelated modules.
Description: Model skill definitions, prerequisites, costs, purchases, duration, and effect identifiers, with all purchases debited atomically through the ledger. Add tests for duplicate purchase, prerequisites, insufficient funds, expiry, idempotency, and an unknown effect.

## 56. Implement the proposed skill effects
Goal: Add the initial interest boost, point bonus, chore immunity, and point gifting behaviours.
Description: Implement each approved effect behind the skill framework with explicit stacking, duration, audit, and permission rules. Test each effect independently as well as conflicts, expiry, insufficient funds, gifting limits, and attempts to bypass chore or household boundaries.

## 57. Containerise the Django API
Goal: Produce a reproducible, non-root backend container suitable for later deployment.
Description: Add a multi-stage container build with locked dependencies, collected static assets, a production application server, and a documented startup contract. Verify image size, startup, graceful shutdown, health checks, configuration injection, and that no secret enters the image.

## 58. Containerise the React frontend
Goal: Produce a reproducible frontend image that serves the production build.
Description: Add a multi-stage build using the locked pnpm dependencies and a minimal non-root runtime. Verify caching, API routing, security headers, health checks, graceful shutdown, and that no development secrets are embedded in browser assets.

## 59. Create the local multi-container environment
Goal: Run the frontend, Django API, PostgreSQL, and supporting services together locally.
Description: Add a development orchestration file with persistent database storage, health-based dependencies, isolated networks, and documented commands. Verify first-time startup, migrations, tests, restart behaviour, clean shutdown, and recovery from an unavailable dependency.

## 60. Add Redis and Celery workers
Goal: Move justified scheduled and asynchronous work out of web requests.
Description: Configure Redis and a separate Celery worker for selected interest, notification, or image tasks with explicit timeouts and retry policies. Test idempotency, duplicate delivery, worker restart, broker outage, failed-task visibility, and graceful shutdown.

## 61. Move media to S3-compatible storage
Goal: Keep uploaded and generated images independent from application containers.
Description: Add an S3-compatible storage adapter with private-by-default access, environment configuration, and a local test substitute. Test upload, retrieval, expiry or signed access, deletion policy, unavailable storage, and cross-household authorisation.

## 62. Add production routing and service health checks
Goal: Provide reliable ingress and machine-readable service readiness.
Description: Configure a reverse proxy or managed-ingress contract for same-origin frontend, API, static, and media routes. Add liveness and readiness checks that distinguish process health from database, cache, and storage availability without leaking sensitive details.

## 63. Add structured logs, metrics, and tracing
Goal: Make failures diagnosable across web requests, workers, and external services.
Description: Define correlation identifiers and structured logging fields, then instrument key request, approval, ledger, job, and storage paths with useful metrics. Add distributed tracing where calls cross process boundaries and verify that credentials, PINs, and sensitive image data are redacted.

## 64. Build the production delivery pipeline
Goal: Automate verified container builds, migrations, and deployments safely.
Description: Extend CI/CD to scan dependencies and images, build immutable artefacts, inject environment-specific secrets, run pre-deployment checks, apply migrations safely, and support rollback. Protect production environments with explicit approvals and document the release procedure.

## 65. Establish backup and recovery procedures
Goal: Prove that persistent application data can be restored after loss or corruption.
Description: Define automated PostgreSQL and object-storage backup retention, encryption, monitoring, and restore ownership. Perform a recovery exercise into an isolated environment, record timings and gaps, and create a concise operational runbook.

## 66. Evaluate a Go or Rust service only from evidence
Goal: Prevent unnecessary language and service complexity while preserving an informed upgrade path.
Description: Use production measurements to identify a specific bottleneck or isolation requirement, then compare Python optimisation, Go, and Rust against agreed criteria. Produce an architecture decision and a bounded proof of concept only if the evidence justifies a new service.
