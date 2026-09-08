"""Tests for the login-abuse control.

Every fixture is synthetic. The rates under test are the configured ones, so
these tests fail if `config/settings.py` ever loosens them silently.
"""

import pytest
from django.core.cache import caches
from django.test import RequestFactory
from rest_framework.settings import api_settings
from rest_framework.test import APIClient

from chorum_murohc.api.session import LOGIN_THROTTLED_DETAIL, LoginView
from chorum_murohc.api.throttling import (
    LOGIN_THROTTLE_CACHE_ALIAS,
    LoginBurstThrottle,
    LoginSustainedThrottle,
)
from chorum_murohc.identity.models import User

LOGIN_PATH = '/api/v1/auth/login/'
SESSION_PATH = '/api/v1/auth/session/'
HEALTH_PATH = '/api/v1/health/'

SYNTHETIC_PASSWORD = 'synthetic-login-value-1'
SYNTHETIC_OTHER_PASSWORD = 'synthetic-login-value-2'

BURST_LIMIT = 10
THROTTLED_BODY = {'detail': LOGIN_THROTTLED_DETAIL}


@pytest.fixture(autouse=True)
def clean_login_throttle():
    caches[LOGIN_THROTTLE_CACHE_ALIAS].clear()
    yield
    caches[LOGIN_THROTTLE_CACHE_ALIAS].clear()


@pytest.fixture
def api_client():
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def member(db):
    return User.objects.create_user(
        username='synthetic-member',
        password=SYNTHETIC_PASSWORD,
    )


def post_login(api_client, username, password, extra_headers=None):
    api_client.get(SESSION_PATH)
    headers = {'x-csrftoken': api_client.cookies['csrftoken'].value}
    headers.update(extra_headers or {})
    return api_client.post(
        LOGIN_PATH,
        {'username': username, 'password': password},
        format='json',
        headers=headers,
    )


def assert_refused(response):
    assert response.status_code == 429
    assert response.json() == THROTTLED_BODY
    # No wait hint and no account hint of any kind.
    assert 'Retry-After' not in response.headers
    assert not any(character.isdigit() for character in response.content.decode())


# The configured control.


def test_both_scopes_use_the_configured_rates():
    assert LoginBurstThrottle.scope == 'login_burst'
    assert LoginSustainedThrottle.scope == 'login_sustained'
    assert LoginBurstThrottle().rate == '10/minute'
    assert LoginSustainedThrottle().rate == '100/hour'
    assert LoginBurstThrottle().num_requests == BURST_LIMIT
    assert LoginSustainedThrottle().num_requests == 100


def test_only_the_login_view_is_throttled():
    assert LoginView.throttle_classes == (
        LoginBurstThrottle,
        LoginSustainedThrottle,
    )
    assert api_settings.DEFAULT_THROTTLE_CLASSES == []


def test_counters_live_in_the_dedicated_cache():
    assert LoginBurstThrottle().cache is caches[LOGIN_THROTTLE_CACHE_ALIAS]
    assert LoginBurstThrottle().cache is not caches['default']


def test_the_cache_key_is_the_client_address_and_never_the_username():
    request = RequestFactory().post(
        LOGIN_PATH,
        {'username': 'synthetic-member', 'password': SYNTHETIC_PASSWORD},
        REMOTE_ADDR='198.51.100.7',
    )

    key = LoginBurstThrottle().get_cache_key(request, None)

    assert key == 'throttle_login_burst_198.51.100.7'
    assert 'synthetic-member' not in key
    assert SYNTHETIC_PASSWORD not in key


# The control in use.


def test_the_eleventh_attempt_is_refused_and_the_tenth_still_authenticates(
    api_client, member
):
    for attempt in range(BURST_LIMIT - 1):
        response = post_login(api_client, member.username, SYNTHETIC_OTHER_PASSWORD)
        assert response.status_code == 400, attempt

    allowed = post_login(api_client, member.username, SYNTHETIC_PASSWORD)
    refused = post_login(api_client, member.username, SYNTHETIC_PASSWORD)

    assert allowed.status_code == 200
    assert allowed.json()['is_authenticated'] is True
    assert_refused(refused)


def test_the_refusal_is_identical_for_a_username_that_does_not_exist(
    api_client, member
):
    for _ in range(BURST_LIMIT):
        post_login(api_client, member.username, SYNTHETIC_OTHER_PASSWORD)

    for_known = post_login(api_client, member.username, SYNTHETIC_OTHER_PASSWORD)
    for_unknown = post_login(api_client, 'synthetic-absent-account', SYNTHETIC_PASSWORD)

    assert_refused(for_known)
    assert_refused(for_unknown)
    assert for_known.content == for_unknown.content
    assert for_known.status_code == for_unknown.status_code
    for header in ('Content-Type', 'Allow', 'Vary'):
        assert for_known.headers.get(header) == for_unknown.headers.get(header)


def test_a_forged_forwarding_header_buys_no_fresh_allowance(api_client, member):
    for _ in range(BURST_LIMIT):
        post_login(api_client, member.username, SYNTHETIC_OTHER_PASSWORD)

    forged = post_login(
        api_client,
        member.username,
        SYNTHETIC_OTHER_PASSWORD,
        extra_headers={'x-forwarded-for': '198.51.100.42'},
    )

    assert_refused(forged)


def test_a_second_client_address_keeps_its_own_allowance(api_client, member):
    for _ in range(BURST_LIMIT):
        post_login(api_client, member.username, SYNTHETIC_OTHER_PASSWORD)
    assert_refused(post_login(api_client, member.username, SYNTHETIC_OTHER_PASSWORD))

    elsewhere = APIClient(enforce_csrf_checks=True, REMOTE_ADDR='198.51.100.9')

    response = post_login(elsewhere, member.username, SYNTHETIC_PASSWORD)

    assert response.status_code == 200


def test_inspection_and_health_are_never_throttled(api_client, member):
    for _ in range(BURST_LIMIT + 1):
        post_login(api_client, member.username, SYNTHETIC_OTHER_PASSWORD)

    assert api_client.get(SESSION_PATH).status_code == 200
    assert api_client.get(HEALTH_PATH).status_code == 200
