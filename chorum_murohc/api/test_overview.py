"""Tests for the parent-only household overview endpoint.

Every fixture is synthetic. No credential, PIN, token, cookie or personal
datum appears in the data, the assertions or the failure output: the test
users are created without a usable password and are signed in through the
session machinery directly, so there is nothing sensitive to print.
"""

import pytest
from django.urls import resolve, reverse
from django.utils import timezone
from rest_framework.test import APIClient

from chorum_murohc.api.overview import OverviewView
from chorum_murohc.api.permissions import PERMISSION_DENIED_DETAIL
from chorum_murohc.chores.models import Chore
from chorum_murohc.creatures.models import CreatureSelection
from chorum_murohc.identity.models import Household, Membership, User
from chorum_murohc.ledger.models import LedgerEntry
from chorum_murohc.progression.models import MAX_LEVEL
from chorum_murohc.submissions.models import Submission

OVERVIEW_PATH = '/api/v1/overview/'

DENIED_BODY = {'detail': PERMISSION_DENIED_DETAIL}


@pytest.fixture
def api_client():
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def household_a(db):
    return Household.objects.create(name='Synthetic Household A')


@pytest.fixture
def household_b(db):
    return Household.objects.create(name='Synthetic Household B')


def make_user(username):
    return User.objects.create_user(username=username)


def make_member(household, username, role):
    user = make_user(username)
    Membership.objects.create(household=household, user=user, role=role)
    return user


def deactivate(user):
    user.is_active = False
    user.save(update_fields=('is_active',))
    return user


@pytest.fixture
def parent_a(household_a):
    return make_member(household_a, 'synthetic-parent-a', Membership.Role.PARENT)


@pytest.fixture
def child_a(household_a):
    return make_member(household_a, 'synthetic-child-a', Membership.Role.CHILD)


def sign_in(api_client, user):
    api_client.force_login(user)
    return api_client


def make_chore(household, *, name='Wash dishes', points=10):
    return Chore.objects.create(household=household, name=name, points=points)


def credit(
    household, user, amount, *, reason=LedgerEntry.Reason.CHORE_CREDIT, offset=0
):
    return LedgerEntry.objects.create(
        household=household,
        user=user,
        amount=amount,
        reason=reason,
        source_type='synthetic.Source',
        source_id=f'synthetic-{offset}',
        idempotency_key=f'synthetic-{user.pk}-{offset}',
    )


def pick_creature(household, user, slug):
    return CreatureSelection.objects.create(
        household=household, user=user, line_slug=slug
    )


def make_submission(
    household, child, chore, *, status=Submission.Status.PENDING, decided_by=None
):
    """A submission can only be created pending (the model's own rule); a
    decided one is created pending and then transitioned, exactly as
    `test_approvals.py`'s own fixture does."""
    submission = Submission.objects.create(
        household=household,
        child=child,
        chore=chore,
        chore_name=chore.name,
        chore_points=chore.points,
        idempotency_key=f'synthetic-submission-{child.pk}-{chore.pk}-{chore.name}',
    )
    if status != Submission.Status.PENDING:
        submission.status = status
        submission.decided_by = decided_by
        submission.decided_at = timezone.now()
        submission.save()
    return submission


# Routing


def test_the_route_is_named_and_resolves():
    assert reverse('api_v1:overview') == OVERVIEW_PATH
    assert resolve(OVERVIEW_PATH).func.view_class is OverviewView


# Authority


def test_an_unauthenticated_caller_is_refused(api_client, household_a):
    response = api_client.get(OVERVIEW_PATH)

    assert response.status_code == 403
    assert 'children' not in response.json()


def test_a_child_is_refused(api_client, household_a, child_a):
    sign_in(api_client, child_a)

    response = api_client.get(OVERVIEW_PATH)

    assert response.status_code == 403
    assert response.json() == DENIED_BODY


def test_a_parent_with_no_resolvable_household_is_refused(api_client, db):
    lone_parent = make_user('synthetic-lone-parent')
    sign_in(api_client, lone_parent)

    response = api_client.get(OVERVIEW_PATH)

    assert response.status_code == 403
    assert response.json() == DENIED_BODY


def test_an_unsupported_method_is_a_compact_405(api_client, household_a, parent_a):
    sign_in(api_client, parent_a)

    response = api_client.post(OVERVIEW_PATH)

    assert response.status_code == 405
    assert set(response.json()) == {'detail'}


# Empty and partial data


def test_a_household_with_only_a_parent_has_an_empty_summary(
    api_client, household_a, parent_a
):
    sign_in(api_client, parent_a)

    response = api_client.get(OVERVIEW_PATH)

    assert response.status_code == 200
    assert response.json() == {
        'children': [],
        'parents': [{'id': parent_a.pk, 'username': parent_a.username}],
        'pending_total': 0,
    }


def test_a_child_with_no_activity_reads_as_the_true_zero_state(
    api_client, household_a, parent_a, child_a
):
    sign_in(api_client, parent_a)

    response = api_client.get(OVERVIEW_PATH)

    assert response.status_code == 200
    assert response.json()['children'] == [
        {
            'id': child_a.pk,
            'username': child_a.username,
            'balance': 0,
            'level': 0,
            'max_level': MAX_LEVEL,
            'creature_line': None,
            'creature_form': None,
            'pending_count': 0,
        }
    ]


def test_a_deactivated_member_is_left_off_the_summary(
    api_client, household_a, parent_a
):
    deactivate(make_member(household_a, 'synthetic-child-gone', Membership.Role.CHILD))
    sign_in(api_client, parent_a)

    response = api_client.get(OVERVIEW_PATH)

    assert response.json()['children'] == []


# Full composition: balance, level, creature, pending


def test_balance_is_the_full_ledger_sum_including_debits(
    api_client, household_a, parent_a, child_a
):
    credit(household_a, child_a, 100, offset=0)
    credit(household_a, child_a, -30, reason=LedgerEntry.Reason.REWARD_DEBIT, offset=1)
    sign_in(api_client, parent_a)

    response = api_client.get(OVERVIEW_PATH)

    assert response.json()['children'][0]['balance'] == 70


def test_level_is_computed_from_lifetime_points_not_current_balance(
    api_client, household_a, parent_a, child_a
):
    # 150 lifetime points reaches level 2; the later debit must not demote it.
    credit(household_a, child_a, 150, offset=0)
    credit(household_a, child_a, -140, reason=LedgerEntry.Reason.REWARD_DEBIT, offset=1)
    sign_in(api_client, parent_a)

    response = api_client.get(OVERVIEW_PATH)

    child = response.json()['children'][0]
    assert child['balance'] == 10
    assert child['level'] == 2
    assert child['max_level'] == MAX_LEVEL


def test_creature_summary_names_the_line_and_current_form_only(
    api_client, household_a, parent_a, child_a
):
    credit(household_a, child_a, 500, offset=0)  # level 4: unlocks the second form
    pick_creature(household_a, child_a, 'dragon')
    sign_in(api_client, parent_a)

    response = api_client.get(OVERVIEW_PATH)

    child = response.json()['children'][0]
    assert child['creature_line'] == 'Dragon'
    assert child['creature_form'] == 'Fledgling'
    # The minimal summary, never the full four-form unlock list.
    assert 'forms' not in child


def test_a_choice_below_the_first_unlock_level_has_no_current_form_yet(
    api_client, household_a, parent_a, child_a
):
    pick_creature(household_a, child_a, 'dragon')
    sign_in(api_client, parent_a)

    response = api_client.get(OVERVIEW_PATH)

    child = response.json()['children'][0]
    assert child['creature_line'] == 'Dragon'
    assert child['creature_form'] is None


def test_pending_count_is_pending_only_not_decided_submissions(
    api_client, household_a, parent_a, child_a
):
    chore = make_chore(household_a)
    make_submission(household_a, child_a, chore, status=Submission.Status.PENDING)
    decided_chore = make_chore(household_a, name='Take out bins')
    make_submission(
        household_a,
        child_a,
        decided_chore,
        status=Submission.Status.APPROVED,
        decided_by=parent_a,
    )
    sign_in(api_client, parent_a)

    response = api_client.get(OVERVIEW_PATH)

    body = response.json()
    assert body['children'][0]['pending_count'] == 1
    assert body['pending_total'] == 1


def test_pending_total_sums_every_child(api_client, household_a, parent_a):
    child_one = make_member(household_a, 'synthetic-child-one', Membership.Role.CHILD)
    child_two = make_member(household_a, 'synthetic-child-two', Membership.Role.CHILD)
    chore = make_chore(household_a)
    make_submission(household_a, child_one, chore)
    another_chore = make_chore(household_a, name='Feed the cat')
    make_submission(household_a, child_two, another_chore)
    make_submission(household_a, child_two, make_chore(household_a, name='Sweep'))
    sign_in(api_client, parent_a)

    response = api_client.get(OVERVIEW_PATH)

    assert response.json()['pending_total'] == 3


# Household isolation


def test_a_foreign_household_never_appears(
    api_client, household_a, household_b, parent_a
):
    foreign_parent = make_member(
        household_b, 'synthetic-parent-b', Membership.Role.PARENT
    )
    foreign_child = make_member(household_b, 'synthetic-child-b', Membership.Role.CHILD)
    credit(household_b, foreign_child, 500, offset=0)
    sign_in(api_client, parent_a)

    response = api_client.get(OVERVIEW_PATH)

    body = response.json()
    assert body['children'] == []
    assert body['parents'] == [{'id': parent_a.pk, 'username': parent_a.username}]
    assert str(foreign_parent.pk) not in response.content.decode()
    assert 'synthetic-child-b' not in response.content.decode()


# Stable ordering


def test_children_and_parents_are_ordered_by_username(
    api_client, household_a, parent_a
):
    make_member(household_a, 'zeta-child', Membership.Role.CHILD)
    make_member(household_a, 'alpha-child', Membership.Role.CHILD)
    make_member(household_a, 'beta-parent', Membership.Role.PARENT)
    sign_in(api_client, parent_a)

    response = api_client.get(OVERVIEW_PATH)

    body = response.json()
    assert [child['username'] for child in body['children']] == [
        'alpha-child',
        'zeta-child',
    ]
    assert [parent['username'] for parent in body['parents']] == [
        'beta-parent',
        'synthetic-parent-a',
    ]


# Query count: fixed regardless of household size.
#
# 13, not 4: `household_overview` itself is exactly the 4 queries its own
# docstring promises (roster, points, creature, pending), but every request
# also re-derives "who is asking" twice over - once for `IsHouseholdParent`
# and once again inside the view, matching every other endpoint in this
# package (`api/balances.py`, `api/progression.py`, `api/creatures.py`) - and
# each of those two derivations costs its own household-candidate lookup, a
# membership lookup, and (via the `Membership.household` foreign key) a
# further household lookup, which is 13 fixed queries whatever the caller
# asks and however many members their household has. What this test actually
# guards is that second, variable part staying flat: a regression that
# resolved balance, level, creature or pending state per child instead of
# once for the whole household would grow this number with the child count
# below, not the fixed authority overhead.


def test_the_query_count_does_not_grow_with_one_child(
    api_client, household_a, parent_a, child_a, django_assert_num_queries
):
    credit(household_a, child_a, 50, offset=0)
    pick_creature(household_a, child_a, 'dragon')
    chore = make_chore(household_a)
    make_submission(household_a, child_a, chore)
    sign_in(api_client, parent_a)

    with django_assert_num_queries(13):
        response = api_client.get(OVERVIEW_PATH)
    assert response.status_code == 200


def test_the_query_count_does_not_grow_with_five_children(
    api_client, household_a, parent_a, django_assert_num_queries
):
    for index in range(5):
        child = make_member(
            household_a, f'synthetic-child-{index}', Membership.Role.CHILD
        )
        credit(household_a, child, 50 + index, offset=0)
        pick_creature(household_a, child, 'dragon')
        chore = make_chore(household_a, name=f'Chore {index}')
        make_submission(household_a, child, chore)
    sign_in(api_client, parent_a)

    with django_assert_num_queries(13):
        response = api_client.get(OVERVIEW_PATH)
    assert response.status_code == 200
