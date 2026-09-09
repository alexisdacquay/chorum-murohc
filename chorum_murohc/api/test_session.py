"""Tests for the session endpoints.

Every fixture is synthetic. No real credential, PIN, token, or personal datum
appears in the data, the assertions, or the failure output, and any check that
could print a controlled sensitive value fails with the value withheld instead
of asserting on it directly.
"""

import ast
import io
import tokenize
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore
from django.core.cache import caches
from django.urls import resolve, reverse
from rest_framework.test import APIClient

from chorum_murohc.api import serializers as serializers_module
from chorum_murohc.api import session as session_module
from chorum_murohc.api import throttling as throttling_module
from chorum_murohc.api.session import (
    LOGIN_FAILED_DETAIL,
    SIGNED_OUT_SESSION,
    LoginView,
    LogoutView,
    SessionView,
    current_session,
    resolve_active_membership,
)
from chorum_murohc.api.throttling import LOGIN_THROTTLE_CACHE_ALIAS
from chorum_murohc.identity.models import Household, Membership, User

SESSION_PATH = '/api/v1/auth/session/'
LOGIN_PATH = '/api/v1/auth/login/'
LOGOUT_PATH = '/api/v1/auth/logout/'
HEALTH_PATH = '/api/v1/health/'

SESSION_COOKIE = settings.SESSION_COOKIE_NAME
CSRF_COOKIE = settings.CSRF_COOKIE_NAME

# Synthetic throughout: these values exist only inside this test module.
SYNTHETIC_PASSWORD = 'synthetic-login-value-1'
SYNTHETIC_OTHER_PASSWORD = 'synthetic-login-value-2'

LOGIN_FAILURE_BODY = {'detail': LOGIN_FAILED_DETAIL}
NOT_AUTHENTICATED_BODY = {'detail': 'Authentication credentials were not provided.'}

# Nothing in this list may ever appear in a session or login body.
FORBIDDEN_BODY_TEXT = (
    'email',
    'example.invalid',
    'staff',
    'superuser',
    'password',
    'csrf',
    'sessionid',
    'last_login',
    'permission',
)


@pytest.fixture(autouse=True)
def clean_login_throttle(db):
    """Keep the throttle counters out of neighbouring tests.

    The cache is database-backed (issue 128), so clearing it needs the `db`
    fixture's opt-in even for a test that otherwise touches no model.
    """
    caches[LOGIN_THROTTLE_CACHE_ALIAS].clear()
    yield
    caches[LOGIN_THROTTLE_CACHE_ALIAS].clear()


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


@pytest.fixture
def member(db):
    return User.objects.create_user(
        username='synthetic-member',
        password=SYNTHETIC_PASSWORD,
    )


def bootstrap_csrf(api_client):
    """Fetch the CSRF cookie the way a browser does, with one safe GET."""
    api_client.get(SESSION_PATH)
    return api_client.cookies[CSRF_COOKIE].value


def post_login(api_client, username, password):
    return api_client.post(
        LOGIN_PATH,
        {'username': username, 'password': password},
        format='json',
        headers={'x-csrftoken': bootstrap_csrf(api_client)},
    )


def post_logout(api_client):
    return api_client.post(
        LOGOUT_PATH,
        headers={'x-csrftoken': bootstrap_csrf(api_client)},
    )


def sign_in(api_client, user, password=SYNTHETIC_PASSWORD):
    response = post_login(api_client, user.get_username(), password)
    assert response.status_code == 200
    return response


def authenticated_body(user, household=None, role=None):
    resolved = None
    if household is not None:
        resolved = {'id': household.pk, 'name': household.name}
    return {
        'is_authenticated': True,
        'user': {'id': user.pk, 'username': user.get_username()},
        'household': resolved,
        'role': role,
    }


def cookie_value(api_client, name):
    cookie = api_client.cookies.get(name)
    return cookie.value if cookie is not None else ''


def assert_no_session(api_client):
    assert not cookie_value(api_client, SESSION_COOKIE)


def assert_withholds(response, *sensitive_values):
    """Fail without printing the value if a response ever discloses one."""
    body = response.content.decode()
    headers = ' '.join(f'{name}: {value}' for name, value in response.headers.items())
    for sensitive_value in sensitive_values:
        if sensitive_value and (sensitive_value in body or sensitive_value in headers):
            pytest.fail(
                'The response disclosed a controlled sensitive value; output withheld.',
                pytrace=False,
            )


# What this task is not allowed to introduce.


def code_without_prose(source):
    """The source with its comments and docstrings removed."""
    docstrings = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef):
            docstring = ast.get_docstring(node, clean=False)
            if docstring:
                docstrings.append(docstring)

    code = ''.join(
        token.string
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type != tokenize.COMMENT
    )
    for docstring in docstrings:
        code = code.replace(docstring, '')
    return code.casefold()


def test_the_session_modules_import_only_the_approved_frameworks():
    for module in (session_module, serializers_module, throttling_module):
        source = Path(module.__file__).read_text(encoding='utf-8')
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
        code = code_without_prose(source)
        for absent in ('jwt', 'bearer', 'authorization', 'cors', 'localstorage'):
            assert absent not in code


# Routing.


def test_auth_urls_are_namespaced_and_resolve_to_their_own_views():
    for name, path, view in (
        ('api_v1:auth-session', SESSION_PATH, SessionView),
        ('api_v1:auth-login', LOGIN_PATH, LoginView),
        ('api_v1:auth-logout', LOGOUT_PATH, LogoutView),
    ):
        assert reverse(name) == path
        assert resolve(path).func.cls is view

    # The route this task inherited is untouched.
    assert reverse('api_v1:health') == HEALTH_PATH


# Session inspection.


def test_unauthenticated_inspection_is_signed_out_and_delivers_the_csrf_cookie(
    api_client,
):
    response = api_client.get(SESSION_PATH)

    assert response.status_code == 200
    assert response.json() == SIGNED_OUT_SESSION
    assert response.json() == {
        'is_authenticated': False,
        'user': None,
        'household': None,
        'role': None,
    }
    # The CSRF bootstrap: the cookie is set, and script must be able to read
    # it so that the interface can echo the value back on an unsafe call.
    assert CSRF_COOKIE in response.cookies
    assert response.cookies[CSRF_COOKIE].value
    assert not response.cookies[CSRF_COOKIE]['httponly']
    assert response.cookies[CSRF_COOKIE]['samesite'] == 'Lax'
    # Looking at the signed-out surface creates no session at all.
    assert SESSION_COOKIE not in response.cookies
    assert_withholds(response, response.cookies[CSRF_COOKIE].value)


@pytest.mark.parametrize(
    'role',
    [Membership.Role.PARENT, Membership.Role.CHILD],
)
def test_one_membership_yields_that_household_and_that_role(
    api_client, household_a, member, role
):
    Membership.objects.create(household=household_a, user=member, role=role)

    sign_in(api_client, member)
    response = api_client.get(SESSION_PATH)

    assert response.status_code == 200
    assert response.json() == authenticated_body(member, household_a, role.value)
    assert response.json()['role'] in {'parent', 'child'}


def test_no_body_carries_a_field_beyond_the_four_named(api_client, household_a, member):
    member.email = 'synthetic-member@example.invalid'
    member.is_staff = True
    member.is_superuser = True
    member.save()
    Membership.objects.create(
        household=household_a,
        user=member,
        role=Membership.Role.PARENT,
    )

    login = sign_in(api_client, member)
    inspection = api_client.get(SESSION_PATH)

    for response in (login, inspection):
        body = response.json()
        assert set(body) == {'is_authenticated', 'user', 'household', 'role'}
        assert set(body['user']) == {'id', 'username'}
        assert set(body['household']) == {'id', 'name'}

        text = response.content.decode().casefold()
        for forbidden in FORBIDDEN_BODY_TEXT:
            assert forbidden not in text

        assert_withholds(
            response,
            SYNTHETIC_PASSWORD,
            cookie_value(api_client, SESSION_COOKIE),
            cookie_value(api_client, CSRF_COOKIE),
        )


def test_login_response_matches_the_inspection_response(
    api_client, household_a, member
):
    Membership.objects.create(
        household=household_a,
        user=member,
        role=Membership.Role.PARENT,
    )

    login = sign_in(api_client, member)

    assert login.json() == api_client.get(SESSION_PATH).json()


# Signing in.


def test_valid_login_authenticates_and_rotates_the_session_identifier(
    api_client, household_a, member
):
    Membership.objects.create(
        household=household_a,
        user=member,
        role=Membership.Role.PARENT,
    )
    stale = SessionStore()
    stale['synthetic'] = 'value'
    stale.save()
    api_client.cookies[SESSION_COOKIE] = stale.session_key

    response = post_login(api_client, member.username, SYNTHETIC_PASSWORD)

    assert response.status_code == 200
    assert response.json() == authenticated_body(member, household_a, 'parent')
    rotated = cookie_value(api_client, SESSION_COOKIE)
    assert rotated
    assert rotated != stale.session_key
    # The identifier the caller arrived with is destroyed, not reused.
    assert not SessionStore().exists(stale.session_key)


@pytest.mark.parametrize(
    'failure',
    ['wrong_password', 'unknown_username', 'inactive_user'],
)
def test_every_credential_failure_shares_one_generic_detail(
    api_client, member, failure
):
    username = member.username
    password = SYNTHETIC_PASSWORD
    if failure == 'wrong_password':
        password = SYNTHETIC_OTHER_PASSWORD
    elif failure == 'unknown_username':
        username = 'synthetic-absent-account'
    else:
        member.is_active = False
        member.save()

    response = post_login(api_client, username, password)

    assert response.status_code == 400
    assert response.json() == LOGIN_FAILURE_BODY
    assert_no_session(api_client)
    assert api_client.get(SESSION_PATH).json() == SIGNED_OUT_SESSION
    assert username not in response.content.decode()
    assert_withholds(response, SYNTHETIC_PASSWORD, SYNTHETIC_OTHER_PASSWORD)


@pytest.mark.parametrize(
    'body',
    [
        {},
        {'username': 'synthetic-member'},
        {'password': SYNTHETIC_PASSWORD},
        {'username': '', 'password': ''},
        [],
    ],
    ids=['empty', 'no-password', 'no-username', 'blank', 'not-an-object'],
)
def test_a_malformed_body_gets_the_same_generic_failure(api_client, member, body):
    response = api_client.post(
        LOGIN_PATH,
        body,
        format='json',
        headers={'x-csrftoken': bootstrap_csrf(api_client)},
    )

    assert response.status_code == 400
    assert response.json() == LOGIN_FAILURE_BODY
    assert_no_session(api_client)


def test_unparsable_json_gets_the_same_generic_failure(api_client, member):
    response = api_client.post(
        LOGIN_PATH,
        'not json at all',
        content_type='application/json',
        headers={'x-csrftoken': bootstrap_csrf(api_client)},
    )

    assert response.status_code == 400
    assert response.json() == LOGIN_FAILURE_BODY
    assert_no_session(api_client)


def test_a_client_authored_role_is_ignored(api_client, household_a, member):
    Membership.objects.create(
        household=household_a,
        user=member,
        role=Membership.Role.CHILD,
    )

    response = api_client.post(
        LOGIN_PATH,
        {
            'username': member.username,
            'password': SYNTHETIC_PASSWORD,
            'role': 'parent',
            'household': household_a.pk,
        },
        format='json',
        headers={'x-csrftoken': bootstrap_csrf(api_client)},
    )

    # The claim is never authority: the stored membership decides.
    assert response.status_code == 200
    assert response.json() == authenticated_body(member, household_a, 'child')


def test_login_without_a_valid_csrf_token_is_refused(api_client, member):
    bootstrap_csrf(api_client)

    for headers in ({}, {'x-csrftoken': 'synthetic-invalid-token'}):
        response = api_client.post(
            LOGIN_PATH,
            {'username': member.username, 'password': SYNTHETIC_PASSWORD},
            format='json',
            headers=headers,
        )

        assert response.status_code == 403
        assert_no_session(api_client)
        assert api_client.get(SESSION_PATH).json() == SIGNED_OUT_SESSION
        assert_withholds(response, SYNTHETIC_PASSWORD)


# Signing out.


def test_logout_ends_the_session_and_returns_no_content(
    api_client, household_a, member
):
    Membership.objects.create(
        household=household_a,
        user=member,
        role=Membership.Role.PARENT,
    )
    sign_in(api_client, member)
    signed_in_key = cookie_value(api_client, SESSION_COOKIE)

    response = post_logout(api_client)

    assert response.status_code == 204
    assert response.content == b''
    assert api_client.get(SESSION_PATH).json() == SIGNED_OUT_SESSION
    assert not SessionStore().exists(signed_in_key)


def test_logout_without_a_valid_csrf_token_leaves_the_session_working(
    api_client, household_a, member
):
    Membership.objects.create(
        household=household_a,
        user=member,
        role=Membership.Role.PARENT,
    )
    sign_in(api_client, member)

    response = api_client.post(LOGOUT_PATH)

    assert response.status_code == 403
    assert api_client.get(SESSION_PATH).json() == authenticated_body(
        member, household_a, 'parent'
    )


def test_unauthenticated_logout_is_refused_and_reveals_nothing(api_client):
    response = api_client.post(
        LOGOUT_PATH,
        headers={'x-csrftoken': bootstrap_csrf(api_client)},
    )

    assert response.status_code == 403
    assert response.json() == NOT_AUTHENTICATED_BODY
    assert_no_session(api_client)


def test_a_deactivated_user_cannot_log_out_either(api_client, member):
    sign_in(api_client, member)
    User.objects.filter(pk=member.pk).update(is_active=False)

    response = post_logout(api_client)

    assert response.status_code == 403
    assert api_client.get(SESSION_PATH).json() == SIGNED_OUT_SESSION


# Safe methods never change state.


def test_safe_methods_on_login_and_logout_change_nothing(
    api_client, household_a, member
):
    Membership.objects.create(
        household=household_a,
        user=member,
        role=Membership.Role.PARENT,
    )
    bootstrap_csrf(api_client)

    for path in (LOGIN_PATH, LOGOUT_PATH):
        for method in (api_client.get, api_client.head):
            # Anonymous: nothing logs in, and no session appears.
            response = method(path)
            assert response.status_code == 405
            assert_no_session(api_client)

    sign_in(api_client, member)

    # Authenticated: the method is refused before any handler runs, and the
    # answer does not depend on who is asking.
    for path in (LOGIN_PATH, LOGOUT_PATH):
        response = api_client.get(path)
        assert response.status_code == 405
        assert api_client.get(SESSION_PATH).json() == authenticated_body(
            member, household_a, 'parent'
        )


def test_a_refused_method_names_only_the_methods_the_endpoint_supports(api_client):
    bootstrap_csrf(api_client)

    for path in (LOGIN_PATH, LOGOUT_PATH):
        response = api_client.get(path)

        assert response.status_code == 405
        assert response.json() == {'detail': 'Method "GET" not allowed.'}
        assert {method.strip() for method in response.headers['Allow'].split(',')} == {
            'POST',
            'OPTIONS',
        }
        assert_no_session(api_client)


def test_the_inspection_endpoint_accepts_only_safe_methods(api_client, member):
    token = bootstrap_csrf(api_client)

    for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        response = api_client.generic(
            method,
            SESSION_PATH,
            data=b'{}',
            content_type='application/json',
            headers={'x-csrftoken': token},
        )

        assert response.status_code == 405
        assert_no_session(api_client)

    assert api_client.head(SESSION_PATH).status_code == 200


# Household resolution fails closed.


def test_zero_memberships_still_signs_in_with_null_household_and_role(
    api_client, member
):
    response = sign_in(api_client, member)

    assert response.json() == authenticated_body(member)
    assert api_client.get(SESSION_PATH).json() == authenticated_body(member)


def test_a_membership_in_two_households_resolves_to_nothing(
    api_client, household_a, household_b, member
):
    Membership.objects.create(
        household=household_a,
        user=member,
        role=Membership.Role.PARENT,
    )
    Membership.objects.create(
        household=household_b,
        user=member,
        role=Membership.Role.CHILD,
    )

    response = sign_in(api_client, member)

    # Ambiguous context denies, and the two roles are never unioned.
    assert response.json() == authenticated_body(member)
    body = response.content.decode()
    assert household_a.name not in body
    assert household_b.name not in body
    assert 'parent' not in body
    assert 'child' not in body


def test_a_deleted_membership_takes_effect_on_the_next_request(
    api_client, household_a, member
):
    membership = Membership.objects.create(
        household=household_a,
        user=member,
        role=Membership.Role.PARENT,
    )
    sign_in(api_client, member)
    assert api_client.get(SESSION_PATH).json()['role'] == 'parent'

    membership.delete()

    # No new sign-in, and no cached authority: the same session sees nulls.
    assert api_client.get(SESSION_PATH).json() == authenticated_body(member)


def test_a_changed_role_takes_effect_on_the_next_request(
    api_client, household_a, member
):
    membership = Membership.objects.create(
        household=household_a,
        user=member,
        role=Membership.Role.PARENT,
    )
    sign_in(api_client, member)
    assert api_client.get(SESSION_PATH).json()['role'] == 'parent'

    Membership.objects.filter(pk=membership.pk).update(role=Membership.Role.CHILD)

    assert api_client.get(SESSION_PATH).json() == authenticated_body(
        member, household_a, 'child'
    )


def test_a_deactivated_user_is_signed_out_on_the_next_request(
    api_client, household_a, member
):
    Membership.objects.create(
        household=household_a,
        user=member,
        role=Membership.Role.PARENT,
    )
    sign_in(api_client, member)

    User.objects.filter(pk=member.pk).update(is_active=False)

    assert api_client.get(SESSION_PATH).json() == SIGNED_OUT_SESSION


def test_another_households_membership_is_never_borrowed(
    api_client, household_a, household_b, member, db
):
    other = User.objects.create_user(
        username='synthetic-other-member',
        password=SYNTHETIC_OTHER_PASSWORD,
    )
    Membership.objects.create(
        household=household_b,
        user=other,
        role=Membership.Role.PARENT,
    )
    Membership.objects.create(
        household=household_a,
        user=member,
        role=Membership.Role.CHILD,
    )

    response = sign_in(api_client, member)

    assert response.json() == authenticated_body(member, household_a, 'child')
    assert household_b.name not in response.content.decode()


# The resolver on its own.


def test_resolver_returns_the_single_live_membership(household_a, member):
    membership = Membership.objects.create(
        household=household_a,
        user=member,
        role=Membership.Role.PARENT,
    )

    assert resolve_active_membership(member) == membership


@pytest.mark.parametrize('role', [Membership.Role.PARENT, Membership.Role.CHILD])
def test_resolver_accepts_both_supported_roles(household_a, member, role):
    Membership.objects.create(household=household_a, user=member, role=role)

    resolved = resolve_active_membership(member)

    assert resolved is not None
    assert resolved.role == role.value


def test_resolver_fails_closed_for_an_unsupported_role(household_a, member):
    Membership.objects.create(
        household=household_a,
        user=member,
        role=Membership.Role.PARENT,
    )
    # The database constraint stops such a row from ever being stored, so the
    # role has to be forced here to prove the second line of the check.
    unsupported = SimpleNamespace(household=household_a, role='guardian')

    with patch.object(
        session_module,
        'resolve_membership',
        return_value=unsupported,
    ):
        assert resolve_active_membership(member) is None
        assert current_session(member) == authenticated_body(member)


def test_resolver_fails_closed_for_every_state_that_is_not_one_membership(
    household_a, household_b, member
):
    # Zero memberships.
    assert resolve_active_membership(member) is None

    Membership.objects.create(
        household=household_a,
        user=member,
        role=Membership.Role.PARENT,
    )
    Membership.objects.create(
        household=household_b,
        user=member,
        role=Membership.Role.CHILD,
    )
    # Two candidate households.
    assert resolve_active_membership(member) is None


def test_resolver_fails_closed_without_an_active_authenticated_user(
    household_a, member
):
    Membership.objects.create(
        household=household_a,
        user=member,
        role=Membership.Role.PARENT,
    )

    assert resolve_active_membership(None) is None
    assert resolve_active_membership(AnonymousUser()) is None
    assert resolve_active_membership(User(username='synthetic-unsaved')) is None

    member.is_active = False
    assert resolve_active_membership(member) is None


def test_current_session_is_the_signed_out_body_without_an_active_user(db):
    assert current_session(None) == SIGNED_OUT_SESSION
    assert current_session(AnonymousUser()) == SIGNED_OUT_SESSION
    assert current_session(User(username='synthetic-unsaved', is_active=False)) == (
        SIGNED_OUT_SESSION
    )
