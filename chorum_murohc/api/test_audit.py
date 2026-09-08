"""Tests for the parent-only read-only audit endpoint.

Every fixture is synthetic. No credential, PIN, token, cookie or personal
datum appears in the data, the assertions or the failure output: the test
users are created without a usable password and are signed in through the
session machinery directly, so there is nothing sensitive to print.
"""

from datetime import UTC, datetime, timedelta

import pytest
from django.conf import settings
from django.db import connection
from django.urls import resolve, reverse
from django.utils import timezone
from rest_framework.test import APIClient

from chorum_murohc.api.audit import (
    DATE_RANGE_DETAIL,
    MAXIMUM_PAGE_SIZE,
    AuditEventListView,
)
from chorum_murohc.api.permissions import PERMISSION_DENIED_DETAIL
from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity.models import Household, Membership, User

LIST_PATH = '/api/v1/audit/'
SESSION_PATH = '/api/v1/auth/session/'
CSRF_COOKIE = settings.CSRF_COOKIE_NAME

DENIED_BODY = {'detail': PERMISSION_DENIED_DETAIL}
EVENT_FIELDS = {
    'id',
    'actor',
    'action',
    'target_type',
    'target_id',
    'created_at',
    'context',
}


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


def sign_in(api_client, user):
    api_client.force_login(user)
    api_client.get(SESSION_PATH)
    return api_client


def csrf_header(api_client):
    cookie = api_client.cookies.get(CSRF_COOKIE)
    return {'x-csrftoken': cookie.value} if cookie is not None else {}


def make_event(
    household,
    *,
    actor=None,
    action='account.updated',
    target_id='1',
    context=None,
    created_at=None,
):
    event = AuditEvent.objects.create(
        household=household,
        actor=actor,
        action=action,
        target_type='identity.User',
        target_id=target_id,
        context=context or {},
    )
    if created_at is not None:
        # `AuditEvent` refuses every ORM update; a direct write is the only
        # way a test can backdate a fixture row, exactly as the model's own
        # tests do.
        with connection.cursor() as cursor:
            cursor.execute(
                'UPDATE audit_auditevent SET created_at = %s WHERE id = %s',
                [created_at, event.pk],
            )
        event.refresh_from_db()
    return event


# Routing


def test_the_route_is_named_and_resolves():
    assert reverse('api_v1:audit-list') == LIST_PATH
    assert resolve(LIST_PATH).func.view_class is AuditEventListView


# Authority


def test_an_unauthenticated_caller_is_refused(api_client, household_a):
    make_event(household_a)

    response = api_client.get(LIST_PATH)

    # An anonymous caller never holds a session, so DRF answers with its own
    # generic authentication-required detail rather than the permission
    # primitive's; the shared behaviour every route relies on is the status
    # code and the absence of any event data, both asserted here.
    assert response.status_code == 403
    assert 'results' not in response.json()


def test_a_child_is_refused(api_client, household_a, child_a):
    make_event(household_a)
    sign_in(api_client, child_a)

    response = api_client.get(LIST_PATH)

    assert response.status_code == 403
    assert response.json() == DENIED_BODY


def test_a_parent_with_no_resolvable_household_is_refused(api_client, db):
    lone_parent = make_user('synthetic-lone-parent')
    sign_in(api_client, lone_parent)

    response = api_client.get(LIST_PATH)

    assert response.status_code == 403
    assert response.json() == DENIED_BODY


def test_a_parent_reads_their_own_household_events(api_client, household_a, parent_a):
    event = make_event(household_a, actor=parent_a, action='chore.create')
    sign_in(api_client, parent_a)

    response = api_client.get(LIST_PATH)

    assert response.status_code == 200
    body = response.json()['results']
    assert len(body) == 1
    assert set(body[0]) == EVENT_FIELDS
    assert body[0]['id'] == event.pk
    assert body[0]['actor'] == parent_a.pk
    assert body[0]['action'] == 'chore.create'


# Household isolation


def test_a_foreign_household_event_never_appears(
    api_client, household_a, household_b, parent_a, parent_b
):
    make_event(household_a, actor=parent_a, target_id='own')
    foreign = make_event(household_b, actor=parent_b, target_id='foreign')
    sign_in(api_client, parent_a)

    response = api_client.get(LIST_PATH)

    body = response.json()['results']
    assert [item['target_id'] for item in body] == ['own']
    assert 'foreign' not in response.content.decode()
    assert foreign.household_id == household_b.pk


def test_an_actor_filter_from_another_household_returns_no_rows_not_an_error(
    api_client, household_a, household_b, parent_a, parent_b
):
    make_event(household_a, actor=parent_a)
    sign_in(api_client, parent_a)

    response = api_client.get(f'{LIST_PATH}?actor={parent_b.pk}')

    assert response.status_code == 200
    assert response.json()['results'] == []


# Redaction


def test_the_stored_redacted_context_passes_through_unchanged(
    api_client, household_a, parent_a
):
    make_event(
        household_a,
        actor=parent_a,
        context={'note': 'safe', 'password': 'synthetic-sensitive-marker'},
    )
    sign_in(api_client, parent_a)

    response = api_client.get(LIST_PATH)

    context = response.json()['results'][0]['context']
    assert context == {'note': 'safe', 'password': '[REDACTED]'}
    assert 'synthetic-sensitive-marker' not in response.content.decode()


# Ordering


def test_results_are_newest_first_with_a_stable_id_tie_breaker(
    api_client, household_a, parent_a
):
    tied_time = timezone.now() - timedelta(days=1)
    first = make_event(household_a, target_id='first', created_at=tied_time)
    second = make_event(household_a, target_id='second', created_at=tied_time)
    third = make_event(household_a, target_id='third')
    sign_in(api_client, parent_a)

    response = api_client.get(LIST_PATH)

    ids = [item['id'] for item in response.json()['results']]
    assert ids == [third.pk, second.pk, first.pk]


# Filtering


def test_the_actor_filter_matches_exactly_one_actor(
    api_client, household_a, parent_a, child_a
):
    matching = make_event(household_a, actor=parent_a, target_id='matching')
    make_event(household_a, actor=child_a, target_id='other')
    sign_in(api_client, parent_a)

    response = api_client.get(f'{LIST_PATH}?actor={parent_a.pk}')

    ids = [item['id'] for item in response.json()['results']]
    assert ids == [matching.pk]


def test_the_action_filter_matches_exactly(api_client, household_a, parent_a):
    matching = make_event(household_a, action='chore.delete', target_id='matching')
    make_event(household_a, action='chore.update', target_id='other')
    sign_in(api_client, parent_a)

    response = api_client.get(f'{LIST_PATH}?action=chore.delete')

    ids = [item['id'] for item in response.json()['results']]
    assert ids == [matching.pk]


def test_the_date_range_filter_is_inclusive_on_both_ends(
    api_client, household_a, parent_a
):
    early = make_event(
        household_a,
        target_id='early',
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    inside = make_event(
        household_a,
        target_id='inside',
        created_at=datetime(2026, 1, 5, tzinfo=UTC),
    )
    make_event(
        household_a,
        target_id='late',
        created_at=datetime(2026, 1, 10, tzinfo=UTC),
    )
    sign_in(api_client, parent_a)

    response = api_client.get(f'{LIST_PATH}?date_from=2026-01-01&date_to=2026-01-05')

    ids = {item['id'] for item in response.json()['results']}
    assert ids == {early.pk, inside.pk}


@pytest.mark.parametrize(
    ('query', 'field'),
    (
        ('actor=not-a-number', 'actor'),
        ('actor=0', 'actor'),
        ('action=' + 'x' * 101, 'action'),
        ('date_from=not-a-date', 'date_from'),
        ('date_from=2026-01-10&date_to=2026-01-01', 'date_to'),
    ),
)
def test_an_invalid_filter_is_a_compact_400_and_reads_nothing(
    api_client, household_a, parent_a, query, field
):
    make_event(household_a, actor=parent_a)
    sign_in(api_client, parent_a)

    response = api_client.get(f'{LIST_PATH}?{query}')

    assert response.status_code == 400
    body = response.json()
    assert field in body
    assert isinstance(body[field], list)


def test_the_date_range_error_names_neither_date(api_client, household_a, parent_a):
    sign_in(api_client, parent_a)

    response = api_client.get(f'{LIST_PATH}?date_from=2026-01-10&date_to=2026-01-01')

    assert response.json() == {'date_to': [DATE_RANGE_DETAIL]}


# Pagination


def test_pagination_is_native_and_page_size_is_capped(
    api_client, household_a, parent_a
):
    for index in range(3):
        make_event(household_a, target_id=str(index))
    sign_in(api_client, parent_a)

    response = api_client.get(LIST_PATH)

    body = response.json()
    assert set(body) == {'count', 'next', 'previous', 'results'}
    assert body['count'] == 3
    assert body['previous'] is None

    capped = api_client.get(f'{LIST_PATH}?page_size={MAXIMUM_PAGE_SIZE + 50}')
    assert len(capped.json()['results']) == 3


def test_a_second_page_holds_the_remainder(api_client, household_a, parent_a):
    for index in range(3):
        make_event(household_a, target_id=str(index))
    sign_in(api_client, parent_a)

    first_page = api_client.get(f'{LIST_PATH}?page_size=2')
    assert len(first_page.json()['results']) == 2
    assert first_page.json()['next'] is not None

    second_page = api_client.get(f'{LIST_PATH}?page_size=2&page=2')
    assert len(second_page.json()['results']) == 1
    assert second_page.json()['next'] is None


# Immutability: no write method exists on this endpoint


@pytest.mark.parametrize('method', ('post', 'put', 'patch', 'delete'))
def test_every_write_method_is_refused_and_nothing_is_written(
    api_client, household_a, parent_a, method
):
    make_event(household_a, actor=parent_a)
    sign_in(api_client, parent_a)
    before = AuditEvent.objects.count()

    handler = getattr(api_client, method)
    response = handler(LIST_PATH, {}, format='json', headers=csrf_header(api_client))

    assert response.status_code == 405
    assert AuditEvent.objects.count() == before


def test_an_unsupported_method_is_refused_before_authority_is_considered(
    api_client, household_a, child_a
):
    # A child (and an unauthenticated caller) get the same 405 as a parent
    # would: the method is refused before role is ever looked at.
    sign_in(api_client, child_a)

    response = api_client.post(LIST_PATH, {}, format='json')

    assert response.status_code == 405

    anonymous_response = APIClient(enforce_csrf_checks=True).post(
        LIST_PATH, {}, format='json'
    )
    assert anonymous_response.status_code == 405
