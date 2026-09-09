"""Tests for the level arithmetic and the acknowledge write.

Every fixture is synthetic. No credential, PIN, token, cookie or personal
datum appears in the data, the assertions or the failure output: the test
users are created without a usable password, so there is nothing sensitive to
print.
"""

import pytest

from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity.models import Household, Membership, User
from chorum_murohc.ledger.models import LedgerEntry
from chorum_murohc.progression.models import MAX_LEVEL, LevelAcknowledgement
from chorum_murohc.progression.services import (
    LEVEL_THRESHOLDS,
    acknowledge_level_up,
    level_for_lifetime_points,
    pending_level_up_for_user,
    progression_for_user,
    progression_summary_for_user,
)


def _household(name='Progression household'):
    return Household.objects.create(name=name)


def _child(household, username='child'):
    user = User.objects.create_user(username=username)
    Membership.objects.create(
        household=household, user=user, role=Membership.Role.CHILD
    )
    return user


def _credit(household, user, amount, key):
    return LedgerEntry.objects.create(
        household=household,
        user=user,
        amount=amount,
        reason=LedgerEntry.Reason.CHORE_CREDIT,
        source_type='synthetic.Source',
        source_id=key,
        idempotency_key=key,
    )


@pytest.fixture
def household(db):
    return _household()


@pytest.fixture
def child(household):
    return _child(household)


# The threshold table itself


def test_there_are_exactly_ten_levels_matching_the_decided_policy():
    assert LEVEL_THRESHOLDS == (50, 150, 300, 500, 750, 1050, 1400, 1800, 2250, 2750)
    assert MAX_LEVEL == 10


# level_for_lifetime_points


@pytest.mark.parametrize(
    ('lifetime_points', 'expected_level'),
    (
        (0, 0),
        (49, 0),
        (50, 1),
        (149, 1),
        (150, 2),
        (2749, 9),
        (2750, 10),
        (999999, 10),
    ),
)
def test_level_for_lifetime_points_matches_the_decided_thresholds(
    lifetime_points, expected_level
):
    assert level_for_lifetime_points(lifetime_points) == expected_level


def test_every_threshold_lands_exactly_on_its_own_level():
    for index, threshold in enumerate(LEVEL_THRESHOLDS, start=1):
        assert level_for_lifetime_points(threshold) == index
        assert level_for_lifetime_points(threshold - 1) == index - 1


# progression_for_user


def test_a_child_with_no_ledger_entry_is_level_zero(household, child):
    state = progression_for_user(household, child)

    assert state == {
        'level': 0,
        'max_level': MAX_LEVEL,
        'lifetime_points': 0,
        'next_level_threshold': 50,
        'points_to_next_level': 50,
    }


def test_a_debit_never_lowers_the_level(household, child):
    _credit(household, child, 100, 'credit-1')
    LedgerEntry.objects.create(
        household=household,
        user=child,
        amount=-60,
        reason=LedgerEntry.Reason.REWARD_DEBIT,
        source_type='synthetic.Source',
        source_id='debit-1',
        idempotency_key='debit-1',
    )

    state = progression_for_user(household, child)

    assert state['lifetime_points'] == 100
    assert state['level'] == level_for_lifetime_points(100)


def test_at_the_maximum_level_there_is_nothing_further_to_reach(household, child):
    _credit(household, child, 10_000, 'credit-max')

    state = progression_for_user(household, child)

    assert state['level'] == MAX_LEVEL
    assert state['next_level_threshold'] is None
    assert state['points_to_next_level'] is None
    # Points themselves keep accruing: the maximum caps levelling, not the
    # figure a child sees.
    assert state['lifetime_points'] == 10_000


def test_progression_never_writes(household, child):
    _credit(household, child, 60, 'credit-1')

    progression_for_user(household, child)

    assert LevelAcknowledgement.objects.count() == 0
    assert AuditEvent.objects.count() == 0


# pending_level_up_for_user and progression_summary_for_user


def test_a_fresh_child_with_no_row_and_level_zero_has_nothing_pending(household, child):
    assert pending_level_up_for_user(household, child) is None


def test_a_freshly_reached_level_is_pending_until_acknowledged(household, child):
    _credit(household, child, 60, 'credit-1')

    assert pending_level_up_for_user(household, child) == 1

    summary = progression_summary_for_user(household, child)
    assert summary['level'] == 1
    assert summary['pending_level_up'] == 1


def test_a_level_already_shown_is_no_longer_pending(household, child):
    _credit(household, child, 60, 'credit-1')
    acknowledge_level_up(household, child)

    assert pending_level_up_for_user(household, child) is None


def test_skipping_several_levels_at_once_offers_only_the_current_one(household, child):
    # One large credit crosses three thresholds (50, 150, 300) in one step.
    _credit(household, child, 320, 'credit-big')

    assert level_for_lifetime_points(320) == 3
    assert pending_level_up_for_user(household, child) == 3


# acknowledge_level_up


def test_acknowledging_a_newly_reached_level_records_the_marker_and_one_event(
    household, child
):
    _credit(household, child, 60, 'credit-1')

    summary, changed = acknowledge_level_up(household, child)

    assert changed is True
    assert summary['level'] == 1
    assert summary['pending_level_up'] is None

    row = LevelAcknowledgement.objects.get(household=household, user=child)
    assert row.highest_level_shown == 1

    event = AuditEvent.objects.get()
    assert event.household == household
    assert event.actor == child
    assert event.action == 'progression.level_up'
    assert event.target_type == 'progression'
    assert event.target_id == str(row.pk)
    assert event.context == {
        'actor_id': child.pk,
        'from_level': 0,
        'to_level': 1,
        'lifetime_points': 60,
    }


def test_a_repeat_acknowledge_with_nothing_new_changes_and_emits_nothing(
    household, child
):
    _credit(household, child, 60, 'credit-1')
    acknowledge_level_up(household, child)

    summary, changed = acknowledge_level_up(household, child)

    assert changed is False
    assert summary['pending_level_up'] is None
    assert AuditEvent.objects.count() == 1
    assert LevelAcknowledgement.objects.count() == 1


def test_a_call_with_nothing_ever_reached_changes_nothing(household, child):
    summary, changed = acknowledge_level_up(household, child)

    assert changed is False
    assert summary['level'] == 0
    assert AuditEvent.objects.count() == 0
    row = LevelAcknowledgement.objects.get(household=household, user=child)
    assert row.highest_level_shown == 0


def test_acknowledging_twice_after_two_separate_level_ups_writes_two_events(
    household, child
):
    _credit(household, child, 60, 'credit-1')
    acknowledge_level_up(household, child)

    _credit(household, child, 100, 'credit-2')  # lifetime now 160, level 2
    summary, changed = acknowledge_level_up(household, child)

    assert changed is True
    assert summary['level'] == 2
    assert AuditEvent.objects.count() == 2
    latest = AuditEvent.objects.order_by('-created_at', '-id').first()
    assert latest.context == {
        'actor_id': child.pk,
        'from_level': 1,
        'to_level': 2,
        'lifetime_points': 160,
    }


def test_acknowledge_is_scoped_to_the_named_household_and_user(household, child):
    other_household = _household('Other household')
    sibling = _child(household, 'sibling')
    _credit(household, child, 60, 'credit-1')
    _credit(household, sibling, 900, 'credit-sibling')

    acknowledge_level_up(household, child)

    assert LevelAcknowledgement.objects.filter(
        household=household, user=child, highest_level_shown=1
    ).exists()
    assert not LevelAcknowledgement.objects.filter(user=sibling).exists()
    assert not LevelAcknowledgement.objects.filter(household=other_household).exists()
