# Accessibility Audit - current scope

> **Status:** Findings only (T094). Nothing here is fixed by the audit; each
> finding is a separate entry for someone to pick up.
>
> **Date:** 2026-09-09, re-run after issue #159 fixed the four findings this
> file previously recorded. **Standard:** WCAG 2.2 level AA.
> **Method:** `python3 -m browser_journeys.run_journeys . audit-accessibility`,
> headless Chrome 149, plus one keyboard pass and a source read.

## What was audited

Every screen the product currently builds, in a real browser, signed in as a
real child and a real parent: sign-in, child chores, points, rewards, levels
and creature, and parent overview, approvals, chore pool, reward requests,
household, activity and approval PIN. All thirteen are real screens; none is
a placeholder any more.

Per screen the audit ran: text alternatives (1.1.1), accessible names for
every visible control (4.1.2), heading structure and the main landmark
(1.3.1), duplicate identifiers and dangling ARIA references (4.1.1, 4.1.2),
positive tabindex (2.4.3), a visible focus indicator on every focusable
control (2.4.7), pointer target size (2.5.8), text contrast against the
computed effective background (1.4.3), page language (3.1.1) and document
title (2.4.2). Between 4 and 16 controls and 6 to 27 text elements were
measured on each screen; the run prints those counts so a silent no-op is
visible.

The keyboard pass covered the interaction most likely to trap a keyboard
user: opening a modal dialog, checking focus enters it, closing it with
Escape, and checking where focus lands.

## Findings

None. `audited every built screen; 0 finding(s)` across all thirteen
screens, and the keyboard pass reports focus back on the trigger after
Escape.

## Fixed by issue #159

The four findings this file previously recorded, kept here as the record of
what was wrong and how it was checked closed.

| Id | Severity | Screen | Criterion | What was wrong | Fix |
| --- | --- | --- | --- | --- | --- |
| A-01 | Medium | Every screen with a dialog; observed on child chores | 2.4.3 Focus order | Closing a dialog with Escape left focus on `body`. Radix's own close-focus restoration only ever focuses the DOM node under its own `<DialogTrigger>`, and nothing in this product renders one - every screen opens its dialog from a plain button tied to local state instead, so that restoration was a no-op on every dialog in the product | The shared `Dialog` wrapper (`frontend/src/components/ui/dialog.tsx`) now remembers what was focused before it opened and restores focus there itself on every close path (Escape, an outside click, or a Close control), fixed once for every dialog rather than at each call site |
| A-02 | Low | Parent chore pool, reward requests, household | 2.5.8 Target size (minimum) | The "Show inactive ..." filter was a bare `input[type=checkbox]` measuring 13x13 CSS px; the reward-requests screen's checkbox also carried a class of its own that no rule styled | Every "Show inactive ..." checkbox now shares one `chore-pool-filter` class, sized to 24x24 CSS px in `styles.css` |
| A-03 | Medium | Every route | 2.4.5 Multiple ways | Loading a route directly - a bookmark, a refresh, a shared link - landed on the role's start path instead. `RoleRouter` rewrote the URL to `/sign-in` while the session request was still pending, because the role reads as unresolved (not yet signed-out) until it settles | The URL-rewrite effect now waits for the session to settle before acting, so the requested route opens once the real role resolves |
| A-04 | Low | Parent overview | 1.3.1 Info and relationships | Each child's card heading was an `h3` directly under the screen's `h1`, so the level jumped by two | The card heading is now an `h2`, directly under the `h1` |

Nothing else was found either time. Contrast, accessible names, text
alternatives, identifiers, ARIA references and focus visibility remain clean
on every screen measured, and heading order is now clean everywhere.

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
