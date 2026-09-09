"""Tests for the login-abuse control.

The control counts FAILED login attempts only, 10 a minute and 100 an hour
per client address, so a login that succeeds spends nothing.

Every fixture is synthetic. The rates under test are the configured ones, so
these tests fail if `config/settings.py` ever loosens them silently.
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from django.core.cache import caches
from django.db import connection
from django.test import RequestFactory
from rest_framework.settings import api_settings
from rest_framework.test import APIClient

from chorum_murohc.api.session import (
    LOGIN_FAILED_DETAIL,
    LOGIN_THROTTLED_DETAIL,
    LoginView,
)
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
LOGIN_FAILURE_BODY = {'detail': LOGIN_FAILED_DETAIL}


@pytest.fixture(autouse=True)
def clean_login_throttle(db):
    # The cache is database-backed (issue 128), so clearing it needs the `db`
    # fixture's opt-in even for a test that otherwise touches no model.
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


def post_unparsable_body(api_client):
    """Post a body the endpoint cannot parse, with a valid CSRF token."""
    api_client.get(SESSION_PATH)
    return api_client.post(
        LOGIN_PATH,
        'not json at all',
        content_type='application/json',
        headers={'x-csrftoken': api_client.cookies['csrftoken'].value},
    )


def recorded_attempts(throttle):
    """The attempts stored for the default test client address."""
    request = RequestFactory().post(LOGIN_PATH)
    return caches[LOGIN_THROTTLE_CACHE_ALIAS].get(throttle.get_cache_key(request, None))


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


@pytest.mark.django_db(transaction=True)
def test_two_independent_cache_clients_share_one_counter():
    """The counter a second worker process would see is the same counter.

    `LocMemCache` only ever shared state within one Python process, which is
    exactly how a second worker used to multiply the allowance (issue 128):
    each process's `LoginBurstThrottle` thought it held the whole ten-request
    budget. Two threads each get their own database connection the same way
    two worker processes would, so recording the burst limit's worth of
    failures on one and then asking the other is as close as one machine
    gets to proving two processes share one counter. Guarded to PostgreSQL
    like the sibling concurrency tests in `ledger/tests.py` and
    `identity/test_services.py`: SQLite's default test database is in
    memory, which does not give two threads two independent connections to
    tell apart.
    """
    if connection.vendor != 'postgresql':
        pytest.skip('requires the guarded PostgreSQL target')

    request = RequestFactory().post(LOGIN_PATH, REMOTE_ADDR='198.51.100.201')

    def spend_the_whole_allowance():
        throttle = LoginBurstThrottle()
        for _ in range(BURST_LIMIT):
            throttle.record_failure(request)

    def allowance_left():
        return LoginBurstThrottle().allow_request(request, None)

    with ThreadPoolExecutor(max_workers=1) as first_worker:
        first_worker.submit(spend_the_whole_allowance).result(timeout=15)

    with ThreadPoolExecutor(max_workers=1) as second_worker:
        still_allowed = second_worker.submit(allowance_left).result(timeout=15)

    # The first worker's ten failures are visible to the second: one shared
    # counter, not one each.
    assert still_allowed is False


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


def test_the_eleventh_failure_is_refused_and_the_tenth_is_still_answered(
    api_client, member
):
    for attempt in range(BURST_LIMIT - 1):
        response = post_login(api_client, member.username, SYNTHETIC_OTHER_PASSWORD)
        assert response.status_code == 400, attempt

    tenth = post_login(api_client, member.username, SYNTHETIC_OTHER_PASSWORD)
    eleventh = post_login(api_client, member.username, SYNTHETIC_OTHER_PASSWORD)

    assert tenth.status_code == 400
    assert tenth.json() == LOGIN_FAILURE_BODY
    assert_refused(eleventh)


def test_ten_successful_logins_in_a_row_are_allowed_and_spend_nothing(
    api_client, member
):
    for attempt in range(BURST_LIMIT):
        response = post_login(api_client, member.username, SYNTHETIC_PASSWORD)
        assert response.status_code == 200, attempt
        assert response.json()['is_authenticated'] is True

    # Nothing was counted at all, so the whole allowance is still there.
    assert recorded_attempts(LoginBurstThrottle()) is None
    assert recorded_attempts(LoginSustainedThrottle()) is None
    for attempt in range(BURST_LIMIT):
        response = post_login(api_client, member.username, SYNTHETIC_OTHER_PASSWORD)
        assert response.status_code == 400, attempt


def test_ten_failures_then_one_more_failure_is_refused(api_client, member):
    for attempt in range(BURST_LIMIT):
        response = post_login(api_client, member.username, SYNTHETIC_OTHER_PASSWORD)
        assert response.status_code == 400, attempt

    assert_refused(post_login(api_client, member.username, SYNTHETIC_OTHER_PASSWORD))


def test_ten_failures_then_the_correct_password_is_still_refused(api_client, member):
    for attempt in range(BURST_LIMIT):
        response = post_login(api_client, member.username, SYNTHETIC_OTHER_PASSWORD)
        assert response.status_code == 400, attempt

    refused = post_login(api_client, member.username, SYNTHETIC_PASSWORD)

    # The brake is already engaged, so the correct password never gets tried.
    assert_refused(refused)
    assert api_client.get(SESSION_PATH).json()['is_authenticated'] is False


def test_an_unparsable_body_counts_as_one_failed_attempt(api_client, member):
    for attempt in range(BURST_LIMIT - 1):
        response = post_login(api_client, member.username, SYNTHETIC_OTHER_PASSWORD)
        assert response.status_code == 400, attempt

    unparsable = post_unparsable_body(api_client)

    assert unparsable.status_code == 400
    assert unparsable.json() == LOGIN_FAILURE_BODY
    # It spent the tenth unit, so the next attempt meets the brake.
    assert_refused(post_login(api_client, member.username, SYNTHETIC_PASSWORD))


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
