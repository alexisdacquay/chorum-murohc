# Approval Authentication Policy

How a parent proves it was them when a submission is approved or rejected.
Approved on issue #29, 2026-09-08. Anything not allowed here is denied.

## The PIN

- A PIN belongs to one parent user account, not to a household. Four to ten
  digits, digits only, hashed with Django's password hashing, never expiring.
- PINs are not unique across a household. Two parents may hold the same value
  and no surface anywhere reveals it.
- Refused at set and at change, with one generic "choose a different PIN": all
  digits identical, an ascending or descending run, a short repeated pattern, a
  value in a small in-code blocklist, or the parent's current PIN.
- A parent sets and changes only their own PIN, and must re-enter their own
  account password in the same request. No parent touches another parent's PIN.
  No child has a PIN. A stored PIN or its hash is never returned or logged.

## Who approves, and how it locks

- On a child's device the flow names the approving parent first, chosen from
  that household's active parents, then checks the PIN against that one parent's
  hash. A PIN that would have matched another parent fails. On a parent's own
  device the approver is the session user, with no choice.
- Verification also requires a live parent membership in the submission's
  household, rechecked inside the writing transaction.
- Five consecutive failures lock that parent's PIN for fifteen minutes. The
  counter is per parent: never per device, per child or per session. A success
  resets it; the lock clears on expiry or when that parent sets a new PIN.
- The counter lives in the database, not the cache, and is incremented under a
  row lock inside the verification transaction. A lockout blocks PIN
  verification and nothing else, on both devices; pending submissions wait.

## Using and forgetting a PIN

- The PIN travels in the same request as the decision: no verified window, token
  or cached elevation. One verification authorises one named pending decision
  and is consumed even if stale, so four decisions need four entries.
- Forgetting is the same operation as changing: sign in, enter the account
  password, set a new PIN, which also clears any lockout. No reset code, no
  security question, no email. If the password is also forgotten the other
  parent changes it, and that must clear the target's PIN and lockout too.

## What is said and recorded

- A wrong PIN, an unknown parent, a parent with no PIN and a stale selection are
  one generic failure. After a lockout the response says only that attempts are
  refused and when they resume.
- The child-device list holds that household's active parents who have a PIN; a
  locked one stays listed, marked temporarily unavailable. An empty list says so
  and offers no other route.
- Audit events: `pin.set`, `pin.change`, `pin.verify_failed`, `pin.locked`,
  `pin.verification_unused`. A success emits none of its own; the decision event
  already names the verified parent as actor and carries their internal integer
  id so attribution survives actor deletion.
- Never recorded anywhere: the PIN, its hash, any digit, prefix or length, any
  "close" or "another parent matched" hint, or whether a parent has a PIN.

The four-digit floor is weak offline: the lockout, not the hash, is the real
defence. Parent names show on a child device before anyone signs in.
