"""Tests for the chore-pool endpoints.

Every fixture is synthetic. No credential, PIN, token, cookie or personal
datum appears in the data, the assertions or the failure output: the test
users are created without a usable password and are signed in through the
session machinery directly, so there is nothing sensitive to print.

The awkward cases the permission matrix names are covered for every route:
unauthenticated, an inactive user holding a live session, the allowed role,
the denied role, no resolvable role, an ambiguous two-household caller, and a
cross-household identifier.
"""

import ast
from pathlib import Path
from unittest.mock import patch

import pytest
from django.conf import settings
from django.urls import resolve, reverse
from rest_framework.test import APIClient

from chorum_murohc.api import chores as chores_module
from chorum_murohc.api.chores import (
    DUPLICATE_NAME_DETAIL,
    POINTS_MAXIMUM,
    ChoreDeactivateView,
    ChoreDetailView,
    ChoreListView,
    ChoreReactivateView,
)
from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.chores.models import Chore
from chorum_murohc.identity.models import Household, Membership, User

LIST_PATH = '/api/v1/chores/'
SESSION_PATH = '/api/v1/auth/session/'
CSRF_COOKIE = settings.CSRF_COOKIE_NAME

CHILD_FIELDS = {'id', 'name', 'points'}
PARENT_FIELDS = {'id', 'name', 'points', 'is_active', 'created_at', 'updated_at'}

NOT_FOUND_BODY = {'detail': 'Not found.'}
BLANK_NAME_DETAIL = 'This field may not be blank.'


def detail_path(chore_id):
    return f'{LIST_PATH}{chore_id}/'


def deactivate_path(chore_id):
    return f'{LIST_PATH}{chore_id}/deactivate/'


def reactivate_path(chore_id):
    return f'{LIST_PATH}{chore_id}/reactivate/'


def every_route(chore_id):
    """Every method and path this task exposes, as one table."""
    return (
        ('get', LIST_PATH),
        ('post', LIST_PATH),
        ('get', detail_path(chore_id)),
        ('patch', detail_path(chore_id)),
        ('delete', detail_path(chore_id)),
        ('post', deactivate_path(chore_id)),
        ('post', reactivate_path(chore_id)),
    )


@pytest.fixture
def api_client():
    # Browser-realistic: CSRF is enforced exactly as it is in production.
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def household_a(db):
    return Household.objects.create(name='Synthetic Household A')


@pytest.fixture
def household_b(db):
    return Household.objects.create(name='Synthetic Household B')


def make_user(username):
    # No password is set, so there is no credential to leak; the tests sign in
    # through the session machinery instead.
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
def chore_a(household_a):
    return Chore.objects.create(household=household_a, name='Dishes', points=5)


def sign_in(api_client, user):
    """Give the client a live session and the CSRF cookie a browser holds."""
    api_client.force_login(user)
    api_client.get(SESSION_PATH)
    return api_client


def csrf_header(api_client):
    cookie = api_client.cookies.get(CSRF_COOKIE)
    return {'x-csrftoken': cookie.value} if cookie is not None else {}


def call(api_client, method, path, body=None, *, with_csrf=True):
    headers = csrf_header(api_client) if with_csrf else {}
    handler = getattr(api_client, method)
    if method in ('get', 'delete'):
        return handler(path, headers=headers)
    return handler(path, body or {}, format='json', headers=headers)


def field_names(item):
    return set(item.keys())


def audit_actions():
    return [event.action for event in AuditEvent.objects.all()]


def one_event(action):
    events = list(AuditEvent.objects.filter(action=action))
    assert len(events) == 1
    return events[0]


# Routing


def test_the_four_routes_are_named_and_resolve():
    assert reverse('api_v1:chore-list') == LIST_PATH
    assert reverse('api_v1:chore-detail', args=(7,)) == '/api/v1/chores/7/'
    assert reverse('api_v1:chore-deactivate', args=(7,)) == (
        '/api/v1/chores/7/deactivate/'
    )
    assert reverse('api_v1:chore-reactivate', args=(7,)) == (
        '/api/v1/chores/7/reactivate/'
    )

    assert resolve(LIST_PATH).func.view_class is ChoreListView
    assert resolve(detail_path(7)).func.view_class is ChoreDetailView
    assert resolve(deactivate_path(7)).func.view_class is ChoreDeactivateView
    assert resolve(reactivate_path(7)).func.view_class is ChoreReactivateView


# Listing


def test_a_child_sees_three_fields_and_active_chores_only(
    api_client, household_a, child_a
):
    Chore.objects.create(household=household_a, name='Active chore', points=3)
    Chore.objects.create(
        household=household_a, name='Retired chore', points=4, is_active=False
    )
    sign_in(api_client, child_a)

    response = api_client.get(LIST_PATH)

    assert response.status_code == 200
    body = response.json()
    assert [item['name'] for item in body] == ['Active chore']
    assert field_names(body[0]) == CHILD_FIELDS
    assert body[0]['points'] == 3


def test_a_child_never_sees_an_inactive_chore_even_with_the_filter(
    api_client, household_a, child_a
):
    Chore.objects.create(
        household=household_a, name='Retired chore', points=4, is_active=False
    )
    sign_in(api_client, child_a)

    response = api_client.get(f'{LIST_PATH}?include_inactive=true')

    assert response.status_code == 200
    assert response.json() == []


def test_a_parent_sees_six_fields_and_active_chores_by_default(
    api_client, household_a, parent_a
):
    Chore.objects.create(household=household_a, name='Active chore', points=3)
    Chore.objects.create(
        household=household_a, name='Retired chore', points=4, is_active=False
    )
    sign_in(api_client, parent_a)

    response = api_client.get(LIST_PATH)

    assert response.status_code == 200
    body = response.json()
    assert [item['name'] for item in body] == ['Active chore']
    assert field_names(body[0]) == PARENT_FIELDS
    assert body[0]['is_active'] is True


def test_a_parent_sees_both_states_behind_the_explicit_filter(
    api_client, household_a, parent_a
):
    Chore.objects.create(household=household_a, name='Active chore', points=3)
    Chore.objects.create(
        household=household_a, name='Retired chore', points=4, is_active=False
    )
    sign_in(api_client, parent_a)

    response = api_client.get(f'{LIST_PATH}?include_inactive=true')

    assert response.status_code == 200
    body = response.json()
    assert [(item['name'], item['is_active']) for item in body] == [
        ('Active chore', True),
        ('Retired chore', False),
    ]


def test_another_household_never_appears_in_either_list(
    api_client, household_a, household_b, parent_a, child_a
):
    Chore.objects.create(household=household_b, name='Foreign chore', points=9)
    Chore.objects.create(household=household_a, name='Own chore', points=1)

    for user in (parent_a, child_a):
        client = APIClient(enforce_csrf_checks=True)
        sign_in(client, user)
        response = client.get(f'{LIST_PATH}?include_inactive=true')
        assert response.status_code == 200
        assert [item['name'] for item in response.json()] == ['Own chore']
        assert 'Foreign chore' not in response.content.decode()


def test_both_list_bodies_are_arrays_and_no_pagination_is_configured(
    api_client, household_a, parent_a, child_a
):
    Chore.objects.create(household=household_a, name='Own chore', points=1)

    for user in (parent_a, child_a):
        client = APIClient(enforce_csrf_checks=True)
        sign_in(client, user)
        body = client.get(LIST_PATH).json()
        assert isinstance(body, list)
        assert len(body) == 1

    rest_framework_settings = getattr(settings, 'REST_FRAMEWORK', {})
    assert 'DEFAULT_PAGINATION_CLASS' not in rest_framework_settings
    assert 'PAGE_SIZE' not in rest_framework_settings


def test_the_list_is_ordered_by_name_then_id(api_client, household_a, parent_a):
    for name in ('gamma', 'alpha', 'beta'):
        Chore.objects.create(household=household_a, name=name, points=1)
    sign_in(api_client, parent_a)

    body = api_client.get(LIST_PATH).json()

    assert [item['name'] for item in body] == ['alpha', 'beta', 'gamma']


# Creating


def test_a_parent_creates_a_chore_and_one_create_event(
    api_client, household_a, parent_a
):
    sign_in(api_client, parent_a)

    response = call(api_client, 'post', LIST_PATH, {'name': 'Dishes', 'points': 5})

    assert response.status_code == 201
    body = response.json()
    assert field_names(body) == PARENT_FIELDS
    assert body['name'] == 'Dishes'
    assert body['points'] == 5
    assert body['is_active'] is True

    chore = Chore.objects.get(pk=body['id'])
    assert chore.household_id == household_a.pk
    assert chore.is_active is True

    event = one_event('chore.create')
    assert audit_actions() == ['chore.create']
    assert event.household_id == household_a.pk
    assert event.actor_id == parent_a.pk
    assert event.target_type == 'chore'
    assert event.target_id == str(chore.pk)
    assert event.context['actor_id'] == parent_a.pk
    assert event.context['name'] == 'Dishes'
    assert event.context['points'] == 5


def test_a_create_body_cannot_choose_the_household_identifier_or_state(
    api_client, household_a, household_b, parent_a
):
    sign_in(api_client, parent_a)

    response = call(
        api_client,
        'post',
        LIST_PATH,
        {
            'name': 'Dishes',
            'points': 5,
            'household': household_b.pk,
            'id': 4242,
            'is_active': False,
            'created_at': '2000-01-01T00:00:00Z',
            'updated_at': '2000-01-01T00:00:00Z',
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body['id'] != 4242
    assert body['is_active'] is True

    chore = Chore.objects.get(pk=body['id'])
    assert chore.household_id == household_a.pk
    assert chore.is_active is True
    assert chore.created_at.year != 2000


# Editing


@pytest.mark.parametrize(
    ('body', 'expected_changes'),
    (
        ({'name': 'Washing up'}, {'name': ('Dishes', 'Washing up')}),
        ({'points': 8}, {'points': (5, 8)}),
        (
            {'name': 'Washing up', 'points': 8},
            {'name': ('Dishes', 'Washing up'), 'points': (5, 8)},
        ),
    ),
)
def test_an_edit_records_the_old_and_new_value_of_each_changed_field(
    api_client, parent_a, chore_a, body, expected_changes
):
    sign_in(api_client, parent_a)

    response = call(api_client, 'patch', detail_path(chore_a.pk), body)

    assert response.status_code == 200
    assert field_names(response.json()) == PARENT_FIELDS

    event = one_event('chore.update')
    assert audit_actions() == ['chore.update']
    assert event.context['actor_id'] == parent_a.pk
    assert event.context['changes'] == {
        field: {'before': before, 'after': after}
        for field, (before, after) in expected_changes.items()
    }

    chore_a.refresh_from_db()
    for field, (_, after) in expected_changes.items():
        assert getattr(chore_a, field) == after


@pytest.mark.parametrize(
    'body', ({}, {'name': 'Dishes'}, {'name': 'Dishes', 'points': 5})
)
def test_an_edit_that_changes_nothing_writes_nothing(
    api_client, parent_a, chore_a, body
):
    sign_in(api_client, parent_a)
    before = Chore.objects.get(pk=chore_a.pk).updated_at

    response = call(api_client, 'patch', detail_path(chore_a.pk), body)

    assert response.status_code == 200
    assert Chore.objects.get(pk=chore_a.pk).updated_at == before
    assert audit_actions() == []


# State transitions


def test_deactivate_writes_one_event_and_hides_the_chore_from_a_child(
    api_client, parent_a, child_a, chore_a
):
    sign_in(api_client, parent_a)

    response = call(api_client, 'post', deactivate_path(chore_a.pk))

    assert response.status_code == 200
    assert response.json()['is_active'] is False

    event = one_event('chore.deactivate')
    assert audit_actions() == ['chore.deactivate']
    assert event.context['actor_id'] == parent_a.pk
    assert event.context['is_active'] == {'before': True, 'after': False}

    child_client = APIClient(enforce_csrf_checks=True)
    sign_in(child_client, child_a)
    assert child_client.get(LIST_PATH).json() == []


def test_reactivate_writes_one_event_and_returns_the_chore_to_a_child(
    api_client, household_a, parent_a, child_a
):
    chore = Chore.objects.create(
        household=household_a, name='Dishes', points=5, is_active=False
    )
    sign_in(api_client, parent_a)

    response = call(api_client, 'post', reactivate_path(chore.pk))

    assert response.status_code == 200
    assert response.json()['is_active'] is True

    event = one_event('chore.reactivate')
    assert audit_actions() == ['chore.reactivate']
    assert event.context['is_active'] == {'before': False, 'after': True}

    child_client = APIClient(enforce_csrf_checks=True)
    sign_in(child_client, child_a)
    assert [item['name'] for item in child_client.get(LIST_PATH).json()] == ['Dishes']


@pytest.mark.parametrize(
    ('path_builder', 'starts_active'),
    ((deactivate_path, False), (reactivate_path, True)),
)
def test_a_transition_that_is_already_done_changes_nothing(
    api_client, household_a, parent_a, path_builder, starts_active
):
    chore = Chore.objects.create(
        household=household_a, name='Dishes', points=5, is_active=starts_active
    )
    sign_in(api_client, parent_a)
    before = Chore.objects.get(pk=chore.pk).updated_at

    response = call(api_client, 'post', path_builder(chore.pk))

    assert response.status_code == 200
    assert response.json()['is_active'] is starts_active

    stored = Chore.objects.get(pk=chore.pk)
    assert stored.is_active is starts_active
    assert stored.updated_at == before
    assert audit_actions() == []


# Deleting


def test_delete_removes_the_row_and_records_counts_but_not_the_name(
    api_client, parent_a, chore_a
):
    sign_in(api_client, parent_a)
    chore_id = chore_a.pk

    response = call(api_client, 'delete', detail_path(chore_id))

    assert response.status_code == 204
    assert response.content == b''
    assert not Chore.objects.filter(pk=chore_id).exists()

    event = one_event('chore.delete')
    assert audit_actions() == ['chore.delete']
    assert event.target_id == str(chore_id)
    assert event.context == {
        'actor_id': parent_a.pk,
        'chore_id': chore_id,
        'points': 5,
        'is_active': True,
        'submissions_removed': 0,
    }
    assert 'Dishes' not in str(event.context)


def test_a_second_delete_is_the_generic_404_and_writes_no_second_event(
    api_client, parent_a, chore_a
):
    sign_in(api_client, parent_a)
    chore_id = chore_a.pk
    assert call(api_client, 'delete', detail_path(chore_id)).status_code == 204

    response = call(api_client, 'delete', detail_path(chore_id))

    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY
    assert audit_actions() == ['chore.delete']


# Name validation


def test_a_case_only_duplicate_is_refused_on_create_and_on_edit(
    api_client, household_a, parent_a, chore_a
):
    other = Chore.objects.create(household=household_a, name='Laundry', points=2)
    sign_in(api_client, parent_a)

    created = call(api_client, 'post', LIST_PATH, {'name': 'dishes', 'points': 1})
    assert created.status_code == 400
    assert created.json() == {'name': [DUPLICATE_NAME_DETAIL]}

    renamed = call(api_client, 'patch', detail_path(other.pk), {'name': 'DISHES'})
    assert renamed.status_code == 400
    assert renamed.json() == {'name': [DUPLICATE_NAME_DETAIL]}

    # Its own name in another case is a rename onto an existing name too.
    recased = call(api_client, 'patch', detail_path(chore_a.pk), {'name': 'dishes'})
    assert recased.status_code == 400
    assert recased.json() == {'name': [DUPLICATE_NAME_DETAIL]}

    chore_a.refresh_from_db()
    other.refresh_from_db()
    assert chore_a.name == 'Dishes'
    assert other.name == 'Laundry'
    assert Chore.objects.count() == 2
    assert audit_actions() == []


def test_the_same_name_is_free_in_another_household(
    api_client, household_a, household_b, parent_b
):
    Chore.objects.create(household=household_a, name='Dishes', points=5)
    sign_in(api_client, parent_b)

    response = call(api_client, 'post', LIST_PATH, {'name': 'Dishes', 'points': 5})

    assert response.status_code == 201
    assert Chore.objects.filter(household=household_b, name='Dishes').count() == 1


def test_a_duplicate_that_slips_past_validation_is_the_same_400(
    api_client, parent_a, chore_a
):
    sign_in(api_client, parent_a)

    # Stand in for the race in which another request commits the same name
    # between this one's check and its insert.
    with patch.object(chores_module, 'duplicate_name_exists', return_value=False):
        response = call(api_client, 'post', LIST_PATH, {'name': 'dishes', 'points': 1})

    assert response.status_code == 400
    assert response.json() == {'name': [DUPLICATE_NAME_DETAIL]}
    assert Chore.objects.count() == 1
    assert audit_actions() == []


def test_a_blank_name_is_refused_and_surrounding_whitespace_is_trimmed(
    api_client, household_a, parent_a
):
    sign_in(api_client, parent_a)

    blank = call(api_client, 'post', LIST_PATH, {'name': '   ', 'points': 1})
    assert blank.status_code == 400
    assert blank.json() == {'name': [BLANK_NAME_DETAIL]}
    assert Chore.objects.count() == 0

    too_long = call(api_client, 'post', LIST_PATH, {'name': 'x' * 101, 'points': 1})
    assert too_long.status_code == 400
    assert 'name' in too_long.json()
    assert Chore.objects.count() == 0

    trimmed = call(api_client, 'post', LIST_PATH, {'name': '  Dishes  ', 'points': 1})
    assert trimmed.status_code == 201
    assert trimmed.json()['name'] == 'Dishes'
    assert Chore.objects.get().name == 'Dishes'


# Point validation


@pytest.mark.parametrize('points', (0, -1, 2.5, 'abc', None, POINTS_MAXIMUM + 1))
def test_an_impossible_point_value_is_refused_and_changes_nothing(
    api_client, parent_a, chore_a, points
):
    sign_in(api_client, parent_a)
    before = Chore.objects.get(pk=chore_a.pk).updated_at

    created = call(
        api_client, 'post', LIST_PATH, {'name': 'Sweeping', 'points': points}
    )
    assert created.status_code == 400
    assert 'points' in created.json()

    edited = call(api_client, 'patch', detail_path(chore_a.pk), {'points': points})
    assert edited.status_code == 400
    assert 'points' in edited.json()

    stored = Chore.objects.get(pk=chore_a.pk)
    assert Chore.objects.count() == 1
    assert stored.points == 5
    assert stored.updated_at == before
    assert audit_actions() == []


def test_a_whole_float_is_accepted_as_its_integer(api_client, parent_a):
    sign_in(api_client, parent_a)

    response = call(api_client, 'post', LIST_PATH, {'name': 'Sweeping', 'points': 2.0})

    assert response.status_code == 201
    assert response.json()['points'] == 2
    assert Chore.objects.get().points == 2


def test_the_largest_allowed_point_value_is_accepted(api_client, parent_a):
    sign_in(api_client, parent_a)

    response = call(
        api_client, 'post', LIST_PATH, {'name': 'Sweeping', 'points': POINTS_MAXIMUM}
    )

    assert response.status_code == 201
    assert Chore.objects.get().points == POINTS_MAXIMUM


# Household isolation and unknown identifiers


def test_an_unknown_and_a_foreign_identifier_answer_the_same_generic_404(
    api_client, household_b, parent_a, chore_a
):
    foreign = Chore.objects.create(household=household_b, name='Foreign', points=1)
    unknown_id = chore_a.pk + 10_000
    sign_in(api_client, parent_a)

    for method, build in (
        ('get', detail_path),
        ('patch', detail_path),
        ('delete', detail_path),
        ('post', deactivate_path),
        ('post', reactivate_path),
    ):
        unknown = call(api_client, method, build(unknown_id))
        cross = call(api_client, method, build(foreign.pk))
        assert unknown.status_code == 404
        assert cross.status_code == 404
        assert unknown.json() == NOT_FOUND_BODY
        assert cross.json() == NOT_FOUND_BODY
        assert 'Foreign' not in cross.content.decode()

    foreign.refresh_from_db()
    assert foreign.name == 'Foreign'
    assert foreign.is_active is True
    assert audit_actions() == []


# Denied callers


def test_a_child_is_refused_every_management_route(api_client, child_a, chore_a):
    sign_in(api_client, child_a)
    before = Chore.objects.get(pk=chore_a.pk).updated_at

    denied = (
        ('post', LIST_PATH),
        ('get', detail_path(chore_a.pk)),
        ('patch', detail_path(chore_a.pk)),
        ('delete', detail_path(chore_a.pk)),
        ('post', deactivate_path(chore_a.pk)),
        ('post', reactivate_path(chore_a.pk)),
    )
    for method, path in denied:
        response = call(api_client, method, path, {'name': 'Attempt', 'points': 1})
        assert response.status_code == 403, (method, path)

    stored = Chore.objects.get(pk=chore_a.pk)
    assert Chore.objects.count() == 1
    assert stored.name == 'Dishes'
    assert stored.is_active is True
    assert stored.updated_at == before
    assert audit_actions() == []


def test_an_unauthenticated_caller_is_refused_every_route(api_client, chore_a):
    # An anonymous browser can still hold a CSRF cookie, so the refusal below
    # is the authority answer and not a token failure.
    api_client.get(SESSION_PATH)

    for method, path in every_route(chore_a.pk):
        response = call(api_client, method, path, {'name': 'Attempt', 'points': 1})
        assert response.status_code == 403, (method, path)
        assert 'Dishes' not in response.content.decode()

    assert Chore.objects.get(pk=chore_a.pk).name == 'Dishes'
    assert audit_actions() == []


def test_a_deactivated_user_with_a_live_session_is_refused_every_route(
    api_client, parent_a, chore_a
):
    sign_in(api_client, parent_a)
    parent_a.is_active = False
    parent_a.save(update_fields=('is_active',))

    for method, path in every_route(chore_a.pk):
        response = call(api_client, method, path, {'name': 'Attempt', 'points': 1})
        assert response.status_code == 403, (method, path)

    assert Chore.objects.get(pk=chore_a.pk).name == 'Dishes'
    assert audit_actions() == []


def test_a_caller_with_no_membership_is_refused_every_route(api_client, chore_a):
    outsider = make_user('synthetic-outsider')
    sign_in(api_client, outsider)

    for method, path in every_route(chore_a.pk):
        response = call(api_client, method, path, {'name': 'Attempt', 'points': 1})
        assert response.status_code == 403, (method, path)

    assert Chore.objects.get(pk=chore_a.pk).name == 'Dishes'
    assert audit_actions() == []


def test_a_caller_with_two_candidate_households_is_refused_every_route(
    api_client, household_a, household_b, chore_a
):
    ambiguous = make_member(household_a, 'synthetic-both', Membership.Role.PARENT)
    Membership.objects.create(
        household=household_b, user=ambiguous, role=Membership.Role.PARENT
    )
    sign_in(api_client, ambiguous)

    for method, path in every_route(chore_a.pk):
        response = call(api_client, method, path, {'name': 'Attempt', 'points': 1})
        assert response.status_code == 403, (method, path)

    assert Chore.objects.get(pk=chore_a.pk).name == 'Dishes'
    assert audit_actions() == []


def test_a_membership_deleted_after_sign_in_is_refused_immediately(
    api_client, parent_a, chore_a
):
    sign_in(api_client, parent_a)
    Membership.objects.filter(user=parent_a).delete()

    for method, path in every_route(chore_a.pk):
        response = call(api_client, method, path, {'name': 'Attempt', 'points': 1})
        assert response.status_code == 403, (method, path)

    assert audit_actions() == []


# CSRF, safe methods and unsupported methods


def test_an_unsafe_method_without_a_csrf_token_is_refused_and_changes_nothing(
    api_client, parent_a, chore_a
):
    sign_in(api_client, parent_a)
    before = Chore.objects.get(pk=chore_a.pk).updated_at

    unsafe = (
        ('post', LIST_PATH),
        ('patch', detail_path(chore_a.pk)),
        ('delete', detail_path(chore_a.pk)),
        ('post', deactivate_path(chore_a.pk)),
        ('post', reactivate_path(chore_a.pk)),
    )
    for method, path in unsafe:
        response = call(
            api_client,
            method,
            path,
            {'name': 'Attempt', 'points': 1},
            with_csrf=False,
        )
        assert response.status_code == 403, (method, path)

    stored = Chore.objects.get(pk=chore_a.pk)
    assert Chore.objects.count() == 1
    assert stored.name == 'Dishes'
    assert stored.updated_at == before
    assert audit_actions() == []


def test_reading_is_side_effect_free(api_client, parent_a, chore_a):
    sign_in(api_client, parent_a)
    before = Chore.objects.get(pk=chore_a.pk).updated_at

    for path in (LIST_PATH, detail_path(chore_a.pk)):
        assert api_client.get(path).status_code == 200
        assert api_client.head(path).status_code == 200

    stored = Chore.objects.get(pk=chore_a.pk)
    assert stored.updated_at == before
    assert audit_actions() == []


@pytest.mark.parametrize(
    ('method', 'path_builder'),
    (
        ('put', detail_path),
        ('get', deactivate_path),
        ('get', reactivate_path),
    ),
)
def test_an_unsupported_detail_method_is_refused(
    api_client, parent_a, chore_a, method, path_builder
):
    sign_in(api_client, parent_a)

    response = call(api_client, method, path_builder(chore_a.pk), {'points': 9})

    assert response.status_code == 405
    assert Chore.objects.get(pk=chore_a.pk).points == 5
    assert audit_actions() == []


def test_the_collection_refuses_delete(api_client, parent_a, chore_a):
    sign_in(api_client, parent_a)

    response = call(api_client, 'delete', LIST_PATH)

    assert response.status_code == 405
    assert Chore.objects.count() == 1
    assert audit_actions() == []


# What this task is not allowed to introduce


def import_roots(module):
    source = Path(module.__file__).read_text(encoding='utf-8')
    roots = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            roots.add((node.module or '').split('.')[0])
    return roots


def test_the_chore_endpoints_import_only_the_approved_frameworks():
    assert import_roots(chores_module) <= {'django', 'rest_framework', 'chorum_murohc'}


def test_no_product_package_imports_the_api_layer():
    package_root = Path(chores_module.__file__).resolve().parent.parent
    offenders = []
    for source_file in sorted(package_root.rglob('*.py')):
        if source_file.parent.name == 'api' or source_file.name.startswith('test'):
            continue
        if source_file.name == 'tests.py':
            continue
        if 'chorum_murohc.api' in source_file.read_text(encoding='utf-8'):
            offenders.append(source_file.name)
    assert offenders == []
