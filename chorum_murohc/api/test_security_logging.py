"""Tests for the refused-request logging (S-04).

Every fixture is synthetic. No credential, PIN, token, cookie or personal
datum appears in the data, the assertions or the failure output.
"""

import logging

import pytest
from django.conf import settings
from rest_framework.exceptions import (
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory

from chorum_murohc.api.security_logging import (
    REFUSAL_STATUS_CODES,
    logging_exception_handler,
)
from chorum_murohc.api.session import LOGIN_FAILED_DETAIL
from chorum_murohc.identity.models import Household, Membership, User

LOGGER_NAME = 'chorum_murohc.security'
LOGIN_PATH = '/api/v1/auth/login/'
SESSION_PATH = '/api/v1/auth/session/'
AUDIT_PATH = '/api/v1/audit/'
CHORE_LIST_PATH = '/api/v1/chores/'
CSRF_COOKIE = settings.CSRF_COOKIE_NAME

SYNTHETIC_OTHER_PASSWORD = 'synthetic-login-value-2'

factory = APIRequestFactory()


def drf_request(path='/api/v1/example/'):
    return Request(factory.get(path))


@pytest.mark.parametrize(
    ('exc', 'expected_status'),
    [
        (PermissionDenied(), 403),
        (NotAuthenticated(), 401),
        (Throttled(wait=None), 429),
    ],
)
def test_every_refusal_status_is_logged_exactly_once(caplog, exc, expected_status):
    assert expected_status in REFUSAL_STATUS_CODES

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        response = logging_exception_handler(exc, {'request': drf_request()})

    assert response.status_code == expected_status
    records = [r for r in caplog.records if r.name == LOGGER_NAME]
    assert len(records) == 1
    message = records[0].getMessage()
    assert type(exc).__name__ in message
    assert str(expected_status) in message
    assert 'GET' in message
    assert '/api/v1/example/' in message


@pytest.mark.parametrize('exc', [ValidationError('bad input'), NotFound()])
def test_a_non_refusal_response_is_not_logged(caplog, exc):
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        response = logging_exception_handler(exc, {'request': drf_request()})

    assert response.status_code not in REFUSAL_STATUS_CODES
    assert [r for r in caplog.records if r.name == LOGGER_NAME] == []


def test_an_unhandled_exception_type_logs_nothing_and_returns_none(caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        response = logging_exception_handler(
            RuntimeError('boom'), {'request': drf_request()}
        )

    assert response is None
    assert [r for r in caplog.records if r.name == LOGGER_NAME] == []


# Full-stack coverage: the real endpoints, not a synthetic exception.


@pytest.fixture
def api_client():
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def household(db):
    return Household.objects.create(name='Synthetic Household')


@pytest.fixture
def parent(household):
    user = User.objects.create_user(username='synthetic-parent')
    Membership.objects.create(
        household=household, user=user, role=Membership.Role.PARENT
    )
    return user


@pytest.fixture
def child(household):
    user = User.objects.create_user(username='synthetic-child')
    Membership.objects.create(
        household=household, user=user, role=Membership.Role.CHILD
    )
    return user


def bootstrap_csrf(api_client):
    api_client.get(SESSION_PATH)
    return api_client.cookies[CSRF_COOKIE].value


def sign_in(api_client, user):
    api_client.force_login(user)
    api_client.get(SESSION_PATH)
    return api_client


def security_records(caplog):
    return [r for r in caplog.records if r.name == LOGGER_NAME]


def test_a_refused_login_emits_one_non_secret_log_record(api_client, db, caplog):
    """The regression test the audit names for S-04."""
    username = 'synthetic-absent-account'

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        response = api_client.post(
            LOGIN_PATH,
            {'username': username, 'password': SYNTHETIC_OTHER_PASSWORD},
            format='json',
            headers={'x-csrftoken': bootstrap_csrf(api_client)},
        )

    assert response.status_code == 400
    assert response.json() == {'detail': LOGIN_FAILED_DETAIL}

    records = security_records(caplog)
    assert len(records) == 1
    message = records[0].getMessage()
    assert 'login_failed' in message
    assert 'POST' in message
    assert LOGIN_PATH in message
    assert '400' in message
    # Nothing the caller submitted, and nothing Django derives from it,
    # reaches the log line.
    assert username not in message
    assert SYNTHETIC_OTHER_PASSWORD not in message
    for record in caplog.records:
        assert username not in record.getMessage()
        assert SYNTHETIC_OTHER_PASSWORD not in record.getMessage()


def test_a_cross_role_permission_denial_is_logged(api_client, child, caplog):
    sign_in(api_client, child)

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        response = api_client.get(AUDIT_PATH)

    assert response.status_code == 403
    records = security_records(caplog)
    assert len(records) == 1
    message = records[0].getMessage()
    assert 'PermissionDenied' in message
    assert AUDIT_PATH in message
    assert '403' in message


def test_a_signed_out_caller_is_logged(api_client, caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        response = api_client.get(CHORE_LIST_PATH)

    assert response.status_code == 403
    records = security_records(caplog)
    assert len(records) == 1
    assert 'NotAuthenticated' in records[0].getMessage()


def test_a_missing_csrf_token_on_an_authenticated_write_is_logged(
    api_client, parent, caplog
):
    sign_in(api_client, parent)

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        response = api_client.post(
            CHORE_LIST_PATH,
            {'name': 'Synthetic chore', 'points': 5},
            format='json',
        )

    assert response.status_code == 403
    records = security_records(caplog)
    assert len(records) == 1
    message = records[0].getMessage()
    assert 'PermissionDenied' in message
    assert CHORE_LIST_PATH in message


def test_a_successful_request_logs_nothing(api_client, parent, caplog):
    sign_in(api_client, parent)

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        response = api_client.get(CHORE_LIST_PATH)

    assert response.status_code == 200
    assert security_records(caplog) == []
