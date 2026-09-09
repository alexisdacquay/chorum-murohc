# Retention Policy

What a parent may deactivate, edit or delete, and what happens to the history
that references it. Approved on issue #20, 2026-09-08. Deactivate is reversible;
delete really removes the row. Anything not allowed here is denied.

## Who may act

Only a parent with one live membership in the target's household may deactivate,
reactivate, edit or delete a member or a chore of that household. Everything
else denies: an unauthenticated caller, an inactive user, any child, an unknown
or missing role, no resolved household or more than one candidate, a stale
membership, a target in another household (indistinguishable from a missing
one), and the actor acting on themselves. Membership, household and target state
are revalidated inside the writing transaction. A repeat call changes nothing
and emits no second audit event.

## Members

- Deactivating sets `is_active=False`, so the member cannot log in from the next
  request. Memberships, submissions, ledger entries, rewards, progression and
  creature selection stay, frozen and attributed. Reactivation restores login.
- Editing covers the username and the product role, never a password. A role
  change takes effect on the next request and never rewrites recorded
  attribution.
- Resetting a member's password (issue #129) needs the "Who may act" floor
  above, plus the acting parent's own PIN or account password in the same
  request - one more factor than every other action here, because it is the
  one action that hands someone else's credential to the caller's own typing.
  A reset on a parent target also clears that parent's PIN and any lockout, per
  `_docs/approval-authentication.md`. A parent's own password change is a
  separate, self-service action and is not covered by this policy at all: it
  needs only the caller's own current password, never another parent's say-so.
- Deleting a member removes their memberships, submissions, ledger entries,
  rewards, progression rows and creature selection, so deleting a child removes
  their points, level and creature permanently. No other member is touched.
- A household must always keep one active, non-deleted parent who can log in.
  Deleting, deactivating or demoting the last one is denied, inside the same
  transaction as the write it guards.

## Chores

- A parent may create a chore and change its name and points in their own
  household. An edit affects only later submissions: a decided one keeps its own
  name and point snapshot, and the ledger keeps the credited amount.
- A deactivated chore is hidden from the child browser and refused for new
  submissions; existing submissions stay readable and decidable.
- Deleting a chore is real, and its pending submissions go with it. Decided
  submissions survive with their snapshots and a null chore reference, and every
  ledger entry is untouched.

## History

No retention action edits a ledger amount, a decided submission's snapshot or an
audit event. Member deletion is the only path that removes ledger rows, and it
removes whole rows of that member, never editing a surviving one.

Every create, edit, deactivate, reactivate and delete writes exactly one audit
event, `account.create`, `account.update`, `account.role_change`,
`account.deactivate`, `account.reactivate`, `account.delete` and the matching
five `chore.*` codes, carrying the acting parent's internal integer id in
`context`, the target type and id, and the before and after of what changed. A
deletion records counts only, with no names or emails.

The trail outlives what it describes: `AuditEvent.household` is `PROTECT`,
`target_type` and `target_id` are char fields, and `actor` is `SET_NULL`.
Parents see active and deactivated members and chores, the deactivated ones
labelled behind an explicit filter. A deleted member or chore is gone from every
surface; only the audit view remembers it, by identifier.
