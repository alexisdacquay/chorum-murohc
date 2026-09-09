"""Tests for the parent-only pending queue, the child-device parent picker,
and the shared decision endpoint (T044, T046; issue #44).

Every fixture is synthetic. No credential, PIN, token, cookie or personal
datum appears in the data, the assertions or the failure output: the test
users are created without a usable password and are signed in through the
session machinery directly, and every parent PIN used here is set through
the real `identity.services.set_or_replace_pin` contract.

The awkward cases the permission matrix names are covered: unauthenticated,
the denied role, no resolvable role, household isolation, empty results,
page boundaries, stable ordering, invalid and locked PINs, a stale decision,
and compact, non-enumerating errors.
"""

from datetime import timedelta
from itertools import count

import pytest
from django.conf import settings
from django.db import connection
from django.urls import resolve, reverse
from django.utils import timezone
from rest_framework.test import APIClient

from chorum_murohc.api.submissions import (
    APPROVING_PARENT_REQUIRED_DETAIL,
    LOCKOUT_MINUTES,
    PIN_INCORRECT_DETAIL,
    PIN_LOCKED_DETAIL,
    ApprovingParentListView,
    PendingApprovalListView,
    SubmissionDecisionView,
)
from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.chores.models import Chore
from chorum_murohc.identity.models import Household, Membership, ParentPin, User
from chorum_murohc.identity.services import set_or_replace_pin
from chorum_murohc.ledger.models import LedgerEntry
from chorum_murohc.ledger.services import balance_for_user
from chorum_murohc.submissions.models import Submission

APPROVALS_PATH = '/api/v1/approvals/'
APPROVING_PARENTS_PATH = '/api/v1/approving-parents/'
SESSION_PATH = '/api/v1/auth/session/'
CSRF_COOKIE = settings.CSRF_COOKIE_NAME

SYNTHETIC_PASSWORD = 'synthetic-only-account-password'
VALID_PIN = '3947'
WRONG_PIN = '8156'

PENDING_APPROVAL_FIELDS = {
    'id',
    'child_id',
    'child_username',
    'chore',
    'chore_name',
    'chore_points',
    'note',
    'created_at',
}
DECISION_RESPONSE_FIELDS = {
    'id',
    'chore_name',
    'chore_points',
    'note',
    'status',
    'rejection_reason',
    'created_at',
    'decided_at',
}


def decide_path(pk):
    return f'/api/v1/submissions/{pk}/decide/'


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
    return User.objects.create_user(username=username, password=SYNTHETIC_PASSWORD)


def make_member(household, username, role):
    user = make_user(username)
    Membership.objects.create(household=household, user=user, role=role)
    return user


def give_pin(user, household, pin=VALID_PIN):
    set_or_replace_pin(
        user=user, household=household, current_password=SYNTHETIC_PASSWORD, new_pin=pin
    )


@pytest.fixture
def parent_a(household_a):
    user = make_member(household_a, 'synthetic-parent-a', Membership.Role.PARENT)
    give_pin(user, household_a)
    return user


@pytest.fixture
def child_a(household_a):
    return make_member(household_a, 'synthetic-child-a', Membership.Role.CHILD)


@pytest.fixture
def parent_b(household_b):
    return make_member(household_b, 'synthetic-parent-b', Membership.Role.PARENT)


@pytest.fixture
def chore_a(household_a):
    return Chore.objects.create(household=household_a, name='Dishes', points=5)


def make_submission(household, child, chore, *, key='sub-1', created_at=None):
    submission = Submission.objects.create(
        household=household,
        child=child,
        chore=chore,
        chore_name=chore.name,
        chore_points=chore.points,
        idempotency_key=key,
    )
    if created_at is not None:
        # `Submission` refuses every ORM update; a direct write is the only
        # way a test can backdate a fixture row, exactly as `test_audit.py`
        # backdates its own append-only `AuditEvent` fixtures.
        with connection.cursor() as cursor:
            cursor.execute(
                'UPDATE submissions_submission SET created_at = %s WHERE id = %s',
                [created_at, submission.pk],
            )
        submission.refresh_from_db()
    return submission


_extra_chore_counter = count()


def make_submissions(household, child, quantity, *, created_at=None):
    """`quantity` pending submissions for `child`, each its own chore: the
    model allows only one pending submission per child-and-chore pair, so a
    test that wants several at once needs several chores, not several keys.
    """
    submissions = []
    for _ in range(quantity):
        index = next(_extra_chore_counter)
        chore = Chore.objects.create(
            household=household, name=f'Extra chore {index}', points=index + 1
        )
        submissions.append(
            make_submission(
                household, child, chore, key=f'k{index}', created_at=created_at
            )
        )
    return submissions


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


def one_event(action):
    events = list(AuditEvent.objects.filter(action=action))
    assert len(events) == 1
    return events[0]


# --- GET /api/v1/approvals/ (T044) -----------------------------------------


def test_the_approvals_route_is_named_and_resolves():
    assert reverse('api_v1:approval-list') == APPROVALS_PATH
    assert resolve(APPROVALS_PATH).func.view_class is PendingApprovalListView


def test_an_unauthenticated_caller_is_refused(api_client, household_a):
    response = call(api_client, 'get', APPROVALS_PATH)
    assert response.status_code == 403


def test_a_child_is_refused(api_client, child_a):
    sign_in(api_client, child_a)
    response = call(api_client, 'get', APPROVALS_PATH)
    assert response.status_code == 403


def test_a_parent_with_no_resolvable_household_is_refused(api_client, db):
    lone_parent = make_user('synthetic-lone-parent')
    sign_in(api_client, lone_parent)
    response = call(api_client, 'get', APPROVALS_PATH)
    assert response.status_code == 403


def test_a_parent_reads_their_own_household_pending_queue(
    api_client, household_a, parent_a, child_a, chore_a
):
    submission = make_submission(household_a, child_a, chore_a)
    sign_in(api_client, parent_a)

    response = call(api_client, 'get', APPROVALS_PATH)

    assert response.status_code == 200
    body = response.json()
    assert body['count'] == 1
    item = body['results'][0]
    assert field_names(item) == PENDING_APPROVAL_FIELDS
    assert item['id'] == submission.pk
    assert item['child_id'] == child_a.pk
    assert item['child_username'] == 'synthetic-child-a'
    assert item['chore'] == chore_a.pk
    assert item['chore_name'] == 'Dishes'
    assert item['chore_points'] == 5


def test_a_foreign_household_submission_never_appears(
    api_client, household_a, household_b, parent_a, parent_b, chore_a
):
    other_child = make_member(household_b, 'synthetic-child-b', Membership.Role.CHILD)
    other_chore = Chore.objects.create(household=household_b, name='Trash', points=3)
    make_submission(household_b, other_child, other_chore)
    sign_in(api_client, parent_a)

    response = call(api_client, 'get', APPROVALS_PATH)

    assert response.json()['count'] == 0


def test_a_decided_submission_never_appears(
    api_client, household_a, parent_a, child_a, chore_a
):
    submission = make_submission(household_a, child_a, chore_a)
    submission.status = Submission.Status.APPROVED
    submission.decided_by = parent_a
    submission.decided_at = timezone.now()
    submission.save()
    sign_in(api_client, parent_a)

    response = call(api_client, 'get', APPROVALS_PATH)

    assert response.json()['count'] == 0


def test_empty_results_when_nothing_is_pending(api_client, household_a, parent_a):
    sign_in(api_client, parent_a)

    response = call(api_client, 'get', APPROVALS_PATH)

    assert response.status_code == 200
    assert response.json() == {
        'count': 0,
        'next': None,
        'previous': None,
        'results': [],
    }


def test_results_are_newest_first_with_a_stable_id_tie_breaker(
    api_client, household_a, parent_a, child_a
):
    tied_time = timezone.now() - timedelta(days=1)
    submissions = make_submissions(household_a, child_a, 2, created_at=tied_time)
    first, second = submissions
    third = make_submissions(household_a, child_a, 1)[0]
    sign_in(api_client, parent_a)

    response = call(api_client, 'get', APPROVALS_PATH)

    ids = [item['id'] for item in response.json()['results']]
    assert ids == [third.pk, second.pk, first.pk]


def test_pagination_is_native_and_page_size_is_capped(
    api_client, household_a, parent_a, child_a
):
    make_submissions(household_a, child_a, 3)
    sign_in(api_client, parent_a)

    response = call(api_client, 'get', APPROVALS_PATH)
    body = response.json()
    assert set(body) == {'count', 'next', 'previous', 'results'}
    assert body['count'] == 3
    assert body['previous'] is None

    capped = call(api_client, 'get', f'{APPROVALS_PATH}?page_size=150')
    assert len(capped.json()['results']) == 3


def test_a_second_page_holds_the_remainder(api_client, household_a, parent_a, child_a):
    make_submissions(household_a, child_a, 3)
    sign_in(api_client, parent_a)

    first_page = call(api_client, 'get', f'{APPROVALS_PATH}?page_size=2')
    assert len(first_page.json()['results']) == 2
    assert first_page.json()['next'] is not None

    second_page = call(api_client, 'get', f'{APPROVALS_PATH}?page_size=2&page=2')
    assert len(second_page.json()['results']) == 1
    assert second_page.json()['next'] is None


@pytest.mark.parametrize('method', ('post', 'put', 'patch', 'delete'))
def test_every_write_method_is_refused(api_client, household_a, parent_a, method):
    sign_in(api_client, parent_a)
    response = call(api_client, method, APPROVALS_PATH)
    assert response.status_code == 405


# --- GET /api/v1/approving-parents/ ------------------------------------------


def test_the_approving_parents_route_is_named_and_resolves():
    assert reverse('api_v1:approving-parent-list') == APPROVING_PARENTS_PATH
    assert resolve(APPROVING_PARENTS_PATH).func.view_class is ApprovingParentListView


def test_a_parent_is_refused_on_the_approving_parents_route(
    api_client, household_a, parent_a
):
    sign_in(api_client, parent_a)
    response = call(api_client, 'get', APPROVING_PARENTS_PATH)
    assert response.status_code == 403


def test_an_unauthenticated_caller_is_refused_on_approving_parents(api_client, db):
    response = call(api_client, 'get', APPROVING_PARENTS_PATH)
    assert response.status_code == 403


def test_a_child_sees_only_parents_who_hold_a_pin(api_client, household_a, child_a):
    with_pin = make_member(
        household_a, 'synthetic-parent-with-pin', Membership.Role.PARENT
    )
    give_pin(with_pin, household_a)
    make_member(household_a, 'synthetic-parent-without-pin', Membership.Role.PARENT)
    sign_in(api_client, child_a)

    response = call(api_client, 'get', APPROVING_PARENTS_PATH)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0] == {
        'id': with_pin.pk,
        'username': 'synthetic-parent-with-pin',
        'available': True,
    }


def test_a_locked_parent_stays_listed_as_unavailable(api_client, household_a, child_a):
    locked_parent = make_member(
        household_a, 'synthetic-locked-parent', Membership.Role.PARENT
    )
    give_pin(locked_parent, household_a)
    ParentPin.objects.filter(user=locked_parent).update(
        failed_attempts=5, locked_until=timezone.now() + timedelta(minutes=15)
    )
    sign_in(api_client, child_a)

    response = call(api_client, 'get', APPROVING_PARENTS_PATH)

    assert response.json() == [
        {
            'id': locked_parent.pk,
            'username': 'synthetic-locked-parent',
            'available': False,
        }
    ]


def test_a_foreign_household_parent_never_appears(
    api_client, household_a, household_b, child_a, parent_b
):
    give_pin(parent_b, household_b)
    sign_in(api_client, child_a)

    response = call(api_client, 'get', APPROVING_PARENTS_PATH)

    assert response.json() == []


# --- POST /api/v1/submissions/<pk>/decide/ (T046) ----------------------------


def test_the_decide_route_is_named_and_resolves(
    household_a, parent_a, child_a, chore_a
):
    submission = make_submission(household_a, child_a, chore_a)
    assert reverse('api_v1:submission-decide', args=[submission.pk]) == decide_path(
        submission.pk
    )
    assert resolve(decide_path(submission.pk)).func.view_class is SubmissionDecisionView


def test_an_unauthenticated_caller_is_refused_on_decide(
    api_client, household_a, child_a, chore_a
):
    submission = make_submission(household_a, child_a, chore_a)
    response = call(
        api_client,
        'post',
        decide_path(submission.pk),
        {'decision': 'approve', 'pin': VALID_PIN},
    )
    assert response.status_code == 403


def test_csrf_is_required(api_client, household_a, parent_a, child_a, chore_a):
    submission = make_submission(household_a, child_a, chore_a)
    sign_in(api_client, parent_a)

    response = call(
        api_client,
        'post',
        decide_path(submission.pk),
        {'decision': 'approve', 'pin': VALID_PIN},
        with_csrf=False,
    )

    assert response.status_code == 403
    assert Submission.objects.get(pk=submission.pk).status == Submission.Status.PENDING


def test_parent_device_approval_credits_and_returns_the_exact_shape(
    api_client, household_a, parent_a, child_a, chore_a
):
    submission = make_submission(household_a, child_a, chore_a)
    sign_in(api_client, parent_a)

    response = call(
        api_client,
        'post',
        decide_path(submission.pk),
        {'decision': 'approve', 'pin': VALID_PIN},
    )

    assert response.status_code == 200
    body = response.json()
    assert field_names(body) == DECISION_RESPONSE_FIELDS
    assert body['status'] == 'approved'
    assert body['rejection_reason'] == ''
    assert balance_for_user(household_a, child_a) == 5

    event = one_event('submission.approve')
    assert event.actor_id == parent_a.pk
    assert event.context['device'] == 'parent'


def test_parent_device_rejection_carries_the_reason_and_credits_nothing(
    api_client, household_a, parent_a, child_a, chore_a
):
    submission = make_submission(household_a, child_a, chore_a)
    sign_in(api_client, parent_a)

    response = call(
        api_client,
        'post',
        decide_path(submission.pk),
        {'decision': 'reject', 'pin': VALID_PIN, 'reason': 'Not dry yet'},
    )

    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'rejected'
    assert body['rejection_reason'] == 'Not dry yet'
    assert balance_for_user(household_a, child_a) == 0
    assert LedgerEntry.objects.count() == 0


def test_child_device_names_a_parent_and_that_parent_is_the_actor(
    api_client, household_a, parent_a, child_a, chore_a
):
    submission = make_submission(household_a, child_a, chore_a)
    sign_in(api_client, child_a)

    response = call(
        api_client,
        'post',
        decide_path(submission.pk),
        {'decision': 'approve', 'pin': VALID_PIN, 'approving_parent': parent_a.pk},
    )

    assert response.status_code == 200
    assert response.json()['status'] == 'approved'
    event = one_event('submission.approve')
    assert event.actor_id == parent_a.pk
    assert event.context['device'] == 'child'


def test_child_device_without_a_named_parent_is_a_compact_validation_error(
    api_client, household_a, child_a, chore_a
):
    submission = make_submission(household_a, child_a, chore_a)
    sign_in(api_client, child_a)

    response = call(
        api_client,
        'post',
        decide_path(submission.pk),
        {'decision': 'approve', 'pin': VALID_PIN},
    )

    assert response.status_code == 400
    assert response.json() == {'approving_parent': [APPROVING_PARENT_REQUIRED_DETAIL]}
    assert Submission.objects.get(pk=submission.pk).status == Submission.Status.PENDING


def test_a_wrong_pin_is_the_generic_compact_detail(
    api_client, household_a, parent_a, child_a, chore_a
):
    submission = make_submission(household_a, child_a, chore_a)
    sign_in(api_client, parent_a)

    response = call(
        api_client,
        'post',
        decide_path(submission.pk),
        {'decision': 'approve', 'pin': WRONG_PIN},
    )

    assert response.status_code == 400
    assert response.json() == {'pin': [PIN_INCORRECT_DETAIL]}
    assert Submission.objects.get(pk=submission.pk).status == Submission.Status.PENDING


def test_a_locked_pin_names_the_lockout_not_a_wrong_guess(
    api_client, household_a, parent_a, child_a, chore_a
):
    submission = make_submission(household_a, child_a, chore_a)
    ParentPin.objects.filter(user=parent_a).update(
        failed_attempts=5, locked_until=timezone.now() + timedelta(minutes=15)
    )
    sign_in(api_client, parent_a)

    response = call(
        api_client,
        'post',
        decide_path(submission.pk),
        {'decision': 'approve', 'pin': VALID_PIN},
    )

    assert response.status_code == 400
    assert response.json() == {'pin': [PIN_LOCKED_DETAIL]}
    assert str(LOCKOUT_MINUTES) in PIN_LOCKED_DETAIL


def test_a_foreign_household_submission_is_a_generic_not_found(
    api_client, household_a, household_b, parent_b, child_a, chore_a
):
    give_pin(parent_b, household_b)
    submission = make_submission(household_a, child_a, chore_a)
    sign_in(api_client, parent_b)

    response = call(
        api_client,
        'post',
        decide_path(submission.pk),
        {'decision': 'approve', 'pin': VALID_PIN},
    )

    assert response.status_code == 404
    assert Submission.objects.get(pk=submission.pk).status == Submission.Status.PENDING


def test_retrying_an_already_decided_submission_is_the_same_not_found_and_credits_once(
    api_client, household_a, parent_a, child_a, chore_a
):
    submission = make_submission(household_a, child_a, chore_a)
    sign_in(api_client, parent_a)
    first = call(
        api_client,
        'post',
        decide_path(submission.pk),
        {'decision': 'approve', 'pin': VALID_PIN},
    )
    assert first.status_code == 200

    retry = call(
        api_client,
        'post',
        decide_path(submission.pk),
        {'decision': 'approve', 'pin': VALID_PIN},
    )

    assert retry.status_code == 404
    assert balance_for_user(household_a, child_a) == 5
    assert LedgerEntry.objects.filter(source_id=str(submission.pk)).count() == 1


def test_an_invalid_decision_value_is_a_compact_validation_error(
    api_client, household_a, parent_a, child_a, chore_a
):
    submission = make_submission(household_a, child_a, chore_a)
    sign_in(api_client, parent_a)

    response = call(
        api_client,
        'post',
        decide_path(submission.pk),
        {'decision': 'maybe', 'pin': VALID_PIN},
    )

    assert response.status_code == 400
    assert 'decision' in response.json()
