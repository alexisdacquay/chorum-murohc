# Security Audit - current scope

> **Status:** Findings only (T095). Nothing here is fixed by the audit.
>
> **Date:** 2026-09-09, re-run against `1ec2d24` once the parent overview and
> activity screens landed; the findings did not change.
> **Method:** live browser probes
> (`python3 -m browser_journeys.run_journeys . audit-security`),
> `manage.py check --deploy` against a production configuration, and a source
> read of settings, permissions, services, the audit writer and CI.

## What was inspected

Sessions and CSRF, role and household isolation, PIN handling, ledger
mutation paths including scheduled interest, idempotency, secrets, logging,
dependencies, CI, external-action boundaries, input validation, the audit
interface, and browser security headers.

## What holds

Proved live, in a browser holding a real child session, against the running
application rather than a test client:

- A child's session is refused by `/api/v1/audit/`, `/api/v1/approvals/` and
  `/api/v1/household-members/` with 403 and a body under 200 bytes that names
  no user.
- An unsafe request with the session cookie but no CSRF token is refused 403.
- The session cookie is not readable from script; the CSRF cookie is, by
  design, and is the only one the interface touches.
- A signed-out caller gets 403 from a product route.
- `X-Content-Type-Options`, `Referrer-Policy` and `X-Frame-Options` are all
  sent on API responses.

Confirmed by reading the source:

- No outbound HTTP from any product module: the backend calls no third party,
  so there is no external-action boundary to abuse.
- No `dangerouslySetInnerHTML`, no `innerHTML` write, no `eval`, and no
  `localStorage` or `sessionStorage` use in product frontend code.
- No secret, key or `.env` file is tracked, and no product module logs.
- PIN comparison happens only in `identity.services.verify_pin`, under a row
  lock, with a five-failure fifteen-minute per-parent lockout; the hash never
  leaves the model.
- Ledger entries refuse update, delete, bulk create and any second `save()`.
  Every credit and debit carries a per-user unique idempotency key, and the
  approval, redemption and interest paths are single transactions.
- `accrue_interest` requires an explicit `--date` and never infers "today", so
  a scheduler misfire cannot silently double-credit a different week.
- CI pins every action to a full commit SHA, grants `contents: read`, never
  uses `pull_request_target`, checks out with `persist-credentials: false`,
  and derives its database credentials inside the job. `main` is protected.

## Findings

| Id | Severity | Boundary | What happens | Expected | Regression test |
| --- | --- | --- | --- | --- | --- |
| S-01 | Medium | Browser to Django | No `Content-Security-Policy` header is sent. React escaping and the absence of any raw-HTML sink are the only defence against an injected script | A CSP that at minimum forbids inline script and restricts `default-src` to `self` | Extend the `audit-security` journey's header probe to require the header and its directives |
| S-02 | Medium | Production transport | `SECURE_HSTS_SECONDS` and `SECURE_SSL_REDIRECT` are unset, so `manage.py check --deploy` warns W004 and W008. The cookies are Secure in production, but nothing forces HTTPS or pins it | Both set for production, and `check --deploy` clean apart from a deliberately silenced check | A settings test asserting both values under `DJANGO_ENVIRONMENT=production` |
| S-03 | Medium | Supply chain | Nothing scans `uv.lock` or `pnpm-lock.yaml` for known vulnerabilities. There is no Dependabot configuration and no audit step in CI | A scheduled advisory check on both lockfiles, failing or reporting on a known vulnerability | The scan itself is the test; assert it runs on a pull request |
| S-04 | Low | Operations | No logging is configured. A burst of 403s, CSRF rejections or throttled logins leaves no trace outside the product audit table, which records successful mutations rather than refused attempts | A minimal structured log of refused authentication, CSRF and permission events, carrying no secret or household content | A test asserting a refused login emits one non-secret log record |
| S-05 | Low | Availability | Only login is rate limited. Submission creation, redemption and PIN verification have no request-rate control; PIN guessing is bounded by the per-parent lockout, and duplicate writes by unique idempotency keys, but a signed-in account can still generate unbounded requests | A bounded control on the unsafe product endpoints, or a recorded acceptance that a signed-in family member is trusted not to flood | An API test asserting the chosen control refuses the N+1st request |

## Accepted residual risks, rechecked

Every risk accepted in `_docs/design.md` and tracked in `_docs/roadmap.md`,
rechecked independently as T095 requires.

| Accepted risk | Owner | Still true? | Still acceptable? |
| --- | --- | --- | --- |
| Privileged database access is trusted; household isolation and audit immutability are application-layer only, with no row-level security, trigger or tamper evidence | [#123](https://github.com/alexisdacquay/chorum-murohc/issues/123) | Yes. Verified: isolation is enforced in `api/permissions.py` and every queryset; immutability is enforced in `LedgerEntry` and `AuditEvent` Python only. No trigger or RLS exists | Yes, for a single-household family app whose database has one operator who is also the product owner. It must not be described as tamper-proof anywhere |
| No bounded login-abuse control | T027 | No longer true. Delivered: 10 failed attempts per minute and 100 per hour per client address, counting failures only | Closed |
| The login throttle counts per process, so a multi-process deployment multiplies the allowance | [#128](https://github.com/alexisdacquay/chorum-murohc/issues/128) | Yes. `CACHES['login_throttle']` is `LocMemCache` | Yes while the deployment is one process. It becomes a real hole the day a second worker starts, so it blocks any multi-process deployment |
| Parent PIN retry, lockout and recovery thresholds undefined | T029 | No longer true. `_docs/approval-authentication.md` is approved and implemented: 4-10 digits, hashed, five failures, fifteen-minute per-parent lockout, recovery by re-setting with the account password | Closed. The four-digit floor stays weak offline; the lockout, not the hash, is the defence, and that is stated in the policy |
| Session cookies are the only authentication factor; no second factor and no single sign-on | Unowned | Yes | Yes for this product. Two parents and their children on household devices; a second factor would cost more than it buys. Needs its own task if the product ever leaves the house |
| No independent human security review; the product owner waived it | [#18](https://github.com/alexisdacquay/chorum-murohc/issues/18#issuecomment-5584623381) | Yes. This audit is the same campaign's own work, not an independent third party | Unchanged. Worth restating rather than quietly retiring |
| No password change or reset path | [#129](https://github.com/alexisdacquay/chorum-murohc/issues/129) | Yes. A forgotten password needs a parent with database or shell access | Yes for now. A parent can recreate an account; there is no self-service path to abuse |
| No way to switch between households in one session | [#130](https://github.com/alexisdacquay/chorum-murohc/issues/130) | Yes. An ambiguous membership fails closed, which is the safe direction | Yes. The failure mode is denial, not leakage |

## Deliberately not covered

- No penetration test, no fuzzing, and no authenticated scanner run.
- No review of the deployment host, TLS termination or backups; there is no
  deployment configuration in this repository to review.
- No cryptographic review of Django's own hashers or session machinery.
