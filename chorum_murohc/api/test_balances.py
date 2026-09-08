"""Tests for the balance and ledger-history endpoints.

Every fixture is synthetic. No credential, PIN, token, cookie or personal
datum appears in the data, the assertions or the failure output: the test
users are created without a usable password and are signed in through the
session machinery directly, so there is nothing sensitive to print.

The awkward cases the permission matrix names are covered for both routes:
unauthenticated, an inactive user holding a live session, the allowed role,
the denied role, no resolvable role, an ambiguous two-household caller, a
membership deleted after sign-in, and a cross-household identifier supplied
in the query string.
"""

import ast
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import pytest
from django.conf import settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from rest_framework.test import APIClient

from chorum_murohc.api import balances as balances_module
from chorum_murohc.api.balances import (
    HISTORY_PAGE_SIZE,
    INVALID_PAGE_DETAIL,
    BalanceView,
    LedgerHistoryView,
)
from chorum_murohc.api.permissions import PERMISSION_DENIED_DETAIL
from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity.models import Household, Membership, User
from chorum_murohc.ledger.models import LedgerEntry

BALANCE_PATH = '/api/v1/balance/'
LEDGER_PATH = '/api/v1/ledger/'
SESSION_PATH = '/api/v1/auth/session/'
CSRF_COOKIE = settings.CSRF_COOKIE_NAME

HISTORY_FIELDS = {'id', 'amount', 'reason', 'reason_label', 'created_at'}
ENVELOPE_FIELDS = {'count', 'next', 'previous', 'results'}
WITHHELD_FIELDS = ('idempotency_key', 'source_type', 'source_id')

NOT_AUTHENTICATED_DETAIL = 'Authentication credentials were not provided.'
INVALID_PAGE_BODY = {'detail': INVALID_PAGE_DETAIL}

BALANCE_BODY_PATTERN = re.compile(r'^\{"balance":\s*(-?\d+)\}$')
LEDGER_TABLE = 'ledger_ledgerentry'
INSTANT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

BOTH_PATHS = (BALANCE_PATH, LEDGER_PATH)
UNSAFE_METHODS = ('post', 'put', 'patch', 'delete')


def make_user(username):
    # No password is set, so there is no credential to leak; the tests sign in
    # through the session machinery instead.
    return User.objects.create_user(username=username)


def make_member(household, username, role=Membership.Role.CHILD):
    user = make_user(username)
    Membership.objects.create(household=household, user=user, role=role)
    return user


def make_entry(household, user, amount, *, reason=None, offset=0, key=None):
    """Create one entry at a controlled instant, so ordering is deterministic."""
    reason = reason or LedgerEntry.Reason.CHORE_CREDIT
    key = key or f'synthetic-{household.pk}-{user.pk}-{offset}-{amount}-{reason}'
    created_at = INSTANT + timedelta(seconds=offset)
    with patch('django.utils.timezone.now', return_value=created_at):
        return LedgerEntry.objects.create(
            household=household,
            user=user,
            amount=amount,
            reason=reason,
            source_type='synthetic.Source',
            source_id=f'synthetic-{offset}',
            idempotency_key=key,
        )


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
def child_a(household_a):
    return make_member(household_a, 'synthetic-child-a')


@pytest.fixture
def sibling_a(household_a):
    return make_member(household_a, 'synthetic-sibling-a')


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


def call(api_client, method, path, body=None):
    headers = csrf_header(api_client)
    handler = getattr(api_client, method)
    if method in ('get', 'head', 'delete'):
        return handler(path, headers=headers)
    return handler(path, body or {}, format='json', headers=headers)


def entry_ids():
    return sorted(LedgerEntry.objects.values_list('pk', flat=True))


def relative(url):
    """Turn the absolute `next` link into the path the test client calls."""
    parts = urlsplit(url)
    return f'{parts.path}?{parts.query}' if parts.query else parts.path


def ledger_queries(captured):
    return [query['sql'] for query in captured if LEDGER_TABLE in query['sql']]


# Routing


def test_both_routes_are_named_and_resolve():
    assert reverse('api_v1:balance') == BALANCE_PATH
    assert reverse('api_v1:ledger-history') == LEDGER_PATH

    assert resolve(BALANCE_PATH).func.view_class is BalanceView
    assert resolve(LEDGER_PATH).func.view_class is LedgerHistoryView


def test_the_merged_routes_still_resolve_unchanged():
    assert reverse('api_v1:health') == '/api/v1/health/'
    assert reverse('api_v1:auth-session') == SESSION_PATH
    assert reverse('api_v1:auth-login') == '/api/v1/auth/login/'
    assert reverse('api_v1:auth-logout') == '/api/v1/auth/logout/'
    assert reverse('api_v1:chore-list') == '/api/v1/chores/'
    assert reverse('api_v1:chore-detail', args=(7,)) == '/api/v1/chores/7/'
    assert reverse('api_v1:chore-deactivate', args=(7,)) == (
        '/api/v1/chores/7/deactivate/'
    )
    assert reverse('api_v1:chore-reactivate', args=(7,)) == (
        '/api/v1/chores/7/reactivate/'
    )


# The balance body


def test_a_child_reads_one_integer_key(api_client, household_a, child_a):
    make_entry(household_a, child_a, 25, offset=0)
    make_entry(household_a, child_a, 40, offset=1)
    sign_in(api_client, child_a)

    response = api_client.get(BALANCE_PATH)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {'balance'}
    assert body['balance'] == 65
    assert isinstance(body['balance'], int)
    assert not isinstance(body['balance'], bool)
    # No quotes and no decimal point in the rendered body.
    assert BALANCE_BODY_PATTERN.match(response.content.decode())


@pytest.mark.parametrize(
    ('amounts', 'expected'),
    (
        ((25, 40), 65),
        ((25, -30), -5),
        ((25, -25), 0),
    ),
)
def test_the_balance_is_the_plain_sum_and_is_never_clamped(
    api_client, household_a, child_a, amounts, expected
):
    for offset, amount in enumerate(amounts):
        reason = (
            LedgerEntry.Reason.CHORE_CREDIT
            if amount > 0
            else LedgerEntry.Reason.REWARD_DEBIT
        )
        make_entry(household_a, child_a, amount, reason=reason, offset=offset)
    sign_in(api_client, child_a)

    response = api_client.get(BALANCE_PATH)

    assert response.status_code == 200
    assert response.json() == {'balance': expected}


def test_a_child_with_no_entry_reads_zero_and_an_empty_page(
    api_client, household_a, child_a
):
    sign_in(api_client, child_a)

    balance = api_client.get(BALANCE_PATH)
    assert balance.status_code == 200
    assert balance.json() == {'balance': 0}
    assert balance.json()['balance'] is not None

    history = api_client.get(LEDGER_PATH)
    assert history.status_code == 200
    assert history.json() == {
        'count': 0,
        'next': None,
        'previous': None,
        'results': [],
    }


# The history body


def test_a_history_item_has_exactly_the_five_agreed_keys(
    api_client, household_a, child_a
):
    entry = make_entry(household_a, child_a, 25, offset=0)
    sign_in(api_client, child_a)

    response = api_client.get(LEDGER_PATH)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == ENVELOPE_FIELDS
    assert body['count'] == 1
    item = body['results'][0]
    assert set(item) == HISTORY_FIELDS
    assert item['id'] == entry.pk
    assert item['amount'] == 25
    assert isinstance(item['amount'], int)
    assert item['reason'] == 'chore_credit'
    assert item['reason_label'] == 'Chore credit'


def test_no_response_carries_a_withheld_field(api_client, household_a, child_a):
    make_entry(household_a, child_a, 25, offset=0)
    sign_in(api_client, child_a)

    for path in BOTH_PATHS:
        content = api_client.get(path).content.decode()
        for field in WITHHELD_FIELDS:
            assert field not in content, (path, field)
        assert '"household"' not in content
        assert '"user"' not in content


@pytest.mark.parametrize(
    ('reason', 'label'),
    (
        (LedgerEntry.Reason.CHORE_CREDIT, 'Chore credit'),
        (LedgerEntry.Reason.INTEREST, 'Interest'),
        (LedgerEntry.Reason.REWARD_DEBIT, 'Reward debit'),
        (LedgerEntry.Reason.LEVEL_DEBIT, 'Level debit'),
    ),
)
def test_each_reason_renders_its_stored_code_and_its_label(
    api_client, household_a, child_a, reason, label
):
    make_entry(household_a, child_a, 25, reason=reason, offset=0)
    sign_in(api_client, child_a)

    item = api_client.get(LEDGER_PATH).json()['results'][0]

    assert item['reason'] == reason.value
    assert item['reason_label'] == label


def test_created_at_is_an_iso_8601_utc_string_ending_in_z(
    api_client, household_a, child_a
):
    entry = make_entry(household_a, child_a, 25, offset=0)
    sign_in(api_client, child_a)

    created_at = api_client.get(LEDGER_PATH).json()['results'][0]['created_at']

    assert created_at.endswith('Z')
    parsed = datetime.fromisoformat(created_at)
    assert parsed == entry.created_at
    assert parsed.utcoffset() == timedelta(0)


# Pagination and ordering


def make_sixty(household, user):
    return [make_entry(household, user, index + 1, offset=index) for index in range(60)]


def test_the_first_page_holds_the_newest_twenty_five(api_client, household_a, child_a):
    entries = make_sixty(household_a, child_a)
    sign_in(api_client, child_a)

    body = api_client.get(LEDGER_PATH).json()

    assert body['count'] == 60
    assert body['previous'] is None
    assert body['next'] is not None
    assert len(body['results']) == HISTORY_PAGE_SIZE
    newest = [entry.pk for entry in reversed(entries)][:HISTORY_PAGE_SIZE]
    assert [item['id'] for item in body['results']] == newest


def test_walking_next_yields_every_entry_exactly_once(api_client, household_a, child_a):
    entries = make_sixty(household_a, child_a)
    sign_in(api_client, child_a)

    seen = []
    path = LEDGER_PATH
    pages = 0
    while path is not None:
        body = api_client.get(path).json()
        assert body['count'] == 60
        seen.extend(body['results'])
        pages += 1
        assert pages <= 4
        path = relative(body['next']) if body['next'] else None

    assert pages == 3
    assert [item['id'] for item in seen] == [entry.pk for entry in reversed(entries)]
    assert len({item['id'] for item in seen}) == 60

    keys = [(item['created_at'], item['id']) for item in seen]
    assert keys == sorted(keys, reverse=True)


def test_two_entries_sharing_a_timestamp_order_by_descending_id_every_time(
    api_client, household_a, child_a
):
    first = make_entry(household_a, child_a, 1, offset=0, key='synthetic-tie-1')
    second = make_entry(household_a, child_a, 2, offset=0, key='synthetic-tie-2')
    sign_in(api_client, child_a)

    for _ in range(3):
        results = api_client.get(LEDGER_PATH).json()['results']
        assert [item['id'] for item in results] == [second.pk, first.pk]
        assert results[0]['created_at'] == results[1]['created_at']


@pytest.mark.parametrize('page', ('0', 'abc', '999'))
def test_an_impossible_page_is_a_compact_404(api_client, household_a, child_a, page):
    make_sixty(household_a, child_a)
    sign_in(api_client, child_a)

    response = api_client.get(f'{LEDGER_PATH}?page={page}')

    assert response.status_code == 404
    assert response.json() == INVALID_PAGE_BODY
    content = response.content.decode()
    # Nothing but the fixed detail: no count, no identifier, no page number
    # and no exception text.
    assert content == '{"detail":"Invalid page."}'
    assert not any(character.isdigit() for character in content)


def test_the_page_size_is_fixed_and_cannot_be_widened(api_client, household_a, child_a):
    make_sixty(household_a, child_a)
    sign_in(api_client, child_a)

    body = api_client.get(f'{LEDGER_PATH}?page_size=60').json()

    assert len(body['results']) == HISTORY_PAGE_SIZE


def test_no_global_pagination_default_is_configured():
    rest_framework_settings = getattr(settings, 'REST_FRAMEWORK', {})
    assert 'DEFAULT_PAGINATION_CLASS' not in rest_framework_settings
    assert 'PAGE_SIZE' not in rest_framework_settings


# The permission matrix rows


def test_an_unauthenticated_caller_is_refused_both_routes(
    api_client, household_a, child_a
):
    make_entry(household_a, child_a, 25, offset=0)
    # An anonymous browser can still hold a CSRF cookie, so the refusal below
    # is the authority answer and not a token failure.
    api_client.get(SESSION_PATH)

    for path in BOTH_PATHS:
        response = api_client.get(path)
        assert response.status_code == 403, path
        assert response.json() == {'detail': NOT_AUTHENTICATED_DETAIL}
        content = response.content.decode()
        assert 'balance' not in content
        assert 'amount' not in content

    assert AuditEvent.objects.count() == 0


def test_a_deactivated_user_with_a_live_session_is_refused_both_routes(
    api_client, household_a, child_a
):
    make_entry(household_a, child_a, 25, offset=0)
    sign_in(api_client, child_a)
    child_a.is_active = False
    child_a.save(update_fields=('is_active',))

    for path in BOTH_PATHS:
        response = api_client.get(path)
        assert response.status_code == 403, path
        # `SessionAuthentication` refuses an inactive account, so the request
        # is anonymous by the time authority is read and the generic detail is
        # the unauthenticated one. It names no account, role or household.
        assert response.json() == {'detail': NOT_AUTHENTICATED_DETAIL}
        content = response.content.decode()
        assert 'balance' not in content
        assert 'amount' not in content


def test_a_caller_with_no_membership_is_refused_both_routes(db, api_client):
    outsider = make_user('synthetic-outsider')
    sign_in(api_client, outsider)

    for path in BOTH_PATHS:
        response = api_client.get(path)
        assert response.status_code == 403, path
        assert response.json() == {'detail': PERMISSION_DENIED_DETAIL}


def test_a_caller_with_two_live_memberships_is_refused_both_routes(
    api_client, household_a, household_b
):
    ambiguous = make_member(household_a, 'synthetic-both')
    Membership.objects.create(
        household=household_b, user=ambiguous, role=Membership.Role.CHILD
    )
    make_entry(household_a, ambiguous, 25, offset=0)
    sign_in(api_client, ambiguous)

    for path in BOTH_PATHS:
        response = api_client.get(path)
        assert response.status_code == 403, path
        assert '25' not in response.content.decode()


def test_a_membership_deleted_after_sign_in_is_refused_immediately(
    api_client, household_a, child_a
):
    make_entry(household_a, child_a, 25, offset=0)
    sign_in(api_client, child_a)
    Membership.objects.filter(user=child_a).delete()

    for path in BOTH_PATHS:
        response = api_client.get(path)
        assert response.status_code == 403, path
        assert response.json() == {'detail': PERMISSION_DENIED_DETAIL}


def test_a_parent_is_refused_both_routes(api_client, household_a, parent_a, child_a):
    make_entry(household_a, parent_a, 25, offset=0)
    make_entry(household_a, child_a, 40, offset=1)
    sign_in(api_client, parent_a)

    for path in BOTH_PATHS:
        response = api_client.get(path)
        assert response.status_code == 403, path
        assert response.json() == {'detail': PERMISSION_DENIED_DETAIL}
        assert 'amount' not in response.content.decode()


# The client never chooses whose figures it reads


def test_a_user_parameter_is_ignored(api_client, household_a, child_a, sibling_a):
    own = make_entry(household_a, child_a, 25, offset=0)
    make_entry(household_a, sibling_a, 900, offset=1)
    sign_in(api_client, child_a)

    balance = api_client.get(f'{BALANCE_PATH}?user={sibling_a.pk}')
    assert balance.json() == {'balance': 25}

    history = api_client.get(f'{LEDGER_PATH}?user={sibling_a.pk}').json()
    assert [item['id'] for item in history['results']] == [own.pk]
    assert history['count'] == 1
    assert '900' not in str(history)


def test_a_household_parameter_is_ignored_and_a_foreign_row_never_appears(
    api_client, household_a, household_b, child_a
):
    own = make_entry(household_a, child_a, 25, offset=0)
    # The same child holds rows in a household they are not a member of.
    make_entry(household_b, child_a, 900, offset=1)
    sign_in(api_client, child_a)

    balance = api_client.get(f'{BALANCE_PATH}?household={household_b.pk}')
    assert balance.json() == {'balance': 25}

    history = api_client.get(f'{LEDGER_PATH}?household={household_b.pk}').json()
    assert [item['id'] for item in history['results']] == [own.pk]
    assert history['count'] == 1
    assert '900' not in str(history)


# Cost


def test_the_balance_issues_one_aggregate_ledger_query(
    api_client, household_a, child_a
):
    make_entry(household_a, child_a, 25, offset=0)
    make_entry(household_a, child_a, 40, offset=1)
    sign_in(api_client, child_a)

    with CaptureQueriesContext(connection) as captured:
        assert api_client.get(BALANCE_PATH).status_code == 200

    queries = ledger_queries(captured)
    assert len(queries) == 1
    assert 'SUM(' in queries[0].upper()


def test_the_history_issues_a_count_and_one_page_query(
    api_client, household_a, child_a
):
    make_sixty(household_a, child_a)
    sign_in(api_client, child_a)

    with CaptureQueriesContext(connection) as captured:
        response = api_client.get(LEDGER_PATH)

    assert len(response.json()['results']) == HISTORY_PAGE_SIZE
    queries = ledger_queries(captured)
    assert len(queries) == 2
    assert sum('COUNT(' in query.upper() for query in queries) == 1


# Read-only


def test_both_routes_refuse_every_unsafe_method(
    api_client, household_a, child_a, parent_a
):
    make_entry(household_a, child_a, 25, offset=0)
    before = entry_ids()

    for user in (child_a, parent_a):
        client = APIClient(enforce_csrf_checks=True)
        sign_in(client, user)
        for path in BOTH_PATHS:
            for method in UNSAFE_METHODS:
                response = call(client, method, path, {'balance': 1})
                assert response.status_code == 405, (user.pk, path, method)

    assert entry_ids() == before
    assert AuditEvent.objects.count() == 0


def test_reading_writes_nothing(api_client, household_a, child_a):
    entry = make_entry(household_a, child_a, 25, offset=0)
    before = entry_ids()
    sign_in(api_client, child_a)

    for path in BOTH_PATHS:
        assert api_client.get(path).status_code == 200
        assert api_client.head(path).status_code == 200

    assert entry_ids() == before
    stored = LedgerEntry.objects.get(pk=entry.pk)
    assert stored.amount == 25
    assert stored.created_at == entry.created_at
    assert AuditEvent.objects.count() == 0


# What this task is not allowed to introduce


def import_roots(module):
    source = Path(module.__file__).read_text(encoding='utf-8')
    roots = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            roots.add((node.module or '').split('.')[0])
    return roots


def test_the_balance_endpoints_import_only_the_approved_modules():
    source = Path(balances_module.__file__).read_text(encoding='utf-8')
    approved_roots = {'django', 'rest_framework', 'chorum_murohc'}
    assert import_roots(balances_module) <= approved_roots

    imported = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
        and (node.module or '').startswith('chorum_murohc')
    }
    assert imported <= {
        'chorum_murohc.api.permissions',
        'chorum_murohc.api.session',
        'chorum_murohc.ledger.models',
        'chorum_murohc.ledger.services',
    }
    # The parent primitive has no place in a child-only module.
    assert 'IsHouseholdParent' not in source
