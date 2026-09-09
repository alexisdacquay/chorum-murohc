"""Tests for `POST /api/v1/auth/password/` (issue #129).

Every fixture is synthetic. No real credential appears in the data, the
assertions, or the failure output: `assert_withholds` fails a check without
ever printing the sensitive value it was comparing, exactly as
`chorum_murohc/api/test_pin.py` does.

The password-change storage rule is proved once, at the service layer, in
`chorum_murohc/identity/test_services.py`. This module proves the HTTP shape
around that service: routing, permissions, CSRF, and that a refusal never
discloses more than the approved contract allows.
"""

import ast
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import resolve, reverse
from rest_framework.test import APIClient

from chorum_murohc.api import password as password_module
from chorum_murohc.api.password import PASSWORD_INCORRECT_DETAIL, PasswordChangeView
from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity.models import Household, Membership, User
from chorum_murohc.identity.services import PASSWORD_CHANGE_ACTION

PASSWORD_PATH = '/api/v1/auth/password/'
SESSION_PATH = '/api/v1/auth/session/'
CSRF_COOKIE = settings.CSRF_COOKIE_NAME

# Synthetic throughout: none of these values is a real account credential.
SYNTHETIC_PASSWORD = 'synthetic-only-account-password-1'
NEW_PASSWORD = 'a genuinely unusual passphrase 42'

PERMISSION_DENIED_BODY_DETAIL = 'You do not have permission to perform this action.'


@pytest.fixture
def api_client():
    # Browser-realistic: CSRF is enforced exactly as it is in production.
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def household_a(db):
    return Household.objects.create(name='Synthetic Household A')


def make_member(household, username, role, password=SYNTHETIC_PASSWORD):
    user = User.objects.create_user(username=username, password=password)
    Membership.objects.create(household=household, user=user, role=role)
    return user


@pytest.fixture
def parent_a(household_a):
    return make_member(household_a, 'synthetic-parent-a', Membership.Role.PARENT)


@pytest.fixture
def child_a(household_a):
    return make_member(household_a, 'synthetic-child-a', Membership.Role.CHILD)


def sign_in(api_client, user):
    """Give the client a live session and the CSRF cookie a browser holds."""
    api_client.force_login(user)
    api_client.get(SESSION_PATH)
    return api_client


def csrf_header(api_client):
    cookie = api_client.cookies.get(CSRF_COOKIE)
    return {'x-csrftoken': cookie.value} if cookie is not None else {}


def post_password(api_client, body, *, with_csrf=True):
    headers = csrf_header(api_client) if with_csrf else {}
    return api_client.post(PASSWORD_PATH, body, format='json', headers=headers)


def assert_withholds(text, *sensitive_values):
    """Fail without printing the value if `text` ever discloses one."""
    for sensitive_value in sensitive_values:
        if sensitive_value and sensitive_value in text:
            pytest.fail(
                'The value disclosed a controlled sensitive value; output withheld.',
                pytrace=False,
            )


# What this task is not allowed to introduce


def test_the_password_api_module_imports_only_the_approved_frameworks():
    source = Path(password_module.__file__).read_text(encoding='utf-8')
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
    assert reverse('api_v1:auth-password') == PASSWORD_PATH
    assert resolve(PASSWORD_PATH).func.cls is PasswordChangeView


def test_an_unsupported_method_is_refused_before_authority_is_considered(
    api_client, household_a, parent_a
):
    sign_in(api_client, parent_a)

    response = api_client.get(PASSWORD_PATH)

    assert response.status_code == 405
    parent_a.refresh_from_db()
    assert parent_a.check_password(SYNTHETIC_PASSWORD) is True


# Permissions: unauthenticated, child, parent


@pytest.mark.django_db
def test_an_unauthenticated_caller_is_denied(api_client):
    response = post_password(
        api_client,
        {'current_password': SYNTHETIC_PASSWORD, 'new_password': NEW_PASSWORD},
    )

    assert response.status_code == 403
    assert_withholds(response.content.decode(), SYNTHETIC_PASSWORD, NEW_PASSWORD)
    assert AuditEvent.objects.exists() is False


def test_a_child_is_denied_and_their_password_is_unchanged(
    api_client, household_a, child_a
):
    sign_in(api_client, child_a)

    response = post_password(
        api_client,
        {'current_password': SYNTHETIC_PASSWORD, 'new_password': NEW_PASSWORD},
    )

    assert response.status_code == 403
    assert response.json() == {'detail': PERMISSION_DENIED_BODY_DETAIL}
    child_a.refresh_from_db()
    assert child_a.check_password(SYNTHETIC_PASSWORD) is True
    assert AuditEvent.objects.exists() is False


def test_csrf_is_enforced_on_this_unsafe_route(api_client, household_a, parent_a):
    sign_in(api_client, parent_a)

    response = post_password(
        api_client,
        {'current_password': SYNTHETIC_PASSWORD, 'new_password': NEW_PASSWORD},
        with_csrf=False,
    )

    assert response.status_code == 403
    parent_a.refresh_from_db()
    assert parent_a.check_password(SYNTHETIC_PASSWORD) is True


# Validation


def test_a_wrong_current_password_is_a_compact_generic_refusal(
    api_client, household_a, parent_a
):
    sign_in(api_client, parent_a)

    response = post_password(
        api_client,
        {'current_password': 'not-the-real-password', 'new_password': NEW_PASSWORD},
    )

    assert response.status_code == 400
    assert response.json() == {'current_password': [PASSWORD_INCORRECT_DETAIL]}
    assert_withholds(
        response.content.decode(),
        SYNTHETIC_PASSWORD,
        NEW_PASSWORD,
        'not-the-real-password',
    )
    parent_a.refresh_from_db()
    assert parent_a.check_password(SYNTHETIC_PASSWORD) is True


@pytest.mark.parametrize('weak_password', ('short', 'password', '11111111'))
def test_a_weak_new_password_names_the_validator_reason(
    api_client, household_a, parent_a, weak_password
):
    sign_in(api_client, parent_a)

    response = post_password(
        api_client,
        {'current_password': SYNTHETIC_PASSWORD, 'new_password': weak_password},
    )

    assert response.status_code == 400
    assert 'new_password' in response.json()
    parent_a.refresh_from_db()
    assert parent_a.check_password(SYNTHETIC_PASSWORD) is True


def test_missing_fields_are_refused_before_the_service_is_called(
    api_client, household_a, parent_a
):
    sign_in(api_client, parent_a)

    response = post_password(api_client, {'new_password': NEW_PASSWORD})

    assert response.status_code == 400
    assert 'current_password' in response.json()
    parent_a.refresh_from_db()
    assert parent_a.check_password(SYNTHETIC_PASSWORD) is True


# Success


def test_a_parent_changes_their_own_password_and_stays_signed_in(
    api_client, household_a, parent_a
):
    sign_in(api_client, parent_a)

    response = post_password(
        api_client,
        {'current_password': SYNTHETIC_PASSWORD, 'new_password': NEW_PASSWORD},
    )

    assert response.status_code == 204
    assert response.content == b''

    parent_a.refresh_from_db()
    assert parent_a.check_password(NEW_PASSWORD) is True
    assert parent_a.check_password(SYNTHETIC_PASSWORD) is False

    # The session is not invalidated by the caller's own change: the next
    # request on the same client still carries an authenticated session.
    follow_up = api_client.get(SESSION_PATH)
    assert follow_up.json()['is_authenticated'] is True

    event = AuditEvent.objects.get()
    assert event.action == PASSWORD_CHANGE_ACTION
    assert event.actor == parent_a
    assert event.household == household_a
    assert event.target_id == str(parent_a.pk)
    assert event.context == {}


def test_an_extra_body_field_can_never_target_another_account(
    api_client, household_a, parent_a
):
    other = make_member(household_a, 'synthetic-other-parent', Membership.Role.PARENT)
    sign_in(api_client, parent_a)

    response = post_password(
        api_client,
        {
            'current_password': SYNTHETIC_PASSWORD,
            'new_password': NEW_PASSWORD,
            'user': other.pk,
            'household': household_a.pk + 999,
        },
    )

    assert response.status_code == 204
    other.refresh_from_db()
    assert other.check_password(SYNTHETIC_PASSWORD) is True
