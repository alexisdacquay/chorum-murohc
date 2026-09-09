"""Tests for `POST /api/v1/auth/pin/` (T031, issue #30).

Every fixture is synthetic. No real credential or PIN appears in the data,
the assertions, or the failure output: `assert_withholds` fails a check
without ever printing the sensitive value it was comparing, exactly as
`chorum_murohc/api/test_session.py` does for a password.

The storage rules, the weak-PIN table, and the lockout arithmetic are proved
once, at the service layer, in `chorum_murohc/identity/test_services.py`.
This module proves the HTTP shape around that service: routing, permissions,
CSRF, household isolation, and that a refusal never discloses more than the
approved contract allows.
"""

import ast
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import resolve, reverse
from rest_framework.test import APIClient

from chorum_murohc.api import pin as pin_module
from chorum_murohc.api.pin import (
    PASSWORD_INCORRECT_DETAIL,
    PIN_FORMAT_DETAIL,
    PIN_WEAK_DETAIL,
    PinView,
)
from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity.models import Household, Membership, ParentPin, User
from chorum_murohc.identity.services import PIN_CHANGE_ACTION, PIN_SET_ACTION

PIN_PATH = '/api/v1/auth/pin/'
SESSION_PATH = '/api/v1/auth/session/'
CSRF_COOKIE = settings.CSRF_COOKIE_NAME

# Synthetic throughout: none of these values is a real account or a real PIN.
SYNTHETIC_PASSWORD = 'synthetic-only-account-password-1'
VALID_PIN = '3947'
OTHER_VALID_PIN = '8156'

PERMISSION_DENIED_BODY_DETAIL = 'You do not have permission to perform this action.'


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


def make_member(household, username, role, password=SYNTHETIC_PASSWORD):
    user = User.objects.create_user(username=username, password=password)
    Membership.objects.create(household=household, user=user, role=role)
    return user


@pytest.fixture
def parent_a(household_a):
    return make_member(household_a, 'synthetic-parent-a', Membership.Role.PARENT)


@pytest.fixture
def other_parent_a(household_a):
    return make_member(household_a, 'synthetic-other-parent-a', Membership.Role.PARENT)


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


def post_pin(api_client, body, *, with_csrf=True):
    headers = csrf_header(api_client) if with_csrf else {}
    return api_client.post(PIN_PATH, body, format='json', headers=headers)


def assert_withholds(text, *sensitive_values):
    """Fail without printing the value if `text` ever discloses one."""
    for sensitive_value in sensitive_values:
        if sensitive_value and sensitive_value in text:
            pytest.fail(
                'The value disclosed a controlled sensitive value; output withheld.',
                pytrace=False,
            )


# What this task is not allowed to introduce


def test_the_pin_api_module_imports_only_the_approved_frameworks():
    source = Path(pin_module.__file__).read_text(encoding='utf-8')
    roots = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            roots.add((node.module or '').split('.')[0])

    assert roots <= {'django', 'rest_framework', 'chorum_murohc'}

    # No token authentication, no cross-origin credential flow, and no
    # browser-stored credential anywhere in the implementation.
    code = source.casefold()
    for absent in ('jwt', 'bearer', 'cors', 'localstorage'):
        assert absent not in code


# Routing


def test_the_route_is_named_and_resolves():
    assert reverse('api_v1:auth-pin') == PIN_PATH
    assert resolve(PIN_PATH).func.cls is PinView


def test_an_unsupported_method_is_refused_before_authority_is_considered(
    api_client, household_a, parent_a
):
    sign_in(api_client, parent_a)

    response = api_client.get(PIN_PATH)

    assert response.status_code == 405
    assert ParentPin.objects.exists() is False


# Permissions: unauthenticated, child, parent


@pytest.mark.django_db
def test_an_unauthenticated_caller_is_denied(api_client):
    response = post_pin(
        api_client, {'current_password': SYNTHETIC_PASSWORD, 'pin': VALID_PIN}
    )

    # DRF answers an anonymous caller with its own generic "not authenticated"
    # detail rather than this package's PERMISSION_DENIED_DETAIL (the same
    # split `test_chores.py` leaves unasserted); the status and the absence of
    # any write are the contract this route owns.
    assert response.status_code == 403
    assert_withholds(response.content.decode(), VALID_PIN, SYNTHETIC_PASSWORD)
    assert ParentPin.objects.exists() is False
    assert AuditEvent.objects.exists() is False


def test_a_child_is_denied_and_writes_no_pin(api_client, household_a, child_a):
    sign_in(api_client, child_a)

    response = post_pin(
        api_client, {'current_password': SYNTHETIC_PASSWORD, 'pin': VALID_PIN}
    )

    assert response.status_code == 403
    assert response.json() == {'detail': PERMISSION_DENIED_BODY_DETAIL}
    assert ParentPin.objects.exists() is False
    assert AuditEvent.objects.exists() is False


def test_csrf_is_enforced_on_this_unsafe_route(api_client, household_a, parent_a):
    sign_in(api_client, parent_a)

    response = post_pin(
        api_client,
        {'current_password': SYNTHETIC_PASSWORD, 'pin': VALID_PIN},
        with_csrf=False,
    )

    assert response.status_code == 403
    assert ParentPin.objects.exists() is False


# Validation


def test_a_wrong_current_password_is_a_compact_generic_refusal(
    api_client, household_a, parent_a
):
    sign_in(api_client, parent_a)

    response = post_pin(
        api_client, {'current_password': 'not-the-real-password', 'pin': VALID_PIN}
    )

    assert response.status_code == 400
    assert response.json() == {'current_password': [PASSWORD_INCORRECT_DETAIL]}
    assert_withholds(
        response.content.decode(),
        SYNTHETIC_PASSWORD,
        VALID_PIN,
        'not-the-real-password',
    )
    assert ParentPin.objects.exists() is False


@pytest.mark.parametrize('bad_pin', ['12a4', '123', '12345678901', ''])
def test_a_malformed_pin_names_the_format_rule(
    api_client, household_a, parent_a, bad_pin
):
    sign_in(api_client, parent_a)

    response = post_pin(
        api_client, {'current_password': SYNTHETIC_PASSWORD, 'pin': bad_pin}
    )

    assert response.status_code == 400
    assert response.json() == {'pin': [PIN_FORMAT_DETAIL]}
    assert ParentPin.objects.exists() is False


@pytest.mark.parametrize('weak_pin', ['1111', '1234', '9876', '1212', '0000'])
def test_a_weak_pin_is_refused_by_one_generic_detail(
    api_client, household_a, parent_a, weak_pin
):
    sign_in(api_client, parent_a)

    response = post_pin(
        api_client, {'current_password': SYNTHETIC_PASSWORD, 'pin': weak_pin}
    )

    assert response.status_code == 400
    assert response.json() == {'pin': [PIN_WEAK_DETAIL]}
    assert ParentPin.objects.exists() is False


def test_missing_fields_are_refused_before_the_service_is_called(
    api_client, household_a, parent_a
):
    sign_in(api_client, parent_a)

    response = post_pin(api_client, {'pin': VALID_PIN})

    assert response.status_code == 400
    assert 'current_password' in response.json()
    assert ParentPin.objects.exists() is False


# Success


def test_a_parent_sets_their_first_pin(api_client, household_a, parent_a):
    sign_in(api_client, parent_a)

    response = post_pin(
        api_client, {'current_password': SYNTHETIC_PASSWORD, 'pin': VALID_PIN}
    )

    assert response.status_code == 204
    assert response.content == b''

    pin_row = ParentPin.objects.get(user=parent_a)
    assert_withholds(pin_row.pin_hash, VALID_PIN)

    event = AuditEvent.objects.get()
    assert event.action == PIN_SET_ACTION
    assert event.actor == parent_a
    assert event.household == household_a
    assert event.context == {}


def test_a_parent_replaces_their_pin(api_client, household_a, parent_a):
    sign_in(api_client, parent_a)
    post_pin(api_client, {'current_password': SYNTHETIC_PASSWORD, 'pin': VALID_PIN})

    response = post_pin(
        api_client, {'current_password': SYNTHETIC_PASSWORD, 'pin': OTHER_VALID_PIN}
    )

    assert response.status_code == 204
    assert ParentPin.objects.filter(user=parent_a).count() == 1
    actions = list(
        AuditEvent.objects.order_by('created_at').values_list('action', flat=True)
    )
    assert actions == [PIN_SET_ACTION, PIN_CHANGE_ACTION]


def test_an_extra_body_field_can_never_target_another_account(
    api_client, household_a, parent_a, other_parent_a
):
    sign_in(api_client, parent_a)

    response = post_pin(
        api_client,
        {
            'current_password': SYNTHETIC_PASSWORD,
            'pin': VALID_PIN,
            'user': other_parent_a.pk,
            'household': household_a.pk + 999,
        },
    )

    assert response.status_code == 204
    assert ParentPin.objects.filter(user=parent_a).exists() is True
    assert ParentPin.objects.filter(user=other_parent_a).exists() is False


# Household isolation: this route only ever touches the caller's own PIN


def test_one_parent_setting_a_pin_never_touches_another_parents_pin(
    api_client, household_a, parent_a, other_parent_a
):
    sign_in(api_client, parent_a)
    post_pin(api_client, {'current_password': SYNTHETIC_PASSWORD, 'pin': VALID_PIN})

    assert ParentPin.objects.filter(user=other_parent_a).exists() is False

    events = list(AuditEvent.objects.filter(action=PIN_SET_ACTION))
    assert len(events) == 1
    assert events[0].actor == parent_a


def test_a_parent_in_another_household_is_wholly_unaffected(
    api_client, household_a, household_b, parent_a, parent_b
):
    sign_in(api_client, parent_a)
    post_pin(api_client, {'current_password': SYNTHETIC_PASSWORD, 'pin': VALID_PIN})

    assert ParentPin.objects.filter(user=parent_b).exists() is False
