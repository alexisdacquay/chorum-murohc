"""Tests for the progression endpoints.

Every fixture is synthetic. No credential, PIN, token, cookie or personal
datum appears in the data, the assertions or the failure output: the test
users are created without a usable password and are signed in through the
session machinery directly, so there is nothing sensitive to print.

The awkward cases the permission matrix names are covered for both routes:
unauthenticated, an inactive user holding a live session, the allowed role,
the denied role, no resolvable role, an ambiguous two-household caller, and a
membership deleted after sign-in.
"""

import ast
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import resolve, reverse
from rest_framework.test import APIClient

from chorum_murohc.api import progression as progression_module
from chorum_murohc.api.permissions import PERMISSION_DENIED_DETAIL
from chorum_murohc.api.progression import ProgressionAcknowledgeView, ProgressionView
from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity.models import Household, Membership, User
from chorum_murohc.ledger.models import LedgerEntry
from chorum_murohc.progression.models import LevelAcknowledgement

READ_PATH = '/api/v1/progression/'
ACKNOWLEDGE_PATH = '/api/v1/progression/acknowledge/'
SESSION_PATH = '/api/v1/auth/session/'
CSRF_COOKIE = settings.CSRF_COOKIE_NAME

SUMMARY_FIELDS = {
    'level',
    'max_level',
    'lifetime_points',
    'next_level_threshold',
    'points_to_next_level',
    'pending_level_up',
}
NOT_AUTHENTICATED_DETAIL = 'Authentication credentials were not provided.'


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
    # No password is set, so there is no credential to leak.
    return User.objects.create_user(username=username)


def make_member(household, username, role=Membership.Role.CHILD):
    user = make_user(username)
    Membership.objects.create(household=household, user=user, role=role)
    return user


@pytest.fixture
def child_a(household_a):
    return make_member(household_a, 'synthetic-child-a')


@pytest.fixture
def sibling_a(household_a):
    return make_member(household_a, 'synthetic-sibling-a')


@pytest.fixture
def parent_a(household_a):
    return make_member(household_a, 'synthetic-parent-a', Membership.Role.PARENT)


def sign_in(api_client, user):
    """Give the client a live session and the CSRF cookie a browser holds."""
    api_client.force_login(user)
    api_client.get(SESSION_PATH)
    return api_client


def csrf_header(api_client):
    cookie = api_client.cookies.get(CSRF_COOKIE)
    return {'x-csrftoken': cookie.value} if cookie is not None else {}


def call(api_client, method, path, *, with_csrf=True):
    headers = csrf_header(api_client) if with_csrf else {}
    handler = getattr(api_client, method)
    if method == 'get':
        return handler(path, headers=headers)
    return handler(path, {}, format='json', headers=headers)


def credit(household, user, amount, key):
    return LedgerEntry.objects.create(
        household=household,
        user=user,
        amount=amount,
        reason=LedgerEntry.Reason.CHORE_CREDIT,
        source_type='synthetic.Source',
        source_id=key,
        idempotency_key=key,
    )


# Routing


def test_both_routes_are_named_and_resolve():
    assert reverse('api_v1:progression') == READ_PATH
    assert reverse('api_v1:progression-acknowledge') == ACKNOWLEDGE_PATH

    assert resolve(READ_PATH).func.view_class is ProgressionView
    assert resolve(ACKNOWLEDGE_PATH).func.view_class is ProgressionAcknowledgeView


# GET progression/


def test_a_fresh_child_reads_level_zero_with_the_exact_agreed_shape(
    api_client, child_a
):
    sign_in(api_client, child_a)

    response = api_client.get(READ_PATH)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == SUMMARY_FIELDS
    assert body == {
        'level': 0,
        'max_level': 10,
        'lifetime_points': 0,
        'next_level_threshold': 50,
        'points_to_next_level': 50,
        'pending_level_up': None,
    }


def test_lifetime_points_credit_a_level_and_it_is_pending_until_shown(
    api_client, household_a, child_a
):
    credit(household_a, child_a, 60, 'credit-1')
    sign_in(api_client, child_a)

    body = api_client.get(READ_PATH).json()

    assert body['level'] == 1
    assert body['lifetime_points'] == 60
    assert body['next_level_threshold'] == 150
    assert body['points_to_next_level'] == 90
    assert body['pending_level_up'] == 1


def test_a_debit_never_lowers_the_level(api_client, household_a, child_a):
    credit(household_a, child_a, 100, 'credit-1')
    LedgerEntry.objects.create(
        household=household_a,
        user=child_a,
        amount=-80,
        reason=LedgerEntry.Reason.REWARD_DEBIT,
        source_type='synthetic.Source',
        source_id='debit-1',
        idempotency_key='debit-1',
    )
    sign_in(api_client, child_a)

    body = api_client.get(READ_PATH).json()

    assert body['lifetime_points'] == 100
    assert body['level'] == 1


def test_at_the_maximum_both_next_fields_are_null_and_points_still_shown(
    api_client, household_a, child_a
):
    credit(household_a, child_a, 5000, 'credit-max')
    sign_in(api_client, child_a)

    body = api_client.get(READ_PATH).json()

    assert body['level'] == 10
    assert body['next_level_threshold'] is None
    assert body['points_to_next_level'] is None
    assert body['lifetime_points'] == 5000


def test_reading_writes_nothing(api_client, household_a, child_a):
    credit(household_a, child_a, 60, 'credit-1')
    sign_in(api_client, child_a)

    api_client.get(READ_PATH)
    api_client.get(READ_PATH)

    assert LevelAcknowledgement.objects.count() == 0
    assert AuditEvent.objects.count() == 0


# POST progression/acknowledge/


def test_acknowledging_clears_the_pending_flag_and_writes_one_event(
    api_client, household_a, child_a
):
    credit(household_a, child_a, 60, 'credit-1')
    sign_in(api_client, child_a)

    response = call(api_client, 'post', ACKNOWLEDGE_PATH)

    assert response.status_code == 200
    body = response.json()
    assert body['level'] == 1
    assert body['pending_level_up'] is None

    assert api_client.get(READ_PATH).json()['pending_level_up'] is None

    event = AuditEvent.objects.get()
    assert event.action == 'progression.level_up'
    assert event.target_type == 'progression'
    assert event.household == household_a
    assert event.actor == child_a
    assert event.context == {
        'actor_id': child_a.pk,
        'from_level': 0,
        'to_level': 1,
        'lifetime_points': 60,
    }


def test_acknowledging_twice_in_a_row_is_a_true_no_op(api_client, household_a, child_a):
    credit(household_a, child_a, 60, 'credit-1')
    sign_in(api_client, child_a)

    first = call(api_client, 'post', ACKNOWLEDGE_PATH)
    second = call(api_client, 'post', ACKNOWLEDGE_PATH)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert AuditEvent.objects.count() == 1


def test_acknowledging_with_nothing_ever_earned_changes_nothing(api_client, child_a):
    sign_in(api_client, child_a)

    response = call(api_client, 'post', ACKNOWLEDGE_PATH)

    assert response.status_code == 200
    assert response.json()['level'] == 0
    assert AuditEvent.objects.count() == 0


def test_the_client_cannot_supply_a_level_or_any_other_body_field(
    api_client, household_a, child_a
):
    credit(household_a, child_a, 60, 'credit-1')
    sign_in(api_client, child_a)
    headers = csrf_header(api_client)

    response = api_client.post(
        ACKNOWLEDGE_PATH,
        {'level': 10, 'pending_level_up': 99, 'household': 999},
        format='json',
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()['level'] == 1


def test_an_unsafe_method_without_a_csrf_token_is_refused_and_changes_nothing(
    api_client, household_a, child_a
):
    credit(household_a, child_a, 60, 'credit-1')
    sign_in(api_client, child_a)

    response = call(api_client, 'post', ACKNOWLEDGE_PATH, with_csrf=False)

    assert response.status_code == 403
    assert LevelAcknowledgement.objects.count() == 0
    assert AuditEvent.objects.count() == 0


# Method restrictions


def test_get_is_not_allowed_on_the_acknowledge_route(api_client, child_a):
    sign_in(api_client, child_a)

    response = api_client.get(ACKNOWLEDGE_PATH, headers=csrf_header(api_client))

    assert response.status_code == 405


def test_post_is_not_allowed_on_the_read_route(api_client, child_a):
    sign_in(api_client, child_a)

    response = call(api_client, 'post', READ_PATH)

    assert response.status_code == 405


# The permission matrix rows


BOTH_METHODS = (('get', READ_PATH), ('post', ACKNOWLEDGE_PATH))


def test_an_unauthenticated_caller_is_refused_both_routes(api_client, household_a):
    api_client.get(SESSION_PATH)

    for method, path in BOTH_METHODS:
        response = call(api_client, method, path)
        assert response.status_code == 403, path
        assert response.json() == {'detail': NOT_AUTHENTICATED_DETAIL}

    assert AuditEvent.objects.count() == 0


def test_a_deactivated_user_with_a_live_session_is_refused_both_routes(
    api_client, child_a
):
    sign_in(api_client, child_a)
    child_a.is_active = False
    child_a.save(update_fields=('is_active',))

    for method, path in BOTH_METHODS:
        response = call(api_client, method, path)
        assert response.status_code == 403, path
        assert response.json() == {'detail': NOT_AUTHENTICATED_DETAIL}


def test_a_caller_with_no_membership_is_refused_both_routes(db, api_client):
    outsider = make_user('synthetic-outsider')
    sign_in(api_client, outsider)

    for method, path in BOTH_METHODS:
        response = call(api_client, method, path)
        assert response.status_code == 403, path
        assert response.json() == {'detail': PERMISSION_DENIED_DETAIL}


def test_a_caller_with_two_live_memberships_is_refused_both_routes(
    api_client, household_a, household_b
):
    ambiguous = make_member(household_a, 'synthetic-both')
    Membership.objects.create(
        household=household_b, user=ambiguous, role=Membership.Role.CHILD
    )
    sign_in(api_client, ambiguous)

    for method, path in BOTH_METHODS:
        response = call(api_client, method, path)
        assert response.status_code == 403, path


def test_a_membership_deleted_after_sign_in_is_refused_immediately(api_client, child_a):
    sign_in(api_client, child_a)
    Membership.objects.filter(user=child_a).delete()

    for method, path in BOTH_METHODS:
        response = call(api_client, method, path)
        assert response.status_code == 403, path
        assert response.json() == {'detail': PERMISSION_DENIED_DETAIL}


def test_a_parent_is_refused_both_routes(api_client, household_a, parent_a, child_a):
    credit(household_a, child_a, 60, 'credit-1')
    sign_in(api_client, parent_a)

    for method, path in BOTH_METHODS:
        response = call(api_client, method, path)
        assert response.status_code == 403, path
        assert response.json() == {'detail': PERMISSION_DENIED_DETAIL}
        assert 'level' not in response.content.decode()

    assert LevelAcknowledgement.objects.count() == 0
    assert AuditEvent.objects.count() == 0


# The client never chooses whose figures it reads


def test_the_answer_is_always_the_callers_own_figures(
    api_client, household_a, child_a, sibling_a
):
    credit(household_a, child_a, 60, 'credit-1')
    credit(household_a, sibling_a, 900, 'credit-sibling')
    sign_in(api_client, child_a)

    body = api_client.get(READ_PATH).json()

    assert body['lifetime_points'] == 60
    assert '900' not in str(body)


# Static hygiene


def import_roots(module):
    tree = ast.parse(Path(module.__file__).resolve().read_text())
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split('.')[0])
    return roots


def test_the_progression_endpoint_imports_only_the_approved_frameworks():
    assert import_roots(progression_module) <= {
        'django',
        'rest_framework',
        'chorum_murohc',
    }
