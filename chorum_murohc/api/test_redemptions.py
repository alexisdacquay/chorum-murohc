"""Tests for the redemption endpoints: request, list, fulfil, and cancel.

Every fixture is synthetic. No credential, PIN, token, cookie or personal
datum appears in the data, the assertions or the failure output: the test
users are created without a usable password and are signed in through the
session machinery directly.

The awkward cases the permission matrix names are covered for every route:
unauthenticated, an inactive user holding a live session, the allowed role,
the denied role, no resolvable role, an ambiguous two-household caller, and
a cross-household identifier.
"""

import pytest
from django.conf import settings
from django.urls import resolve, reverse
from rest_framework.test import APIClient

from chorum_murohc.api.redemptions import (
    INSUFFICIENT_POINTS_DETAIL,
    RedemptionCancelView,
    RedemptionFulfilView,
    RedemptionListView,
)
from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity.models import Household, Membership, User
from chorum_murohc.ledger.models import LedgerEntry
from chorum_murohc.ledger.services import balance_for_user
from chorum_murohc.rewards.models import Redemption, Reward

LIST_PATH = '/api/v1/redemptions/'
SESSION_PATH = '/api/v1/auth/session/'
CSRF_COOKIE = settings.CSRF_COOKIE_NAME

CHILD_FIELDS = {
    'id',
    'reward_name',
    'reward_points',
    'status',
    'created_at',
    'decided_at',
}
PARENT_FIELDS = CHILD_FIELDS | {'child_id', 'child_username'}


def fulfil_path(redemption_id):
    return f'{LIST_PATH}{redemption_id}/fulfil/'


def cancel_path(redemption_id):
    return f'{LIST_PATH}{redemption_id}/cancel/'


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


@pytest.fixture
def parent_a(household_a):
    return make_member(household_a, 'synthetic-parent-a', Membership.Role.PARENT)


@pytest.fixture
def child_a(household_a):
    return make_member(household_a, 'synthetic-child-a', Membership.Role.CHILD)


@pytest.fixture
def parent_b(household_b):
    return make_member(household_b, 'synthetic-parent-b', Membership.Role.PARENT)


@pytest.fixture
def reward_a(household_a):
    return Reward.objects.create(household=household_a, name='Screen time', points=15)


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


def sign_in(api_client, user):
    api_client.force_login(user)
    api_client.get(SESSION_PATH)
    return api_client


def csrf_header(api_client):
    cookie = api_client.cookies.get(CSRF_COOKIE)
    return {'x-csrftoken': cookie.value} if cookie is not None else {}


def call(api_client, method, path, body=None, *, with_csrf=True):
    headers = csrf_header(api_client) if with_csrf else {}
    handler = getattr(api_client, method)
    if method == 'get':
        return handler(path, headers=headers)
    return handler(path, body or {}, format='json', headers=headers)


def field_names(item):
    return set(item.keys())


def audit_actions():
    return [event.action for event in AuditEvent.objects.all()]


def redeem(api_client, child, reward, key='k1'):
    sign_in(api_client, child)
    return call(
        api_client, 'post', LIST_PATH, {'reward': reward.pk, 'idempotency_key': key}
    )


# Routing


def test_the_routes_are_named_and_resolve():
    assert reverse('api_v1:redemption-list') == LIST_PATH
    assert (
        reverse('api_v1:redemption-fulfil', args=(7,))
        == '/api/v1/redemptions/7/fulfil/'
    )
    assert (
        reverse('api_v1:redemption-cancel', args=(7,))
        == '/api/v1/redemptions/7/cancel/'
    )

    assert resolve(LIST_PATH).func.view_class is RedemptionListView
    assert resolve(fulfil_path(7)).func.view_class is RedemptionFulfilView
    assert resolve(cancel_path(7)).func.view_class is RedemptionCancelView


# Redeeming


def test_a_child_redeems_a_reward_and_debits_the_ledger(
    api_client, household_a, child_a, reward_a
):
    credit(household_a, child_a, 20, key='c1')

    response = redeem(api_client, child_a, reward_a)

    assert response.status_code == 201
    body = response.json()
    assert field_names(body) == CHILD_FIELDS
    assert body['reward_name'] == 'Screen time'
    assert body['reward_points'] == 15
    assert body['status'] == 'pending'
    assert body['decided_at'] is None
    assert balance_for_user(household_a, child_a) == 5
    assert audit_actions() == ['reward.request']


def test_insufficient_points_is_refused_compactly_and_writes_nothing(
    api_client, household_a, child_a, reward_a
):
    credit(household_a, child_a, 10, key='c1')

    response = redeem(api_client, child_a, reward_a)

    assert response.status_code == 400
    assert response.json() == {'reward': [INSUFFICIENT_POINTS_DETAIL]}
    assert Redemption.objects.count() == 0
    assert balance_for_user(household_a, child_a) == 10
    assert audit_actions() == []


def test_a_repeated_idempotency_key_returns_the_same_row_without_a_second_debit(
    api_client, household_a, child_a, reward_a
):
    credit(household_a, child_a, 20, key='c1')

    first = redeem(api_client, child_a, reward_a, key='same-key')
    second = redeem(api_client, child_a, reward_a, key='same-key')

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()['id'] == second.json()['id']
    assert Redemption.objects.count() == 1
    assert balance_for_user(household_a, child_a) == 5


def test_an_unknown_inactive_or_foreign_reward_is_a_generic_404(
    api_client, household_a, household_b, child_a, reward_a
):
    reward_a.is_active = False
    reward_a.save()
    foreign = Reward.objects.create(household=household_b, name='Foreign', points=1)
    credit(household_a, child_a, 100, key='c1')

    sign_in(api_client, child_a)
    for reward_id, key in ((reward_a.pk, 'k1'), (foreign.pk, 'k2'), (999999, 'k3')):
        response = call(
            api_client, 'post', LIST_PATH, {'reward': reward_id, 'idempotency_key': key}
        )
        assert response.status_code == 404, reward_id

    assert Redemption.objects.count() == 0


def test_a_missing_idempotency_key_is_a_validation_error(
    api_client, household_a, child_a, reward_a
):
    credit(household_a, child_a, 100, key='c1')
    sign_in(api_client, child_a)

    response = call(api_client, 'post', LIST_PATH, {'reward': reward_a.pk})

    assert response.status_code == 400
    assert 'idempotency_key' in response.json()
    assert Redemption.objects.count() == 0


def test_a_parent_cannot_redeem(api_client, household_a, parent_a, reward_a):
    credit(household_a, parent_a, 100, key='c1')

    response = redeem(api_client, parent_a, reward_a)

    assert response.status_code == 403
    assert Redemption.objects.count() == 0


# Listing


def test_a_child_sees_only_their_own_redemptions(
    api_client, household_a, child_a, reward_a
):
    other_child = make_member(household_a, 'other-child', Membership.Role.CHILD)
    credit(household_a, child_a, 20, key='c1')
    credit(household_a, other_child, 20, key='c2')
    redeem(api_client, child_a, reward_a, key='mine')
    redeem(api_client, other_child, reward_a, key='theirs')

    sign_in(api_client, child_a)
    response = api_client.get(LIST_PATH)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert field_names(body[0]) == CHILD_FIELDS


def test_a_parent_sees_every_redemption_in_the_household_with_who_asked(
    api_client, household_a, parent_a, child_a, reward_a
):
    credit(household_a, child_a, 20, key='c1')
    redeem(api_client, child_a, reward_a, key='k1')

    sign_in(api_client, parent_a)
    response = api_client.get(LIST_PATH)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert field_names(body[0]) == PARENT_FIELDS
    assert body[0]['child_id'] == child_a.pk
    assert body[0]['child_username'] == child_a.username


def test_another_household_never_appears_in_either_list(
    api_client, household_a, household_b, parent_a, child_a, reward_a
):
    foreign_child = make_member(household_b, 'foreign-child', Membership.Role.CHILD)
    foreign_reward = Reward.objects.create(
        household=household_b, name='Foreign reward', points=1
    )
    credit(household_b, foreign_child, 10, key='fc')
    redeem(api_client, foreign_child, foreign_reward, key='fk')

    for user in (parent_a, child_a):
        client = APIClient(enforce_csrf_checks=True)
        sign_in(client, user)
        response = client.get(LIST_PATH)
        assert response.status_code == 200
        assert response.json() == []


# Fulfilling and cancelling


def test_a_parent_fulfils_a_pending_redemption_and_points_do_not_move(
    api_client, household_a, parent_a, child_a, reward_a
):
    credit(household_a, child_a, 20, key='c1')
    redemption_id = redeem(api_client, child_a, reward_a).json()['id']
    balance_before = balance_for_user(household_a, child_a)

    sign_in(api_client, parent_a)
    response = call(api_client, 'post', fulfil_path(redemption_id))

    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'fulfilled'
    assert body['decided_at'] is not None
    assert balance_for_user(household_a, child_a) == balance_before
    assert audit_actions() == ['reward.fulfil', 'reward.request']


def test_a_parent_cancels_a_pending_redemption_and_the_points_return(
    api_client, household_a, parent_a, child_a, reward_a
):
    credit(household_a, child_a, 20, key='c1')
    redemption_id = redeem(api_client, child_a, reward_a).json()['id']

    sign_in(api_client, parent_a)
    response = call(api_client, 'post', cancel_path(redemption_id))

    assert response.status_code == 200
    assert response.json()['status'] == 'cancelled'
    assert balance_for_user(household_a, child_a) == 20
    assert audit_actions() == ['reward.cancel', 'reward.request']


@pytest.mark.parametrize('action_path', (fulfil_path, cancel_path))
def test_a_decided_redemption_cannot_be_decided_again(
    api_client, household_a, parent_a, child_a, reward_a, action_path
):
    credit(household_a, child_a, 20, key='c1')
    redemption_id = redeem(api_client, child_a, reward_a).json()['id']
    sign_in(api_client, parent_a)
    first = call(api_client, 'post', action_path(redemption_id))
    assert first.status_code == 200

    second = call(api_client, 'post', action_path(redemption_id))

    assert second.status_code == 404


@pytest.mark.parametrize('action_path', (fulfil_path, cancel_path))
def test_a_child_cannot_fulfil_or_cancel(
    api_client, household_a, child_a, reward_a, action_path
):
    credit(household_a, child_a, 20, key='c1')
    redemption_id = redeem(api_client, child_a, reward_a).json()['id']

    sign_in(api_client, child_a)
    response = call(api_client, 'post', action_path(redemption_id))

    assert response.status_code == 403
    assert Redemption.objects.get(pk=redemption_id).status == Redemption.Status.PENDING


@pytest.mark.parametrize('action_path', (fulfil_path, cancel_path))
def test_a_cross_household_parent_gets_the_generic_404(
    api_client, household_a, household_b, parent_b, child_a, reward_a, action_path
):
    credit(household_a, child_a, 20, key='c1')
    redemption_id = redeem(api_client, child_a, reward_a).json()['id']

    sign_in(api_client, parent_b)
    response = call(api_client, 'post', action_path(redemption_id))

    assert response.status_code == 404
    assert Redemption.objects.get(pk=redemption_id).status == Redemption.Status.PENDING


# Denied callers on every route


def every_route(redemption_id):
    return (
        ('get', LIST_PATH),
        ('post', LIST_PATH),
        ('post', fulfil_path(redemption_id)),
        ('post', cancel_path(redemption_id)),
    )


def test_an_unauthenticated_caller_is_refused_every_route(
    api_client, household_a, child_a, reward_a
):
    credit(household_a, child_a, 20, key='c1')
    redemption_id = redeem(api_client, child_a, reward_a).json()['id']

    anonymous = APIClient(enforce_csrf_checks=True)
    anonymous.get(SESSION_PATH)
    for method, path in every_route(redemption_id):
        response = call(
            anonymous, method, path, {'reward': reward_a.pk, 'idempotency_key': 'x'}
        )
        assert response.status_code == 403, (method, path)


def test_a_deactivated_user_with_a_live_session_is_refused_every_route(
    api_client, household_a, parent_a, child_a, reward_a
):
    credit(household_a, child_a, 20, key='c1')
    redemption_id = redeem(api_client, child_a, reward_a).json()['id']
    sign_in(api_client, parent_a)
    parent_a.is_active = False
    parent_a.save(update_fields=('is_active',))

    for method, path in every_route(redemption_id):
        response = call(
            api_client, method, path, {'reward': reward_a.pk, 'idempotency_key': 'x'}
        )
        assert response.status_code == 403, (method, path)


def test_a_caller_with_no_membership_is_refused_every_route(
    api_client, household_a, child_a, reward_a
):
    credit(household_a, child_a, 20, key='c1')
    redemption_id = redeem(api_client, child_a, reward_a).json()['id']
    outsider = make_user('synthetic-outsider')
    sign_in(api_client, outsider)

    for method, path in every_route(redemption_id):
        response = call(
            api_client, method, path, {'reward': reward_a.pk, 'idempotency_key': 'x'}
        )
        assert response.status_code == 403, (method, path)


def test_a_membership_deleted_after_sign_in_is_refused_immediately(
    api_client, household_a, parent_a, child_a, reward_a
):
    credit(household_a, child_a, 20, key='c1')
    redemption_id = redeem(api_client, child_a, reward_a).json()['id']
    sign_in(api_client, parent_a)
    Membership.objects.filter(user=parent_a).delete()

    for method, path in every_route(redemption_id):
        response = call(
            api_client, method, path, {'reward': reward_a.pk, 'idempotency_key': 'x'}
        )
        assert response.status_code == 403, (method, path)


# CSRF and unsupported methods


def test_an_unsafe_method_without_a_csrf_token_is_refused_and_changes_nothing(
    api_client, household_a, child_a, reward_a
):
    credit(household_a, child_a, 20, key='c1')
    sign_in(api_client, child_a)

    response = call(
        api_client,
        'post',
        LIST_PATH,
        {'reward': reward_a.pk, 'idempotency_key': 'x'},
        with_csrf=False,
    )

    assert response.status_code == 403
    assert Redemption.objects.count() == 0


@pytest.mark.parametrize('method', ('put', 'delete', 'patch'))
def test_an_unsupported_method_on_the_collection_is_refused(
    api_client, parent_a, method
):
    sign_in(api_client, parent_a)

    response = call(api_client, method, LIST_PATH)

    assert response.status_code == 405
