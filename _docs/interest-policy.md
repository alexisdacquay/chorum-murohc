# Interest Policy

> **Status:** Approved. Decided by the product owner directly in issue #49's
> feature brief (2026-09-08). This document turns that decision into exact
> arithmetic (T050) and supersedes the monthly-rate, daily-accrual,
> level-bonus draft in `_docs/plan.md`, which was never implemented.

## The rule

Once a week, every eligible child's ledger balance earns interest:

- **Rate**: 2 percent of the balance held at the moment the accrual runs
  (the "closing balance").
- **Frequency**: once a week, not daily. There is no compounding within a
  week: the calculation happens once, against the current balance, never
  once a day against a running total.
- **Rounding**: floor to the nearest whole point, `balance * 2 // 100`,
  integer arithmetic only. Never a float.
- **Cap**: at most 20 points from one accrual, however large the balance.
- **Floor**: a balance of zero or less earns nothing. There is no negative
  interest and no interest charged on a debt.
- **Level**: none. Every child earns the same 2 percent; there is no
  per-level bonus or multiplier. (The original T050-T054 backlog briefs
  assumed a level-scaled rate carried over from `_docs/plan.md`'s draft;
  issue #49's feature brief replaced that with this flat rule, and this
  document records the replacement, not the superseded draft.)

Implemented as `chorum_murohc.interest.calculator.weekly_interest`, a pure
integer function with no database access and no clock:

    weekly_interest(balance) = 0                           if balance <= 0
                              = min(balance * 2 // 100, 20) otherwise

## Worked examples

| Balance | Exact 2% | Rounded down | After the 20-point cap | Ledger entry |
| --- | --- | --- | --- | --- |
| -30 | n/a | n/a | n/a | none (balance is at or below zero) |
| 0 | n/a | n/a | n/a | none (balance is at or below zero) |
| 25 | 0.50 | 0 | 0 | none (`LedgerEntry` forbids a zero amount) |
| 50 | 1.00 | 1 | 1 | +1, reason `interest` |
| 999 | 19.98 | 19 | 19 | +19, reason `interest` |
| 1,000 | 20.00 | 20 | 20 | +20, reason `interest` |
| 1,001 | 20.02 | 20 | 20 | +20, reason `interest` |
| 50,000 | 1,000.00 | 1,000 | 20 | +20, reason `interest` |

A balance between 1 and 49 always rounds down to zero and never produces a
ledger entry at all: this is a direct consequence of the rounding rule
above, not a separate exception, and it happens to line up with
`LedgerEntry`'s existing "amount is never zero" database constraint
(`chorum_murohc/ledger/models.py`), so there is nothing extra to enforce for
it.

## When it runs

- **Balance read**: the ledger balance
  (`chorum_murohc.ledger.services.balance_for_user`) at the moment the
  accrual service actually runs. There is no historical "balance as of last
  Sunday" snapshot kept anywhere: the policy is defined on the balance held
  right now, which is what makes running the job promptly after the week
  boundary matter in practice. Running it late simply uses whatever the
  balance is by the time it runs; see "Missed week" below.
- **Time zone**: `config/settings.py` sets `TIME_ZONE = 'UTC'`, and every
  date this policy and its command use is a UTC calendar date. There is no
  other time zone to convert to or from.
- **Cadence**: once a week. `_docs/interest-schedule.md` records the actual
  cron line and day (currently Sunday).
- **Missed week**: there is no backfill and no catch-up multiplier. A week
  the job did not run for is a week with no interest for that week.
  `_docs/interest-schedule.md`'s command can be re-run for the missed date
  to accrue it late, but two different weeks are never folded into one
  accrual, and a late run still reads whatever the balance is when it
  actually runs, not what it was on the missed date.

## Idempotency

At most one ledger entry per user per accrual date, enforced by the
existing `LedgerEntry` unique constraint on `(user, idempotency_key)`
(`chorum_murohc/ledger/models.py`), keyed as `interest:<accrual-date>`.
Running the accrual command twice for the same date is a no-op the second
time: `chorum_murohc.interest.services.accrue_interest_for_user` checks for
an existing entry for that user and date before writing anything, and
returns the existing row unchanged when it finds one. This is proved by a
repeat-execution test in `chorum_murohc/interest/test_services.py` and
`chorum_murohc/interest/test_accrue_interest_command.py`.

## Eligibility

Every currently active (`is_active=True`) child membership, in every
household, unless the command is scoped to one household with
`--household`. A parent membership never accrues interest: only a child
holds a spendable balance in this product (`_docs/design.md`'s permission
matrix: balance and ledger history are child-only by default).

## Approval

Decided by the product owner directly in the T049 feature brief (issue #49
comment, 2026-09-08):

> Interest policy, decided: 2 percent of the closing balance, once a week,
> rounded down to whole points, capped at 20 points a week. It applies to
> the balance held, it does not compound within a week, and it is skipped
> entirely for a zero or negative balance.

This document is that decision written out as exact arithmetic. It does not
reopen it; a future change to the rate, cadence, cap, or eligibility needs
its own product-owner decision recorded the same way.
