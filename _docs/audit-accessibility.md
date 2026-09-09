# Accessibility Audit - current scope

> **Status:** Findings only (T094). Nothing here is fixed by the audit; each
> finding is a separate entry for someone to pick up.
>
> **Date:** 2026-09-09. **Standard:** WCAG 2.2 level AA.
> **Method:** `python3 -m browser_journeys.run_journeys . audit-accessibility`,
> headless Chrome 149, plus one keyboard pass and a source read.

## What was audited

Every screen the product currently builds, in a real browser, signed in as a
real child and a real parent: sign-in, child chores, points, rewards, levels
and creature, and parent overview, approvals, chore pool, reward requests,
household, activity and approval PIN. Overview and activity are still the
router's placeholder panel; the real screens are owned by
[#84](https://github.com/alexisdacquay/chorum-murohc/issues/84).

Per screen the audit ran: text alternatives (1.1.1), accessible names for
every visible control (4.1.2), heading structure and the main landmark
(1.3.1), duplicate identifiers and dangling ARIA references (4.1.1, 4.1.2),
positive tabindex (2.4.3), a visible focus indicator on every focusable
control (2.4.7), pointer target size (2.5.8), text contrast against the
computed effective background (1.4.3), page language (3.1.1) and document
title (2.4.2). Between 4 and 13 controls and 6 to 18 text elements were
measured on each screen; the run prints those counts so a silent no-op is
visible.

The keyboard pass covered the interaction most likely to trap a keyboard
user: opening a modal dialog, checking focus enters it, closing it with
Escape, and checking where focus lands.

## Findings

| Id | Severity | Screen | Criterion | What happens | Expected | How to verify |
| --- | --- | --- | --- | --- | --- | --- |
| A-01 | Medium | Every screen with a dialog; observed on child chores | 2.4.3 Focus order | Closing a dialog with Escape leaves focus on `body`. Every dialog in the product is mounted conditionally (`{target !== null ? <Dialog .../> : null}`), so the component unmounts before Radix can restore focus to the trigger | Focus returns to the control that opened the dialog | Run the `audit-accessibility` journey; the finding disappears when the check reports focus back on the trigger |
| A-02 | Low | Parent chore pool, reward requests, household | 2.5.8 Target size (minimum) | The "Show inactive ..." filter is a bare `input[type=checkbox]` measuring 13x13 CSS px | At least 24x24 CSS px, or a confirmed spacing exemption | Same journey; the automated check does not evaluate 2.5.8's spacing exception, so a fix may equally be a recorded exemption with the measured clearance |
| A-03 | Medium | Every route | 2.4.5 Multiple ways | Loading a route directly - a bookmark, a refresh, a shared link - lands on the role's start path instead. `RoleRouter` rewrites the URL to `/sign-in` while the session request is still pending, then redirects the now-signed-in viewer to `/chores` or `/overview` | The requested route opens once the session resolves | Same journey: it loads `/points` directly and reports where it landed |

Nothing else was found. Contrast, accessible names, text alternatives,
heading order, identifiers, ARIA references and focus visibility were clean
on every screen measured.

## Deliberately not covered

Stated so the clean result is not read as more than it is.

- No screen-reader listening pass with an actual screen reader. The audit
  checks the structures a screen reader depends on, not how they sound.
- No 1.4.11 non-text contrast, 1.4.10 reflow at 400 percent zoom, or
  prefers-reduced-motion behaviour. Narrow-width layout is covered separately
  by the layout probe.
- No check of error-message suggestions (3.3.3), language of parts (3.1.2),
  or timing (2.2.x); the product has no timed interaction.
- The audit reads the DOM after the page settles, so a transient state during
  loading is not measured.
