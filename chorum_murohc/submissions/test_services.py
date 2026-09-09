"""Tests for `chorum_murohc.submissions.services.decide_submission`
(T045, issue #44).

Every fixture is synthetic. No credential, PIN, token, cookie or personal
datum appears in the data, the assertions or the failure output: the test
users are created without a usable password, and PINs are set through the
real `identity.services.set_or_replace_pin` contract rather than written
directly, so there is nothing sensitive to print.
"""

import pytest

from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.chores.models import Chore
from chorum_murohc.identity.models import Household, Membership, ParentPin, User
from chorum_murohc.identity.services import (
    MAX_FAILED_ATTEMPTS,
    PinVerificationResult,
    set_or_replace_pin,
)
from chorum_murohc.ledger.models import LedgerEntry
from chorum_murohc.ledger.services import balance_for_user
from chorum_murohc.submissions.models import Submission
from chorum_murohc.submissions.services import (
    DECISION_APPROVE,
    DECISION_REJECT,
    SubmissionAuthorityError,
    SubmissionPinError,
    decide_submission,
)

SYNTHETIC_PASSWORD = 'synthetic-only-account-password'
VALID_PIN = '3947'
WRONG_PIN = '8156'


def make_user(username):
    return User.objects.create_user(username=username, password=SYNTHETIC_PASSWORD)


def make_member(household, username, role):
    user = make_user(username)
    Membership.objects.create(household=household, user=user, role=role)
    return user


def give_pin(user, household, pin=VALID_PIN):
    set_or_replace_pin(
        user=user, household=household, current_password=SYNTHETIC_PASSWORD, new_pin=pin
    )


@pytest.fixture
def household(db):
    return Household.objects.create(name='Synthetic household')


@pytest.fixture
def other_household(db):
    return Household.objects.create(name='Other household')


@pytest.fixture
def child(household):
    return make_member(household, 'synthetic-child', Membership.Role.CHILD)


@pytest.fixture
def parent(household):
    user = make_member(household, 'synthetic-parent', Membership.Role.PARENT)
    give_pin(user, household)
    return user


@pytest.fixture
def other_parent(household):
    """A second parent of the same household, holding its own PIN."""
    user = make_member(household, 'synthetic-parent-2', Membership.Role.PARENT)
    give_pin(user, household, pin='2604')
    return user


@pytest.fixture
def chore(household):
    return Chore.objects.create(household=household, name='Dishes', points=7)


def make_submission(household, child, chore, *, key='sub-1'):
    return Submission.objects.create(
        household=household,
        child=child,
        chore=chore,
        chore_name=chore.name,
        chore_points=chore.points,
        idempotency_key=key,
    )


def one_event(action):
    events = list(AuditEvent.objects.filter(action=action))
    assert len(events) == 1
    return events[0]


# --- the parent's own device: no parent selection -----------------------------


@pytest.mark.django_db
def test_parent_device_approval_credits_the_ledger_and_writes_one_event(
    household, child, parent, chore
):
    submission = make_submission(household, child, chore)

    decided = decide_submission(
        household=household,
        acting_user=parent,
        submission_id=submission.pk,
        decision=DECISION_APPROVE,
        pin=VALID_PIN,
    )

    assert decided.status == Submission.Status.APPROVED
    assert decided.decided_by_id == parent.pk
    assert balance_for_user(household, child) == 7

    entry = LedgerEntry.objects.get(source_id=str(submission.pk))
    assert entry.amount == 7
    assert entry.reason == LedgerEntry.Reason.CHORE_CREDIT
    assert entry.user_id == child.pk

    event = one_event('submission.approve')
    assert event.actor_id == parent.pk
    assert event.context['device'] == 'parent'
    assert event.context['child_id'] == child.pk


@pytest.mark.django_db
def test_parent_device_rejection_records_the_reason_and_credits_nothing(
    household, child, parent, chore
):
    submission = make_submission(household, child, chore)

    decided = decide_submission(
        household=household,
        acting_user=parent,
        submission_id=submission.pk,
        decision=DECISION_REJECT,
        pin=VALID_PIN,
        reason='Left the floor wet',
    )

    assert decided.status == Submission.Status.REJECTED
    assert decided.rejection_reason == 'Left the floor wet'
    assert decided.decided_by_id == parent.pk
    assert balance_for_user(household, child) == 0
    assert LedgerEntry.objects.count() == 0

    event = one_event('submission.reject')
    assert event.context['rejection_reason'] == 'Left the floor wet'


@pytest.mark.django_db
def test_a_parent_supplied_approving_parent_id_is_ignored(
    household, child, parent, other_parent, chore
):
    """The session user decides on their own device; a client-named third
    party is never trusted, even when it names a real parent."""
    submission = make_submission(household, child, chore)

    decided = decide_submission(
        household=household,
        acting_user=parent,
        submission_id=submission.pk,
        decision=DECISION_APPROVE,
        pin=VALID_PIN,
        approving_parent_id=other_parent.pk,
    )

    assert decided.decided_by_id == parent.pk


# --- the child's own device: a named parent's PIN ------------------------------


@pytest.mark.django_db
def test_child_device_approval_attributes_the_named_parent_not_the_child(
    household, child, parent, chore
):
    submission = make_submission(household, child, chore)

    decided = decide_submission(
        household=household,
        acting_user=child,
        submission_id=submission.pk,
        decision=DECISION_APPROVE,
        pin=VALID_PIN,
        approving_parent_id=parent.pk,
    )

    assert decided.status == Submission.Status.APPROVED
    assert decided.decided_by_id == parent.pk
    event = one_event('submission.approve')
    assert event.actor_id == parent.pk
    assert event.context['device'] == 'child'


@pytest.mark.django_db
def test_child_device_with_no_parent_named_is_the_generic_pin_failure(
    household, child, parent, chore
):
    submission = make_submission(household, child, chore)

    with pytest.raises(SubmissionPinError) as excinfo:
        decide_submission(
            household=household,
            acting_user=child,
            submission_id=submission.pk,
            decision=DECISION_APPROVE,
            pin=VALID_PIN,
        )

    assert excinfo.value.result == PinVerificationResult.NO_MATCH
    assert Submission.objects.get(pk=submission.pk).status == Submission.Status.PENDING


@pytest.mark.django_db
def test_child_device_naming_an_unknown_parent_id_is_the_generic_pin_failure(
    household, child, chore
):
    submission = make_submission(household, child, chore)

    with pytest.raises(SubmissionPinError) as excinfo:
        decide_submission(
            household=household,
            acting_user=child,
            submission_id=submission.pk,
            decision=DECISION_APPROVE,
            pin=VALID_PIN,
            approving_parent_id=999999,
        )

    assert excinfo.value.result == PinVerificationResult.NO_MATCH


@pytest.mark.django_db
def test_child_device_naming_a_child_as_the_approving_parent_is_refused(
    household, child, chore
):
    second_child = make_member(household, 'synthetic-child-2', Membership.Role.CHILD)
    submission = make_submission(household, child, chore)

    with pytest.raises(SubmissionPinError) as excinfo:
        decide_submission(
            household=household,
            acting_user=child,
            submission_id=submission.pk,
            decision=DECISION_APPROVE,
            pin=VALID_PIN,
            approving_parent_id=second_child.pk,
        )

    assert excinfo.value.result == PinVerificationResult.NO_MATCH


@pytest.mark.django_db
def test_a_foreign_household_parent_cannot_be_named(
    household, other_household, child, chore
):
    foreign_parent = make_member(
        other_household, 'synthetic-foreign-parent', Membership.Role.PARENT
    )
    give_pin(foreign_parent, other_household)
    submission = make_submission(household, child, chore)

    with pytest.raises(SubmissionPinError) as excinfo:
        decide_submission(
            household=household,
            acting_user=child,
            submission_id=submission.pk,
            decision=DECISION_APPROVE,
            pin=VALID_PIN,
            approving_parent_id=foreign_parent.pk,
        )

    assert excinfo.value.result == PinVerificationResult.NO_MATCH


# --- wrong and locked PINs: refused, and never a partial write ----------------


@pytest.mark.django_db
def test_a_wrong_pin_changes_nothing_but_still_counts_the_attempt(
    household, child, parent, chore
):
    submission = make_submission(household, child, chore)

    with pytest.raises(SubmissionPinError) as excinfo:
        decide_submission(
            household=household,
            acting_user=parent,
            submission_id=submission.pk,
            decision=DECISION_APPROVE,
            pin=WRONG_PIN,
        )

    assert excinfo.value.result == PinVerificationResult.NO_MATCH
    # The decision itself made no change...
    submission.refresh_from_db()
    assert submission.status == Submission.Status.PENDING
    assert submission.decided_by_id is None
    assert LedgerEntry.objects.count() == 0
    assert AuditEvent.objects.filter(action='submission.approve').count() == 0
    # ...but `verify_pin`'s own failed-attempt bookkeeping is not part of that
    # rollback: it already committed on its own, independent transaction, so
    # the lockout counter still moves and its own audit event still exists.
    # This is the invariant the whole call-verify_pin-before-our-own-
    # transaction design in `services.py` exists to protect.
    assert ParentPin.objects.get(user=parent).failed_attempts == 1
    assert AuditEvent.objects.filter(action='pin.verify_failed').count() == 1


@pytest.mark.django_db
def test_a_locked_pin_is_refused_as_locked_not_as_a_wrong_guess(
    household, child, parent, chore
):
    submission = make_submission(household, child, chore)
    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(SubmissionPinError):
            decide_submission(
                household=household,
                acting_user=parent,
                submission_id=submission.pk,
                decision=DECISION_APPROVE,
                pin=WRONG_PIN,
            )

    with pytest.raises(SubmissionPinError) as excinfo:
        decide_submission(
            household=household,
            acting_user=parent,
            submission_id=submission.pk,
            decision=DECISION_APPROVE,
            pin=VALID_PIN,
        )

    assert excinfo.value.result == PinVerificationResult.LOCKED
    assert Submission.objects.get(pk=submission.pk).status == Submission.Status.PENDING


# --- stale state, retry, and concurrency ---------------------------------------


@pytest.mark.django_db
def test_deciding_an_already_decided_submission_again_is_refused_and_credits_once(
    household, child, parent, chore
):
    submission = make_submission(household, child, chore)
    decide_submission(
        household=household,
        acting_user=parent,
        submission_id=submission.pk,
        decision=DECISION_APPROVE,
        pin=VALID_PIN,
    )

    # A retry of the same request (a lost response, a double-tapped button)
    # never double-credits: the submission is no longer pending, so it reads
    # as the same refusal a submission that never existed would.
    with pytest.raises(Submission.DoesNotExist):
        decide_submission(
            household=household,
            acting_user=parent,
            submission_id=submission.pk,
            decision=DECISION_APPROVE,
            pin=VALID_PIN,
        )

    assert balance_for_user(household, child) == 7
    assert LedgerEntry.objects.filter(source_id=str(submission.pk)).count() == 1


@pytest.mark.django_db
def test_two_decisions_racing_for_the_same_submission_cannot_both_succeed(
    household, child, parent, other_parent, chore
):
    # No real thread race here (tests stay deterministic per the testing
    # guidelines); this proves the same invariant the row lock and the
    # `status=pending` filter enforce under concurrency: once one decision
    # commits, a second one for the same submission always loses.
    submission = make_submission(household, child, chore)

    decide_submission(
        household=household,
        acting_user=parent,
        submission_id=submission.pk,
        decision=DECISION_APPROVE,
        pin=VALID_PIN,
    )

    with pytest.raises(Submission.DoesNotExist):
        decide_submission(
            household=household,
            acting_user=other_parent,
            submission_id=submission.pk,
            decision=DECISION_REJECT,
            pin='2604',
        )

    assert Submission.objects.get(pk=submission.pk).status == Submission.Status.APPROVED
    assert balance_for_user(household, child) == 7


@pytest.mark.django_db
def test_a_submission_from_another_household_is_refused(
    household, other_household, child, chore
):
    foreign_parent = make_member(
        other_household, 'synthetic-foreign-parent', Membership.Role.PARENT
    )
    give_pin(foreign_parent, other_household)
    submission = make_submission(household, child, chore)

    with pytest.raises(Submission.DoesNotExist):
        decide_submission(
            household=other_household,
            acting_user=foreign_parent,
            submission_id=submission.pk,
            decision=DECISION_APPROVE,
            pin=VALID_PIN,
        )

    assert Submission.objects.get(pk=submission.pk).status == Submission.Status.PENDING


# --- caller authority -----------------------------------------------------------


@pytest.mark.django_db
def test_a_caller_with_no_membership_in_the_household_is_refused(
    household, child, chore
):
    outsider = make_user('synthetic-outsider')
    submission = make_submission(household, child, chore)

    with pytest.raises(SubmissionAuthorityError):
        decide_submission(
            household=household,
            acting_user=outsider,
            submission_id=submission.pk,
            decision=DECISION_APPROVE,
            pin=VALID_PIN,
        )

    assert Submission.objects.get(pk=submission.pk).status == Submission.Status.PENDING
