# Approval Authentication Policy

> **Status:** Approved product decision for task T029. The decision is recorded
> in issue
> [#29 comment 5591127462](https://github.com/alexisdacquay/chorum-murohc/issues/29#issuecomment-5591127462)
> by `alexisdacquay`, product owner, on 2026-09-08. It approves the proposal in
> [comment 5589059278](https://github.com/alexisdacquay/chorum-murohc/issues/29#issuecomment-5589059278)
> with one change: the minimum PIN length is four digits, not six. The security
> acceptance this document relies on, and the part of it that is still missing,
> are recorded in [Approval record](#approval-record). This document is policy
> only. It implements no endpoint, model field, migration, service, permission,
> interface or audit event, and it changes no merged behaviour.

This policy answers one question for every approval in the product: which adult
approved a submission, how that adult proved it, and what the product may say
and record about the attempt. The tasks listed in
[Inheriting issues](#inheriting-issues) implement it. They must not invent an
answer this document already gives, and they must not take authority this
document does not grant.

The words **must**, **must not**, **allow** and **deny** are normative.
Anything not explicitly allowed is denied.

## Approval record

| Approval | Where | What it covers |
| --- | --- | --- |
| Product owner | [issue #29 comment 5591127462](https://github.com/alexisdacquay/chorum-murohc/issues/29#issuecomment-5591127462) | This exact policy: per-parent PINs, parent named first on a child device, four-digit minimum, own password to set or change, five failures then a fifteen-minute lock, forgotten PIN handled by password alone, one entry per decision, the audit table below |
| Security acceptance | [issue #18 comment 5584623381](https://github.com/alexisdacquay/chorum-murohc/issues/18#issuecomment-5584623381) | The project-level acceptance by `alexisdacquay`, acting as the human accepting security risk, which deliberately waived an independent third-party security reviewer for this project and recorded undefined parent PIN retry, lockout and recovery thresholds as accepted residual risk 3, owner #29 |

That security acceptance is project-level. It waives independent review and it
names this decision as the risk it is waiting on, but it was written before this
policy existed and it does not itself accept the four residual risks in
[Residual risks](#residual-risks) below. No separate security-acceptance comment
naming those four risks exists on issue #29. That gap is recorded here rather
than hidden, and no agent approved this policy.

The gate in `_docs/tasks.md` reads "Obtain product-owner and security approval
before PIN storage or approval implementation". Recording the decision is this
task; storing or verifying a PIN is not. So: the issues in
[Inheriting issues](#inheriting-issues) must not start until a security
acceptance naming the four residual risks below is recorded on issue #29. If
that acceptance changes any rule here, this document is amended first and the
issues follow the amended text.

## Relation to the approved permission matrix

The authority ceiling comes unchanged from the `Trust Boundaries and Permission
Matrix` and `PIN and Approval Invariants` sections of [`design.md`](design.md),
approved in issue
[#18](https://github.com/alexisdacquay/chorum-murohc/issues/18). This document
widens nothing in them and amends no part of them. Where that matrix denies an
actor, this document also denies that actor. Where it says a parent may set a
PIN "only after the exact T029 and T031 proof and recovery contract", the
contract named here is that contract and no other.

Two invariants of that matrix are restated because every rule below depends on
them: product endpoints never honour Django `is_staff`, `is_superuser`, groups
or model permissions as a household-role bypass, and a frontend route, hidden
control or disabled button is never an authorisation control.

The residual risk line in `design.md` reading "Parent PIN retry, lockout, and
recovery thresholds are undefined" is settled by this document, but that line
belongs to T018. It is not amended here; a follow-up issue must retire it.

## Vocabulary

- **PIN**: a digits-only secret belonging to one parent user account, used only
  to prove that this named parent authorised one named decision.
- **Approving parent**: the single active parent of the submission's household
  whose PIN was verified for that decision. Attribution names them and nobody
  else.
- **Verification**: one server-side comparison of a supplied PIN against that
  one parent's stored hash, inside the request that carries the decision.
- **Lockout**: a time-bounded refusal to perform verification for one parent.
- **Deny**: perform no verification and no mutation, and reveal no protected
  data. A denied, absent, deactivated and wrong-PIN case must be
  indistinguishable to the caller.

## Identity: whose PIN, and how the parent is chosen

A PIN belongs to **one parent user account**, not to a household and not to a
membership. PINs are **not household-unique**: two parents may hold the same
value, neither is told so, and no surface anywhere reveals it.

- **On a child's device**, the flow **names the approving parent first**, chosen
  from that household's active parents, and then verifies the supplied PIN
  against **that one parent's hash and no other**. A PIN that would have matched
  a different parent fails.
- **On a parent's own device**, the approver is the session user. No selection
  step exists and no parent may approve as another.

Household-unique PINs are refused for two reasons, and both are consequences the
product accepts. Enforcing uniqueness would tell the second parent that a value
is already taken, which leaks another parent's secret. Matching a typed PIN
against every parent's hash would make attribution ambiguous the moment two
parents chose the same value, and exact attribution is the point of the flow.
The price is that the child device shows its own household's parent names before
anyone has authenticated.

A parent who belongs to two households has **one PIN and one lockout**, because
the PIN belongs to the account. Verification additionally requires a live parent
membership in the **submission's** household, rechecked inside the writing
transaction.

## The PIN value

- **Length: four digits minimum, ten digits maximum.** Four is the plan's own
  minimum in [`plan.md`](plan.md); this document does not weaken it. A parent
  may choose any length in that range.
- **Characters: digits only.** Letters are refused, because a keyboard secret on
  a child's tablet pushes parents to write the PIN down.
- **Refused at set and at change**, with a generic "choose a different PIN"
  response that never says which rule fired:
  - every digit identical;
  - a consecutive ascending run;
  - a consecutive descending run;
  - a short pattern repeated to fill the length;
  - any value in a small in-code blocklist of common choices;
  - any value equal to the parent's current PIN.
- **PINs never expire.** No rotation, no reminder, no forced change.

## Who may set or change a PIN

- A parent may set and change **only their own PIN**, and must **re-enter their
  own account password in the same request**.
- No parent may set, read, clear or replace another parent's PIN, and no
  interface offers it.
- **No child has a PIN.** A child account cannot set one and cannot be given one.
- One PIN per user account, shared across that account's memberships.
- The parent's live membership in the target household is rechecked **inside the
  writing transaction**, so a membership removed mid-request cannot be used.
- A stored PIN is never returned, echoed, logged or rendered, and neither is its
  hash.

## Attempts and lockout

- **Five consecutive failed verifications lock that parent's PIN for fifteen
  minutes.**
- The counter is **per parent**. It is never per device, per child, per
  household or per session, so a child cannot reset it by switching devices and
  one parent's failures never lock another.
- **A successful verification resets the counter to zero.**
- **The lock clears** on expiry, or at once when that parent sets a new PIN with
  their password.
- Counter and lock state live **in the database**, not the cache. No shared
  cache backend is configured, so a default per-process cache would let a
  restart or a second worker erase the count.
- The counter is **read and incremented under a row lock inside the verification
  transaction**, so two parallel guesses cannot both observe the same starting
  value.
- **A lockout blocks PIN verification and nothing else.** It applies on both the
  child's device and the parent's own device, because a lock covering one device
  is escaped by walking to the other. It never blocks login, navigation, chore
  management or any other action; it never affects the other parent; and a
  pending submission simply waits.

This document claims no database or cryptographic guarantee beyond what Django's
own password hashing and the configured database provide. The lockout, not the
hash, is the primary defence.

## Forgetting a PIN

**Forgetting the PIN is the same operation as changing it.** The parent signs
in, enters their account password, and sets a new PIN, which also clears any
lockout. There is no reset code, no security question, no recovery email and no
support path, because the product sends no email.

If the parent has also forgotten their **password**, the other parent changes it
through [#22](https://github.com/alexisdacquay/chorum-murohc/issues/22). That
password change **must clear the target parent's PIN and lockout**, so that a
new password can never silently inherit the old PIN. A household with only one
parent has no self-service route until
[#27](https://github.com/alexisdacquay/chorum-murohc/issues/27) provides one.

## One verification, one decision

The approve or reject call **carries the PIN in the same request as the
decision**. There is no verified window, no capability token and no cached
elevation to expire, replay or revoke, and the merged matrix forbids reusable
elevation.

- A verification authorises **exactly one named pending decision**.
- It is consumed whether the decision succeeds or the submission turns out to be
  stale.
- Four queued submissions need four PIN entries.
- A child-device attempt never changes the child session, its membership, its
  navigation or any later request.

## Audit attribution

Event codes follow the merged `noun.verb` style. Every event records the
verified parent as actor, and writes that parent's internal integer identifier
into context so attribution survives actor deletion.

| Event | Emitted when | Context beyond actor, target and household |
| --- | --- | --- |
| `pin.set` | A parent first sets a PIN | none |
| `pin.change` | A parent replaces a PIN, forgotten or not | whether a lockout was cleared |
| `pin.verify_failed` | One failed verification | which approval path, consecutive failure count |
| `pin.locked` | The fifth consecutive failure | threshold, lock duration in seconds |
| `pin.verification_unused` | A verified check whose decision was stale | submission identifier |

- **A successful verification emits no event of its own.** The decision event
  owned by [#45](https://github.com/alexisdacquay/chorum-murohc/issues/45)
  already records the verified parent as actor and which path was used.
- **An expiring lock emits nothing.** Expiry is the absence of an action.
- On a child device the actor is the **verified parent**, never the child whose
  device hosted the flow.

**Never recorded, anywhere.** Not in an audit event, a log line, an error
message, an API response, the interface, a test name or test output:

- the PIN itself, any hash of it, any single digit, prefix, suffix, length or
  transformation of it;
- any "close", "wrong length" or "another parent would have matched" signal;
- whether the selected parent has a PIN at all.

## What the product says back

- **Responses never enumerate.** A wrong PIN, an unknown selected parent, a
  parent with no PIN and a stale selection are **one generic failure** with no
  distinguishing code, message or timing claim.
- **After a lockout**, the response says only that attempts are refused and when
  they resume. It never says how many attempts were made or remain.
- **The child-device parent list** contains only that household's **active
  parents who have a usable PIN**. A locked parent stays listed and is marked
  temporarily unavailable, because removing them would say what the lockout
  already told the room.
- **When that list is empty**, the dialog says that no parent has set an
  approval PIN yet, and offers no other route.

## Awkward cases, decided

1. **No parent in the household has a PIN yet.** The child-device parent list is
   empty and the dialog says so. Approval on the child device is unavailable
   until a parent sets one. Nothing is queued, retried or emailed, and the
   submission stays pending.
2. **The selected parent is deactivated or removed mid-flow.** Verification
   fails with the same generic failure as a wrong PIN, no counter is
   incremented for the removed parent, and no decision is written. The child
   sees the refreshed list.
3. **The other parent decided first.** The verification is consumed and
   `pin.verification_unused` is emitted with the submission identifier. No
   second decision is written, no second credit is granted, and the caller is
   told the submission is no longer pending.
4. **A parent belongs to two households.** One PIN, one counter, one lockout.
   Failed guesses on one household's child device lock that parent's approvals
   in the other household too. The product owner accepted this.
5. **A locked parent on their own queue.** Their own approve and reject calls
   are refused for the remainder of the lock, exactly as on the child device.
   Login and every non-approval action stay available, and setting a new PIN
   with their password ends the lock at once.
6. **A repeated identical request.** The first request decides. A repeat of the
   same decision on the same submission still consumes its own verification,
   writes no second decision, grants no second credit and emits no second
   decision event.
7. **Two parallel guesses.** The row lock inside the verification transaction
   serialises them, so the counter cannot be read as zero twice.
8. **A parent sets the PIN they already have.** Refused as a trivial value, with
   the same generic response, and no `pin.change` event.

## Residual risks

These are the risks the product accepts by approving this policy. They are
listed so a security acceptance on issue #29 can name them.

1. **A four-digit secret is weak offline.** If the database leaks, the hash
   delays an offline attacker by minutes, not months. The lockout, not the hash,
   is the real defence.
2. **The lockout is the primary defence.** Five attempts per fifteen minutes
   caps a patient guesser at roughly 480 attempts a day against ten thousand
   four-digit combinations, so a full week of guessing still matters. Longer
   PINs are allowed and are the parent's own mitigation.
3. **Parent names are visible on the child device before anyone
   authenticates.** That is the price of exact attribution.
4. **One parent can change another parent's password** through #22 and thereby
   clear their PIN. Mandatory clearing prevents silent inheritance, but it does
   not prevent a parent from taking over another parent's approval identity, and
   the resulting audit events name the acting parent.

## Inheriting issues

Each issue below implements part of this policy and must not depart from it.

| Issue | What it inherits |
| --- | --- |
| [#22](https://github.com/alexisdacquay/chorum-murohc/issues/22) Account and role update | An administrative password change must clear the target parent's PIN and lockout |
| [#30](https://github.com/alexisdacquay/chorum-murohc/issues/30) PIN storage and verification | One hashed PIN per user account, Django password hashing, the length, character and trivial-value rules, the transactional membership recheck, `pin.set` and `pin.change`, and the never-recorded list |
| [#31](https://github.com/alexisdacquay/chorum-murohc/issues/31) PIN management operations | Own PIN only, own password in the same request, no cross-parent management, no child PIN, generic refusals |
| [#32](https://github.com/alexisdacquay/chorum-murohc/issues/32) PIN settings screen | Set and change surfaces only, no reveal, no reset code, forgotten-PIN wording that matches the change flow |
| [#33](https://github.com/alexisdacquay/chorum-murohc/issues/33) Attempt limits | Five failures, fifteen minutes, per parent, database-held, row-locked increment, reset on success, cleared by a new PIN, `pin.verify_failed` and `pin.locked` |
| [#45](https://github.com/alexisdacquay/chorum-murohc/issues/45) Atomic approval | One verification per decision inside one transaction, the verified parent as actor, consumption on a stale submission with `pin.verification_unused`, no second credit |
| [#46](https://github.com/alexisdacquay/chorum-murohc/issues/46) Decision endpoint | The PIN travels with the decision, no verified window or token, one generic failure shape, lockout response wording |
| [#47](https://github.com/alexisdacquay/chorum-murohc/issues/47) Child-device dialog | Parent named before the PIN is typed, the active-parents-with-a-PIN list, locked parents marked unavailable, the empty-list message, no session change |
| [#48](https://github.com/alexisdacquay/chorum-murohc/issues/48) Parent queue | A PIN entry per decision on the parent's own device, and the lockout applying there too |

Anything not explicitly allowed above is denied, in every one of these issues.

## Out of scope

- Every model field, migration, service, endpoint and interface named above.
  This document decides behaviour; those issues build it.
- Login-abuse control and password reset
  [#27](https://github.com/alexisdacquay/chorum-murohc/issues/27), the
  permission matrix [#18](https://github.com/alexisdacquay/chorum-murohc/issues/18),
  the permission primitive
  [#19](https://github.com/alexisdacquay/chorum-murohc/issues/19), the audit view
  [#86](https://github.com/alexisdacquay/chorum-murohc/issues/86) and the
  security recheck
  [#95](https://github.com/alexisdacquay/chorum-murohc/issues/95).
- Biometrics, a second factor, device trust, a shared verified window and PIN
  expiry. None has an issue, none is required by this policy, and one must be
  filed and approved before any is built.
