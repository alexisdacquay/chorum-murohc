"""Tests for the write-side reward service: `redeem_reward`, `fulfil_redemption`
and `cancel_redemption`.

Every fixture is synthetic. No credential, PIN, token, cookie or personal
datum appears in the data, the assertions or the failure output: the test
users are created without a usable password, so there is nothing sensitive
to print.
"""

import pytest

from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity.models import Household, Membership, User
from chorum_murohc.ledger.models import LedgerEntry
from chorum_murohc.ledger.services import balance_for_user
from chorum_murohc.rewards.models import Redemption, Reward
from chorum_murohc.rewards.services import (
    InsufficientPointsError,
    RewardAuthorityError,
    cancel_redemption,
    fulfil_redemption,
    redeem_reward,
)


def make_user(username):
    return User.objects.create_user(username=username)


def make_member(household, username, role):
    user = make_user(username)
    Membership.objects.create(household=household, user=user, role=role)
    return user


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
    return make_member(household, 'synthetic-parent', Membership.Role.PARENT)


@pytest.fixture
def reward(household):
    return Reward.objects.create(household=household, name='Screen time', points=15)


def credit(household, user, amount, *, key):
    return LedgerEntry.objects.create(
        household=household,
        user=user,
        amount=amount,
        reason=LedgerEntry.Reason.CHORE_CREDIT,
        source_type='synthetic.Source',
        source_id='synthetic',
        idempotency_key=key,
    )


def one_event(action):
    events = list(AuditEvent.objects.filter(action=action))
    assert len(events) == 1
    return events[0]


# --- redeem_reward -----------------------------------------------------------


@pytest.mark.django_db
def test_redeeming_debits_the_ledger_and_creates_a_pending_row(
    household, child, reward
):
    credit(household, child, 20, key='c1')

    redemption, created = redeem_reward(
        household=household, child=child, reward_id=reward.pk, idempotency_key='k1'
    )

    assert created is True
    assert redemption.status == Redemption.Status.PENDING
    assert redemption.reward_id == reward.pk
    assert redemption.reward_name == 'Screen time'
    assert redemption.reward_points == 15
    assert balance_for_user(household, child) == 5

    entry = LedgerEntry.objects.get(
        source_type='rewards.redemption', source_id=str(redemption.pk)
    )
    assert entry.amount == -15
    assert entry.reason == LedgerEntry.Reason.REWARD_DEBIT
    assert entry.idempotency_key == f'redemption:{redemption.pk}:debit'

    event = one_event('reward.request')
    assert event.actor_id == child.pk
    assert event.target_type == 'redemption'
    assert event.target_id == str(redemption.pk)
    assert event.context['points'] == 15
    assert event.context['status'] == {'before': None, 'after': 'pending'}


@pytest.mark.django_db
def test_an_exact_balance_redemption_leaves_zero_not_negative(household, child, reward):
    credit(household, child, 15, key='c1')

    _redemption, created = redeem_reward(
        household=household, child=child, reward_id=reward.pk, idempotency_key='k1'
    )

    assert created is True
    assert balance_for_user(household, child) == 0


@pytest.mark.django_db
def test_insufficient_points_creates_no_row_and_no_ledger_entry(
    household, child, reward
):
    credit(household, child, 14, key='c1')

    with pytest.raises(InsufficientPointsError):
        redeem_reward(
            household=household, child=child, reward_id=reward.pk, idempotency_key='k1'
        )

    assert Redemption.objects.count() == 0
    assert LedgerEntry.objects.filter(user=child).count() == 1  # only the credit
    assert AuditEvent.objects.count() == 0


@pytest.mark.django_db
def test_a_missing_reward_id_raises_does_not_exist_and_writes_nothing(household, child):
    credit(household, child, 100, key='c1')

    with pytest.raises(Reward.DoesNotExist):
        redeem_reward(
            household=household, child=child, reward_id=999999, idempotency_key='k1'
        )

    assert Redemption.objects.count() == 0
    assert AuditEvent.objects.count() == 0


@pytest.mark.django_db
def test_an_inactive_reward_cannot_be_redeemed(household, child, reward):
    reward.is_active = False
    reward.save()
    credit(household, child, 100, key='c1')

    with pytest.raises(Reward.DoesNotExist):
        redeem_reward(
            household=household, child=child, reward_id=reward.pk, idempotency_key='k1'
        )


@pytest.mark.django_db
def test_a_reward_from_another_household_cannot_be_redeemed(
    household, other_household, child
):
    foreign_reward = Reward.objects.create(
        household=other_household, name='Foreign reward', points=1
    )
    credit(household, child, 100, key='c1')

    with pytest.raises(Reward.DoesNotExist):
        redeem_reward(
            household=household,
            child=child,
            reward_id=foreign_reward.pk,
            idempotency_key='k1',
        )


@pytest.mark.django_db
def test_a_parent_cannot_redeem_through_this_service(household, parent, reward):
    credit(household, parent, 100, key='c1')

    with pytest.raises(RewardAuthorityError):
        redeem_reward(
            household=household, child=parent, reward_id=reward.pk, idempotency_key='k1'
        )
    assert Redemption.objects.count() == 0


@pytest.mark.django_db
def test_a_repeated_idempotency_key_returns_the_same_row_and_does_not_redebit(
    household, child, reward
):
    credit(household, child, 20, key='c1')

    first, first_created = redeem_reward(
        household=household,
        child=child,
        reward_id=reward.pk,
        idempotency_key='same-key',
    )
    second, second_created = redeem_reward(
        household=household,
        child=child,
        reward_id=reward.pk,
        idempotency_key='same-key',
    )

    assert first_created is True
    assert second_created is False
    assert first.pk == second.pk
    assert Redemption.objects.count() == 1
    assert (
        LedgerEntry.objects.filter(reason=LedgerEntry.Reason.REWARD_DEBIT).count() == 1
    )
    assert balance_for_user(household, child) == 5
    assert AuditEvent.objects.filter(action='reward.request').count() == 1


@pytest.mark.django_db
def test_two_redemptions_racing_for_the_same_points_cannot_both_succeed(
    household, child, reward
):
    # No real thread races here (tests stay deterministic per the testing
    # guidelines); this proves the same invariant the row lock enforces
    # under concurrency: two different requests for a balance that can
    # afford only one of them never both succeed.
    credit(household, child, 15, key='c1')
    second_reward = Reward.objects.create(household=household, name='Other', points=15)

    redeem_reward(
        household=household, child=child, reward_id=reward.pk, idempotency_key='k1'
    )
    with pytest.raises(InsufficientPointsError):
        redeem_reward(
            household=household,
            child=child,
            reward_id=second_reward.pk,
            idempotency_key='k2',
        )

    assert Redemption.objects.count() == 1
    assert balance_for_user(household, child) == 0


# --- fulfil_redemption ---------------------------------------------------------


@pytest.mark.django_db
def test_fulfil_marks_pending_fulfilled_and_moves_no_points(
    household, child, parent, reward
):
    credit(household, child, 20, key='c1')
    redemption, _ = redeem_reward(
        household=household, child=child, reward_id=reward.pk, idempotency_key='k1'
    )
    balance_before = balance_for_user(household, child)

    fulfilled = fulfil_redemption(
        household=household, parent=parent, redemption_id=redemption.pk
    )

    assert fulfilled.status == Redemption.Status.FULFILLED
    assert fulfilled.decided_by_id == parent.pk
    assert fulfilled.decided_at is not None
    assert balance_for_user(household, child) == balance_before
    assert (
        LedgerEntry.objects.filter(reason=LedgerEntry.Reason.REWARD_DEBIT).count() == 1
    )

    event = one_event('reward.fulfil')
    assert event.actor_id == parent.pk
    assert event.context['status'] == {'before': 'pending', 'after': 'fulfilled'}


@pytest.mark.django_db
def test_fulfilling_an_already_fulfilled_redemption_is_refused_and_stays_final(
    household, child, parent, reward
):
    credit(household, child, 20, key='c1')
    redemption, _ = redeem_reward(
        household=household, child=child, reward_id=reward.pk, idempotency_key='k1'
    )
    fulfil_redemption(household=household, parent=parent, redemption_id=redemption.pk)

    with pytest.raises(Redemption.DoesNotExist):
        fulfil_redemption(
            household=household, parent=parent, redemption_id=redemption.pk
        )

    assert (
        Redemption.objects.get(pk=redemption.pk).status == Redemption.Status.FULFILLED
    )
    assert AuditEvent.objects.filter(action='reward.fulfil').count() == 1


@pytest.mark.django_db
def test_a_cross_household_parent_cannot_fulfil(
    household, other_household, child, reward
):
    credit(household, child, 20, key='c1')
    redemption, _ = redeem_reward(
        household=household, child=child, reward_id=reward.pk, idempotency_key='k1'
    )
    foreign_parent = make_member(
        other_household, 'foreign-parent', Membership.Role.PARENT
    )

    with pytest.raises(Membership.DoesNotExist):
        fulfil_redemption(
            household=household, parent=foreign_parent, redemption_id=redemption.pk
        )
    assert Redemption.objects.get(pk=redemption.pk).status == Redemption.Status.PENDING


@pytest.mark.django_db
def test_a_child_cannot_fulfil_through_this_service(household, child, reward):
    credit(household, child, 20, key='c1')
    redemption, _ = redeem_reward(
        household=household, child=child, reward_id=reward.pk, idempotency_key='k1'
    )

    with pytest.raises(RewardAuthorityError):
        fulfil_redemption(
            household=household, parent=child, redemption_id=redemption.pk
        )
    assert Redemption.objects.get(pk=redemption.pk).status == Redemption.Status.PENDING


# --- cancel_redemption ---------------------------------------------------------


@pytest.mark.django_db
def test_cancel_refunds_the_points_in_a_new_positive_entry(
    household, child, parent, reward
):
    credit(household, child, 20, key='c1')
    redemption, _ = redeem_reward(
        household=household, child=child, reward_id=reward.pk, idempotency_key='k1'
    )
    assert balance_for_user(household, child) == 5

    cancelled = cancel_redemption(
        household=household, parent=parent, redemption_id=redemption.pk
    )

    assert cancelled.status == Redemption.Status.CANCELLED
    assert cancelled.decided_by_id == parent.pk
    assert balance_for_user(household, child) == 20

    debit = LedgerEntry.objects.get(idempotency_key=f'redemption:{redemption.pk}:debit')
    refund = LedgerEntry.objects.get(
        idempotency_key=f'redemption:{redemption.pk}:refund'
    )
    assert debit.amount == -15
    assert refund.amount == 15
    assert debit.reason == LedgerEntry.Reason.REWARD_DEBIT
    assert refund.reason == LedgerEntry.Reason.REWARD_DEBIT
    # The ledger is append-only: cancelling adds a row, never edits the debit.
    assert LedgerEntry.objects.filter(source_id=str(redemption.pk)).count() == 2

    event = one_event('reward.cancel')
    assert event.actor_id == parent.pk
    assert event.context['status'] == {'before': 'pending', 'after': 'cancelled'}


@pytest.mark.django_db
def test_cancel_is_refused_once_fulfilled_and_never_double_refunds(
    household, child, parent, reward
):
    credit(household, child, 20, key='c1')
    redemption, _ = redeem_reward(
        household=household, child=child, reward_id=reward.pk, idempotency_key='k1'
    )
    fulfil_redemption(household=household, parent=parent, redemption_id=redemption.pk)

    with pytest.raises(Redemption.DoesNotExist):
        cancel_redemption(
            household=household, parent=parent, redemption_id=redemption.pk
        )

    assert balance_for_user(household, child) == 5
    assert (
        LedgerEntry.objects.filter(reason=LedgerEntry.Reason.REWARD_DEBIT).count() == 1
    )


@pytest.mark.django_db
def test_cancelling_twice_is_refused_the_second_time_and_refunds_once(
    household, child, parent, reward
):
    credit(household, child, 20, key='c1')
    redemption, _ = redeem_reward(
        household=household, child=child, reward_id=reward.pk, idempotency_key='k1'
    )
    cancel_redemption(household=household, parent=parent, redemption_id=redemption.pk)

    with pytest.raises(Redemption.DoesNotExist):
        cancel_redemption(
            household=household, parent=parent, redemption_id=redemption.pk
        )

    assert balance_for_user(household, child) == 20
    assert LedgerEntry.objects.filter(source_id=str(redemption.pk)).count() == 2


@pytest.mark.django_db
def test_a_child_cannot_cancel_through_this_service(household, child, reward):
    credit(household, child, 20, key='c1')
    redemption, _ = redeem_reward(
        household=household, child=child, reward_id=reward.pk, idempotency_key='k1'
    )

    with pytest.raises(RewardAuthorityError):
        cancel_redemption(
            household=household, parent=child, redemption_id=redemption.pk
        )
    assert Redemption.objects.get(pk=redemption.pk).status == Redemption.Status.PENDING
    assert balance_for_user(household, child) == 5
