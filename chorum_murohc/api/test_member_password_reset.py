"""Tests for `POST /api/v1/household-members/<pk>/reset-password/` (issue #129).

`chorum_murohc/api/test_members.py` already proves this route is wired into
the directory's shared plumbing: routing, the child/unauthenticated/no-
membership/two-household/deleted-membership denials, CSRF enforcement, the
unsupported-method refusal, and the unknown/foreign-identifier 404. This
module proves what is specific to a password reset: the acting parent's own
PIN-or-password proof, the target's PIN and lockout being cleared, that a
reset never targets the caller, and the compact non-enumerating shape of a
failed proof.

Every fixture is synthetic. No real credential or PIN appears in the data,
the assertions, or the failure output.
"""

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from chorum_murohc.api.members import AUDIT_PASSWORD_RESET, VERIFICATION_FAILED_DETAIL
from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity.models import Household, Membership, ParentPin, User
from chorum_murohc.identity.services import set_or_replace_pin

LIST_PATH = '/api/v1/household-members/'
SESSION_PATH = '/api/v1/auth/session/'
CSRF_COOKIE = settings.CSRF_COOKIE_NAME

# Synthetic throughout: none of these values is a real account or a real PIN.
ACTOR_PASSWORD = 'synthetic-only-actor-password-1'
TARGET_OLD_PASSWORD = 'synthetic-only-target-password-1'
NEW_PASSWORD = 'a genuinely unusual passphrase 42'
ACTOR_PIN = '3947'


def reset_path(user_id):
    return f'{LIST_PATH}{user_id}/reset-password/'


@pytest.fixture
def api_client():
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def household_a(db):
    return Household.objects.create(name='Synthetic Household A')


@pytest.fixture
def household_b(db):
    return Household.objects.create(name='Synthetic Household B')


def make_member(household, username, role, password):
    user = User.objects.create_user(username=username, password=password)
    Membership.objects.create(household=household, user=user, role=role)
    return user


@pytest.fixture
def parent_a(household_a):
    return make_member(
        household_a, 'synthetic-parent-a', Membership.Role.PARENT, ACTOR_PASSWORD
    )


@pytest.fixture
def second_parent_a(household_a):
    return make_member(
        household_a,
        'synthetic-parent-a2',
        Membership.Role.PARENT,
        TARGET_OLD_PASSWORD,
    )


@pytest.fixture
def child_a(household_a):
    return make_member(
        household_a, 'synthetic-child-a', Membership.Role.CHILD, TARGET_OLD_PASSWORD
    )


def sign_in(api_client, user):
    api_client.force_login(user)
    api_client.get(SESSION_PATH)
    return api_client


def csrf_header(api_client):
    cookie = api_client.cookies.get(CSRF_COOKIE)
    return {'x-csrftoken': cookie.value} if cookie is not None else {}


def post_reset(api_client, user_id, body):
    return api_client.post(
        reset_path(user_id), body, format='json', headers=csrf_header(api_client)
    )


def one_event(action):
    events = list(AuditEvent.objects.filter(action=action))
    assert len(events) == 1
    return events[0]


def assert_withholds(text, *sensitive_values):
    for sensitive_value in sensitive_values:
        if sensitive_value and sensitive_value in text:
            pytest.fail(
                'The value disclosed a controlled sensitive value; output withheld.',
                pytrace=False,
            )


# Verifying with the acting parent's own password


def test_a_parent_resets_a_childs_password_using_their_own_account_password(
    api_client, household_a, parent_a, child_a
):
    sign_in(api_client, parent_a)

    response = post_reset(
        api_client,
        child_a.pk,
        {'password': ACTOR_PASSWORD, 'new_password': NEW_PASSWORD},
    )

    assert response.status_code == 200
    child_a.refresh_from_db()
    assert child_a.check_password(NEW_PASSWORD) is True
    assert child_a.check_password(TARGET_OLD_PASSWORD) is False

    event = one_event(AUDIT_PASSWORD_RESET)
    assert event.actor == parent_a
    assert event.household == household_a
    assert event.target_id == str(child_a.pk)
    assert event.context == {
        'actor_id': parent_a.pk,
        'target_id': child_a.pk,
        'verification_method': 'password',
        'pin_cleared': False,
    }


def test_the_acting_parents_own_wrong_password_is_a_compact_generic_refusal(
    api_client, household_a, parent_a, child_a
):
    sign_in(api_client, parent_a)

    response = post_reset(
        api_client,
        child_a.pk,
        {'password': 'not-the-real-password', 'new_password': NEW_PASSWORD},
    )

    assert response.status_code == 400
    assert response.json() == {'detail': VERIFICATION_FAILED_DETAIL}
    assert_withholds(
        response.content.decode(), ACTOR_PASSWORD, NEW_PASSWORD, TARGET_OLD_PASSWORD
    )
    child_a.refresh_from_db()
    assert child_a.check_password(TARGET_OLD_PASSWORD) is True
    assert AuditEvent.objects.exists() is False


# Verifying with the acting parent's own PIN


def test_a_parent_resets_a_childs_password_using_their_own_pin(
    api_client, household_a, parent_a, child_a
):
    set_or_replace_pin(
        user=parent_a,
        household=household_a,
        current_password=ACTOR_PASSWORD,
        new_pin=ACTOR_PIN,
    )
    sign_in(api_client, parent_a)

    response = post_reset(
        api_client,
        child_a.pk,
        {'pin': ACTOR_PIN, 'new_password': NEW_PASSWORD},
    )

    assert response.status_code == 200
    child_a.refresh_from_db()
    assert child_a.check_password(NEW_PASSWORD) is True

    event = one_event(AUDIT_PASSWORD_RESET)
    assert event.context['verification_method'] == 'pin'


def test_a_wrong_pin_is_a_compact_generic_refusal_and_counts_against_the_actor(
    api_client, household_a, parent_a, child_a
):
    set_or_replace_pin(
        user=parent_a,
        household=household_a,
        current_password=ACTOR_PASSWORD,
        new_pin=ACTOR_PIN,
    )
    sign_in(api_client, parent_a)

    response = post_reset(
        api_client, child_a.pk, {'pin': '0000', 'new_password': NEW_PASSWORD}
    )

    assert response.status_code == 400
    assert response.json() == {'detail': VERIFICATION_FAILED_DETAIL}
    child_a.refresh_from_db()
    assert child_a.check_password(TARGET_OLD_PASSWORD) is True

    # The wrong guess is charged to the actor's own PIN, exactly as it would
    # be from the approval flow: this route is not a side channel that lets
    # a PIN be brute-forced for free.
    pin_row = ParentPin.objects.get(user=parent_a)
    assert pin_row.failed_attempts == 1


def test_a_parent_with_no_pin_gets_the_same_generic_refusal(
    api_client, household_a, parent_a, child_a
):
    sign_in(api_client, parent_a)

    response = post_reset(
        api_client, child_a.pk, {'pin': '1357', 'new_password': NEW_PASSWORD}
    )

    assert response.status_code == 400
    assert response.json() == {'detail': VERIFICATION_FAILED_DETAIL}


# Clearing the target's PIN and lockout (approval-authentication.md)


def test_resetting_a_parents_password_clears_their_pin_and_lockout(
    api_client, household_a, parent_a, second_parent_a
):
    set_or_replace_pin(
        user=second_parent_a,
        household=household_a,
        current_password=TARGET_OLD_PASSWORD,
        new_pin='8156',
    )
    sign_in(api_client, parent_a)

    response = post_reset(
        api_client,
        second_parent_a.pk,
        {'password': ACTOR_PASSWORD, 'new_password': NEW_PASSWORD},
    )

    assert response.status_code == 200
    assert ParentPin.objects.filter(user=second_parent_a).exists() is False

    event = one_event(AUDIT_PASSWORD_RESET)
    assert event.context['pin_cleared'] is True


def test_resetting_a_childs_password_reports_no_pin_to_clear(
    api_client, household_a, parent_a, child_a
):
    sign_in(api_client, parent_a)

    post_reset(
        api_client,
        child_a.pk,
        {'password': ACTOR_PASSWORD, 'new_password': NEW_PASSWORD},
    )

    event = one_event(AUDIT_PASSWORD_RESET)
    assert event.context['pin_cleared'] is False


def test_resetting_a_parent_with_no_pin_set_is_a_silent_no_op_not_an_error(
    api_client, household_a, parent_a, second_parent_a
):
    sign_in(api_client, parent_a)

    response = post_reset(
        api_client,
        second_parent_a.pk,
        {'password': ACTOR_PASSWORD, 'new_password': NEW_PASSWORD},
    )

    assert response.status_code == 200
    event = one_event(AUDIT_PASSWORD_RESET)
    assert event.context['pin_cleared'] is False


def test_resetting_one_parents_password_never_touches_the_actors_own_pin(
    api_client, household_a, parent_a, second_parent_a
):
    set_or_replace_pin(
        user=parent_a,
        household=household_a,
        current_password=ACTOR_PASSWORD,
        new_pin=ACTOR_PIN,
    )
    sign_in(api_client, parent_a)

    post_reset(
        api_client,
        second_parent_a.pk,
        {'password': ACTOR_PASSWORD, 'new_password': NEW_PASSWORD},
    )

    assert ParentPin.objects.filter(user=parent_a).exists() is True


# Body shape


def test_neither_pin_nor_password_is_refused_locally(
    api_client, household_a, parent_a, child_a
):
    sign_in(api_client, parent_a)

    response = post_reset(api_client, child_a.pk, {'new_password': NEW_PASSWORD})

    assert response.status_code == 400
    child_a.refresh_from_db()
    assert child_a.check_password(TARGET_OLD_PASSWORD) is True
    assert AuditEvent.objects.exists() is False


def test_both_pin_and_password_together_is_refused(
    api_client, household_a, parent_a, child_a
):
    sign_in(api_client, parent_a)

    response = post_reset(
        api_client,
        child_a.pk,
        {'pin': '1234', 'password': ACTOR_PASSWORD, 'new_password': NEW_PASSWORD},
    )

    assert response.status_code == 400
    child_a.refresh_from_db()
    assert child_a.check_password(TARGET_OLD_PASSWORD) is True
    assert AuditEvent.objects.exists() is False


@pytest.mark.parametrize('weak_password', ('short', 'password', '11111111'))
def test_a_weak_new_password_is_refused_and_never_stored(
    api_client, household_a, parent_a, child_a, weak_password
):
    sign_in(api_client, parent_a)

    response = post_reset(
        api_client,
        child_a.pk,
        {'password': ACTOR_PASSWORD, 'new_password': weak_password},
    )

    assert response.status_code == 400
    assert 'new_password' in response.json()
    child_a.refresh_from_db()
    assert child_a.check_password(TARGET_OLD_PASSWORD) is True
    assert AuditEvent.objects.exists() is False


def test_missing_new_password_is_refused_before_verification_is_attempted(
    api_client, household_a, parent_a, child_a
):
    sign_in(api_client, parent_a)

    response = post_reset(api_client, child_a.pk, {'password': ACTOR_PASSWORD})

    assert response.status_code == 400
    assert 'new_password' in response.json()


# Self-target denial


def test_a_parent_cannot_reset_their_own_password_through_this_route(
    api_client, household_a, parent_a
):
    sign_in(api_client, parent_a)

    response = post_reset(
        api_client,
        parent_a.pk,
        {'password': ACTOR_PASSWORD, 'new_password': NEW_PASSWORD},
    )

    assert response.status_code == 403
    parent_a.refresh_from_db()
    assert parent_a.check_password(ACTOR_PASSWORD) is True
    assert AuditEvent.objects.exists() is False


# Household isolation


def test_a_parent_in_another_household_cannot_reset_this_target(
    api_client, household_a, household_b, child_a
):
    outsider = make_member(
        household_b, 'synthetic-outsider', Membership.Role.PARENT, ACTOR_PASSWORD
    )
    sign_in(api_client, outsider)

    response = post_reset(
        api_client,
        child_a.pk,
        {'password': ACTOR_PASSWORD, 'new_password': NEW_PASSWORD},
    )

    assert response.status_code == 404
    child_a.refresh_from_db()
    assert child_a.check_password(TARGET_OLD_PASSWORD) is True
