"""Tests for the read-only ledger services.

Every fixture is synthetic. No credential, PIN, token, cookie or personal
datum appears in the data, the assertions or the failure output: the test
users are created without a usable password, so there is nothing sensitive to
print.

These are the arithmetic and scoping proofs. The HTTP shape, the permission
rows and the pagination behaviour are proved next to the endpoints in
`chorum_murohc/api/test_balances.py`.
"""

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity.models import Household, Membership, User
from chorum_murohc.ledger import services as services_module
from chorum_murohc.ledger.models import LedgerEntry
from chorum_murohc.ledger.services import balance_for_user, ledger_history_for_user

INSTANT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def make_user(username):
    # No password is set, so there is no credential to leak.
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


# Balance arithmetic


def test_two_credits_sum(household_a, child_a):
    make_entry(household_a, child_a, 25, offset=0)
    make_entry(household_a, child_a, 40, offset=1)

    assert balance_for_user(household_a, child_a) == 65


def test_a_debit_larger_than_the_credit_is_negative_and_never_clamped(
    household_a, child_a
):
    make_entry(household_a, child_a, 25, offset=0)
    make_entry(
        household_a, child_a, -30, reason=LedgerEntry.Reason.REWARD_DEBIT, offset=1
    )

    assert balance_for_user(household_a, child_a) == -5


def test_a_credit_cancelled_by_its_debit_is_zero(household_a, child_a):
    make_entry(household_a, child_a, 25, offset=0)
    make_entry(
        household_a, child_a, -25, reason=LedgerEntry.Reason.LEVEL_DEBIT, offset=1
    )

    assert balance_for_user(household_a, child_a) == 0


def test_no_entry_at_all_is_zero_and_never_none(household_a, child_a):
    balance = balance_for_user(household_a, child_a)

    assert balance == 0
    assert balance is not None
    assert isinstance(balance, int)


def test_a_sibling_balance_is_never_included(household_a, child_a, sibling_a):
    make_entry(household_a, child_a, 25, offset=0)
    make_entry(household_a, sibling_a, 900, offset=1)

    assert balance_for_user(household_a, child_a) == 25
    assert balance_for_user(household_a, sibling_a) == 900


def test_another_household_is_never_included(household_a, household_b, child_a):
    make_entry(household_a, child_a, 25, offset=0)
    make_entry(household_b, child_a, 900, offset=1)

    assert balance_for_user(household_a, child_a) == 25
    assert balance_for_user(household_b, child_a) == 900


def test_the_balance_is_one_aggregate_query(
    household_a, child_a, django_assert_num_queries
):
    make_entry(household_a, child_a, 25, offset=0)
    make_entry(household_a, child_a, 40, offset=1)

    with django_assert_num_queries(1):
        assert balance_for_user(household_a, child_a) == 65


# History


def test_the_history_is_newest_first(household_a, child_a):
    oldest = make_entry(household_a, child_a, 1, offset=0)
    middle = make_entry(household_a, child_a, 2, offset=1)
    newest = make_entry(household_a, child_a, 3, offset=2)

    history = list(ledger_history_for_user(household_a, child_a))

    assert [entry.pk for entry in history] == [newest.pk, middle.pk, oldest.pk]


def test_entries_sharing_a_timestamp_order_by_descending_id(household_a, child_a):
    first = make_entry(household_a, child_a, 1, offset=0, key='synthetic-tie-1')
    second = make_entry(household_a, child_a, 2, offset=0, key='synthetic-tie-2')

    history = list(ledger_history_for_user(household_a, child_a))

    assert first.created_at == second.created_at
    assert [entry.pk for entry in history] == [second.pk, first.pk]


def test_the_history_order_does_not_depend_on_the_model_default(household_a, child_a):
    assert ledger_history_for_user(household_a, child_a).query.order_by == (
        '-created_at',
        '-id',
    )


def test_the_history_holds_only_the_named_user_in_the_named_household(
    household_a, household_b, child_a, sibling_a
):
    own = make_entry(household_a, child_a, 25, offset=0)
    make_entry(household_a, sibling_a, 900, offset=1)
    make_entry(household_b, child_a, 900, offset=2)

    history = list(ledger_history_for_user(household_a, child_a))

    assert [entry.pk for entry in history] == [own.pk]


def test_an_empty_history_is_an_empty_queryset(household_a, child_a):
    assert list(ledger_history_for_user(household_a, child_a)) == []


def test_reading_writes_nothing(household_a, child_a):
    make_entry(household_a, child_a, 25, offset=0)
    before = list(LedgerEntry.objects.values_list('pk', flat=True))

    balance_for_user(household_a, child_a)
    list(ledger_history_for_user(household_a, child_a))

    assert list(LedgerEntry.objects.values_list('pk', flat=True)) == before
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


def ledger_sources():
    package_root = Path(services_module.__file__).resolve().parent
    return [
        source_file
        for source_file in sorted(package_root.rglob('*.py'))
        if not source_file.name.startswith('test') and source_file.name != 'tests.py'
    ]


def test_the_services_import_only_django_and_the_ledger_models():
    assert import_roots(services_module) <= {'django', 'chorum_murohc'}

    imported = {
        node.module
        for node in ast.walk(
            ast.parse(Path(services_module.__file__).read_text(encoding='utf-8'))
        )
        if isinstance(node, ast.ImportFrom)
        and (node.module or '').startswith('chorum_murohc')
    }
    assert imported == {'chorum_murohc.ledger.models'}


def test_the_ledger_package_holds_no_view_serializer_or_route():
    offenders = []
    for source_file in ledger_sources():
        source = source_file.read_text(encoding='utf-8')
        if 'rest_framework' in source or 'django.urls' in source:
            offenders.append(source_file.name)
    assert offenders == []


def test_the_ledger_package_never_imports_the_api_layer():
    offenders = []
    for source_file in ledger_sources():
        tree = ast.parse(source_file.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or '']
            else:
                continue
            if any(name.startswith('chorum_murohc.api') for name in names):
                offenders.append(source_file.name)
    assert offenders == []


def test_no_denormalised_balance_column_exists():
    stored_fields = {field.name for field in LedgerEntry._meta.get_fields()}
    assert 'balance' not in stored_fields
    assert 'running_total' not in stored_fields

    household_fields = {field.name for field in Household._meta.get_fields()}
    user_fields = {field.name for field in User._meta.get_fields()}
    for name in ('balance', 'points', 'points_balance', 'running_total'):
        assert name not in household_fields
        assert name not in user_fields
