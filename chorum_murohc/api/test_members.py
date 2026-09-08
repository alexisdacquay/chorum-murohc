"""Tests for the household account directory endpoints.

Every fixture is synthetic. No credential, PIN, token, cookie or personal
datum appears in the data, the assertions or the failure output: test users
are created without a usable password (`make_user`) or with an ordinary
throwaway one that is never asserted or printed, and they are signed in
through the session machinery directly.

The awkward cases the permission matrix names are covered for every route:
unauthenticated, an inactive user holding a live session, a child (denied
here even for reading, unlike the chore pool), no resolvable role, an
ambiguous two-household caller, and a cross-household identifier.
"""

import ast
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

import pytest
from django.conf import settings
from django.db import connection
from django.urls import resolve, reverse
from rest_framework.test import APIClient

from chorum_murohc.api import members as members_module
from chorum_murohc.api.members import (
    DUPLICATE_USERNAME_DETAIL,
    LAST_PARENT_DETAIL,
    MemberDeactivateView,
    MemberDetailView,
    MemberListView,
    MemberReactivateView,
    _deny_if_would_remove_last_active_parent,
    _lock_parents,
)
from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity.models import Household, Membership, User
from chorum_murohc.ledger.models import LedgerEntry
from chorum_murohc.submissions.models import Submission

LIST_PATH = '/api/v1/household-members/'
SESSION_PATH = '/api/v1/auth/session/'
CSRF_COOKIE = settings.CSRF_COOKIE_NAME

MEMBER_FIELDS = {'id', 'username', 'role', 'is_active', 'date_joined'}

NOT_FOUND_BODY = {'detail': 'Not found.'}
BLANK_USERNAME_DETAIL = 'This field may not be blank.'
BLANK_PASSWORD_DETAIL = 'This field may not be blank.'

# A password ordinary enough to pass every configured validator, and never
# asserted or printed anywhere below.
GOOD_PASSWORD = 'a genuinely unusual passphrase 42'


def detail_path(user_id):
    return f'{LIST_PATH}{user_id}/'


def deactivate_path(user_id):
    return f'{LIST_PATH}{user_id}/deactivate/'


def reactivate_path(user_id):
    return f'{LIST_PATH}{user_id}/reactivate/'


def every_route(user_id):
    """Every method and path this task exposes, as one table."""
    return (
        ('get', LIST_PATH),
        ('post', LIST_PATH),
        ('get', detail_path(user_id)),
        ('patch', detail_path(user_id)),
        ('delete', detail_path(user_id)),
        ('post', deactivate_path(user_id)),
        ('post', reactivate_path(user_id)),
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
    # No password is set, so there is nothing sensitive to leak; the tests
    # sign in through the session machinery instead.
    return User.objects.create_user(username=username)


def make_member(household, username, role):
    user = make_user(username)
    Membership.objects.create(household=household, user=user, role=role)
    return user


@pytest.fixture
def parent_a(household_a):
    return make_member(household_a, 'synthetic-parent-a', Membership.Role.PARENT)


@pytest.fixture
def second_parent_a(household_a):
    return make_member(household_a, 'synthetic-parent-a2', Membership.Role.PARENT)


@pytest.fixture
def child_a(household_a):
    return make_member(household_a, 'synthetic-child-a', Membership.Role.CHILD)


@pytest.fixture
def parent_b(household_b):
    return make_member(household_b, 'synthetic-parent-b', Membership.Role.PARENT)


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
    assert reverse('api_v1:member-list') == LIST_PATH
    assert reverse('api_v1:member-detail', args=(7,)) == '/api/v1/household-members/7/'
    assert reverse('api_v1:member-deactivate', args=(7,)) == (
        '/api/v1/household-members/7/deactivate/'
    )
    assert reverse('api_v1:member-reactivate', args=(7,)) == (
        '/api/v1/household-members/7/reactivate/'
    )

    assert resolve(LIST_PATH).func.view_class is MemberListView
    assert resolve(detail_path(7)).func.view_class is MemberDetailView
    assert resolve(deactivate_path(7)).func.view_class is MemberDeactivateView
    assert resolve(reactivate_path(7)).func.view_class is MemberReactivateView


# Listing


def test_a_parent_sees_five_fields_and_active_members_by_default(
    api_client, household_a, parent_a, child_a
):
    make_member(household_a, 'synthetic-retired', Membership.Role.CHILD).delete()
    inactive = make_member(household_a, 'synthetic-inactive', Membership.Role.CHILD)
    inactive.is_active = False
    inactive.save(update_fields=('is_active',))
    sign_in(api_client, parent_a)

    response = api_client.get(LIST_PATH)

    assert response.status_code == 200
    body = response.json()
    usernames = {item['username'] for item in body}
    assert usernames == {parent_a.username, child_a.username}
    assert field_names(body[0]) == MEMBER_FIELDS


def test_a_parent_sees_both_states_behind_the_explicit_filter(
    api_client, household_a, parent_a, child_a
):
    child_a.is_active = False
    child_a.save(update_fields=('is_active',))
    sign_in(api_client, parent_a)

    response = api_client.get(f'{LIST_PATH}?include_inactive=true')

    assert response.status_code == 200
    body = response.json()
    assert {item['username']: item['is_active'] for item in body} == {
        parent_a.username: True,
        child_a.username: False,
    }


def test_the_list_is_ordered_by_username_then_id(api_client, household_a, parent_a):
    for name in ('gamma', 'alpha', 'beta'):
        make_member(household_a, name, Membership.Role.CHILD)
    sign_in(api_client, parent_a)

    body = api_client.get(LIST_PATH).json()

    assert [item['username'] for item in body] == [
        'alpha',
        'beta',
        'gamma',
        parent_a.username,
    ]


def test_another_household_never_appears_in_the_list(
    api_client, household_a, household_b, parent_a
):
    make_member(household_b, 'synthetic-foreign', Membership.Role.PARENT)
    sign_in(api_client, parent_a)

    response = api_client.get(f'{LIST_PATH}?include_inactive=true')

    assert response.status_code == 200
    assert [item['username'] for item in response.json()] == [parent_a.username]


def test_no_pagination_is_configured(api_client, household_a, parent_a):
    sign_in(api_client, parent_a)

    body = api_client.get(LIST_PATH).json()

    assert isinstance(body, list)
    rest_framework_settings = getattr(settings, 'REST_FRAMEWORK', {})
    assert 'DEFAULT_PAGINATION_CLASS' not in rest_framework_settings


# Creating


def test_a_parent_creates_a_child_and_one_create_event(
    api_client, household_a, parent_a
):
    sign_in(api_client, parent_a)

    response = call(
        api_client,
        'post',
        LIST_PATH,
        {'username': 'new-child', 'password': GOOD_PASSWORD, 'role': 'child'},
    )

    assert response.status_code == 201
    body = response.json()
    assert field_names(body) == MEMBER_FIELDS
    assert body['username'] == 'new-child'
    assert body['role'] == 'child'
    assert body['is_active'] is True

    user = User.objects.get(pk=body['id'])
    assert user.check_password(GOOD_PASSWORD)
    membership = Membership.objects.get(user=user)
    assert membership.household_id == household_a.pk
    assert membership.role == Membership.Role.CHILD

    event = one_event('account.create')
    assert audit_actions() == ['account.create']
    assert event.household_id == household_a.pk
    assert event.actor_id == parent_a.pk
    assert event.target_type == 'account'
    assert event.target_id == str(user.pk)
    assert event.context['actor_id'] == parent_a.pk
    assert event.context['role'] == 'child'


def test_a_parent_can_create_a_second_parent(api_client, household_a, parent_a):
    sign_in(api_client, parent_a)

    response = call(
        api_client,
        'post',
        LIST_PATH,
        {'username': 'new-parent', 'password': GOOD_PASSWORD, 'role': 'parent'},
    )

    assert response.status_code == 201
    assert response.json()['role'] == 'parent'


def test_a_create_body_cannot_choose_the_household_id_or_state(
    api_client, household_a, household_b, parent_a
):
    sign_in(api_client, parent_a)

    response = call(
        api_client,
        'post',
        LIST_PATH,
        {
            'username': 'new-child',
            'password': GOOD_PASSWORD,
            'role': 'child',
            'household': household_b.pk,
            'id': 4242,
            'is_active': False,
            'date_joined': '2000-01-01T00:00:00Z',
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body['id'] != 4242
    assert body['is_active'] is True

    membership = Membership.objects.get(user_id=body['id'])
    assert membership.household_id == household_a.pk


def test_a_duplicate_username_is_refused_on_create(api_client, household_a, parent_a):
    make_member(household_a, 'taken', Membership.Role.CHILD)
    sign_in(api_client, parent_a)

    response = call(
        api_client,
        'post',
        LIST_PATH,
        {'username': 'taken', 'password': GOOD_PASSWORD, 'role': 'child'},
    )

    assert response.status_code == 400
    assert response.json() == {'username': [DUPLICATE_USERNAME_DETAIL]}
    assert audit_actions() == []


def test_a_username_taken_in_another_household_is_still_refused(
    api_client, household_a, household_b, parent_a
):
    make_member(household_b, 'taken', Membership.Role.PARENT)
    sign_in(api_client, parent_a)

    response = call(
        api_client,
        'post',
        LIST_PATH,
        {'username': 'taken', 'password': GOOD_PASSWORD, 'role': 'child'},
    )

    assert response.status_code == 400
    assert response.json() == {'username': [DUPLICATE_USERNAME_DETAIL]}


def test_a_duplicate_that_slips_past_validation_is_the_same_400(
    api_client, household_a, parent_a
):
    make_member(household_a, 'taken', Membership.Role.CHILD)
    sign_in(api_client, parent_a)

    # Stand in for the race in which another request commits the same
    # username between this one's check and its insert.
    with patch.object(members_module, '_clean_username', side_effect=lambda v, **_: v):
        response = call(
            api_client,
            'post',
            LIST_PATH,
            {'username': 'taken', 'password': GOOD_PASSWORD, 'role': 'child'},
        )

    assert response.status_code == 400
    assert response.json() == {'username': [DUPLICATE_USERNAME_DETAIL]}
    assert audit_actions() == []


def test_a_blank_username_is_refused(api_client, household_a, parent_a):
    sign_in(api_client, parent_a)

    response = call(
        api_client,
        'post',
        LIST_PATH,
        {'username': '', 'password': GOOD_PASSWORD, 'role': 'child'},
    )

    assert response.status_code == 400
    assert response.json() == {'username': [BLANK_USERNAME_DETAIL]}


def test_a_blank_password_is_refused(api_client, household_a, parent_a):
    sign_in(api_client, parent_a)

    response = call(
        api_client,
        'post',
        LIST_PATH,
        {'username': 'new-child', 'password': '', 'role': 'child'},
    )

    assert response.status_code == 400
    assert response.json() == {'password': [BLANK_PASSWORD_DETAIL]}
    assert not User.objects.filter(username='new-child').exists()


@pytest.mark.parametrize('password', ('short', 'password', '11111111'))
def test_a_weak_password_is_refused_and_never_stored(
    api_client, household_a, parent_a, password
):
    sign_in(api_client, parent_a)

    response = call(
        api_client,
        'post',
        LIST_PATH,
        {'username': 'new-child', 'password': password, 'role': 'child'},
    )

    # The validators' own fixed wording legitimately contains ordinary words
    # like "password" and "short", so this only checks that the account was
    # refused and never created, not that the message excludes those words.
    assert response.status_code == 400
    assert 'password' in response.json()
    assert not User.objects.filter(username='new-child').exists()


@pytest.mark.parametrize('role', ('admin', 'staff', '', 'PARENT'))
def test_an_invalid_role_is_refused(api_client, household_a, parent_a, role):
    sign_in(api_client, parent_a)

    response = call(
        api_client,
        'post',
        LIST_PATH,
        {'username': 'new-child', 'password': GOOD_PASSWORD, 'role': role},
    )

    assert response.status_code == 400
    assert 'role' in response.json()
    assert not User.objects.filter(username='new-child').exists()


# Editing


def test_an_edit_records_the_old_and_new_username_as_account_update(
    api_client, household_a, parent_a, child_a
):
    sign_in(api_client, parent_a)

    response = call(
        api_client, 'patch', detail_path(child_a.pk), {'username': 'renamed-child'}
    )

    assert response.status_code == 200
    assert response.json()['username'] == 'renamed-child'

    event = one_event('account.update')
    assert audit_actions() == ['account.update']
    assert event.context['actor_id'] == parent_a.pk
    assert event.context['target_id'] == child_a.pk
    assert event.context['changes'] == {
        'username': {'before': 'synthetic-child-a', 'after': 'renamed-child'}
    }

    child_a.refresh_from_db()
    assert child_a.username == 'renamed-child'


def test_a_role_change_writes_role_change_even_with_another_field(
    api_client, household_a, parent_a, child_a
):
    sign_in(api_client, parent_a)

    response = call(
        api_client,
        'patch',
        detail_path(child_a.pk),
        {'username': 'promoted', 'role': 'parent'},
    )

    assert response.status_code == 200
    assert response.json()['role'] == 'parent'

    event = one_event('account.role_change')
    assert audit_actions() == ['account.role_change']
    assert event.context['changes']['role'] == {'before': 'child', 'after': 'parent'}
    assert event.context['changes']['username'] == {
        'before': 'synthetic-child-a',
        'after': 'promoted',
    }

    assert Membership.objects.get(user=child_a).role == Membership.Role.PARENT


def test_a_password_reset_is_never_logged_or_returned(
    api_client, household_a, parent_a, child_a
):
    sign_in(api_client, parent_a)
    new_password = 'a totally different passphrase 99'

    response = call(
        api_client, 'patch', detail_path(child_a.pk), {'password': new_password}
    )

    assert response.status_code == 200
    assert 'password' not in response.json()
    assert new_password not in response.content.decode()

    child_a.refresh_from_db()
    assert child_a.check_password(new_password)

    event = one_event('account.update')
    # `AuditEvent`'s own context sanitiser (`audit/models.py`) redacts any
    # value stored under a key named "password", whatever shape that value
    # takes - so the marker this view writes is redacted too, defence in
    # depth on top of this view never writing the password itself.
    assert event.context['changes'] == {'password': '[REDACTED]'}
    assert new_password not in str(event.context)


@pytest.mark.parametrize('body', ({}, {'username': 'synthetic-child-a'}))
def test_an_edit_that_changes_nothing_writes_nothing(
    api_client, household_a, parent_a, child_a, body
):
    sign_in(api_client, parent_a)

    response = call(api_client, 'patch', detail_path(child_a.pk), body)

    assert response.status_code == 200
    assert audit_actions() == []


def test_a_parent_cannot_edit_their_own_account(api_client, household_a, parent_a):
    sign_in(api_client, parent_a)

    response = call(
        api_client, 'patch', detail_path(parent_a.pk), {'username': 'renamed-self'}
    )

    assert response.status_code == 403
    parent_a.refresh_from_db()
    assert parent_a.username == 'synthetic-parent-a'
    assert audit_actions() == []


def test_editing_to_a_taken_username_is_refused(
    api_client, household_a, parent_a, child_a
):
    make_member(household_a, 'taken', Membership.Role.CHILD)
    sign_in(api_client, parent_a)

    response = call(api_client, 'patch', detail_path(child_a.pk), {'username': 'taken'})

    assert response.status_code == 400
    assert response.json() == {'username': [DUPLICATE_USERNAME_DETAIL]}


# Deactivate and reactivate


def test_deactivate_writes_one_event(api_client, household_a, parent_a, child_a):
    sign_in(api_client, parent_a)

    response = call(api_client, 'post', deactivate_path(child_a.pk))

    assert response.status_code == 200
    assert response.json()['is_active'] is False

    event = one_event('account.deactivate')
    assert audit_actions() == ['account.deactivate']
    assert event.context['is_active'] == {'before': True, 'after': False}

    child_a.refresh_from_db()
    assert child_a.is_active is False


def test_reactivate_writes_one_event(api_client, household_a, parent_a, child_a):
    child_a.is_active = False
    child_a.save(update_fields=('is_active',))
    sign_in(api_client, parent_a)

    response = call(api_client, 'post', reactivate_path(child_a.pk))

    assert response.status_code == 200
    assert response.json()['is_active'] is True

    event = one_event('account.reactivate')
    assert event.context['is_active'] == {'before': False, 'after': True}


@pytest.mark.parametrize(
    ('path_builder', 'starts_active'),
    ((deactivate_path, False), (reactivate_path, True)),
)
def test_a_transition_that_is_already_done_changes_nothing(
    api_client, household_a, parent_a, child_a, path_builder, starts_active
):
    child_a.is_active = starts_active
    child_a.save(update_fields=('is_active',))
    sign_in(api_client, parent_a)

    response = call(api_client, 'post', path_builder(child_a.pk))

    assert response.status_code == 200
    assert response.json()['is_active'] is starts_active
    assert audit_actions() == []


def test_a_parent_cannot_deactivate_or_reactivate_themselves(
    api_client, household_a, parent_a
):
    sign_in(api_client, parent_a)

    for path_builder in (deactivate_path, reactivate_path):
        response = call(api_client, 'post', path_builder(parent_a.pk))
        assert response.status_code == 403

    parent_a.refresh_from_db()
    assert parent_a.is_active is True
    assert audit_actions() == []


def test_a_parent_can_deactivate_another_parent_leaving_one_active(
    api_client, household_a, parent_a, second_parent_a
):
    sign_in(api_client, parent_a)

    response = call(api_client, 'post', deactivate_path(second_parent_a.pk))

    assert response.status_code == 200
    second_parent_a.refresh_from_db()
    assert second_parent_a.is_active is False
    parent_a.refresh_from_db()
    assert parent_a.is_active is True


# Deleting


def test_delete_removes_the_account_and_cascades_the_rows_the_policy_names(
    api_client, household_a, parent_a, child_a
):
    Submission.objects.create(
        household=household_a,
        child=child_a,
        chore=None,
        chore_name='Dishes',
        chore_points=5,
        idempotency_key='sub-1',
    )
    LedgerEntry.objects.create(
        household=household_a,
        user=child_a,
        amount=5,
        reason=LedgerEntry.Reason.CHORE_CREDIT,
        source_type='submission',
        source_id='1',
        idempotency_key='ledger-1',
    )
    sign_in(api_client, parent_a)
    child_id = child_a.pk

    response = call(api_client, 'delete', detail_path(child_id))

    assert response.status_code == 204
    assert response.content == b''
    assert not User.objects.filter(pk=child_id).exists()
    assert not Membership.objects.filter(user_id=child_id).exists()
    assert not Submission.objects.filter(child_id=child_id).exists()
    assert not LedgerEntry.objects.filter(user_id=child_id).exists()

    event = one_event('account.delete')
    assert audit_actions() == ['account.delete']
    assert event.target_id == str(child_id)
    assert event.context == {
        'actor_id': parent_a.pk,
        'target_id': child_id,
        'role': 'child',
        'memberships_removed': 1,
        'submissions_removed': 1,
        'ledger_entries_removed': 1,
        'rewards_removed': 0,
        'progression_rows_removed': 0,
        'creature_selection_removed': 0,
    }
    assert 'synthetic-child-a' not in str(event.context)


def test_a_second_delete_is_the_generic_404_and_writes_no_second_event(
    api_client, household_a, parent_a, child_a
):
    sign_in(api_client, parent_a)
    child_id = child_a.pk
    assert call(api_client, 'delete', detail_path(child_id)).status_code == 204

    response = call(api_client, 'delete', detail_path(child_id))

    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY
    assert audit_actions() == ['account.delete']


def test_a_parent_cannot_delete_their_own_account(api_client, household_a, parent_a):
    sign_in(api_client, parent_a)

    response = call(api_client, 'delete', detail_path(parent_a.pk))

    assert response.status_code == 403
    assert User.objects.filter(pk=parent_a.pk).exists()
    assert audit_actions() == []


def test_a_parent_can_delete_another_parent_leaving_one_active(
    api_client, household_a, parent_a, second_parent_a
):
    sign_in(api_client, parent_a)

    response = call(api_client, 'delete', detail_path(second_parent_a.pk))

    assert response.status_code == 204
    assert not User.objects.filter(pk=second_parent_a.pk).exists()
    assert User.objects.filter(pk=parent_a.pk, is_active=True).exists()


def test_deleting_a_decided_submissions_actor_only_nulls_the_reference(
    api_client, household_a, parent_a, second_parent_a, child_a
):
    submission = Submission.objects.create(
        household=household_a,
        child=child_a,
        chore=None,
        chore_name='Dishes',
        chore_points=5,
        idempotency_key='sub-1',
    )
    submission.status = Submission.Status.APPROVED
    submission.decided_by = second_parent_a
    submission.decided_at = submission.created_at
    submission.save()
    sign_in(api_client, parent_a)

    response = call(api_client, 'delete', detail_path(second_parent_a.pk))

    assert response.status_code == 204
    submission.refresh_from_db()
    assert submission.decided_by_id is None
    assert submission.status == Submission.Status.APPROVED


# Last-active-parent guard


def test_the_guard_denies_when_the_target_is_the_only_active_parent(household_a):
    lone_parent = make_member(household_a, 'lone-parent', Membership.Role.PARENT)

    with pytest.raises(Exception) as excinfo:
        _deny_if_would_remove_last_active_parent(
            _lock_parents(household_a), excluded_user_id=lone_parent.pk
        )
    assert str(excinfo.value.detail['detail']) == LAST_PARENT_DETAIL


def test_the_guard_allows_when_another_active_parent_remains(
    household_a, parent_a, second_parent_a
):
    _deny_if_would_remove_last_active_parent(
        _lock_parents(household_a), excluded_user_id=parent_a.pk
    )  # does not raise


@pytest.mark.django_db(transaction=True)
def test_two_concurrent_removals_of_the_last_two_parents_leave_exactly_one(
    household_a, parent_a, second_parent_a
):
    if connection.vendor != 'postgresql':
        pytest.skip('requires the guarded PostgreSQL target')

    barrier = Barrier(2)
    results = {}

    def deactivate_the_other(actor, target, key):
        client = APIClient(enforce_csrf_checks=True)
        sign_in(client, actor)
        barrier.wait(timeout=10)
        response = call(client, 'post', deactivate_path(target.pk))
        results[key] = response.status_code
        connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                deactivate_the_other, parent_a, second_parent_a, 'a_removes_b'
            ),
            executor.submit(
                deactivate_the_other, second_parent_a, parent_a, 'b_removes_a'
            ),
        ]
        for future in futures:
            future.result(timeout=15)

    assert sorted(results.values()) == [200, 400]
    active_parents = User.objects.filter(
        household_memberships__household=household_a,
        household_memberships__role=Membership.Role.PARENT,
        is_active=True,
    ).count()
    assert active_parents == 1


# Household isolation and unknown identifiers


def test_an_unknown_and_a_foreign_identifier_answer_the_same_generic_404(
    api_client, household_b, parent_a, child_a
):
    foreign = make_member(household_b, 'synthetic-foreign', Membership.Role.CHILD)
    unknown_id = child_a.pk + 10_000
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
        assert 'synthetic-foreign' not in cross.content.decode()

    foreign.refresh_from_db()
    assert foreign.is_active is True
    assert audit_actions() == []


# Denied callers


def test_a_child_is_refused_every_route_including_reading(
    api_client, household_a, child_a
):
    sign_in(api_client, child_a)

    for method, path in every_route(child_a.pk):
        response = call(api_client, method, path, {'role': 'parent'})
        assert response.status_code == 403, (method, path)

    assert audit_actions() == []


def test_an_unauthenticated_caller_is_refused_every_route(api_client, parent_a):
    # An anonymous browser can still hold a CSRF cookie, so the refusal below
    # is the authority answer and not a token failure.
    api_client.get(SESSION_PATH)

    for method, path in every_route(parent_a.pk):
        response = call(api_client, method, path, {'role': 'parent'})
        assert response.status_code == 403, (method, path)

    assert audit_actions() == []


def test_a_deactivated_user_with_a_live_session_is_refused_every_route(
    api_client, household_a, parent_a, child_a
):
    sign_in(api_client, parent_a)
    parent_a.is_active = False
    parent_a.save(update_fields=('is_active',))

    for method, path in every_route(child_a.pk):
        response = call(api_client, method, path, {'role': 'parent'})
        assert response.status_code == 403, (method, path)

    assert audit_actions() == []


def test_a_caller_with_no_membership_is_refused_every_route(api_client, child_a):
    outsider = make_user('synthetic-outsider')
    sign_in(api_client, outsider)

    for method, path in every_route(child_a.pk):
        response = call(api_client, method, path, {'role': 'parent'})
        assert response.status_code == 403, (method, path)

    assert audit_actions() == []


def test_a_caller_with_two_candidate_households_is_refused_every_route(
    api_client, household_a, household_b, child_a
):
    ambiguous = make_member(household_a, 'synthetic-both', Membership.Role.PARENT)
    Membership.objects.create(
        household=household_b, user=ambiguous, role=Membership.Role.PARENT
    )
    sign_in(api_client, ambiguous)

    for method, path in every_route(child_a.pk):
        response = call(api_client, method, path, {'role': 'parent'})
        assert response.status_code == 403, (method, path)

    assert audit_actions() == []


def test_a_membership_deleted_after_sign_in_is_refused_immediately(
    api_client, household_a, parent_a, child_a
):
    sign_in(api_client, parent_a)
    Membership.objects.filter(user=parent_a).delete()

    for method, path in every_route(child_a.pk):
        response = call(api_client, method, path, {'role': 'parent'})
        assert response.status_code == 403, (method, path)

    assert audit_actions() == []


# CSRF, safe methods and unsupported methods


def test_an_unsafe_method_without_a_csrf_token_is_refused_and_changes_nothing(
    api_client, household_a, parent_a, child_a
):
    sign_in(api_client, parent_a)

    unsafe = (
        ('post', LIST_PATH),
        ('patch', detail_path(child_a.pk)),
        ('delete', detail_path(child_a.pk)),
        ('post', deactivate_path(child_a.pk)),
        ('post', reactivate_path(child_a.pk)),
    )
    for method, path in unsafe:
        response = call(api_client, method, path, {'role': 'parent'}, with_csrf=False)
        assert response.status_code == 403, (method, path)

    assert User.objects.filter(pk=child_a.pk, is_active=True).exists()
    assert audit_actions() == []


def test_reading_is_side_effect_free(api_client, household_a, parent_a, child_a):
    sign_in(api_client, parent_a)

    for path in (LIST_PATH, detail_path(child_a.pk)):
        assert api_client.get(path).status_code == 200
        assert api_client.head(path).status_code == 200

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
    api_client, household_a, parent_a, child_a, method, path_builder
):
    sign_in(api_client, parent_a)

    response = call(api_client, method, path_builder(child_a.pk), {'role': 'parent'})

    assert response.status_code == 405
    assert audit_actions() == []


def test_the_collection_refuses_delete(api_client, household_a, parent_a):
    sign_in(api_client, parent_a)

    response = call(api_client, 'delete', LIST_PATH)

    assert response.status_code == 405
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


def test_the_member_endpoints_import_only_the_approved_frameworks():
    assert import_roots(members_module) <= {'django', 'rest_framework', 'chorum_murohc'}
