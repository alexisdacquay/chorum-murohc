"""Proofs that two harness runs cannot collide.

The browser journeys themselves need a browser, so they cannot run in the
backend gate. What the gate can prove, and what T088 actually asks for, is
the isolation underneath them: that a second run - sequential or parallel -
shares no database, no household, no user and no credential with the first,
and that no journey inside a run can see another journey's rows.

Every credential here is generated for the test and thrown away with the
test database. Nothing asserts on a credential's value, only on whether two
runs produced the same one.
"""

import re

import pytest
from django.contrib.auth.hashers import check_password

from browser_journeys.diagnostics import secret_values
from browser_journeys.seed import JOURNEY_NAMES, new_run_token, seed_dataset
from chorum_murohc.identity.models import Household, Membership, ParentPin, User
from chorum_murohc.submissions.models import Submission


@pytest.fixture
def fast_hashing(settings):
    """Hash cheaply: this suite creates a dozen accounts and two dozen PINs."""
    settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']


@pytest.fixture
def one_run(db, fast_hashing):
    return seed_dataset(new_run_token())


@pytest.fixture
def two_runs(db, fast_hashing):
    return seed_dataset(new_run_token()), seed_dataset(new_run_token())


def test_run_token_is_new_every_time():
    tokens = {new_run_token() for _ in range(50)}

    assert len(tokens) == 50
    assert all(re.fullmatch(r'[0-9a-f]{10}', token) for token in tokens)


def test_every_journey_is_seeded(one_run):
    assert set(one_run['journeys']) == set(JOURNEY_NAMES)


def test_each_journey_gets_a_household_of_its_own(one_run):
    names = [journey['household'] for journey in one_run['journeys'].values()]

    assert len(set(names)) == len(JOURNEY_NAMES)
    assert Household.objects.count() == len(JOURNEY_NAMES)


def test_no_user_belongs_to_two_journeys(one_run):
    for user in User.objects.all():
        assert Membership.objects.filter(user=user).count() == 1


def test_every_household_name_carries_its_run_token(one_run):
    for journey in one_run['journeys'].values():
        assert one_run['token'] in journey['household']


def test_two_runs_share_no_household(two_runs):
    first, second = two_runs
    names = [
        {journey['household'] for journey in run['journeys'].values()}
        for run in (first, second)
    ]

    assert names[0].isdisjoint(names[1])


def test_two_runs_share_no_user(two_runs):
    first, second = two_runs
    usernames = [
        set(
            User.objects.filter(username__contains=run['token']).values_list(
                'username', flat=True
            )
        )
        for run in (first, second)
    ]

    assert usernames[0]
    assert usernames[0].isdisjoint(usernames[1])
    assert User.objects.count() == len(usernames[0]) + len(usernames[1])


def test_two_runs_share_no_credential(two_runs):
    first, second = two_runs

    assert set(secret_values(first)).isdisjoint(secret_values(second))


def test_every_account_has_its_own_password(one_run):
    passwords = [
        value
        for journey in one_run['journeys'].values()
        for value in secret_values(journey)
    ]

    assert len(passwords) == len(set(passwords))


def test_a_pin_is_stored_only_as_a_hash(one_run):
    pins = [
        member['pin']
        for journey in one_run['journeys'].values()
        for member in journey.values()
        if isinstance(member, dict) and 'pin' in member
    ]
    stored = list(ParentPin.objects.values_list('pin_hash', flat=True))

    assert pins
    assert set(stored).isdisjoint(pins)
    assert all(
        any(check_password(pin, pin_hash) for pin_hash in stored) for pin in pins
    )


def test_the_parent_queue_journey_starts_with_work_waiting(one_run):
    """A silently empty queue would let that journey pass without proving anything."""
    household = Household.objects.get(
        name=one_run['journeys']['parent-queue']['household']
    )
    pending = Submission.objects.filter(
        household=household,
        status=Submission.Status.PENDING,
    )

    assert pending.count() == 2


def test_secret_values_finds_every_password_and_pin(one_run):
    found = secret_values(one_run)
    accounts = [
        member
        for journey in one_run['journeys'].values()
        for member in journey.values()
        if isinstance(member, dict) and 'password' in member
    ]
    expected = len(accounts) + sum(1 for member in accounts if 'pin' in member)

    assert len(found) == expected
    assert all(value for value in found)
