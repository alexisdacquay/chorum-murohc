# Interest Accrual Schedule

Operational runbook for `manage.py accrue_interest` (T053), the one entry
point that applies `_docs/interest-policy.md`. This document records what
the cron line should be; it is not evidence that any host has it installed.
Installing or editing a real host's scheduler needs separate explicit
authorisation (`_docs/tasks.md` T054's own rule) and is deliberately not
done as part of building the command itself.

## The cron line

Run once a week, shortly after the UTC week boundary this policy uses
(Sunday 00:00 UTC), guarded by `flock` so an overrunning previous invocation
can never overlap a new one:

    5 0 * * 0 flock -n /path/to/app/interest.lock \
      /path/to/app/.venv/bin/python /path/to/app/manage.py accrue_interest \
      --date "$(date -u -d yesterday +\%Y-\%m-\%d)" \
      >> /path/to/app/logs/interest.log 2>&1

- `flock -n` (non-blocking): if a run is still going when the next trigger
  fires, the new one exits immediately instead of queuing. Nothing is lost
  by skipping an overlap, because the command is already safe to run twice
  for the same date (see "Idempotency" in `_docs/interest-policy.md`) - the
  lock exists to avoid two processes writing at once, not to avoid a missed
  week.
- `--date` is always computed explicitly, never left to the command's own
  idea of "today": firing just after midnight Sunday and asking for
  "yesterday" names the completed week ending that Sunday.
- Create `logs/` first if it does not exist (`mkdir -p /path/to/app/logs`);
  `*.log` is already `.gitignore`d, so nothing here needs a repository
  change.
- Adjust `/path/to/app` to the real deployment path before installing this
  line anywhere.

## Log location

`logs/interest.log`, one line per run, written by the command itself
(`chorum_murohc/interest/management/commands/accrue_interest.py`):

    Interest accrual for 2026-09-07: 4 credited, 11 skipped, 0 failed.

Never a username, a balance, or any other per-child detail - those stay in
the audit trail (`chorum_murohc.interest.services.AUDIT_ACCRUE`, readable by
a parent once the audit API in T086 exists) and in the ledger itself, which
is exactly what `_docs/design.md`'s audit and sensitive-output contract asks
operational logs to leave out.

## Disable

Comment out or remove the cron line. The command does nothing on its own
between invocations; no other process depends on it running, and nothing
else needs to change to turn it off.

## Manual retry

Re-run the exact command for the date that needs it:

    python manage.py accrue_interest --date 2026-09-07

Safe to run for today, for a past date, or for a date already fully
accrued: a repeat run reports `0 credited` and the rest `skipped`, and
writes nothing.

## Missed-run recovery

If a week's run never fired (host down, cron misconfigured, deploy in
progress), run it by hand for the missed Sunday's date once the host is
back, using the manual retry command above. A late run still reads whatever
the balance is *when it runs*, not what it was on the missed date -
`_docs/interest-policy.md`'s "Missed week" section is explicit that there is
no backfill of a past balance and no catch-up multiplier.

## Scope during rollout or recovery

    python manage.py accrue_interest --date 2026-09-07 --household 3
    python manage.py accrue_interest --date 2026-09-07 --dry-run

`--household` bounds one run to a single household (useful when only one
family needs a manual recovery run); `--dry-run` reports the
credited/skipped counts a real run would produce, without writing anything,
for checking a date before committing to it.

## Why not Celery or Redis

`_docs/roadmap.md`'s technical-evolution section already names Celery for
"scheduled interest processing" as a future possibility, not a current
requirement. A once-a-week job built from one idempotent, per-user
transaction needs no queue, no broker, and no worker process; cron plus
`flock` is the smallest mechanism that satisfies T054's instruction to do
this "without adding Redis or Celery."
