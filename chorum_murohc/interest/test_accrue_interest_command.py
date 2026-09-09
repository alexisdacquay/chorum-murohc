"""Tests for `manage.py accrue_interest` (T053).

Exercises the command as an operator would run it: through `call_command`,
asserting on its stdout summary line and its exit behaviour, never on
private helpers.
"""

from io import StringIO
from itertools import count
from unittest.mock import patch

import pytest
from django.core.management import CommandError, call_command

from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity.models import Household, Membership, User
from chorum_murohc.interest import services as services_module
from chorum_murohc.ledger.models import LedgerEntry

DATE = '2026-09-06'


def make_user(username, *, is_active=True):
    return User.objects.create_user(username=username, is_active=is_active)


def make_member(household, username, role=Membership.Role.CHILD, *, is_active=True):
    user = make_user(username, is_active=is_active)
    Membership.objects.create(household=household, user=user, role=role)
    return user


_credit_sequence = count()


def credit(household, user, amount):
    LedgerEntry.objects.create(
        household=household,
        user=user,
        amount=amount,
        reason=LedgerEntry.Reason.CHORE_CREDIT,
        source_type='synthetic.Source',
        source_id='synthetic-credit',
        idempotency_key=f'synthetic-credit-{next(_credit_sequence)}',
    )


def run(*args):
    stdout, stderr = StringIO(), StringIO()
    call_command('accrue_interest', *args, stdout=stdout, stderr=stderr)
    return stdout.getvalue(), stderr.getvalue()


@pytest.fixture
def household_a(db):
    return Household.objects.create(name='Synthetic Household A')


@pytest.fixture
def household_b(db):
    return Household.objects.create(name='Synthetic Household B')


def test_an_invalid_date_is_a_command_error_and_writes_nothing(db):
    with pytest.raises(CommandError, match='Invalid date'):
        call_command('accrue_interest', '--date', 'not-a-date')

    assert LedgerEntry.objects.count() == 0


def test_date_is_a_required_argument(db):
    with pytest.raises((CommandError, SystemExit)):
        call_command('accrue_interest')


def test_one_household_credits_only_its_own_eligible_children(household_a, household_b):
    child_a = make_member(household_a, 'synthetic-child-a')
    child_b = make_member(household_b, 'synthetic-child-b')
    credit(household_a, child_a, 1_000)
    credit(household_b, child_b, 1_000)

    stdout, _stderr = run('--date', DATE, '--household', str(household_a.pk))

    assert '1 credited, 0 skipped, 0 failed' in stdout
    assert LedgerEntry.objects.filter(user=child_a, reason='interest').count() == 1
    assert LedgerEntry.objects.filter(user=child_b, reason='interest').count() == 0


def test_all_households_credits_every_eligible_child(household_a, household_b):
    child_a = make_member(household_a, 'synthetic-child-a')
    child_b = make_member(household_b, 'synthetic-child-b')
    make_member(household_a, 'synthetic-parent-a', Membership.Role.PARENT)
    credit(household_a, child_a, 1_000)
    credit(household_b, child_b, 25)  # rounds to zero, so this one is skipped

    stdout, _stderr = run('--date', DATE)

    assert '1 credited, 1 skipped, 0 failed' in stdout
    assert LedgerEntry.objects.filter(reason='interest').count() == 1


def test_dry_run_reports_counts_and_writes_nothing(household_a):
    child_a = make_member(household_a, 'synthetic-child-a')
    credit(household_a, child_a, 1_000)

    stdout, _stderr = run('--date', DATE, '--dry-run')

    assert stdout.startswith('Dry run: ')
    assert '1 credited, 0 skipped, 0 failed' in stdout
    assert LedgerEntry.objects.filter(reason='interest').count() == 0
    assert AuditEvent.objects.count() == 0


def test_repeat_execution_the_same_day_is_a_no_op_the_second_time(household_a):
    child_a = make_member(household_a, 'synthetic-child-a')
    credit(household_a, child_a, 1_000)

    first_stdout, _ = run('--date', DATE)
    second_stdout, _ = run('--date', DATE)

    assert '1 credited, 0 skipped, 0 failed' in first_stdout
    assert '0 credited, 1 skipped, 0 failed' in second_stdout
    assert LedgerEntry.objects.filter(reason='interest').count() == 1
    assert AuditEvent.objects.count() == 1


def test_a_partial_failure_still_credits_the_other_users_and_exits_non_zero(
    household_a,
):
    healthy_child = make_member(household_a, 'synthetic-healthy-child')
    broken_child = make_member(household_a, 'synthetic-broken-child')
    credit(household_a, healthy_child, 1_000)
    credit(household_a, broken_child, 1_000)

    real_accrue = services_module.accrue_interest_for_user

    def flaky_accrue(*, household, user, accrual_date):
        if user.pk == broken_child.pk:
            raise RuntimeError('synthetic failure')
        return real_accrue(household=household, user=user, accrual_date=accrual_date)

    with (
        patch(
            'chorum_murohc.interest.management.commands.accrue_interest.'
            'accrue_interest_for_user',
            side_effect=flaky_accrue,
        ),
        pytest.raises(CommandError, match='unrecovered failures'),
    ):
        run('--date', DATE)

    assert (
        LedgerEntry.objects.filter(user=healthy_child, reason='interest').count() == 1
    )
    assert LedgerEntry.objects.filter(user=broken_child, reason='interest').count() == 0


def test_a_failure_message_names_no_username(household_a):
    broken_child = make_member(household_a, 'synthetic-broken-child')
    credit(household_a, broken_child, 1_000)

    with patch(
        'chorum_murohc.interest.management.commands.accrue_interest.'
        'accrue_interest_for_user',
        side_effect=RuntimeError('synthetic failure'),
    ):
        stdout, stderr = StringIO(), StringIO()
        with pytest.raises(CommandError):
            call_command(
                'accrue_interest', '--date', DATE, stdout=stdout, stderr=stderr
            )

    assert broken_child.username not in stderr.getvalue()
    assert broken_child.username not in stdout.getvalue()
    assert str(household_a.pk) in stderr.getvalue()
    assert str(broken_child.pk) in stderr.getvalue()


def test_no_eligible_children_is_a_clean_zero_run(db):
    stdout, _stderr = run('--date', DATE)

    assert '0 credited, 0 skipped, 0 failed' in stdout
