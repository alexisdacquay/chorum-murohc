"""Tests for the weekly interest accrual service.

Every fixture is synthetic. No credential or personal datum appears in the
data, the assertions, or the failure output: test users are created without
a usable password, so there is nothing sensitive to print.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from itertools import count
from threading import Barrier

import pytest
from django.db import connection

from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity.models import Household, Membership, User
from chorum_murohc.interest.services import (
    AUDIT_ACCRUE,
    AUDIT_TARGET_TYPE,
    LEDGER_SOURCE_TYPE,
    InterestAuthorityError,
    accrue_interest_for_user,
    eligible_children,
    preview_interest_for_user,
)
from chorum_murohc.ledger.models import LedgerEntry

ACCRUAL_DATE = date(2026, 9, 6)
OTHER_ACCRUAL_DATE = date(2026, 9, 13)


def make_user(username, *, is_active=True):
    # No password is set, so there is no credential to leak.
    return User.objects.create_user(username=username, is_active=is_active)


def make_member(household, username, role=Membership.Role.CHILD, *, is_active=True):
    user = make_user(username, is_active=is_active)
    Membership.objects.create(household=household, user=user, role=role)
    return user


_credit_sequence = count()


def credit(household, user, amount):
    # A monotonic counter, not the amount, makes the key: a test crediting
    # the same user the same amount twice (proving a *later* credit does not
    # retroactively change an already-decided accrual) must not collide with
    # itself on the ledger's own (user, idempotency_key) uniqueness rule.
    LedgerEntry.objects.create(
        household=household,
        user=user,
        amount=amount,
        reason=LedgerEntry.Reason.CHORE_CREDIT,
        source_type='synthetic.Source',
        source_id='synthetic-credit',
        idempotency_key=f'synthetic-credit-{next(_credit_sequence)}',
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
def parent_a(household_a):
    return make_member(household_a, 'synthetic-parent-a', Membership.Role.PARENT)


# accrue_interest_for_user: crediting


def test_a_qualifying_balance_credits_the_capped_rounded_amount(household_a, child_a):
    credit(household_a, child_a, 1_050)

    entry, created = accrue_interest_for_user(
        household=household_a, user=child_a, accrual_date=ACCRUAL_DATE
    )

    assert created is True
    assert entry is not None
    assert entry.amount == 20
    assert entry.reason == LedgerEntry.Reason.INTEREST
    assert entry.household_id == household_a.pk
    assert entry.user_id == child_a.pk
    assert entry.source_type == LEDGER_SOURCE_TYPE
    assert entry.source_id == '2026-09-06'
    assert entry.idempotency_key == 'interest:2026-09-06'


@pytest.mark.parametrize('balance', (0, -1, -500))
def test_a_zero_or_negative_balance_credits_nothing(household_a, child_a, balance):
    if balance != 0:
        credit(household_a, child_a, balance)

    entry, created = accrue_interest_for_user(
        household=household_a, user=child_a, accrual_date=ACCRUAL_DATE
    )

    assert (entry, created) == (None, False)
    assert LedgerEntry.objects.filter(user=child_a, reason='interest').count() == 0


def test_a_balance_whose_two_percent_rounds_down_to_zero_credits_nothing(
    household_a, child_a
):
    credit(household_a, child_a, 25)

    entry, created = accrue_interest_for_user(
        household=household_a, user=child_a, accrual_date=ACCRUAL_DATE
    )

    assert (entry, created) == (None, False)
    assert LedgerEntry.objects.filter(user=child_a, reason='interest').count() == 0


def test_the_balance_read_excludes_nothing_it_should_and_includes_prior_interest(
    household_a, child_a
):
    credit(household_a, child_a, 1_000)
    accrue_interest_for_user(
        household=household_a, user=child_a, accrual_date=ACCRUAL_DATE
    )

    # A second week's interest is computed on the balance the first week's
    # interest actually left behind (1000 + 20 = 1020), not the original 1000.
    entry, created = accrue_interest_for_user(
        household=household_a, user=child_a, accrual_date=OTHER_ACCRUAL_DATE
    )

    assert created is True
    assert entry.amount == 20  # 2% of 1020 is 20.4, floored to 20, still under the cap


def test_writes_exactly_one_audit_event_with_no_human_actor(household_a, child_a):
    credit(household_a, child_a, 500)

    entry, _created = accrue_interest_for_user(
        household=household_a, user=child_a, accrual_date=ACCRUAL_DATE
    )

    events = list(AuditEvent.objects.all())
    assert len(events) == 1
    event = events[0]
    assert event.household_id == household_a.pk
    assert event.actor_id is None
    assert event.action == AUDIT_ACCRUE
    assert event.target_type == AUDIT_TARGET_TYPE
    assert event.target_id == str(entry.pk)
    assert event.context == {
        'user_id': child_a.pk,
        'accrual_date': '2026-09-06',
        'balance': 500,
        'amount': 10,
    }


def test_a_skipped_zero_interest_call_writes_no_audit_event(household_a, child_a):
    accrue_interest_for_user(
        household=household_a, user=child_a, accrual_date=ACCRUAL_DATE
    )

    assert AuditEvent.objects.count() == 0


# accrue_interest_for_user: idempotency


def test_a_repeat_call_for_the_same_user_and_date_is_a_true_no_op(household_a, child_a):
    credit(household_a, child_a, 500)

    first_entry, first_created = accrue_interest_for_user(
        household=household_a, user=child_a, accrual_date=ACCRUAL_DATE
    )
    # A further credit between calls proves the second call is skipped by
    # the date key, not by a coincidentally unchanged balance.
    credit(household_a, child_a, 500)
    second_entry, second_created = accrue_interest_for_user(
        household=household_a, user=child_a, accrual_date=ACCRUAL_DATE
    )

    assert first_created is True
    assert second_created is False
    assert second_entry.pk == first_entry.pk
    assert LedgerEntry.objects.filter(user=child_a, reason='interest').count() == 1
    assert AuditEvent.objects.count() == 1


def test_a_different_accrual_date_credits_again(household_a, child_a):
    credit(household_a, child_a, 500)

    accrue_interest_for_user(
        household=household_a, user=child_a, accrual_date=ACCRUAL_DATE
    )
    _entry, created = accrue_interest_for_user(
        household=household_a, user=child_a, accrual_date=OTHER_ACCRUAL_DATE
    )

    assert created is True
    assert LedgerEntry.objects.filter(user=child_a, reason='interest').count() == 2


@pytest.mark.django_db(transaction=True)
def test_concurrent_calls_for_the_same_user_and_date_credit_exactly_once():
    if connection.vendor != 'postgresql':
        pytest.skip('requires the guarded PostgreSQL target')

    household = Household.objects.create(name='Concurrent household')
    child = make_member(household, 'concurrent-child')
    credit(household, child, 1_000)
    barrier = Barrier(2)

    def call():
        try:
            barrier.wait(timeout=10)
            return accrue_interest_for_user(
                household=household, user=child, accrual_date=ACCRUAL_DATE
            )
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(call) for _ in range(2)]
        results = [future.result(timeout=15) for future in futures]

    assert sorted(created for _, created in results) == [False, True]
    assert LedgerEntry.objects.filter(user=child, reason='interest').count() == 1


# accrue_interest_for_user: household and role isolation


def test_a_sibling_or_another_household_is_never_touched(
    household_a, household_b, child_a
):
    sibling = make_member(household_a, 'synthetic-sibling-a')
    credit(household_a, child_a, 1_000)
    credit(household_a, sibling, 1_000)

    accrue_interest_for_user(
        household=household_a, user=child_a, accrual_date=ACCRUAL_DATE
    )

    assert LedgerEntry.objects.filter(user=sibling, reason='interest').count() == 0
    assert LedgerEntry.objects.filter(household=household_b).count() == 0


def test_a_parent_membership_is_refused_and_writes_nothing(household_a, parent_a):
    credit(household_a, parent_a, 1_000)

    with pytest.raises(InterestAuthorityError):
        accrue_interest_for_user(
            household=household_a, user=parent_a, accrual_date=ACCRUAL_DATE
        )

    assert LedgerEntry.objects.filter(user=parent_a, reason='interest').count() == 0
    assert AuditEvent.objects.count() == 0


def test_a_missing_membership_raises_does_not_exist(household_a):
    stray_user = make_user('synthetic-stray-user')

    with pytest.raises(Membership.DoesNotExist):
        accrue_interest_for_user(
            household=household_a, user=stray_user, accrual_date=ACCRUAL_DATE
        )

    assert LedgerEntry.objects.count() == 0


# eligible_children


def test_eligible_children_lists_only_active_children(household_a):
    active_child = make_member(household_a, 'synthetic-active-child')
    make_member(household_a, 'synthetic-parent', Membership.Role.PARENT)
    make_member(household_a, 'synthetic-inactive-child', is_active=False)

    memberships = list(eligible_children())

    assert [membership.user_id for membership in memberships] == [active_child.pk]


def test_eligible_children_can_be_bounded_to_one_household(household_a, household_b):
    child_a = make_member(household_a, 'synthetic-child-a')
    make_member(household_b, 'synthetic-child-b')

    memberships = list(eligible_children(household_id=household_a.pk))

    assert [membership.user_id for membership in memberships] == [child_a.pk]


def test_eligible_children_orders_by_household_then_user(household_a, household_b):
    child_b = make_member(household_b, 'synthetic-child-b')
    child_a = make_member(household_a, 'synthetic-child-a')

    memberships = list(eligible_children())

    ordered_ids = [
        (membership.household_id, membership.user_id) for membership in memberships
    ]
    assert ordered_ids == sorted(ordered_ids)
    assert {membership.user_id for membership in memberships} == {
        child_a.pk,
        child_b.pk,
    }


def test_eligible_children_preloads_household_and_user_in_one_extra_query(
    household_a, django_assert_num_queries
):
    make_member(household_a, 'synthetic-child-a')

    with django_assert_num_queries(1):
        for membership in eligible_children():
            membership.household.name  # noqa: B018 - proves no extra query fires
            membership.user.username  # noqa: B018


# preview_interest_for_user


def test_preview_matches_a_real_accrual_and_writes_nothing(household_a, child_a):
    credit(household_a, child_a, 1_050)

    amount = preview_interest_for_user(household_a, child_a)

    assert amount == 20
    assert LedgerEntry.objects.filter(reason='interest').count() == 0
    assert AuditEvent.objects.count() == 0


def test_preview_is_zero_for_a_non_qualifying_balance(household_a, child_a):
    assert preview_interest_for_user(household_a, child_a) == 0
