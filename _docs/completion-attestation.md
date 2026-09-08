# Completion Attestation Policy

> **Status:** Approved product decision for task T040. The proposal is recorded
> in issue
> [#40 comment 5589068054](https://github.com/alexisdacquay/chorum-murohc/issues/40#issuecomment-5589068054)
> and approved as proposed in
> [comment 5591127275](https://github.com/alexisdacquay/chorum-murohc/issues/40#issuecomment-5591127275)
> by the orchestrator under the product owner's standing instruction, on
> 2026-09-08. This document is policy only. It implements no model, endpoint,
> service, interface or migration. Plan coverage: `TC-01`, `TC-07`.

This policy answers one question: what a child asserts when they submit a
chore without photo proof, what counts as a duplicate, what may happen to a
submission afterwards, and what is audited. The tasks listed in
[Inheriting issues](#inheriting-issues) implement it. They must not invent an
answer this document already gives, and they must not take authority this
document does not grant.

The words **must**, **must not**, **allow** and **deny** are normative.
Anything not explicitly allowed is denied.

## Relation to the approved permission matrix and the retention policy

The authority ceiling comes unchanged from the `Trust Boundaries and Permission
Matrix` section of [`design.md`](design.md), approved in issue
[#18](https://github.com/alexisdacquay/chorum-murohc/issues/18). This document
widens nothing in it and amends no part of it: submission remains self only,
for an active own-household chore only, and a parent never submits for a
child. Every decision below on what happens when a chore or a child changes
underneath a pending submission restates
[`retention-policy.md`](retention-policy.md) for task T020; it does not amend
that policy, and where the two could be read to differ, the retention policy
governs.

## 1. What the child asserts

A submission is the child's own claim that the work is done. The server
cannot independently prove physical completion, and no surface, wording, log
or audit context may describe a submission as proof.

The child-facing wording, rendered by
[#43](https://github.com/alexisdacquay/chorum-murohc/issues/43), is exactly:

- Heading: `Finished this chore?`
- Chore name and points, for example: `Tidy your room - 20 points`
- Confirmation line: `I have finished this chore. A grown-up will check it before I get the points.`
- Buttons: `Yes, I finished it` and `Not yet`
- Waiting state: `Waiting for a grown-up to check it.`

Child screens use short words a six year old reads. The words attest,
declare, certify and submission are banned from child-facing text.

Submission requires a true confirmation flag as input. The server must reject
a submission that does not carry it; there is no way to submit by omission or
by a default value.

## 2. Duplicates

At most one open (`pending`) claim may exist per child per chore.

- A second submission for a chore while that child already has a pending
  claim on it is refused with a compact message meaning "already waiting to
  be checked", and creates no row.
- Two different children may each hold their own pending claim on the same
  chore at the same time, because the chore pool is shared and nothing about
  a pending claim reserves the chore.
- An idempotent retry that reuses the same submission idempotency key returns
  the existing row. It is not a duplicate and does not create a second row or
  a second audit event.

## 3. Repeats over time

Repeat submissions of the same chore by the same child, over time, are
allowed without limit. There is no daily cap and no cooldown between one
decided claim and the next. The only limiting window is the duplicate rule in
[section 2](#2-duplicates): a state, not a clock. It lasts exactly as long as
that child's claim for that chore is `pending`.

A per-day cap or cooldown would need a household timezone and a midnight rule
this product does not have. Frequency policing is left to the deciding
parent, and every repeat still costs one parent PIN decision.

## 4. Pending submissions: withdrawal

While their own submission is `pending`, the submitting child may withdraw it.
No other change is allowed: a pending submission may never be edited, by the
child or by anyone else.

- Withdrawal is a state change to `withdrawn`, never a deletion. The row
  stays, credits nothing, leaves the parent's pending queue, and frees the
  duplicate slot in [section 2](#2-duplicates) so the same child may submit
  that chore again.
- If a parent decides the submission (approves or rejects it) before the
  child's withdrawal request reaches the server, the parent's decision wins.
  The withdrawal attempt fails with a stale-state error and changes nothing.

## 5. Rejection

On rejection the child sees: the chore name, when they submitted it, the
label `Not approved`, and the parent's note if one was given. No points are
credited and no scolding wording is shown anywhere in the product.

Resubmission is immediate: a rejected submission is decided, so it is no
longer `pending`, and the child may submit that chore again the moment they
choose to, subject only to the duplicate rule in
[section 2](#2-duplicates), which no longer applies once the prior claim is
`rejected` rather than `pending`.

The rejection reason is optional free text, at most 200 characters. It is
visible only to the submitting child and to parents in that same household. A
rejection reason is household content: it must never appear in audit context,
in operational or application logs, or in an error message. Audit and log
producers may record only whether a reason was given (a boolean), never its
text.

## 6. The chore or the child changes underneath a pending submission

This section restates [`retention-policy.md`](retention-policy.md) as it
applies to a submission in flight. It decides nothing new.

- **Chore deactivated.** Existing pending claims on it stay pending,
  decidable, and payable at their own snapshot if approved. Only new
  submissions against that chore are refused, per the deactivation rule in
  `retention-policy.md`.
- **Chore edited (points changed).** The claim keeps the point snapshot taken
  at submission time. Approval credits that snapshot, never the chore's
  current value, exactly as `retention-policy.md` section
  "Create and edit a chore" decides.
- **Chore deleted.** A pending claim on a deleted chore is removed together
  with the chore and can never be approved, exactly as `retention-policy.md`
  decides for member and chore deletion. A decided (approved or rejected)
  claim survives with its own name and point snapshot and a null chore
  reference. The parent-facing delete confirmation must state how many
  pending claims disappear; that confirmation surface is owned by
  [#35](https://github.com/alexisdacquay/chorum-murohc/issues/35) and
  [#37](https://github.com/alexisdacquay/chorum-murohc/issues/37), not by this
  document.
- **Child deactivated.** Their pending claims stay decidable. Deactivation
  removes the ability to log in; it does not undo finished work already
  submitted for review.
- **Child deleted.** All of that child's submissions, in every state, are
  removed with them, per `retention-policy.md` and the T020 product decision.
  This document grants no exception to that rule.

## 7. States and transitions

There are exactly four states: `pending`, `approved`, `rejected`,
`withdrawn`.

Exactly four transitions are legal:

| From | To | Actor |
| --- | --- | --- |
| (none) | `pending` | The submitting child, creating the submission |
| `pending` | `approved` | One PIN-verified parent in the household |
| `pending` | `rejected` | One PIN-verified parent in the household |
| `pending` | `withdrawn` | The submitting child only |

Every other transition is denied, including: reversing a decision, deciding
an already-decided submission a second time, editing a `pending` submission's
content, and editing any `approved`, `rejected` or `withdrawn` row. A row
leaves the product only through the two retention deletions named in
[section 6](#6-the-chore-or-the-child-changes-underneath-a-pending-submission)
(chore deletion of a pending row, member deletion of all of a child's rows).

A mistaken approval is not reversible in current scope. The point ledger is
append-only, per [`design.md`](design.md) and
[#38](https://github.com/alexisdacquay/chorum-murohc/issues/38), and no task
in the current plan owns a compensating entry. Reversing a mistaken approval
is out of scope; see [Out of scope](#out-of-scope).

## 8. Audit

Exactly one audit event is emitted per state change, and no audit event is
emitted for anything that changes no state (a refused duplicate, a rejected
withdrawal race, or any other denial).

| Action code | Emitted on | Actor |
| --- | --- | --- |
| `submission.create` | A child creates a `pending` submission | The submitting child |
| `submission.withdraw` | A child withdraws their own `pending` submission | The submitting child |
| `submission.approve` | A parent approves a `pending` submission | The verified parent |
| `submission.reject` | A parent rejects a `pending` submission | The verified parent |

Approval and rejection are attributed to the verified parent, never to the
child whose device may have hosted the PIN-entry flow, consistent with the
PIN and Approval Invariants in [`design.md`](design.md).

Every event carries the submission as its target, plus:

- the chore identifier;
- the point snapshot recorded on the submission; and
- the acting parent's internal identifier, for `submission.approve` and
  `submission.reject` only, per the audit contract in
  [`design.md`](design.md).

`submission.approve` additionally carries the credited point amount and its
ledger reference. `submission.reject` additionally carries a boolean for
whether a reason was given, never the reason text itself (see
[section 5](#5-rejection)).

No refused duplicate and no failed PIN attempt emits an event, because
neither changes any submission's state. The audit trail will therefore not
show, for example, that a child was refused five times in a row for the same
open claim; that trail gap is accepted, matching the equivalent PIN-attempt
behaviour in [`design.md`](design.md).

## Inheriting issues

Each issue below implements part of this policy and must not depart from it.

| Issue | What it inherits |
| --- | --- |
| [#41](https://github.com/alexisdacquay/chorum-murohc/issues/41) Submission schema and snapshots | Four states; point and name snapshot taken at submission; nullable chore reference on decided rows |
| [#42](https://github.com/alexisdacquay/chorum-murohc/issues/42) Submission API, confirmation input and idempotency | Required true confirmation flag; duplicate rule; idempotent retry by key |
| [#43](https://github.com/alexisdacquay/chorum-murohc/issues/43) Child submission interaction | The six verbatim child-facing strings; banned words |
| [#44](https://github.com/alexisdacquay/chorum-murohc/issues/44) Pending-approvals API | Household-scoped pending queue only |
| [#45](https://github.com/alexisdacquay/chorum-murohc/issues/45) Atomic approval and rejection | The four legal transitions; rejection never credits; approval credits the snapshot exactly once |
| [#46](https://github.com/alexisdacquay/chorum-murohc/issues/46) Approval and rejection API | `submission.approve` and `submission.reject` events attributed to the verified parent |
| [#47](https://github.com/alexisdacquay/chorum-murohc/issues/47) Child-device parent approval | PIN-verified parent decision from a child device; no elevation of the child session |
| [#48](https://github.com/alexisdacquay/chorum-murohc/issues/48) Parent approval queue | Rejection reason visible to that child and household parents only; optional, at most 200 characters |

Related but not decided here: PIN identification, length, retry and lockout
([#29](https://github.com/alexisdacquay/chorum-murohc/issues/29),
[#30](https://github.com/alexisdacquay/chorum-murohc/issues/30) to
[#33](https://github.com/alexisdacquay/chorum-murohc/issues/33)); chore state
and delete-confirmation counts
([#34](https://github.com/alexisdacquay/chorum-murohc/issues/34),
[#35](https://github.com/alexisdacquay/chorum-murohc/issues/35),
[#37](https://github.com/alexisdacquay/chorum-murohc/issues/37)); the points
ledger ([#38](https://github.com/alexisdacquay/chorum-murohc/issues/38),
[#39](https://github.com/alexisdacquay/chorum-murohc/issues/39)); the audit
view ([#86](https://github.com/alexisdacquay/chorum-murohc/issues/86)); the
permission matrix
([#18](https://github.com/alexisdacquay/chorum-murohc/issues/18)); the
retention policy
([#20](https://github.com/alexisdacquay/chorum-murohc/issues/20)); the
permission primitive
([#19](https://github.com/alexisdacquay/chorum-murohc/issues/19)); and the
independent security recheck
([#95](https://github.com/alexisdacquay/chorum-murohc/issues/95)).

## Out of scope

- Every endpoint, model field, migration, service and interface named above.
  This document decides behaviour; those issues build it.
- Reversing a mistaken approval, per-day caps, cooldowns, scheduling, streaks,
  and the roadmap's future photo-proof item. No issue exists for any of them,
  none is required by this policy, and one must be filed and approved before
  any is built.
- PIN identification, length, retry and lockout
  ([#29](https://github.com/alexisdacquay/chorum-murohc/issues/29) with
  [#30](https://github.com/alexisdacquay/chorum-murohc/issues/30) to
  [#33](https://github.com/alexisdacquay/chorum-murohc/issues/33)); chore
  state and delete-confirmation counts
  ([#34](https://github.com/alexisdacquay/chorum-murohc/issues/34),
  [#35](https://github.com/alexisdacquay/chorum-murohc/issues/35),
  [#37](https://github.com/alexisdacquay/chorum-murohc/issues/37)); the ledger
  ([#38](https://github.com/alexisdacquay/chorum-murohc/issues/38),
  [#39](https://github.com/alexisdacquay/chorum-murohc/issues/39)); the audit
  view ([#86](https://github.com/alexisdacquay/chorum-murohc/issues/86)); the
  permission matrix
  ([#18](https://github.com/alexisdacquay/chorum-murohc/issues/18)); the
  retention policy
  ([#20](https://github.com/alexisdacquay/chorum-murohc/issues/20)); the
  permission primitive
  ([#19](https://github.com/alexisdacquay/chorum-murohc/issues/19)); and the
  independent security recheck
  ([#95](https://github.com/alexisdacquay/chorum-murohc/issues/95)).
