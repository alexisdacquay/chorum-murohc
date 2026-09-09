"""Decide a pending submission: approve it and credit the ledger, or reject
it, in one atomic transaction (T045, T046; issue #44).

Implements the write half of `_docs/approval-authentication.md`. There are
two call sites for the one function here, `decide_submission`, distinguished
only by the caller's own household role, never by a client-supplied "device"
flag:

- A parent calling from their own device supplies no `approving_parent_id`:
  "the approver is the session user, with no choice" (the approved policy).
- A child calling from their own device must name which parent is deciding;
  that parent's own PIN, not the child's session, is what authorises the
  decision. The child's session is never elevated and is never itself
  sufficient authority.

Lives in the `submissions` package rather than in the API layer, matching the
approved direction map in `_docs/design.md`: `submissions` may import
`identity`, `chores`, `ledger`, and `audit`, and no product package may
import the API layer above it, so a service placed there could never be
reused here.

`chorum_murohc.identity.services.verify_pin` is called *before* this
module's own `transaction.atomic()` block, deliberately outside it, even
though almost every other write service in this project nests its lookups
inside one outer transaction. `verify_pin` runs its own bookkeeping (the
failed-attempt counter and the `pin.verify_failed` / `pin.locked` audit
events) inside its own `transaction.atomic()`; nesting that call inside a
second, enclosing transaction that later raises for an unrelated reason (a
stale submission, a revoked membership) would roll the whole enclosing
transaction back and erase that bookkeeping with it, silently disabling the
five-attempt lockout. Calling it first, standalone, makes its effects commit
immediately and independently of whatever this module does afterward, which
is exactly "one verification authorises one named pending decision and is
consumed whether that decision succeeds or becomes stale."

Only a `PinVerificationResult.MATCH` reaches the decision transaction below.
That transaction locks the pending submission and re-locks both the caller's
own membership and the verified parent's membership immediately before
writing, matching invariant 5 in `_docs/design.md`: a membership revoked in
the sliver of time since the PIN matched cannot still slip a decision
through.
"""

from django.db import transaction
from django.utils import timezone

from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity.models import Membership, User
from chorum_murohc.identity.services import PinVerificationResult, verify_pin
from chorum_murohc.ledger.models import LedgerEntry
from chorum_murohc.submissions.models import Submission

DECISION_APPROVE = 'approve'
DECISION_REJECT = 'reject'

AUDIT_TARGET_TYPE = 'submission'
AUDIT_APPROVE = 'submission.approve'
AUDIT_REJECT = 'submission.reject'

# The ledger source this service writes into `LedgerEntry.source_type`, kept
# here next to the one place that writes it rather than duplicated at each
# call site, matching `rewards.services.LEDGER_SOURCE_TYPE`.
LEDGER_SOURCE_TYPE = 'submissions.submission'


class SubmissionAuthorityError(Exception):
    """The re-resolved caller membership does not hold a role this action
    needs. The API layer already gates every route by role before this
    module is ever called; this is the same defence in depth
    `rewards.services.RewardAuthorityError` applies, re-checked here inside
    the locked transaction, immediately before a write.
    """


class SubmissionPinError(Exception):
    """PIN verification did not return `MATCH`.

    `result` is `PinVerificationResult.NO_MATCH` or `.LOCKED`, exactly the
    value `identity.services.verify_pin` returned. The caller maps both to
    the one generic wrong-PIN detail and the one generic lockout detail the
    approved contract requires; neither this exception nor its caller ever
    names a parent, a household, or which rule refused the value.
    """

    def __init__(self, result):
        super().__init__(str(result))
        self.result = result


def _decision_context(*, parent, submission, previous_status, device, reason):
    # `AuditEvent.context` only accepts exact JSON primitive types (see
    # `chorum_murohc/audit/models.py`), and a `TextChoices` member is not
    # exactly `str` even though it behaves like one, so both sides of the
    # transition are coerced to plain strings before they are stored.
    return {
        'actor_id': parent.pk,
        'submission_id': submission.pk,
        'chore_id': submission.chore_id,
        'chore_name': submission.chore_name,
        'chore_points': submission.chore_points,
        'child_id': submission.child_id,
        # The device the decision was made from, never the child's own
        # identity as a second actor: `_docs/approval-authentication.md`
        # requires "the verified parent as actor, not the child whose device
        # hosted the flow", and `child_id` above already names the child.
        'device': device,
        'rejection_reason': reason,
        'status': {'before': str(previous_status), 'after': str(submission.status)},
    }


def decide_submission(
    *,
    household,
    acting_user,
    submission_id,
    decision,
    pin,
    approving_parent_id=None,
    reason='',
):
    """Approve or reject one pending submission of `household`.

    `decision` is `DECISION_APPROVE` or `DECISION_REJECT`. On approval, one
    `chore_credit` ledger entry is appended for the submission's own snapshot
    point value; on rejection, `reason` (already trimmed and length-checked
    by the caller) is stored and nothing is credited.

    Raises `Membership.DoesNotExist` if the caller's own membership no longer
    exists, `SubmissionAuthorityError` if that membership is no longer a
    parent's or a child's, `SubmissionPinError` for a wrong or locked PIN
    (including an unresolved or missing `approving_parent_id` on a child
    device, which is refused the identical generic way a wrong PIN is), and
    `Submission.DoesNotExist` for a submission that is missing, in another
    household, or no longer pending. Every failure leaves the database
    exactly as it was, except for `verify_pin`'s own independent lockout
    bookkeeping on a failed PIN, which is deliberately not rolled back.
    """
    caller_membership = Membership.objects.filter(
        household=household, user=acting_user
    ).first()
    if caller_membership is None or caller_membership.role not in (
        Membership.Role.PARENT,
        Membership.Role.CHILD,
    ):
        raise SubmissionAuthorityError()

    if caller_membership.role == Membership.Role.PARENT:
        device = 'parent'
        target_user = acting_user
    else:
        device = 'child'
        target_user = None
        if approving_parent_id is not None:
            target_user = User.objects.filter(pk=approving_parent_id).first()
        if target_user is None:
            raise SubmissionPinError(PinVerificationResult.NO_MATCH)

    result = verify_pin(user=target_user, household=household, submitted_pin=pin)
    if result is not PinVerificationResult.MATCH:
        raise SubmissionPinError(result)

    parent = target_user

    with transaction.atomic():
        submission = Submission.objects.select_for_update().get(
            household=household, pk=submission_id, status=Submission.Status.PENDING
        )
        caller_membership = Membership.objects.select_for_update().get(
            household=household, user=acting_user
        )
        if caller_membership.role not in (
            Membership.Role.PARENT,
            Membership.Role.CHILD,
        ):
            raise SubmissionAuthorityError()
        # The verified parent's own membership, re-locked and re-checked the
        # same way, immediately before it is recorded as the decision actor.
        Membership.objects.select_for_update().get(
            household=household, user=parent, role=Membership.Role.PARENT
        )

        previous_status = submission.status
        if decision == DECISION_APPROVE:
            submission.status = Submission.Status.APPROVED
        else:
            submission.status = Submission.Status.REJECTED
            submission.rejection_reason = reason
        submission.decided_by = parent
        submission.decided_at = timezone.now()
        submission.save()

        if decision == DECISION_APPROVE:
            LedgerEntry.objects.create(
                household=household,
                user=submission.child,
                amount=submission.chore_points,
                reason=LedgerEntry.Reason.CHORE_CREDIT,
                source_type=LEDGER_SOURCE_TYPE,
                source_id=str(submission.pk),
                idempotency_key=f'submission:{submission.pk}:credit',
            )

        AuditEvent.objects.create(
            household=household,
            actor=parent,
            action=AUDIT_APPROVE if decision == DECISION_APPROVE else AUDIT_REJECT,
            target_type=AUDIT_TARGET_TYPE,
            target_id=str(submission.pk),
            context=_decision_context(
                parent=parent,
                submission=submission,
                previous_status=previous_status,
                device=device,
                reason=submission.rejection_reason,
            ),
        )
        return submission
