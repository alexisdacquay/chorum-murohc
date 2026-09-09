# Browser journeys

Five household journeys and two audits, driven in a real browser against the
real product. Nothing here is imported by product code.

## What it is

One disposable container from the same pinned image the backend gate uses
serves three things on one port: `/api/` from Django, everything else from
the built frontend in `frontend/dist`, and `/__harness__/` for the driver
page. One origin is the point - Django session cookies and CSRF only work
that way, so a harness that proxied the API from elsewhere would be testing
a different application.

Headless Chrome then opens the driver page once per journey with a fresh
profile. The driver and the application share an origin, so the driver
reaches into the application's document the way a person reaches the screen:
it finds controls by their visible or accessible name, clicks them, types the
way a keyboard does, and waits for what the screen says next. It never calls
the API on the application's behalf, so a journey can only pass if the
interface really works.

There is no new dependency. Playwright is still unasked-for in
`_docs/dependency-approvals.md`, and the whole harness is standard library
Python plus the browser.

## Running it

    pnpm --dir frontend build
    python3 -m browser_journeys.run_journeys /path/to/worktree

That runs the five journeys. Name journeys to run a subset, and pass
`--chrome` for a browser at another path:

    python3 -m browser_journeys.run_journeys . reward creature
    python3 -m browser_journeys.run_journeys . audit-accessibility

| Journey | What it protects |
| --- | --- |
| `smoke` | The harness itself: one origin, a real sign-in, cookies |
| `child-submission` | Attest, pend, hand over the device, PIN, approve, reject |
| `parent-queue` | The parent's own queue, a PIN per decision, empty state |
| `reward` | Balance, refusal when short, redemption, exact ledger effect |
| `creature` | Choosing a line write-once, and a levelled child's evolution |
| `audit-accessibility` | WCAG 2.2 AA checks over every built screen (reports) |
| `audit-security` | Live cross-role, CSRF and header probes (reports) |

The two audits report findings instead of asserting there are none, so they
are excluded from the default run. Their findings live in
`_docs/audit-accessibility.md` and `_docs/audit-security.md`.

## Isolation

Every run mints a run token. The token names the throwaway SQLite file, and
it is the suffix of every household and every username the run creates; every
password and PIN is generated with `secrets` for that run alone. Each journey
inside a run gets its own household, so no journey can see another's rows,
and each journey gets its own browser profile, so no journey inherits
another's cookies.

`test_seed.py` proves that in the backend gate, where the browser is not
available: two runs share no database, household, user or credential, and no
PIN is ever stored in the clear.

## Diagnostics

A journey types real passwords and PINs. Every step label, failure message
and screen snapshot is scrubbed of the run's own secrets before it leaves the
browser, and the runner checks the scrubbing again before printing: a report
that still carries a credential is a failed run whatever the journey said.
`diagnostics.py` owns both halves and `test_diagnostics.py` proves them.

## Why it is not a CI check

CI would need a browser on the runner. The only one available there is the
hosted image's own Chrome, whose version changes without notice, which is
exactly the pinning the rest of this repository refuses to give up. Until a
pinned browser image is approved, the journeys are a local gate: run them
before landing anything that touches a journey the table above names.
