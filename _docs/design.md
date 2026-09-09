# Chorum-murohc - Design v1

> **Status:** Selected planning direction; not yet implemented.

## Design Goals

- Deliver a modern, polished, mobile-first user interface.
- Keep product behaviour modular so that it can be designed, implemented,
  tested, troubleshot, and evolved in bounded areas.
- Begin with a manageable local architecture while preserving a clear path to
  containerised, distributed, production-grade operation.
- Avoid premature microservices and introduce operational complexity only when
  scale or reliability requirements justify it.

## Architecture

Chorum-murohc will use a monorepo containing two principal applications:

1. A React frontend that provides the user interface.
2. A Django backend that exposes the application API and owns business rules,
   authentication, and persistent data.

The backend will begin as a modular monolith. Domain boundaries will be kept
explicit so that independently scalable services can be extracted later if a
demonstrated need arises.

The initial deployment should keep the frontend and backend on the same origin.
This permits Django session authentication and CSRF protection without adding
unnecessary token-management or cross-origin complexity.

## Selected Technology Track

| Area | Selected technology | Purpose |
| --- | --- | --- |
| Backend language | Python 3.13 | Primary implementation language |
| Backend framework | Django 5.2 LTS | Application framework, authentication, administration, and business logic |
| API | Django REST Framework | Versioned HTTP API for the frontend |
| Database | PostgreSQL | Durable transactional system of record |
| Frontend language | TypeScript | Safer, maintainable browser application code |
| Frontend framework | React | Component-based user interface |
| Frontend tooling | Vite | Development server and production builds |
| Styling and components | Tailwind CSS and shadcn/ui | Modern, consistent, accessible visual system |
| Animation | Motion | Point rewards, creature evolution, and interface transitions |
| Server-state management | TanStack Query | API requests, caching, and synchronisation |
| Forms and validation | React Hook Form and Zod | Form state and client-side validation |
| Authentication | Django sessions with CSRF protection | Secure same-origin browser authentication |
| Python packages | uv | Python environments, dependencies, and locking |
| Frontend packages | pnpm | JavaScript and TypeScript dependency management |
| Backend testing | pytest and pytest-django | Unit and integration testing |
| Frontend testing | Vitest and Testing Library | Component and interaction testing |
| End-to-end testing | Headless Chrome, driven by `browser_journeys/` | Browser-level workflow testing with no added dependency |

SQLite may remain useful for very early local experiments, but PostgreSQL is
the selected implementation database so that development and production
behaviour do not diverge unnecessarily.

## Approved Backend Boundaries

The repository and public product remain **Chorum-murohc**. The Python
distribution remains `chorum-murohc`, and all importable product packages use
the valid Python namespace `chorum_murohc`. The backend is not a standalone
`chores` project, and the nested chores app does not replace the existing root
app.

`config` is the Django composition root. It owns settings, root URLs, ASGI, and
WSGI only; it may register every app but owns no product models or migrations.
The existing `chorum_murohc` app remains installed as the Chorum-murohc
compatibility/root app and package namespace. It imports no domain
implementation and owns no product models or product migrations.

The following packages are the approved backend boundaries. The tasks in the
final column own future model and migration changes for that app; this boundary
task creates only the eight nested app shells and their empty migrations
packages.

| Package / Django app | Responsibility | Future model and migration owner |
| --- | --- | --- |
| `config` | Django composition root: settings, root URLs, ASGI, and WSGI only | No product models or migrations |
| `chorum_murohc` | Existing installed Chorum-murohc compatibility/root app and package namespace | No product models or product migrations |
| `chorum_murohc.api` | Versioned HTTP API layer: routing, endpoints, serializers, and the shared household-role permission primitive | No product models or migrations |
| `chorum_murohc.identity` | Users, households, memberships, and parent PIN persistence | T006, T007, and T030 |
| `chorum_murohc.audit` | Append-only audit events | T008 |
| `chorum_murohc.chores` | Reusable household chore definitions | T034 |
| `chorum_murohc.submissions` | Completion submissions and approval state | T041 and later submission-schema changes |
| `chorum_murohc.ledger` | Immutable point transactions | T038 and later ledger-schema changes |
| `chorum_murohc.rewards` | Reward-redemption records | T056 and later reward-schema changes |
| `chorum_murohc.progression` | Per-child level state | T062 and later progression-schema changes |
| `chorum_murohc.creatures` | Creature catalogue (code, not a table) and per-child selection state | #66 and later creature-schema changes |
| `chorum_murohc.interest` | Weekly interest accrual policy and command; no product models of its own | T052 and later interest-accrual changes |

Python dependencies between product apps must follow this acyclic direction
map:

| Importing package | Product packages it may import |
| --- | --- |
| `chorum_murohc` root | None |
| `chorum_murohc.api` | Every product package: `identity`, `audit`, `chores`, `submissions`, `ledger`, `rewards`, `progression`, `creatures`, `interest` |
| `chorum_murohc.audit` | None |
| `chorum_murohc.identity` | `audit` |
| `chorum_murohc.chores` | `audit` |
| `chorum_murohc.ledger` | `audit` |
| `chorum_murohc.submissions` | `identity`, `chores`, `ledger`, `audit` |
| `chorum_murohc.rewards` | `identity`, `ledger`, `audit` |
| `chorum_murohc.progression` | `identity`, `ledger`, `audit` |
| `chorum_murohc.creatures` | `identity`, `progression`, `audit` |
| `chorum_murohc.interest` | `identity`, `ledger`, `audit` |

`chorum_murohc.api` is the top layer and no product package may import it.
It was promoted out of the root boundary so that one household-role permission
primitive can serve every endpoint. Hosting that primitive in
`chorum_murohc.identity` was rejected: the audit read API would then need
`audit` to import `identity` while `identity` already imports `audit`, which is
a cycle. Placing the shared HTTP concerns above every domain keeps the map
acyclic and leaves each domain package free of endpoint code.

Reverse or undeclared product-package imports are forbidden. Cross-app model
references use Django lazy string references or `settings.AUTH_USER_MODEL`,
with migration dependencies declared only when the owning model task adds a
migration.

The frontend should follow the same domain boundaries for screens, components,
API clients, and tests. Shared UI primitives should remain separate from
product-specific features.

## Data and Security Principles

- Create the custom Django user model before business database migrations.
- Record points in an auditable transaction ledger rather than relying only on
  a mutable balance.
- Use database transactions for approvals, spending, interest, and levelling.
- Represent points and rates with integer or decimal arithmetic, never floats.
- Store parent PINs as secure hashes and rate-limit failed attempts.
- Keep credentials outside version control and inject production secrets at
  runtime.

## Trust Boundaries and Permission Matrix

> **Status:** Approved access policy for task T018. Product-owner approval and
> security acceptance are recorded in issue
> [#18](https://github.com/alexisdacquay/chorum-murohc/issues/18); see Approval
> evidence below. This section is policy only. It implements no permission,
> endpoint, session flow, PIN flow, database rule, interface gate, logger, or
> audit view. Plan coverage: `IT-02`, `UA-02`, `TC-06`. Recording that coverage
> does not claim that any endpoint behaviour is implemented or verified.

The words **must**, **must not**, **allow**, and **deny** are normative here.
`Allow` is a maximum authority that an owning follow-up task may expose; it does
not create an endpoint and does not require broader data. Anything not
explicitly allowed is denied.

### Definitions and Actor Model

- **Authenticated active user**: Django reports an authenticated `request.user`
  and the merged user row has `is_active=True`. Authentication alone grants no
  household or product authority.
- **Active household context**: the one household resolved by trusted
  server-side state for the operation. A body, query parameter, path value,
  header, browser route, local storage value, username, or cached frontend role
  is never authority. T027 owns the exact session and current-household
  representation.
- **Current membership**: exactly one live `Membership` connecting the
  authenticated active user to the active or resource-owning household. The role
  must be exactly `parent` or `child`.
- **Parent** and **child**: product roles taken from the current household
  membership. They are not global user attributes.
- **Product admin**: the plan's "admin/parent" means the `parent` membership
  role for the active household. Django `is_staff`, `is_superuser`, groups, or
  model permissions do not make a user a product parent and do not bypass
  product API checks.
- **PIN-verified parent on a child device**: a specifically identified active
  parent in the same household whose PIN is verified for one pending decision.
  This creates no parent session, changes no child membership, and grants no
  reusable elevation.
- **Trusted server operation**: one named domain service, management command, or
  scheduled job acting only within the capability granted by its owning task. It
  is not a browser actor and has no general bypass.
- **Deny**: perform no read or mutation and reveal no protected resource data. A
  foreign-household identifier must be indistinguishable from a missing or
  otherwise unavailable resource at the product response boundary.
- **Sensitive output**: audit context, application and worker logs, exception
  reporting, console output, API errors, browser DOM and accessibility text,
  screenshots, CI artefacts, and test failure messages.

### Protected Assets and Security Objectives

| Asset | Required protection |
| --- | --- |
| Passwords, password hashes, parent PINs and hashes, session identifiers, cookies, CSRF values, tokens, and recovery material | Confidential; never returned, rendered, logged, placed in audit context, or accepted outside the owning flow |
| User state, membership, role, household association, active-household context, staff and superuser flags | Integrity and request-time freshness; server-derived only |
| Household existence, member directory, chores, submissions, balances, reward, progression, and creature state | Confidentiality between households and least-privilege visibility within one household |
| Submission decisions, ledger entries, reward debits, interest, level changes, and creature selection | Atomic integrity, exact actor attribution, idempotency where retryable, and no direct client-authored financial values |
| Audit events | Same-household parent visibility only, append-only through supported application APIs, safe context, stable actor, action, and target attribution |
| Operational logs and diagnostics | Operator-only, minimised, structured, non-enumerating, and free of secrets and personal or household content |
| Availability of login, PIN, approval, and mutation surfaces | Bounded abuse handling owned by the implementing task; no unbounded retry or concurrency amplification |

### Trust Boundaries and Mitigation Owners

| Boundary | Required rule | Mitigation owner |
| --- | --- | --- |
| Untrusted browser to same-origin Django | Django authenticates identity, validates all input, enforces CSRF on unsafe session-authenticated requests, and never accepts browser role or household claims as authority | T027 for sessions and CSRF; T019 plus every endpoint owner for authorisation |
| Session identity to household role | Re-read active-user and exact household membership state for each protected request; do not union roles across households or trust stale session or interface copies | T019, T027 |
| One household to another | Scope querysets and service inputs to the authorised household before object lookup; return non-enumerating denial | T019 and every household API task |
| API layer to domain mutation | API code supplies the authenticated actor and validated identifiers; named atomic services compute trusted values and enforce transitions and idempotency | T045, T052, T056, T063 and each later mutation owner |
| Domain code to audit events | Producers pass only allow-listed safe context; recursive key redaction is defence in depth, not permission to pass a secret | T008 contract plus every event-producing task; T086 for views |
| Application to database | PostgreSQL and privileged database operators are trusted. Household isolation and audit immutability are application-enforced; no row-level-security or database-tamper-proof claim is made | Every model and service owner; independent recheck in T095 |
| Trusted command or job to household data | Use only the named service and its explicit bounded scope, date, and idempotency contract; no generic operator bypass and no caller-supplied arbitrary action | T009, T053, T054 and the owning domain task |
| Frontend and navigation to backend | Route visibility and hidden controls are usability only. Every API independently enforces the matrix | T015, T019, all API owners |

### Global Authorisation and Isolation Invariants

1. Default deny. An absent matrix row, absent policy, malformed state, or
   unapproved transition grants nothing.
2. Unauthenticated or inactive users receive no product-domain data and no
   mutation authority. The existing public zero-data health endpoint and the
   exact T027 session-establishment and signed-out surfaces are the only
   exceptions.
3. The database permits one user to be a parent in household A and a child in
   household B. Each request uses only the role for its one active or
   resource-owning household; roles and permissions never aggregate.
4. No active household, more than one unresolved candidate household, a missing
   membership, a deleted or stale membership, an unsupported role, conflicting
   state, or a disabled user fails closed.
5. A role or membership change takes effect on the next request even if the
   session persists. A security-sensitive mutation revalidates actor,
   membership, resource household, and current state inside its transaction
   immediately before writing.
6. Collection creation uses a server-validated active household. Existing
   resource operations derive the household from a household-scoped lookup. A
   client-supplied household or resource identifier may select a candidate only;
   it never proves access.
7. Cross-household identifiers must not disclose whether a household, user,
   chore, submission, ledger entry, reward, progression row, creature selection,
   or audit event exists.
8. Product endpoints never honour Django staff or superuser status, groups, or
   model permissions as a household-role bypass. Product account operations
   never grant those platform flags.
9. Read endpoints are side-effect free. Mutations use an unsafe method, require
   CSRF under session authentication, validate server-owned state, and never
   accept a client-authored role decision, point amount, balance, rate, level
   cost, approval actor, audit actor, or trusted reason code.
10. A frontend route, hidden control, disabled button, cached query result, or
    local browser state is never an authorisation control.
11. Every endpoint tests unauthenticated, inactive, allowed role, denied role,
    missing or unknown role, and cross-household cases; endpoint-specific tasks
    also test their own matrix row and awkward states.
12. Retryable business mutations have an owning idempotency contract. Approval,
    credit, debit, interest, reward, and level transitions are atomic and cannot
    partially commit or double-apply under retry or concurrency.
13. Denial and validation responses are compact and non-enumerating. They do not
    echo a protected identifier, role, household, username, PIN result, balance,
    server exception, or body from another trust boundary.
14. Audit and operational evidence records the minimum actor, action, target, and
    result needed. It does not become an alternate data store or a permission
    bypass.
15. Any later task that needs authority broader than this matrix must stop, amend
    this policy, obtain product-owner and independent security approval, merge
    the amendment, and only then continue.

### Session and CSRF Policy

- Use Django username and password authentication, same-origin Django sessions,
  and CSRF protection. Do not add JWTs, bearer tokens, cross-origin credential
  flow, or browser-stored authentication tokens.
- Login rotates the session identifier. Logout is an unsafe CSRF-protected
  operation and flushes the authenticated session. Safe methods do not log in,
  log out, select a household, or mutate product state.
- The session cookie is HttpOnly and, in production, Secure with at least
  SameSite=Lax. The exact same-origin CSRF-token delivery and current-user
  response belong to T027; neither value may enter logs or visible errors.
- Login, logout, and session inspection return only the minimum contract groomed
  in T027. Invalid username, invalid password, disabled account, and foreign or
  ambiguous membership states do not reveal account existence through distinct
  public wording.
- Session identity does not cache durable authority. Current `is_active`,
  membership, role, and household scope are evaluated at use.
- T027 must record a bounded login-abuse control, or an explicit independently
  approved residual-risk acceptance, before it becomes Ready. T018 does not
  select a package, threshold, expiry duration, or recovery mechanism.
- CORS is not an authorisation mechanism and is not added. CSRF protects unsafe
  same-origin session requests; permission checks still run independently.

### Permission Matrix

| Surface or capability | Unauthenticated | Child in current household | Parent in current household | Exact scope and implementation owner |
| --- | --- | --- | --- | --- |
| Existing `/api/v1/health/` | Allow fixed zero-data health result | Same | Same | Existing T010 and T016 contract only |
| Login, CSRF bootstrap, signed-out session inspection | Allow only exact T027 entry points | Not applicable once authenticated | Not applicable once authenticated | T027; generic failures and no product data |
| Current session inspection and logout | Deny authenticated data; signed-out shape only | Allow own minimum identity, active-household and role data; logout self | Same | T027; never return password, PIN, session value, or other memberships beyond its approved minimum |
| Select or resolve active household | Deny | Allow only among own live memberships | Same | T027; zero or ambiguous unresolved context denies, and roles never union |
| View household account directory | Deny | Deny | Allow own household minimum account fields | T021; no credential, PIN, platform permission, or foreign membership data |
| Create household account and assign product role | Deny | Deny | Allow in own household | T021; role is exactly parent or child; cannot grant staff, superuser, groups, or model permissions |
| Edit account or product role | Deny | Deny | Allow in own household subject to last-active-parent protection | T022; self-action and stale target fail safely |
| Remove, deactivate, or anonymise account | Deny | Deny | Deny until approved retention policy, then only the exact own-household transition | T020, T023; never remove the last active parent |
| Set or replace parent PIN | Deny | Deny | Allow own PIN only after the exact T029 and T031 proof and recovery contract | T029 to T033; never read a PIN or hash and never manage another parent's PIN |
| List active chores | Deny | Allow active own-household chores | Allow own-household chores needed for management | T035 |
| Create, edit, remove, or deactivate chores | Deny | Deny | Allow own household subject to approved retention rules | T020, T034, T035; child denial is absolute |
| Submit completed chore attestation | Deny | Allow for self and an active own-household chore only after T040 policy | Deny | T040 to T042; cannot submit for another child or before explicit attestation |
| Read submissions | Deny | At most own submissions exposed by the owning contract | Allow own-household pending queue only through approved queue fields | T042, T044; no peer-child or foreign data |
| Approve or reject on parent device | Deny | Deny | Allow one own-household pending decision only after own PIN re-verification | T045, T046; exact actor, atomic decision, one credit at most |
| Approve or reject on child device | Deny | Child session alone denies; it may host only the T029 PIN challenge | A specifically identified, active, same-household parent may authorise exactly one decision | T029, T033, T045 to T047; no role elevation and no reusable parent capability |
| Read point balance and ledger history | Deny | Allow own household-scoped balance and history | No detailed child history by default; allow only the plan-required household balance summary via T084 | T039, T084; broader parent history needs new approval |
| Append, edit, or delete ledger value | Deny | Deny direct mutation | Deny direct mutation | Only named atomic services in T045, T052, T056, and T063 append server-computed entries; no application update or delete |
| Initiate or view child reward | Deny | Allow own reward initiation and status only after T055 policy | Deny child operation | T055 to T057; exact server conversion, balance, and idempotency |
| Fulfil, reject, cancel, or reverse reward | Deny | Deny | Deny until T055 explicitly grants a named same-household parent transition | T055, T059; otherwise the task is formally not applicable |
| Read or advance level | Deny | Allow own read, and own acknowledgement that a reached level has been shown | No mutation; allow own-household level summary through T084 | T061 to T064, T084; level is server-computed from lifetime ledger credits, never client-supplied, and never spent or lost |
| Creature catalogue, selection, and evolution | Deny product state | Allow own catalogue read, own evolution state, and one write-once selection of own line | Allow only the plan-required household summary; no selection and no catalogue route | #66, T084; the catalogue is global but user selection and state remain scoped, and the client never supplies the level or the unlocked forms |
| Parent household overview | Deny | Deny | Allow minimum own-household member, balance, level, and pending summary | T084; no foreign household and no detailed secret or history expansion |
| Read audit history | Deny | Deny | Allow redacted own-household events only | T086; native pagination, safe filters, immutable read only |
| Create audit event | Deny direct access | Deny direct access | Deny direct access | Named server mutations emit exact events; bootstrap and system may use `actor=None` only when no human actor exists |
| Read operational logs or diagnostics | Deny | Deny | Deny | Trusted operators only, outside product APIs; T095 verifies exposure boundaries |

### PIN and Approval Invariants

- Both plan-defined approval paths require one specifically attributable active
  parent in the submission household. A parent session alone and a PIN alone are
  each insufficient.
- T029 owns parent selection versus household-unique PINs, PIN length beyond the
  plan's four-digit minimum, retry threshold, lockout, reset, recovery, and audit
  attribution. Until its exact product-approved and security-approved policy
  merges, PIN setup and approval mutations remain denied.
- PIN comparison occurs only in the trusted verification service using a secure
  hash. The API and interface never receive a stored PIN or hash and never state
  which parent exists or which PIN matched.
- A child-device attempt never changes the child session, membership,
  navigation, or later requests. Successful verification authorises one named
  pending decision and is consumed whether that decision succeeds or becomes
  stale.
- Approval and rejection recheck parent membership, child and submission
  household, pending state, PIN result, and idempotency inside one transaction.
  Rejection never credits; approval credits the configured snapshot exactly once.
- Audit attribution uses the verified parent as actor, not the child whose device
  hosted the flow. Additional initiating context must be minimal and
  non-sensitive.

### Audit and Sensitive-Output Contract

- Audit events are immutable only through supported application ORM APIs. There
  is deliberately no database trigger and no cryptographic tamper evidence;
  privileged database access is a trusted residual risk and must not be described
  as impossible.
- `actor=None` is valid only for a real bootstrap or system action with no human
  actor. A human-authorised mutation records the actual user; a PIN approval
  records the verified parent.
- Event producers use stable action codes, target type and identifier, actor
  relation, household relation, and only the minimum allow-listed structured
  context. They never copy a request body, response body, model dump, headers,
  credentials, exception, or arbitrary user-controlled mapping.
- Existing recursive sensitive-key redaction is defence in depth. Producers must
  not place a secret under an innocuous key and must not depend on redaction to
  make unsafe input acceptable.
- Password and PIN values or hashes, session, cookie, CSRF, token, and
  authorization values, email addresses, raw usernames, household names,
  free-text personal content, and runtime-generated sensitive markers are
  forbidden in audit context, operational logs, visible errors, browser console
  output, screenshots, CI artefacts, and test failure text.
- Operational logs may contain a stable action code, route template, outcome
  class, non-secret correlation identifier, and internal actor or target
  identifiers only where needed. They must not expose a protected resource's
  existence to an unauthorised caller.
- Product errors remain compact and generic. Detailed server exceptions may reach
  trusted development diagnostics only under existing environment controls and
  must never include a deliberately logged secret or a full request payload.
- Audit reads are parent-only, household-scoped, redacted, paginated, and
  read-only. An audit event never grants authority over its referenced actor or
  target.

### Abuse Cases, Required Mitigation, and Owner

| Abuse case | Required mitigation | Owner |
| --- | --- | --- |
| Client forges role, household, or current-user fields | Ignore client claims; derive active user and exact membership server-side | T019, T027, every API owner |
| Parent in household A uses an identifier from household B, or a child enumerates peer data | Household-scope before lookup and use non-enumerating denial | T019 and each household endpoint |
| User has roles in multiple households and gains their union | Select one trusted context and evaluate only that membership; unresolved context denies | T019, T027 |
| Disabled, removed, changed, stale, missing, or corrupt role remains cached | Revalidate `is_active`, membership, role, and household on every protected request and inside sensitive writes | T019 and the mutation owner |
| Staff or superuser flag bypasses household policy | Product permission code ignores platform flags and groups | T019 and all product APIs |
| Session fixation, CSRF, logout replay, or browser token theft | Rotate and flush the Django session, enforce same-origin CSRF on unsafe methods, use secure cookie settings, store no bearer token | T027 |
| Credential guessing or account enumeration | Generic outcomes plus a bounded control or an explicitly approved residual risk | T027 and its security review |
| Child creates chores, approves, edits the ledger, or calls a parent route directly | Backend matrix denial independent of interface and navigation | T019, T035, T042, T046, T057, T064 |
| Parent removes or demotes the last active parent, or acts across households | Transactional last-parent and household checks under the approved retention policy | T020 to T023 |
| PIN guessing, parent enumeration, replay, or reusable elevation | Exact T029 identity contract, secure hashing, capped attempts and lockout, one-action capability, generic response | T029 to T033, T045, T046 |
| Duplicate or concurrent submission, approval, credit, debit, reward, interest, or level request | Unique idempotency key and state transition, transaction, locking, and exact rollback | T041 to T046, T052, T056, T063 |
| Client changes amount, rate, cost, balance, role, or audit actor | Server computes from approved policy and persisted state; reject client-owned authoritative values | The owning domain service or API |
| Audit or log injection, or a secret copied under a safe-looking key | Structured allow-list at the producer, recursive sanitisation as backup, generic output, targeted tests | Every event and log producer; T086, T095 |
| Attacker treats audit data as proof of access, or mutates history | The audit view independently authorises the current parent and household; application APIs expose no update or delete | T086; residual database trust reviewed in T095 |
| Frontend route or cached data exposes a stale control | Remove stale interface promptly but rely on server denial; never treat route visibility as authority | T015, T028 and every feature interface and API |
| Background command or job processes arbitrary scope twice | Explicit scope and date, named service, idempotency, and bounded reporting | T009, T053, T054 and the domain service owner |
| Cross-site scripting or unsafe rendering uses user content to act with a session | React text rendering, no dynamic HTML, no credential storage, server-side CSRF and permission checks | Every interface task; final review T095 |

### Decisions Deliberately Owned by Linked Follow-ups

These are not open authority grants. Until each policy is approved and merged,
the related mutation remains denied.

| Decision | Owning follow-up | T018 invariant |
| --- | --- | --- |
| Account removal, deactivation, anonymisation, and referenced-history retention | T020 | Parent-only own-household ceiling; never remove the last active parent |
| Exact session and current-user shape, active-household selection, expiry and error handling, login-abuse handling | T027 | Same-origin Django session; server-derived role; ambiguous context denies |
| Parent identity, PIN uniqueness and selection, length, retry, lockout, recovery, and attribution | T029 | No approval or PIN management before exact product and security approval |
| Completion wording, duplicate rule, and rejection semantics | T040 | Child self-attestation only; parent creation denied |
| Interest arithmetic, time, rounding, and missed-day behaviour | T050 | No user direct mutation and no accrual before the approved service |
| Reward debit, fulfil, cancel, and reversal transitions | T055 | Child self-initiation ceiling; parent transitions denied until approved |
| Level costs, maximum, and form mapping | T061 | Child self-level-up ceiling; the server computes the exact cost |
| Creature rights, assets, and catalogue contract | #66 | Settled in `_docs/creature-catalogue-policy.md`: no third-party intellectual property, original committed SVG only, and no external media action |
| Initial creature chooser, actor, timing, incomplete state, and repeat rule | #66 | The child picks their own line at first sign-in, after their account exists; the choice is write-once |

### Approval Evidence

- Proposal reviewed:
  [issue 18 comment 5582416492](https://github.com/alexisdacquay/chorum-murohc/issues/18#issuecomment-5582416492).
- Product-owner approval: `alexisdacquay`, 2026-09-08,
  [issue 18 comment 5584426439](https://github.com/alexisdacquay/chorum-murohc/issues/18#issuecomment-5584426439).
- Security acceptance: `alexisdacquay`, 2026-09-08,
  [issue 18 comment 5584623381](https://github.com/alexisdacquay/chorum-murohc/issues/18#issuecomment-5584623381).
  The product owner deliberately waived a separate third-party security
  reviewer, having been shown the residual risks below. That waiver is recorded
  on the issue rather than hidden.
- Any substantive change to actor authority, data scope, denial behaviour, trust
  assumptions, or mitigation ownership requires both approvals again.

### Accepted Residual Risks

Each risk is accepted, owned, and tracked as a security todo in the
[roadmap](roadmap.md). None is a permanent exemption, and T095 must recheck all
of them independently.

| Accepted residual risk | Owner |
| --- | --- |
| Privileged database access is trusted. Household isolation and audit immutability are application-layer only, with no row-level security, trigger, or tamper evidence | [issue #123](https://github.com/alexisdacquay/chorum-murohc/issues/123) |
| No bounded login-abuse control exists until the authentication contract merges | T027 |
| Parent PIN retry, lockout, and recovery thresholds are undefined, and PIN and approval mutations stay denied until then | T029 |
| Session cookies are the only authentication factor; there is no second factor and no single sign-on | Unowned; adoption needs its own approved task |

## Deferred Technology

Go and Rust are not part of the present implementation track. They may later be
introduced behind stable interfaces when measurement demonstrates a suitable
need: Go for concurrent network services or workers, and Rust for CPU-intensive
or unusually safety-critical components.

The suggested operational additions and production evolution are recorded
separately from product features in the [long-term roadmap](roadmap.md).
