"""Tests for the creature endpoints.

Every fixture is synthetic. No credential, PIN, token, cookie or personal
datum appears in the data, the assertions or the failure output: the test
users are created without a usable password and are signed in through the
session machinery directly, so there is nothing sensitive to print.

The awkward cases the permission matrix names are covered for all three
routes: unauthenticated, an inactive user holding a live session, the allowed
role, the denied role, no resolvable role, an ambiguous two-household caller,
and a membership deleted after sign-in.
"""

import pytest
from django.conf import settings
from django.urls import resolve, reverse
from rest_framework.test import APIClient

from chorum_murohc.api.creatures import (
    LINE_ALREADY_CHOSEN_DETAIL,
    CreatureLineListView,
    CreatureView,
)
from chorum_murohc.api.permissions import PERMISSION_DENIED_DETAIL
from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.creatures.catalogue import CREATURE_LINES
from chorum_murohc.creatures.models import CreatureSelection
from chorum_murohc.creatures.services import AUDIT_LINE_SELECTED
from chorum_murohc.identity.models import Household, Membership, User
from chorum_murohc.ledger.models import LedgerEntry

CREATURE_PATH = '/api/v1/creature/'
LINES_PATH = '/api/v1/creature/lines/'
SESSION_PATH = '/api/v1/auth/session/'
CSRF_COOKIE = settings.CSRF_COOKIE_NAME

STATE_FIELDS = {'level', 'max_level', 'line', 'current_form', 'forms'}
FORM_FIELDS = {'index', 'name', 'alt_text', 'unlock_level', 'asset_path', 'unlocked'}
PREVIEW_FIELDS = {'index', 'name', 'alt_text', 'unlock_level', 'asset_path'}
NOT_AUTHENTICATED_DETAIL = 'Authentication credentials were not provided.'

POINTS_FOR_LEVEL = {1: 50, 4: 500, 7: 1400, 10: 2750}


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


def choose(api_client, line, *, with_csrf=True):
    headers = csrf_header(api_client) if with_csrf else {}
    return api_client.post(
        CREATURE_PATH, {'line': line}, format='json', headers=headers
    )


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


# Routing


def test_both_routes_are_named_and_resolve():
    assert reverse('api_v1:creature') == CREATURE_PATH
    assert reverse('api_v1:creature-line-list') == LINES_PATH

    assert resolve(CREATURE_PATH).func.view_class is CreatureView
    assert resolve(LINES_PATH).func.view_class is CreatureLineListView


# GET creature/lines/


def test_the_catalogue_lists_seven_lines_with_one_preview_each(api_client, child_a):
    sign_in(api_client, child_a)

    response = api_client.get(LINES_PATH)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {'lines'}
    assert len(body['lines']) == 7
    assert [line['slug'] for line in body['lines']] == [
        line.slug for line in CREATURE_LINES
    ]
    for line in body['lines']:
        assert set(line) == {'slug', 'name', 'description', 'preview'}
        assert set(line['preview']) == PREVIEW_FIELDS
        assert line['preview']['index'] == 1
        assert line['preview']['asset_path'] == f'/creatures/{line["slug"]}/form-1.svg'


def test_the_catalogue_is_the_same_before_and_after_choosing(api_client, child_a):
    sign_in(api_client, child_a)
    before = api_client.get(LINES_PATH).json()

    choose(api_client, 'dragon')

    assert api_client.get(LINES_PATH).json() == before


# GET creature/


def test_a_child_with_no_selection_reads_the_exact_agreed_shape(api_client, child_a):
    sign_in(api_client, child_a)

    response = api_client.get(CREATURE_PATH)

    assert response.status_code == 200
    assert response.json() == {
        'level': 0,
        'max_level': 10,
        'line': None,
        'current_form': None,
        'forms': [],
    }


def test_a_chosen_line_reports_four_forms_and_the_one_reached(
    api_client, household_a, child_a
):
    credit(household_a, child_a, POINTS_FOR_LEVEL[4], 'credit-1')
    sign_in(api_client, child_a)
    choose(api_client, 'griffin')

    body = api_client.get(CREATURE_PATH).json()

    assert set(body) == STATE_FIELDS
    assert body['level'] == 4
    assert body['line'] == {
        'slug': 'griffin',
        'name': 'Griffin',
        'description': 'Half eagle and half lion, with an eye on every horizon.',
    }
    assert len(body['forms']) == 4
    for form in body['forms']:
        assert set(form) == FORM_FIELDS
    assert [form['unlocked'] for form in body['forms']] == [True, True, False, False]
    assert body['current_form']['index'] == 2
    assert body['current_form']['asset_path'] == '/creatures/griffin/form-2.svg'


def test_locked_forms_are_still_described_so_they_can_be_silhouetted(
    api_client, child_a
):
    sign_in(api_client, child_a)
    choose(api_client, 'treant')

    body = api_client.get(CREATURE_PATH).json()

    assert body['current_form'] is None
    assert [form['unlock_level'] for form in body['forms']] == [1, 4, 7, 10]
    assert all(form['alt_text'] for form in body['forms'])
    assert all(form['unlocked'] is False for form in body['forms'])


def test_one_child_never_reads_another_child_creature(api_client, household_a, child_a):
    sibling = make_member(household_a, 'synthetic-sibling-a')
    sign_in(api_client, sibling)
    choose(api_client, 'kraken')

    api_client.logout()
    sign_in(api_client, child_a)

    assert api_client.get(CREATURE_PATH).json()['line'] is None


# POST creature/


def test_choosing_answers_201_with_the_new_state_and_writes_one_audit_event(
    api_client, household_a, child_a
):
    sign_in(api_client, child_a)

    response = choose(api_client, 'phoenix')

    assert response.status_code == 201
    body = response.json()
    assert set(body) == STATE_FIELDS
    assert body['line']['slug'] == 'phoenix'
    assert (
        CreatureSelection.objects.get(household=household_a, user=child_a).line_slug
        == 'phoenix'
    )

    event = AuditEvent.objects.get(action=AUDIT_LINE_SELECTED)
    assert event.actor_id == child_a.pk
    assert event.context['line_slug'] == 'phoenix'


def test_choosing_the_same_line_again_answers_200_and_writes_nothing_more(
    api_client, child_a
):
    sign_in(api_client, child_a)
    choose(api_client, 'golem')

    response = choose(api_client, 'golem')

    assert response.status_code == 200
    assert response.json()['line']['slug'] == 'golem'
    assert AuditEvent.objects.filter(action=AUDIT_LINE_SELECTED).count() == 1


def test_choosing_a_different_line_answers_409_and_keeps_the_first(api_client, child_a):
    sign_in(api_client, child_a)
    choose(api_client, 'sphinx')

    response = choose(api_client, 'dragon')

    assert response.status_code == 409
    assert response.json()['detail'] == LINE_ALREADY_CHOSEN_DETAIL
    assert api_client.get(CREATURE_PATH).json()['line']['slug'] == 'sphinx'


@pytest.mark.parametrize(
    'body',
    [{}, {'line': ''}, {'line': 'pikachu'}, {'line': 'DRAGON'}, {'line': None}],
)
def test_an_invalid_line_answers_400_and_writes_nothing(api_client, child_a, body):
    sign_in(api_client, child_a)

    response = api_client.post(
        CREATURE_PATH, body, format='json', headers=csrf_header(api_client)
    )

    assert response.status_code == 400
    assert 'line' in response.json()
    assert CreatureSelection.objects.count() == 0
    assert AuditEvent.objects.count() == 0


def test_a_post_without_the_csrf_header_is_refused(api_client, child_a):
    sign_in(api_client, child_a)

    response = choose(api_client, 'dragon', with_csrf=False)

    assert response.status_code == 403
    assert CreatureSelection.objects.count() == 0


def test_the_client_cannot_name_the_household_the_level_or_the_forms(
    api_client, household_a, household_b, child_a
):
    sign_in(api_client, child_a)

    response = api_client.post(
        CREATURE_PATH,
        {
            'line': 'kraken',
            'household': household_b.pk,
            'level': 10,
            'forms': [],
            'current_form': {'index': 4},
        },
        format='json',
        headers=csrf_header(api_client),
    )

    assert response.status_code == 201
    body = response.json()
    assert body['level'] == 0
    assert body['current_form'] is None
    assert CreatureSelection.objects.get(user=child_a).household_id == household_a.pk


# Authority, for every route


@pytest.mark.parametrize('path', [CREATURE_PATH, LINES_PATH])
def test_an_anonymous_caller_is_refused(api_client, db, path):
    response = api_client.get(path)

    assert response.status_code == 403
    assert response.json()['detail'] in {
        NOT_AUTHENTICATED_DETAIL,
        PERMISSION_DENIED_DETAIL,
    }


@pytest.mark.parametrize('path', [CREATURE_PATH, LINES_PATH])
def test_a_parent_is_refused_every_creature_route(api_client, parent_a, path):
    sign_in(api_client, parent_a)

    response = api_client.get(path)

    assert response.status_code == 403
    assert response.json()['detail'] == PERMISSION_DENIED_DETAIL


def test_a_parent_cannot_choose_a_creature(api_client, parent_a):
    sign_in(api_client, parent_a)

    response = choose(api_client, 'dragon')

    assert response.status_code == 403
    assert CreatureSelection.objects.count() == 0


@pytest.mark.parametrize('path', [CREATURE_PATH, LINES_PATH])
def test_a_user_with_no_membership_is_refused(api_client, db, path):
    stranger = make_user('synthetic-stranger')
    sign_in(api_client, stranger)

    assert api_client.get(path).status_code == 403


@pytest.mark.parametrize('path', [CREATURE_PATH, LINES_PATH])
def test_a_caller_in_two_households_is_refused(
    api_client, household_a, household_b, path
):
    ambiguous = make_member(household_a, 'synthetic-ambiguous')
    Membership.objects.create(
        household=household_b, user=ambiguous, role=Membership.Role.CHILD
    )
    sign_in(api_client, ambiguous)

    assert api_client.get(path).status_code == 403


@pytest.mark.parametrize('path', [CREATURE_PATH, LINES_PATH])
def test_a_deactivated_child_holding_a_live_session_is_refused(
    api_client, child_a, path
):
    sign_in(api_client, child_a)
    child_a.is_active = False
    child_a.save(update_fields=['is_active'])

    assert api_client.get(path).status_code == 403


def test_a_membership_deleted_after_sign_in_stops_the_next_write(
    api_client, household_a, child_a
):
    sign_in(api_client, child_a)
    Membership.objects.filter(household=household_a, user=child_a).delete()

    response = choose(api_client, 'dragon')

    assert response.status_code == 403
    assert CreatureSelection.objects.count() == 0


@pytest.mark.parametrize(
    ('path', 'method'),
    [
        (CREATURE_PATH, 'put'),
        (CREATURE_PATH, 'patch'),
        (CREATURE_PATH, 'delete'),
        (LINES_PATH, 'post'),
        (LINES_PATH, 'delete'),
    ],
)
def test_an_unsupported_method_is_refused_the_same_way_for_everyone(
    api_client, child_a, path, method
):
    sign_in(api_client, child_a)
    handler = getattr(api_client, method)

    response = handler(path, {}, format='json', headers=csrf_header(api_client))

    assert response.status_code == 405


def test_the_read_route_writes_nothing(api_client, child_a):
    sign_in(api_client, child_a)

    api_client.get(CREATURE_PATH)
    api_client.get(LINES_PATH)

    assert CreatureSelection.objects.count() == 0
    assert AuditEvent.objects.count() == 0
