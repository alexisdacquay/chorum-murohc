"""Tests for the pure weekly-interest arithmetic (`_docs/interest-policy.md`).

Every case here is one row of the worked-examples table in that document, so
a change to either must change the other. No database, no fixture, no
Django test case: `weekly_interest` needs none of that.
"""

import pytest

from chorum_murohc.interest.calculator import RATE_PERCENT, WEEKLY_CAP, weekly_interest


def test_the_policy_constants_are_exactly_two_percent_capped_at_twenty():
    assert RATE_PERCENT == 2
    assert WEEKLY_CAP == 20


@pytest.mark.parametrize(
    ('balance', 'expected'),
    (
        (-1_000_000, 0),
        (-30, 0),
        (-1, 0),
        (0, 0),
        (1, 0),
        (24, 0),
        (25, 0),
        (49, 0),
        (50, 1),
        (51, 1),
        (99, 1),
        (100, 2),
        (999, 19),
        (1_000, 20),
        (1_001, 20),
        (1_050, 20),
        (50_000, 20),
    ),
)
def test_worked_examples_match_the_policy_document(balance, expected):
    assert weekly_interest(balance) == expected


def test_the_result_is_never_negative_and_never_above_the_cap():
    for balance in range(-100, 5_000, 7):
        amount = weekly_interest(balance)
        assert 0 <= amount <= WEEKLY_CAP


def test_the_result_is_always_a_plain_int_never_a_bool_or_a_float():
    for balance in (-5, 0, 5, 50, 5_000):
        amount = weekly_interest(balance)
        assert type(amount) is int


def test_a_zero_or_negative_balance_earns_nothing_regardless_of_magnitude():
    for balance in (0, -1, -50, -1_000_000):
        assert weekly_interest(balance) == 0


def test_the_cap_applies_at_exactly_the_balance_where_two_percent_reaches_it():
    # 2% of 1000 is exactly 20, the cap; one point below or above the
    # threshold balance must not change the capped result.
    assert weekly_interest(999) == 19
    assert weekly_interest(1_000) == 20
    assert weekly_interest(1_001) == 20


def test_rounding_always_floors_and_never_rounds_to_the_nearest_point():
    # 2% of 99 is 1.98; a nearest-point rounding would give 2, the policy's
    # floor rule gives 1.
    assert weekly_interest(99) == 1
