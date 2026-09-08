"""Tests for the reward-catalogue endpoints.

Shaped exactly like `chorum_murohc/api/test_chores.py`, since the two route
sets are deliberately the same shape. The awkward cases the permission
matrix names are covered for every route: unauthenticated, an inactive user
holding a live session, the allowed role, the denied role, no resolvable
role, an ambiguous two-household caller, and a cross-household identifier.
"""

import ast
from pathlib import Path
from unittest.mock import patch

import pytest
from django.conf import settings
from django.urls import resolve, reverse
from rest_framework.test import APIClient

from chorum_murohc.api import rewards as rewards_module
from chorum_murohc.api.rewards import (
    DUPLICATE_NAME_DETAIL,
    POINTS_MAXIMUM,
    RewardDeactivateView,
    RewardDetailView,
    RewardListView,
    RewardReactivateView,
)
from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity.models import Household, Membership, User
from chorum_murohc.rewards.models import Reward

LIST_PATH = '/api/v1/rewards/'
SESSION_PATH = '/api/v1/auth/session/'
CSRF_COOKIE = settings.CSRF_COOKIE_NAME

CHILD_FIELDS = {'id', 'name', 'points'}
PARENT_FIELDS = {'id', 'name', 'points', 'is_active', 'created_at', 'updated_at'}

NOT_FOUND_BODY = {'detail': 'Not found.'}
BLANK_NAME_DETAIL = 'This field may not be blank.'


def detail_path(reward_id):
    return f'{LIST_PATH}{reward_id}/'


def deactivate_path(reward_id):
    return f'{LIST_PATH}{reward_id}/deactivate/'


def reactivate_path(reward_id):
    return f'{LIST_PATH}{reward_id}/reactivate/'


def every_route(reward_id):
    return (
        ('get', LIST_PATH),
        ('post', LIST_PATH),
        ('get', detail_path(reward_id)),
        ('patch', detail_path(reward_id)),
        ('delete', detail_path(reward_id)),
        ('post', deactivate_path(reward_id)),
        ('post', reactivate_path(reward_id)),
    )


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


def test_the_routes_are_named_and_resolve():
    assert reverse('api_v1:reward-list') == LIST_PATH
    assert reverse('api_v1:reward-detail', args=(7,)) == '/api/v1/rewards/7/'
    assert reverse('api_v1:reward-deactivate', args=(7,)) == (
        '/api/v1/rewards/7/deactivate/'
    )
    assert reverse('api_v1:reward-reactivate', args=(7,)) == (
        '/api/v1/rewards/7/reactivate/'
    )

    assert resolve(LIST_PATH).func.view_class is RewardListView
    assert resolve(detail_path(7)).func.view_class is RewardDetailView
    assert resolve(deactivate_path(7)).func.view_class is RewardDeactivateView
    assert resolve(reactivate_path(7)).func.view_class is RewardReactivateView


# Listing


def test_a_child_sees_three_fields_and_active_rewards_only(
    api_client, household_a, child_a
):
    Reward.objects.create(household=household_a, name='Active reward', points=3)
    Reward.objects.create(
        household=household_a, name='Retired reward', points=4, is_active=False
    )
    sign_in(api_client, child_a)

    response = api_client.get(LIST_PATH)

    assert response.status_code == 200
    body = response.json()
    assert [item['name'] for item in body] == ['Active reward']
    assert field_names(body[0]) == CHILD_FIELDS


def test_a_parent_sees_six_fields_and_active_rewards_by_default(
    api_client, household_a, parent_a
):
    Reward.objects.create(household=household_a, name='Active reward', points=3)
    Reward.objects.create(
        household=household_a, name='Retired reward', points=4, is_active=False
    )
    sign_in(api_client, parent_a)

    response = api_client.get(LIST_PATH)

    assert response.status_code == 200
    body = response.json()
    assert [item['name'] for item in body] == ['Active reward']
    assert field_names(body[0]) == PARENT_FIELDS


def test_a_parent_sees_both_states_behind_the_explicit_filter(
    api_client, household_a, parent_a
):
    Reward.objects.create(household=household_a, name='Active reward', points=3)
    Reward.objects.create(
        household=household_a, name='Retired reward', points=4, is_active=False
    )
    sign_in(api_client, parent_a)

    response = api_client.get(f'{LIST_PATH}?include_inactive=true')

    assert response.status_code == 200
    body = response.json()
    assert [(item['name'], item['is_active']) for item in body] == [
        ('Active reward', True),
        ('Retired reward', False),
    ]


def test_another_household_never_appears_in_either_list(
    api_client, household_a, household_b, parent_a, child_a
):
    Reward.objects.create(household=household_b, name='Foreign reward', points=9)
    Reward.objects.create(household=household_a, name='Own reward', points=1)

    for user in (parent_a, child_a):
        client = APIClient(enforce_csrf_checks=True)
        sign_in(client, user)
        response = client.get(f'{LIST_PATH}?include_inactive=true')
        assert response.status_code == 200
        assert [item['name'] for item in response.json()] == ['Own reward']
        assert 'Foreign reward' not in response.content.decode()


def test_the_list_is_ordered_by_name_then_id(api_client, household_a, parent_a):
    for name in ('gamma', 'alpha', 'beta'):
        Reward.objects.create(household=household_a, name=name, points=1)
    sign_in(api_client, parent_a)

    body = api_client.get(LIST_PATH).json()

    assert [item['name'] for item in body] == ['alpha', 'beta', 'gamma']


# Creating


def test_a_parent_creates_a_reward_and_one_create_event(
    api_client, household_a, parent_a
):
    sign_in(api_client, parent_a)

    response = call(
        api_client, 'post', LIST_PATH, {'name': 'Movie night', 'points': 200}
    )

    assert response.status_code == 201
    body = response.json()
    assert field_names(body) == PARENT_FIELDS
    assert body['name'] == 'Movie night'
    assert body['points'] == 200
    assert body['is_active'] is True

    reward = Reward.objects.get(pk=body['id'])
    assert reward.household_id == household_a.pk

    event = one_event('reward.create')
    assert audit_actions() == ['reward.create']
    assert event.context['actor_id'] == parent_a.pk
    assert event.context['name'] == 'Movie night'
    assert event.context['points'] == 200


def test_a_create_body_cannot_choose_the_household_identifier_or_state(
    api_client, household_a, household_b, parent_a
):
    sign_in(api_client, parent_a)

    response = call(
        api_client,
        'post',
        LIST_PATH,
        {
            'name': 'Movie night',
            'points': 200,
            'household': household_b.pk,
            'id': 4242,
            'is_active': False,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body['id'] != 4242
    assert body['is_active'] is True

    reward = Reward.objects.get(pk=body['id'])
    assert reward.household_id == household_a.pk


# Editing


def test_an_edit_records_the_old_and_new_value_of_each_changed_field(
    api_client, parent_a, reward_a
):
    sign_in(api_client, parent_a)

    response = call(
        api_client,
        'patch',
        detail_path(reward_a.pk),
        {'name': 'Later bedtime', 'points': 40},
    )

    assert response.status_code == 200
    event = one_event('reward.update')
    assert event.context['changes'] == {
        'name': {'before': 'Screen time', 'after': 'Later bedtime'},
        'points': {'before': 15, 'after': 40},
    }


def test_an_edit_that_changes_nothing_writes_nothing(api_client, parent_a, reward_a):
    sign_in(api_client, parent_a)
    before = Reward.objects.get(pk=reward_a.pk).updated_at

    response = call(
        api_client,
        'patch',
        detail_path(reward_a.pk),
        {'name': 'Screen time', 'points': 15},
    )

    assert response.status_code == 200
    assert Reward.objects.get(pk=reward_a.pk).updated_at == before
    assert audit_actions() == []


# State transitions


def test_deactivate_writes_one_event_and_hides_the_reward_from_a_child(
    api_client, parent_a, child_a, reward_a
):
    sign_in(api_client, parent_a)

    response = call(api_client, 'post', deactivate_path(reward_a.pk))

    assert response.status_code == 200
    assert response.json()['is_active'] is False
    event = one_event('reward.deactivate')
    assert event.context['is_active'] == {'before': True, 'after': False}

    child_client = APIClient(enforce_csrf_checks=True)
    sign_in(child_client, child_a)
    assert child_client.get(LIST_PATH).json() == []


def test_reactivate_writes_one_event_and_returns_the_reward_to_a_child(
    api_client, household_a, parent_a, child_a
):
    reward = Reward.objects.create(
        household=household_a, name='Screen time', points=15, is_active=False
    )
    sign_in(api_client, parent_a)

    response = call(api_client, 'post', reactivate_path(reward.pk))

    assert response.status_code == 200
    event = one_event('reward.reactivate')
    assert event.context['is_active'] == {'before': False, 'after': True}


@pytest.mark.parametrize(
    ('path_builder', 'starts_active'),
    ((deactivate_path, False), (reactivate_path, True)),
)
def test_a_transition_that_is_already_done_changes_nothing(
    api_client, household_a, parent_a, path_builder, starts_active
):
    reward = Reward.objects.create(
        household=household_a, name='Screen time', points=15, is_active=starts_active
    )
    sign_in(api_client, parent_a)

    response = call(api_client, 'post', path_builder(reward.pk))

    assert response.status_code == 200
    assert audit_actions() == []


# Deleting


def test_delete_removes_the_row_and_records_counts_but_not_the_name(
    api_client, parent_a, reward_a
):
    sign_in(api_client, parent_a)
    reward_id = reward_a.pk

    response = call(api_client, 'delete', detail_path(reward_id))

    assert response.status_code == 204
    assert not Reward.objects.filter(pk=reward_id).exists()

    event = one_event('reward.delete')
    assert event.context == {
        'actor_id': parent_a.pk,
        'reward_id': reward_id,
        'points': 15,
        'is_active': True,
    }
    assert 'Screen time' not in str(event.context)


def test_a_second_delete_is_the_generic_404_and_writes_no_second_event(
    api_client, parent_a, reward_a
):
    sign_in(api_client, parent_a)
    reward_id = reward_a.pk
    assert call(api_client, 'delete', detail_path(reward_id)).status_code == 204

    response = call(api_client, 'delete', detail_path(reward_id))

    assert response.status_code == 404
    assert audit_actions() == ['reward.delete']


# Name validation


def test_a_case_only_duplicate_is_refused_on_create_and_on_edit(
    api_client, household_a, parent_a, reward_a
):
    other = Reward.objects.create(household=household_a, name='Movie night', points=200)
    sign_in(api_client, parent_a)

    created = call(api_client, 'post', LIST_PATH, {'name': 'screen time', 'points': 1})
    assert created.status_code == 400
    assert created.json() == {'name': [DUPLICATE_NAME_DETAIL]}

    renamed = call(api_client, 'patch', detail_path(other.pk), {'name': 'SCREEN TIME'})
    assert renamed.status_code == 400
    assert renamed.json() == {'name': [DUPLICATE_NAME_DETAIL]}

    assert Reward.objects.count() == 2
    assert audit_actions() == []


def test_the_same_name_is_free_in_another_household(
    api_client, household_a, household_b, parent_b
):
    Reward.objects.create(household=household_a, name='Screen time', points=15)
    sign_in(api_client, parent_b)

    response = call(
        api_client, 'post', LIST_PATH, {'name': 'Screen time', 'points': 15}
    )

    assert response.status_code == 201
    assert Reward.objects.filter(household=household_b, name='Screen time').count() == 1


def test_a_duplicate_that_slips_past_validation_is_the_same_400(
    api_client, parent_a, reward_a
):
    sign_in(api_client, parent_a)

    with patch.object(rewards_module, 'duplicate_name_exists', return_value=False):
        response = call(
            api_client, 'post', LIST_PATH, {'name': 'screen time', 'points': 1}
        )

    assert response.status_code == 400
    assert response.json() == {'name': [DUPLICATE_NAME_DETAIL]}
    assert Reward.objects.count() == 1
    assert audit_actions() == []


def test_a_blank_name_is_refused_and_surrounding_whitespace_is_trimmed(
    api_client, parent_a
):
    sign_in(api_client, parent_a)

    blank = call(api_client, 'post', LIST_PATH, {'name': '   ', 'points': 1})
    assert blank.status_code == 400
    assert blank.json() == {'name': [BLANK_NAME_DETAIL]}

    trimmed = call(
        api_client, 'post', LIST_PATH, {'name': '  Movie night  ', 'points': 1}
    )
    assert trimmed.status_code == 201
    assert trimmed.json()['name'] == 'Movie night'


# Point validation


@pytest.mark.parametrize('points', (0, -1, 2.5, 'abc', None, POINTS_MAXIMUM + 1))
def test_an_impossible_point_value_is_refused_and_changes_nothing(
    api_client, parent_a, reward_a, points
):
    sign_in(api_client, parent_a)

    created = call(api_client, 'post', LIST_PATH, {'name': 'Bedtime', 'points': points})
    assert created.status_code == 400
    assert 'points' in created.json()

    edited = call(api_client, 'patch', detail_path(reward_a.pk), {'points': points})
    assert edited.status_code == 400
    assert 'points' in edited.json()

    stored = Reward.objects.get(pk=reward_a.pk)
    assert stored.points == 15
    assert audit_actions() == []


# Household isolation and unknown identifiers


def test_an_unknown_and_a_foreign_identifier_answer_the_same_generic_404(
    api_client, household_b, parent_a, reward_a
):
    foreign = Reward.objects.create(household=household_b, name='Foreign', points=1)
    unknown_id = reward_a.pk + 10_000
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
        assert 'Foreign' not in cross.content.decode()

    foreign.refresh_from_db()
    assert foreign.name == 'Foreign'
    assert audit_actions() == []


# Denied callers


def test_a_child_is_refused_every_management_route(api_client, child_a, reward_a):
    sign_in(api_client, child_a)

    denied = (
        ('post', LIST_PATH),
        ('get', detail_path(reward_a.pk)),
        ('patch', detail_path(reward_a.pk)),
        ('delete', detail_path(reward_a.pk)),
        ('post', deactivate_path(reward_a.pk)),
        ('post', reactivate_path(reward_a.pk)),
    )
    for method, path in denied:
        response = call(api_client, method, path, {'name': 'Attempt', 'points': 1})
        assert response.status_code == 403, (method, path)

    assert Reward.objects.count() == 1
    assert audit_actions() == []


def test_an_unauthenticated_caller_is_refused_every_route(api_client, reward_a):
    api_client.get(SESSION_PATH)

    for method, path in every_route(reward_a.pk):
        response = call(api_client, method, path, {'name': 'Attempt', 'points': 1})
        assert response.status_code == 403, (method, path)

    assert audit_actions() == []


def test_a_deactivated_user_with_a_live_session_is_refused_every_route(
    api_client, parent_a, reward_a
):
    sign_in(api_client, parent_a)
    parent_a.is_active = False
    parent_a.save(update_fields=('is_active',))

    for method, path in every_route(reward_a.pk):
        response = call(api_client, method, path, {'name': 'Attempt', 'points': 1})
        assert response.status_code == 403, (method, path)

    assert audit_actions() == []


def test_a_caller_with_no_membership_is_refused_every_route(api_client, reward_a):
    outsider = make_user('synthetic-outsider')
    sign_in(api_client, outsider)

    for method, path in every_route(reward_a.pk):
        response = call(api_client, method, path, {'name': 'Attempt', 'points': 1})
        assert response.status_code == 403, (method, path)

    assert audit_actions() == []


def test_a_caller_with_two_candidate_households_is_refused_every_route(
    api_client, household_a, household_b, reward_a
):
    ambiguous = make_member(household_a, 'synthetic-both', Membership.Role.PARENT)
    Membership.objects.create(
        household=household_b, user=ambiguous, role=Membership.Role.PARENT
    )
    sign_in(api_client, ambiguous)

    for method, path in every_route(reward_a.pk):
        response = call(api_client, method, path, {'name': 'Attempt', 'points': 1})
        assert response.status_code == 403, (method, path)

    assert audit_actions() == []


def test_a_membership_deleted_after_sign_in_is_refused_immediately(
    api_client, parent_a, reward_a
):
    sign_in(api_client, parent_a)
    Membership.objects.filter(user=parent_a).delete()

    for method, path in every_route(reward_a.pk):
        response = call(api_client, method, path, {'name': 'Attempt', 'points': 1})
        assert response.status_code == 403, (method, path)

    assert audit_actions() == []


# CSRF and unsupported methods


def test_an_unsafe_method_without_a_csrf_token_is_refused_and_changes_nothing(
    api_client, parent_a, reward_a
):
    sign_in(api_client, parent_a)

    response = call(
        api_client, 'post', LIST_PATH, {'name': 'Attempt', 'points': 1}, with_csrf=False
    )

    assert response.status_code == 403
    assert Reward.objects.count() == 1


@pytest.mark.parametrize('method', ('put', 'delete'))
def test_an_unsupported_method_is_refused(api_client, parent_a, method):
    sign_in(api_client, parent_a)

    response = call(api_client, method, LIST_PATH)

    assert response.status_code == 405


def import_roots(module):
    roots = set()
    tree = ast.parse(Path(module.__file__).resolve().read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            roots.add((node.module or '').split('.')[0])
    return roots


def test_the_reward_endpoints_import_only_the_approved_frameworks():
    assert import_roots(rewards_module) <= {'django', 'rest_framework', 'chorum_murohc'}
