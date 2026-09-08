# Retention Policy

> **Status:** Approved product decision for task T020. The decision is recorded
> in issue
> [#20 comment 5588419413](https://github.com/alexisdacquay/chorum-murohc/issues/20#issuecomment-5588419413)
> by `alexisdacquay`, product owner, on 2026-09-08. It supersedes the
> never-hard-delete proposal in
> [comment 5587967903](https://github.com/alexisdacquay/chorum-murohc/issues/20#issuecomment-5587967903),
> which was rejected. This document is policy only. It implements no endpoint,
> model field, migration, service, permission, interface, or audit view, and it
> changes no merged behaviour.

This policy answers one question for every delete action in the product: what a
parent may deactivate, edit or delete, and what happens to the history that
references it. The tasks listed in [Inheriting issues](#inheriting-issues)
implement it. They must not invent an answer this document already gives, and
they must not take authority this document does not grant.

The words **must**, **must not**, **allow** and **deny** are normative.
Anything not explicitly allowed is denied.

## Relation to the approved permission matrix

The authority ceiling comes unchanged from the `Trust Boundaries and Permission
Matrix` section of [`design.md`](design.md), approved in issue
[#18](https://github.com/alexisdacquay/chorum-murohc/issues/18). This document
widens nothing in it and amends no part of it. Where that matrix denies an
actor, this document also denies that actor; where the matrix says "deny until
approved retention policy, then only the exact own-household transition", the
transitions named here are those exact transitions and no others.

Two invariants of that matrix are restated because every rule below depends on
them: product endpoints never honour Django `is_staff`, `is_superuser`, groups
or model permissions as a household-role bypass, and a frontend route, hidden
control or disabled button is never an authorisation control.

## Vocabulary

- **Deactivate**: reversible. The row and every row referencing it stay, with
  attribution intact. For a member this sets `is_active=False`; for a chore it
  sets the chore's inactive state owned by T034.
- **Reactivate**: the inverse of deactivate. Available for any deactivated
  member or chore.
- **Edit**: change stored fields on a row that continues to exist.
- **Delete**: real removal of the row from the product database. It is not a
  disguised deactivation and it is not reversible.
- **Anonymise**: not a state in this product. The rejected proposal offered it;
  the approved decision replaced it with delete. No task implements it.
- **Deny**: perform no read and no mutation, and reveal no protected resource
  data. A denied target must be indistinguishable from a missing one.

## Authority: who may act

Only a **parent with one live membership in the target's household** may
deactivate, reactivate, edit or delete a member or a chore of that household.
Every one of the following denies:

| Case | Result |
| --- | --- |
| Unauthenticated caller | Deny. No retention operation and no retention-related data, not even the existence of a target. |
| Authenticated user with `is_active=False` | Deny. Deactivation takes effect on the next request even if the session persists. |
| Child in the target's household | Deny absolutely, for deactivate, reactivate, edit and delete, of members and of chores, whatever any interface shows. |
| Unknown, missing, unsupported or corrupt membership role | Deny. Only exactly `parent` allows. |
| No resolved household context, or more than one candidate household | Deny. Roles never union across households. |
| Stale or deleted membership | Deny. The membership is read again on the request and again inside the writing transaction. |
| Target in another household | Deny, indistinguishable from a missing resource. The response must not disclose that the household, member or chore exists. |
| Actor acting on their own account | Deny. Self-deactivation and self-deletion are denied; a parent cannot remove or disable themselves. |

The actor's membership, the target's household and the target's current state
are revalidated **inside the writing transaction**, immediately before the
write. A check performed only at request admission is not sufficient.

Repeat calls are idempotent. Deleting an already deleted target, or
deactivating an already deactivated one, changes nothing further and emits **no
second audit event**.

## Household member

### Deactivate and reactivate a member

- Allowed for a parent, on another member of the same household.
- Sets `is_active=False`. The member cannot log in and every protected request
  fails closed from the next request onward.
- Every referencing row stays exactly as it is: memberships, submissions in any
  state, ledger entries, rewards, progression rows and creature selection. All
  attribution stays named.
- Balance, interest accrual as recorded, level and creature state are frozen as
  they stand. They are never recalculated, transferred or zeroed by
  deactivation.
- Reactivation restores login and is otherwise a no-op on history.
- Deactivation is the softer, reversible option and remains available for a
  member who should keep their history but lose access.

### Edit a member

- Allowed for a parent, on a member of the same household. Account fields and
  the product role are in scope, owned by
  [#22](https://github.com/alexisdacquay/chorum-murohc/issues/22).
- A role change takes effect on the next request. It never rewrites the
  attribution of anything already recorded.
- A role change that would leave the household without an active parent is
  denied; see [Last active parent](#last-active-parent).

### Delete a member

Deletion is real, and the product owner accepted its consequence explicitly.

- Allowed for a parent, on another member of the same household.
- Deleting a member removes **that member's product state**: their memberships,
  their submissions in any state, their ledger entries, their rewards, their
  progression rows and their creature selection.
- **Deleting a child therefore removes that child's points, level and
  creature.** They are gone and there is no recovery path and no transfer. This
  consequence is the recorded decision of the product owner in
  [comment 5588419413](https://github.com/alexisdacquay/chorum-murohc/issues/20#issuecomment-5588419413):
  "delete (and log)".
- No other member is affected. Another child's balance, level, creature and
  history are untouched, and a chore that the deleted member had submitted
  stays in the pool.
- The household itself is never deleted. `AuditEvent.household` is `PROTECT` in
  merged code and no household-deletion operation exists in scope.
- The audit trail of the deleted member survives the deletion; see
  [Logging](#logging) and
  [The audit trail outlives what it describes](#the-audit-trail-outlives-what-it-describes).

## Chore

### Create and edit a chore

- Allowed for a parent, in their own household.
- A parent may change a chore's **name** and its **points**.
- An edit affects only submissions created after it. Points already credited
  keep the amount recorded at approval time, because the ledger stores the
  credited value and a decided submission carries its own immutable name and
  point snapshot (T041). A later edit never rewrites history.

### Deactivate and reactivate a chore

- Allowed for a parent, in their own household.
- A deactivated chore is hidden from the child chore browser and refused for
  new submissions.
- History is kept. Existing submissions stay decidable and readable, and the
  chore remains resolvable from a decided submission.
- Reactivation returns the chore to the child browser.

### Delete a chore

- Allowed for a parent, in their own household. Deletion is real.
- The chore row goes, and its **pending** submissions go with it. They leave no
  entry in any parent approval queue and can no longer be approved, so no point
  can be credited for a deleted chore after its deletion.
- **Decided** submissions, approved or rejected, survive. They keep their own
  immutable name and point snapshot, and their reference to the chore becomes
  null rather than dangling.
- Ledger entries are untouched. A point credited for a chore that was later
  deleted stays credited, at the amount recorded at approval time.

## Never rewritten

No retention action edits a ledger amount, a decided submission's name or point
snapshot, or an audit event. Ledger entries and audit events remain append-only
through application services, exactly as
[#38](https://github.com/alexisdacquay/chorum-murohc/issues/38) and the merged
audit model require.

Member deletion is the **only** path that removes ledger rows. It removes whole
rows belonging to the deleted member only, and it is a removal, not an edit: no
surviving entry's amount, reason or timestamp changes. The append-only rule of
#38 stands unchanged for every other caller, and no other operation anywhere in
the product may delete a ledger row.

## Last active parent

A household must always keep at least one active, non-deleted parent who can
log in. Deleting, deactivating or demoting the last such parent is **denied**,
and the check runs inside the same transaction as the write it guards, so two
concurrent requests cannot each pass the check and together empty the
household.

The guard covers all three operations: `account.delete`, `account.deactivate`
and `account.role_change` to `child`. Nothing in the approved decision asks for
the ability to leave a household without an administrator, and doing so would
strand every remaining member.

## Logging

Everything is logged. Every create, edit, deactivate, reactivate and delete
writes exactly one audit event. The audit trail is **backend evidence only**:
this policy exposes nothing in the interface. The parent-facing audit view
stays with [#86](https://github.com/alexisdacquay/chorum-murohc/issues/86), and
the merged permission matrix still limits it to same-household parents.

Action codes:

| Action code | Emitted by |
| --- | --- |
| `account.create` | Creating a household account |
| `account.update` | Editing account fields |
| `account.role_change` | Changing a member's product role |
| `account.deactivate` | Deactivating a member |
| `account.reactivate` | Reactivating a member |
| `account.delete` | Deleting a member |
| `chore.create` | Creating a chore |
| `chore.update` | Editing a chore's name or points |
| `chore.deactivate` | Deactivating a chore |
| `chore.reactivate` | Reactivating a chore |
| `chore.delete` | Deleting a chore |

Every event carries:

- the acting parent's **internal identifier** in `context`, as an integer;
- the target type and target identifier;
- the before and after state of what changed.

A `chore.update` event that changes points records **both** the old and the new
point value, so the value in force when any submission was made stays provable.

A deletion event records **counts only**: the number of submissions removed,
the number of ledger entries removed, the points total removed, the level, the
creature and the number of memberships removed. It records no username, no
email, no display name and no free text. The sensitive-output contract in
[`design.md`](design.md) applies in full: no password, PIN, session, cookie,
CSRF or token value, and no household content, may appear in audit context,
logs, errors or test output.

## The audit trail outlives what it describes

A deletion that erases its own evidence is not an acceptable implementation of
this policy. The merged audit schema already satisfies this and **needs no
change**:

- `AuditEvent.household` is `on_delete=PROTECT`, and no household deletion is
  in scope.
- `target_type` and `target_id` are plain `CharField`s, not foreign keys, so
  deleting a member or a chore cannot touch them. The event still names its
  target after the target is gone.
- `AuditEvent.actor` is `on_delete=SET_NULL, null=True`. Deleting the actor of
  earlier events is allowed: the events stay readable and only `actor_id`
  becomes null. The merged test
  `test_household_is_protected_and_actor_deletion_only_nulls_actor` proves this.
- Because `actor_id` can null, producers must additionally write the acting
  parent's stable **internal identifier** into `context`, so attribution
  survives the actor's own deletion. An internal integer identifier is
  permitted by the audit and sensitive-output contract, which forbids raw
  usernames and email addresses but not internal identifiers.

A dedicated audit actor-snapshot column is **not** adopted. If it is ever
preferred, it is an audit-app migration with no owning task today and needs a
new issue, groomed and approved, before any code is written. This policy does
not require one.

No database-level or cryptographic guarantee is claimed here. Household
isolation and audit immutability remain application-enforced, and privileged
database access remains the accepted residual risk recorded in
[`design.md`](design.md).

## Visibility

- **Same-household parents** see active and deactivated members and chores.
  Deactivated ones are labelled with their state and appear only behind an
  explicit filter; default lists show active members and chores.
- **A deleted member or chore disappears from every product surface.** It is in
  no list, no filter, no summary and no queue. Only the audit trail remembers
  it, and only through
  [#86](https://github.com/alexisdacquay/chorum-murohc/issues/86), which
  exposes counts and identifiers rather than the deleted person's details.
- **Children** see their own data only, unchanged by this policy. A child never
  sees a deactivated or deleted chore, and never sees another child's data.
- **Nobody, anywhere** sees data from another household, or the former
  username, name or email address of a deleted member. Those values are gone
  with the row and are never written into an audit event, a log line or an
  error message.

## Awkward cases, decided

1. **Deleting a chore that has pending submissions.** The pending submissions
   are removed with the chore. They leave no entry in any parent approval
   queue, so no stale row can be approved afterwards. Decided submissions
   survive with their name and point snapshots and a null chore reference, and
   every ledger entry is kept.
2. **Deleting a child who has pending submissions.** That child's submissions
   in every state are removed with the child, together with their ledger
   entries, rewards, progression rows and creature selection, so their points,
   level and creature are gone. No entry for them remains in any parent queue.
   No other member's submissions or ledger entries are touched. This is the one
   case where decided submissions and ledger rows do not survive, because they
   belong to the deleted member and the product owner accepted that loss.
3. **A points edit between submission and approval.** Approval credits the
   submission's own point snapshot, taken when the child submitted, not the new
   value. The `chore.update` event records both the old and the new value, so
   the two amounts are always reconcilable.
4. **Deleting a member who is the actor of existing audit events.** Allowed.
   The events stay readable, `actor_id` becomes null, and the internal actor
   identifier already written into `context` preserves the attribution.
5. **No deletion orphans history.** Every surviving row either goes with the
   row it references, or holds a **nullable** reference plus its own snapshot
   of what it needs. No non-nullable reference is left dangling, and no
   surviving row points at a row that no longer exists.
6. **A repeated delete.** The second call finds nothing to delete, changes
   nothing and emits no second audit event. The same holds for a repeated
   deactivate on an already-inactive target.
7. **The last active parent.** Delete, deactivate and demote are all denied for
   them, inside the transaction that checks it. Deactivation of any other
   parent remains available.
8. **A parent acting on themselves.** Denied for delete and for deactivate,
   whether or not another active parent exists.

## Inheriting issues

Each issue below implements part of this policy and must not depart from it.

| Issue | What it inherits |
| --- | --- |
| [#21](https://github.com/alexisdacquay/chorum-murohc/issues/21) Account directory API | Parent-only own-household listing and creation; `account.create` events; deactivated members labelled and filtered |
| [#22](https://github.com/alexisdacquay/chorum-murohc/issues/22) Account and role update | Edit and role-change rules; transactional last-active-parent guard; `account.update` and `account.role_change` events |
| [#23](https://github.com/alexisdacquay/chorum-murohc/issues/23) Account removal API | Deactivate, reactivate and real delete exactly as decided here; idempotent retry; self-action denial; deletion counts in the audit event |
| [#24](https://github.com/alexisdacquay/chorum-murohc/issues/24) Account directory interface | Active-by-default lists with an explicit inactive filter; no removal control |
| [#25](https://github.com/alexisdacquay/chorum-murohc/issues/25) Account and role editing | Edit surfaces and last-active-parent feedback; no removal surface |
| [#26](https://github.com/alexisdacquay/chorum-murohc/issues/26) Account removal interface | Destructive confirmation stating that a deleted child's points, level and creature are gone permanently |
| [#34](https://github.com/alexisdacquay/chorum-murohc/issues/34) Chore schema | Active and inactive chore state; nullable chore reference on decided submissions |
| [#35](https://github.com/alexisdacquay/chorum-murohc/issues/35) Chore API | Chore create, edit, deactivate, reactivate and delete rules; `chore.*` events; child denial |
| [#38](https://github.com/alexisdacquay/chorum-murohc/issues/38) Points ledger | Append-only for every caller; member deletion is the only row removal, and it is not an edit |
| [#39](https://github.com/alexisdacquay/chorum-murohc/issues/39) Balances and history | Balances derived from surviving ledger rows; a deleted member has no balance to show |
| [#86](https://github.com/alexisdacquay/chorum-murohc/issues/86) Audit view | The only surface where a deleted member or chore is still remembered; parent-only, own-household, redacted, read-only |

Related but not decided here: submission snapshots
[#41](https://github.com/alexisdacquay/chorum-murohc/issues/41), PIN storage
and destruction [#30](https://github.com/alexisdacquay/chorum-murohc/issues/30),
the parent overview [#84](https://github.com/alexisdacquay/chorum-murohc/issues/84),
and the audit interface
[#87](https://github.com/alexisdacquay/chorum-murohc/issues/87).

## Out of scope

- Every endpoint, model field, migration, service and interface named above.
  This document decides behaviour; those issues build it.
- The permission matrix [#18](https://github.com/alexisdacquay/chorum-murohc/issues/18),
  the permission primitive
  [#19](https://github.com/alexisdacquay/chorum-murohc/issues/19) and the
  security recheck [#95](https://github.com/alexisdacquay/chorum-murohc/issues/95).
- A dedicated audit actor column, statutory data-subject erasure and export
  requests, backup expiry and operational-log retention. No issue exists for
  any of them, none is required by this policy, and one must be filed and
  approved before any is built.
