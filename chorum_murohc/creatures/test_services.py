"""Tests for choosing a creature line and resolving unlocked forms.

Every fixture is synthetic: the users are created without a usable password,
so nothing sensitive appears in the data or in a failure message.

The interesting behaviour is at the boundaries. A form unlocks at exactly its
level and not one point earlier; a child below level 1 has chosen a line but
holds no form; selection is write-once; and a level is never stored, so the
same ledger read that drives `/levels` drives the creature too.
"""

import pytest

from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.creatures.catalogue import CREATURE_LINES, line_for_slug
from chorum_murohc.creatures.models import CreatureSelection
from chorum_murohc.creatures.services import (
    AUDIT_LINE_SELECTED,
    CreatureLineAlreadyChosenError,
    UnknownCreatureLineError,
    creature_state_for_user,
    select_creature_line,
    selected_line_slug,
)
from chorum_murohc.identity.models import Household, Membership, User
from chorum_murohc.ledger.models import LedgerEntry

# Lifetime points that reach each of the four unlock levels exactly, read from
# `progression.services.LEVEL_THRESHOLDS`: levels 1, 4, 7 and 10.
POINTS_FOR_LEVEL = {1: 50, 4: 500, 7: 1400, 10: 2750}


@pytest.fixture
def household(db):
    return Household.objects.create(name='Synthetic Household')


def make_child(household, username):
    user = User.objects.create_user(username=username)
    Membership.objects.create(
        household=household, user=user, role=Membership.Role.CHILD
    )
    return user


@pytest.fixture
def child(household):
    return make_child(household, 'synthetic-child')


def credit(household, user, amount, key):
    LedgerEntry.objects.create(
        household=household,
        user=user,
        amount=amount,
        reason=LedgerEntry.Reason.CHORE_CREDIT,
        source_type='synthetic.Source',
        source_id=key,
        idempotency_key=key,
    )


# Reading before anything is chosen


def test_a_child_with_no_selection_has_no_line_and_no_forms(household, child):
    state = creature_state_for_user(household, child)

    assert state == {
        'level': 0,
        'max_level': 10,
        'line': None,
        'current_form': None,
        'forms': [],
    }
    assert selected_line_slug(household, child) is None


# Choosing


def test_choosing_records_the_line_and_emits_one_audit_event(household, child):
    state, created = select_creature_line(household, child, 'kraken')

    assert created is True
    assert state['line']['slug'] == 'kraken'
    assert state['line']['name'] == 'Kraken'
    assert selected_line_slug(household, child) == 'kraken'

    events = AuditEvent.objects.filter(action=AUDIT_LINE_SELECTED)
    assert events.count() == 1
    event = events.get()
    assert event.household_id == household.pk
    assert event.actor_id == child.pk
    assert event.context['line_slug'] == 'kraken'


def test_choosing_the_same_line_again_changes_nothing_and_emits_nothing(
    household, child
):
    select_creature_line(household, child, 'phoenix')

    state, created = select_creature_line(household, child, 'phoenix')

    assert created is False
    assert state['line']['slug'] == 'phoenix'
    assert (
        CreatureSelection.objects.filter(household=household, user=child).count() == 1
    )
    assert AuditEvent.objects.filter(action=AUDIT_LINE_SELECTED).count() == 1


def test_choosing_a_different_line_is_refused_and_leaves_the_first(household, child):
    select_creature_line(household, child, 'treant')

    with pytest.raises(CreatureLineAlreadyChosenError):
        select_creature_line(household, child, 'dragon')

    assert selected_line_slug(household, child) == 'treant'
    assert AuditEvent.objects.filter(action=AUDIT_LINE_SELECTED).count() == 1


def test_an_unknown_line_is_refused_before_anything_is_written(household, child):
    with pytest.raises(UnknownCreatureLineError):
        select_creature_line(household, child, 'pikachu')

    assert CreatureSelection.objects.count() == 0
    assert AuditEvent.objects.count() == 0


def test_two_children_hold_separate_selections(household, child):
    sibling = make_child(household, 'synthetic-sibling')

    select_creature_line(household, child, 'golem')
    select_creature_line(household, sibling, 'sphinx')

    assert selected_line_slug(household, child) == 'golem'
    assert selected_line_slug(household, sibling) == 'sphinx'


def test_a_selection_in_another_household_is_not_read_here(household, child):
    other_household = Household.objects.create(name='Synthetic Household B')
    other_child = make_child(other_household, 'synthetic-other-child')
    select_creature_line(other_household, other_child, 'griffin')

    assert selected_line_slug(household, child) is None
    assert creature_state_for_user(household, child)['line'] is None


# Unlocking


def test_a_chosen_line_below_level_one_shows_four_locked_forms(household, child):
    select_creature_line(household, child, 'dragon')

    state = creature_state_for_user(household, child)

    assert state['level'] == 0
    assert state['current_form'] is None
    assert [form['unlocked'] for form in state['forms']] == [False] * 4
    assert [form['unlock_level'] for form in state['forms']] == [1, 4, 7, 10]


@pytest.mark.parametrize(
    ('level', 'expected_unlocked'),
    [
        (1, [True, False, False, False]),
        (4, [True, True, False, False]),
        (7, [True, True, True, False]),
        (10, [True, True, True, True]),
    ],
)
def test_each_form_unlocks_exactly_at_its_level(
    household, child, level, expected_unlocked
):
    select_creature_line(household, child, 'dragon')
    credit(household, child, POINTS_FOR_LEVEL[level], f'credit-{level}')

    state = creature_state_for_user(household, child)

    assert state['level'] == level
    assert [form['unlocked'] for form in state['forms']] == expected_unlocked
    assert state['current_form']['index'] == expected_unlocked.count(True)


def test_one_point_short_of_a_threshold_does_not_unlock_the_next_form(household, child):
    select_creature_line(household, child, 'dragon')
    credit(household, child, POINTS_FOR_LEVEL[4] - 1, 'credit-just-short')

    state = creature_state_for_user(household, child)

    assert state['level'] == 3
    assert state['current_form']['index'] == 1
    assert [form['unlocked'] for form in state['forms']] == [True, False, False, False]


def test_spending_points_never_locks_a_form_again(household, child):
    select_creature_line(household, child, 'dragon')
    credit(household, child, POINTS_FOR_LEVEL[4], 'credit-1')
    LedgerEntry.objects.create(
        household=household,
        user=child,
        amount=-POINTS_FOR_LEVEL[4],
        reason=LedgerEntry.Reason.REWARD_DEBIT,
        source_type='synthetic.Source',
        source_id='debit-1',
        idempotency_key='debit-1',
    )

    state = creature_state_for_user(household, child)

    assert state['level'] == 4
    assert state['current_form']['index'] == 2


def test_every_form_carries_the_drawing_and_text_the_catalogue_holds(household, child):
    select_creature_line(household, child, 'phoenix')
    credit(household, child, POINTS_FOR_LEVEL[10], 'credit-max')

    state = creature_state_for_user(household, child)
    catalogue_line = line_for_slug('phoenix')

    assert len(state['forms']) == 4
    for form, expected in zip(state['forms'], catalogue_line.forms, strict=True):
        assert form['name'] == expected.name
        assert form['alt_text'] == expected.alt_text
        assert form['asset_path'] == expected.asset_path


def test_every_line_in_the_catalogue_can_be_chosen(household):
    for index, line in enumerate(CREATURE_LINES):
        child = make_child(household, f'synthetic-child-{index}')

        state, created = select_creature_line(household, child, line.slug)

        assert created is True
        assert state['line']['slug'] == line.slug
        assert len(state['forms']) == 4
