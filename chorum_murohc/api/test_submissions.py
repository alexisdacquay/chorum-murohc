"""Tests for the child completion-attestation endpoint.

Every fixture is synthetic. No credential, PIN, token, cookie or personal
datum appears in the data, the assertions or the failure output: the test
users are created without a usable password and are signed in through the
session machinery directly, so there is nothing sensitive to print.

The awkward cases the permission matrix names are covered: unauthenticated,
an inactive user holding a live session, the allowed role, the denied role,
no resolvable role, an ambiguous two-household caller, a membership deleted
after sign-in, and a cross-household identifier.
"""

import ast
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import resolve, reverse
from rest_framework.test import APIClient

from chorum_murohc.api import submissions as submissions_module
from chorum_murohc.api.submissions import (
    DUPLICATE_PENDING_DETAIL,
    IDEMPOTENCY_KEY_REUSED_DETAIL,
    NOTE_MAX_LENGTH,
    SubmissionListView,
)
from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.chores.models import Chore
from chorum_murohc.identity.models import Household, Membership, User
from chorum_murohc.submissions.models import Submission

LIST_PATH = '/api/v1/submissions/'
SESSION_PATH = '/api/v1/auth/session/'
CSRF_COOKIE = settings.CSRF_COOKIE_NAME

READ_FIELDS = {
    'id',
    'chore',
    'chore_name',
    'chore_points',
    'note',
    'status',
    'created_at',
}
NOT_FOUND_BODY = {'detail': 'Not found.'}
CHORE_REQUIRED_DETAIL = 'This field is required.'


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
def second_child_a(household_a):
    return make_member(household_a, 'synthetic-child-a-2', Membership.Role.CHILD)


@pytest.fixture
def parent_b(household_b):
    return make_member(household_b, 'synthetic-parent-b', Membership.Role.PARENT)


@pytest.fixture
def chore_a(household_a):
    return Chore.objects.create(household=household_a, name='Dishes', points=5)


@pytest.fixture
def inactive_chore_a(household_a):
    return Chore.objects.create(
        household=household_a, name='Retired chore', points=4, is_active=False
    )


@pytest.fixture
def chore_b(household_b):
    return Chore.objects.create(household=household_b, name='Foreign chore', points=9)


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
    if method == 'get':
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


def submit(api_client, chore, *, note='', key='key-1'):
    return call(
        api_client,
        'post',
        LIST_PATH,
        {'chore': chore.pk, 'note': note, 'idempotency_key': key},
    )


# Routing


def test_the_route_is_named_and_resolves():
    assert reverse('api_v1:submission-list') == LIST_PATH
    assert resolve(LIST_PATH).func.view_class is SubmissionListView


# Creating


def test_a_child_creates_a_pending_submission_and_one_create_event(
    api_client, household_a, child_a, chore_a
):
    sign_in(api_client, child_a)

    response = submit(api_client, chore_a, note='Left the mop out')

    assert response.status_code == 201
    body = response.json()
    assert field_names(body) == READ_FIELDS
    assert body['chore'] == chore_a.pk
    assert body['chore_name'] == 'Dishes'
    assert body['chore_points'] == 5
    assert body['note'] == 'Left the mop out'
    assert body['status'] == 'pending'

    submission = Submission.objects.get(pk=body['id'])
    assert submission.household_id == household_a.pk
    assert submission.child_id == child_a.pk
    assert submission.idempotency_key == 'key-1'

    event = one_event('submission.create')
    assert audit_actions() == ['submission.create']
    assert event.household_id == household_a.pk
    assert event.actor_id == child_a.pk
    assert event.target_type == 'submission'
    assert event.target_id == str(submission.pk)
    assert event.context['actor_id'] == child_a.pk
    assert event.context['chore_id'] == chore_a.pk
    assert event.context['note'] == 'Left the mop out'


def test_a_note_is_optional(api_client, child_a, chore_a):
    sign_in(api_client, child_a)

    response = submit(api_client, chore_a, note='')

    assert response.status_code == 201
    assert response.json()['note'] == ''


def test_a_create_body_cannot_choose_the_household_or_child(
    api_client, household_a, household_b, child_a
):
    sign_in(api_client, child_a)

    response = call(
        api_client,
        'post',
        LIST_PATH,
        {
            'chore': Chore.objects.create(
                household=household_a, name='Dishes', points=5
            ).pk,
            'household': household_b.pk,
            'child': 4242,
            'status': 'approved',
            'idempotency_key': 'key-1',
        },
    )

    assert response.status_code == 201
    submission = Submission.objects.get(pk=response.json()['id'])
    assert submission.household_id == household_a.pk
    assert submission.child_id == child_a.pk
    assert submission.status == Submission.Status.PENDING


def test_a_missing_chore_is_a_compact_validation_error(api_client, child_a):
    sign_in(api_client, child_a)

    response = call(api_client, 'post', LIST_PATH, {'idempotency_key': 'key-1'})

    assert response.status_code == 400
    assert response.json()['chore'] == [CHORE_REQUIRED_DETAIL]
    assert Submission.objects.count() == 0


def test_a_missing_idempotency_key_is_a_compact_validation_error(
    api_client, child_a, chore_a
):
    sign_in(api_client, child_a)

    response = call(api_client, 'post', LIST_PATH, {'chore': chore_a.pk})

    assert response.status_code == 400
    assert response.json()['idempotency_key'] == [CHORE_REQUIRED_DETAIL]
    assert Submission.objects.count() == 0


def test_a_note_over_the_limit_is_refused(api_client, child_a, chore_a):
    sign_in(api_client, child_a)

    response = submit(api_client, chore_a, note='x' * (NOTE_MAX_LENGTH + 1))

    assert response.status_code == 400
    assert 'note' in response.json()
    assert Submission.objects.count() == 0


def test_an_inactive_chore_is_the_generic_404_and_writes_no_event(
    api_client, child_a, inactive_chore_a
):
    sign_in(api_client, child_a)

    response = submit(api_client, inactive_chore_a)

    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY
    assert Submission.objects.count() == 0
    assert audit_actions() == []


def test_a_foreign_household_chore_is_the_same_generic_404(
    api_client, child_a, chore_b
):
    sign_in(api_client, child_a)

    response = submit(api_client, chore_b)

    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY
    assert Submission.objects.count() == 0


# Duplicate policy


def test_a_second_submission_while_one_is_pending_is_refused(
    api_client, child_a, chore_a
):
    sign_in(api_client, child_a)
    first = submit(api_client, chore_a, key='key-1')
    assert first.status_code == 201

    second = submit(api_client, chore_a, key='key-2')

    assert second.status_code == 400
    assert second.json()['chore'] == [DUPLICATE_PENDING_DETAIL]
    assert Submission.objects.count() == 1
    assert audit_actions() == ['submission.create']


def test_a_second_submission_is_allowed_once_the_first_is_decided(
    api_client, child_a, parent_a, chore_a
):
    sign_in(api_client, child_a)
    first = submit(api_client, chore_a, key='key-1')
    submission = Submission.objects.get(pk=first.json()['id'])
    submission.status = Submission.Status.APPROVED
    submission.decided_by = parent_a
    submission.decided_at = submission.created_at
    submission.save()

    second = submit(api_client, chore_a, key='key-2')

    assert second.status_code == 201
    assert Submission.objects.count() == 2


# Idempotent retry


def test_retrying_the_same_key_for_the_same_chore_returns_the_original(
    api_client, child_a, chore_a
):
    sign_in(api_client, child_a)
    first = submit(api_client, chore_a, note='Left the mop out', key='same-key')
    assert first.status_code == 201

    retry = submit(api_client, chore_a, note='Left the mop out', key='same-key')

    assert retry.status_code == 200
    assert retry.json()['id'] == first.json()['id']
    assert Submission.objects.count() == 1
    assert audit_actions() == ['submission.create']


def test_reusing_the_same_key_for_a_different_chore_is_refused(
    api_client, household_a, child_a, chore_a
):
    other_chore = Chore.objects.create(household=household_a, name='Vacuum', points=3)
    sign_in(api_client, child_a)
    first = submit(api_client, chore_a, key='same-key')
    assert first.status_code == 201

    response = submit(api_client, other_chore, key='same-key')

    assert response.status_code == 400
    assert response.json()['idempotency_key'] == [IDEMPOTENCY_KEY_REUSED_DETAIL]
    assert Submission.objects.count() == 1


# Reading


def test_get_lists_only_the_callers_own_pending_submissions(
    api_client, household_a, child_a, second_child_a, chore_a
):
    mine = Submission.objects.create(
        household=household_a,
        child=child_a,
        chore=chore_a,
        chore_name=chore_a.name,
        chore_points=chore_a.points,
        idempotency_key='mine',
    )
    Submission.objects.create(
        household=household_a,
        child=second_child_a,
        chore=chore_a,
        chore_name=chore_a.name,
        chore_points=chore_a.points,
        idempotency_key='theirs',
    )
    sign_in(api_client, child_a)

    response = call(api_client, 'get', LIST_PATH)

    assert response.status_code == 200
    body = response.json()
    assert [item['id'] for item in body] == [mine.pk]
    assert field_names(body[0]) == READ_FIELDS


def test_get_never_includes_a_decided_submission(api_client, child_a, chore_a):
    decided = Submission.objects.create(
        household=chore_a.household,
        child=child_a,
        chore=chore_a,
        chore_name=chore_a.name,
        chore_points=chore_a.points,
        idempotency_key='decided',
    )
    decided.status = Submission.Status.WITHDRAWN
    decided.decided_by = child_a
    decided.decided_at = decided.created_at
    decided.save()
    sign_in(api_client, child_a)

    response = call(api_client, 'get', LIST_PATH)

    assert response.status_code == 200
    assert response.json() == []


def test_reading_is_side_effect_free(api_client, child_a, chore_a):
    sign_in(api_client, child_a)

    call(api_client, 'get', LIST_PATH)

    assert Submission.objects.count() == 0
    assert audit_actions() == []


# Authority


def test_a_parent_is_refused_both_methods(api_client, parent_a, chore_a):
    sign_in(api_client, parent_a)

    assert call(api_client, 'get', LIST_PATH).status_code == 403
    assert submit(api_client, chore_a).status_code == 403
    assert Submission.objects.count() == 0


def test_an_unauthenticated_caller_is_refused_both_methods(api_client, chore_a):
    # An anonymous browser can still hold a CSRF cookie, so the refusal below
    # is the authority answer and not a token failure.
    api_client.get(SESSION_PATH)

    assert call(api_client, 'get', LIST_PATH).status_code == 403
    assert submit(api_client, chore_a, key='anon').status_code == 403
    assert Submission.objects.count() == 0


def test_a_deactivated_user_with_a_live_session_is_refused(
    api_client, child_a, chore_a
):
    sign_in(api_client, child_a)
    child_a.is_active = False
    child_a.save(update_fields=('is_active',))

    assert submit(api_client, chore_a).status_code == 403


def test_a_caller_with_no_membership_is_refused(api_client, chore_a):
    user = make_user('synthetic-no-membership')
    sign_in(api_client, user)

    assert submit(api_client, chore_a).status_code == 403


def test_a_caller_with_two_candidate_households_is_refused(
    api_client, household_a, household_b, chore_a
):
    user = make_user('synthetic-two-households')
    Membership.objects.create(
        household=household_a, user=user, role=Membership.Role.CHILD
    )
    Membership.objects.create(
        household=household_b, user=user, role=Membership.Role.CHILD
    )
    sign_in(api_client, user)

    assert submit(api_client, chore_a).status_code == 403


def test_a_membership_deleted_after_sign_in_is_refused_immediately(
    api_client, child_a, chore_a
):
    sign_in(api_client, child_a)
    Membership.objects.filter(user=child_a).delete()

    assert submit(api_client, chore_a).status_code == 403


def test_an_unsafe_method_without_a_csrf_token_is_refused_and_changes_nothing(
    api_client, child_a, chore_a
):
    sign_in(api_client, child_a)

    response = call(
        api_client,
        'post',
        LIST_PATH,
        {'chore': chore_a.pk, 'idempotency_key': 'key-1'},
        with_csrf=False,
    )

    assert response.status_code == 403
    assert Submission.objects.count() == 0


def test_an_unsupported_method_is_refused(api_client, child_a):
    sign_in(api_client, child_a)

    response = call(api_client, 'delete', LIST_PATH)

    assert response.status_code == 405


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


def test_the_submissions_endpoint_imports_only_the_approved_frameworks():
    assert import_roots(submissions_module) <= {
        'django',
        'rest_framework',
        'chorum_murohc',
    }
