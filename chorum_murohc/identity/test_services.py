"""Tests for `chorum_murohc.identity.services` (T030, T033; issue #30).

Every fixture is synthetic. No real credential or PIN appears in the data,
the assertions, or the failure output: `assert_withholds` fails a check
without ever printing the sensitive value it was comparing, exactly as
`chorum_murohc/api/test_session.py` does for a password.

These are the storage, weakness-rule, and lockout proofs at the service
layer. The HTTP shape, the permission rows, and the compact response bodies
are proved next to the endpoint in `chorum_murohc/api/test_pin.py`.
"""

import ast
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier

import pytest
from django.contrib.auth.hashers import check_password
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity import services as services_module
from chorum_murohc.identity.models import Household, Membership, ParentPin, User
from chorum_murohc.identity.services import (
    LOCKOUT_DURATION,
    MAX_FAILED_ATTEMPTS,
    PASSWORD_CHANGE_ACTION,
    PIN_CHANGE_ACTION,
    PIN_LOCKED_ACTION,
    PIN_MAX_LENGTH,
    PIN_MIN_LENGTH,
    PIN_SET_ACTION,
    PIN_VERIFY_FAILED_ACTION,
    PasswordMismatchError,
    PasswordWeakError,
    PinFormatError,
    PinPasswordError,
    PinVerificationResult,
    PinWeakError,
    change_own_password,
    set_or_replace_pin,
    verify_pin,
)

# Synthetic throughout: none of these values is a real account or a real PIN.
SYNTHETIC_PASSWORD = 'synthetic-only-account-password-1'
SYNTHETIC_OTHER_PASSWORD = 'synthetic-only-account-password-2'
VALID_PIN = '3947'
OTHER_VALID_PIN = '8156'
LONG_VALID_PIN = '3948271605'


def latest_event_id():
    """The highest `AuditEvent` id so far, or 0. `AuditEvent` refuses delete()
    (by design: it is append-only through the application), so a test that
    wants only the events one action produced marks this before that action
    and reads `events_after` afterwards, rather than clearing the table."""
    return AuditEvent.objects.order_by('-id').values_list('id', flat=True).first() or 0


def events_after(marker_id):
    return AuditEvent.objects.filter(id__gt=marker_id).order_by('created_at', 'id')


def assert_withholds(value, *sensitive_values):
    """Fail without printing the value if it ever discloses a sensitive one."""
    rendered = repr(value)
    for sensitive_value in sensitive_values:
        if sensitive_value and sensitive_value in rendered:
            pytest.fail(
                'The value disclosed a controlled sensitive value; output withheld.',
                pytrace=False,
            )


@pytest.fixture
def household(db):
    return Household.objects.create(name='Synthetic Household')


@pytest.fixture
def other_household(db):
    return Household.objects.create(name='Synthetic Other Household')


@pytest.fixture
def parent(household):
    user = User.objects.create_user(
        username='synthetic-parent', password=SYNTHETIC_PASSWORD
    )
    Membership.objects.create(
        household=household, user=user, role=Membership.Role.PARENT
    )
    return user


@pytest.fixture
def other_parent(household):
    """A second parent of the same household, holding no PIN of their own."""
    user = User.objects.create_user(
        username='synthetic-other-parent', password=SYNTHETIC_OTHER_PASSWORD
    )
    Membership.objects.create(
        household=household, user=user, role=Membership.Role.PARENT
    )
    return user


# Model shape


def test_parent_pin_has_the_exact_runtime_model_contract():
    fields = ParentPin._meta.local_fields
    assert tuple(field.name for field in fields) == (
        'id',
        'user',
        'pin_hash',
        'failed_attempts',
        'locked_until',
        'updated_at',
    )

    user = ParentPin._meta.get_field('user')
    assert user.one_to_one is True
    assert user.related_model is User
    assert user.remote_field.on_delete.__name__ == 'CASCADE'
    assert user.remote_field.related_name == 'parent_pin'

    pin_hash = ParentPin._meta.get_field('pin_hash')
    assert pin_hash.max_length == 255

    failed_attempts = ParentPin._meta.get_field('failed_attempts')
    assert failed_attempts.has_default() is True
    assert failed_attempts.default == 0

    locked_until = ParentPin._meta.get_field('locked_until')
    assert locked_until.null is True
    assert locked_until.blank is True

    updated_at = ParentPin._meta.get_field('updated_at')
    assert updated_at.auto_now is True

    constraint_names = {constraint.name for constraint in ParentPin._meta.constraints}
    assert constraint_names == {'identity_parentpin_failed_attempts_not_negative'}


@pytest.mark.django_db
def test_the_database_rejects_a_negative_failed_attempts_value():
    user = User.objects.create_user(username='synthetic-negative-user')

    with pytest.raises(IntegrityError), transaction.atomic():
        ParentPin.objects.create(user=user, pin_hash='x', failed_attempts=-1)


# set_or_replace_pin: the current-password gate


@pytest.mark.django_db
def test_a_wrong_current_password_is_refused_and_writes_no_pin(household, parent):
    with pytest.raises(PinPasswordError):
        set_or_replace_pin(
            user=parent,
            household=household,
            current_password='not-the-real-password',
            new_pin=VALID_PIN,
        )

    assert ParentPin.objects.filter(user=parent).exists() is False
    assert AuditEvent.objects.count() == 0


# set_or_replace_pin: format


@pytest.mark.parametrize(
    'bad_pin',
    ['123', '12345678901', 'abcd', '12a4', '', '12 4'],
)
@pytest.mark.django_db
def test_a_malformed_pin_is_refused_before_any_write(household, parent, bad_pin):
    with pytest.raises(PinFormatError):
        set_or_replace_pin(
            user=parent,
            household=household,
            current_password=SYNTHETIC_PASSWORD,
            new_pin=bad_pin,
        )

    assert ParentPin.objects.filter(user=parent).exists() is False
    assert AuditEvent.objects.count() == 0


# set_or_replace_pin: the weak-PIN rules, every one behind one identical error


@pytest.mark.parametrize(
    'weak_pin',
    [
        '1111',  # every digit identical
        '1234',  # ascending run
        '9876',  # descending run
        '1212',  # short repeated pattern
        '123123',  # short repeated pattern, longer
        '0000',  # blocklisted
        '123456',  # blocklisted
    ],
)
@pytest.mark.django_db
def test_every_weak_pin_is_refused_by_one_shared_error(household, parent, weak_pin):
    with pytest.raises(PinWeakError):
        set_or_replace_pin(
            user=parent,
            household=household,
            current_password=SYNTHETIC_PASSWORD,
            new_pin=weak_pin,
        )

    assert ParentPin.objects.filter(user=parent).exists() is False


@pytest.mark.django_db
def test_resubmitting_the_current_pin_is_refused_as_weak(household, parent):
    set_or_replace_pin(
        user=parent,
        household=household,
        current_password=SYNTHETIC_PASSWORD,
        new_pin=VALID_PIN,
    )

    with pytest.raises(PinWeakError):
        set_or_replace_pin(
            user=parent,
            household=household,
            current_password=SYNTHETIC_PASSWORD,
            new_pin=VALID_PIN,
        )


# set_or_replace_pin: success


@pytest.mark.django_db
def test_the_first_pin_is_created_hashed_and_writes_pin_set(household, parent):
    before = timezone.now()

    set_or_replace_pin(
        user=parent,
        household=household,
        current_password=SYNTHETIC_PASSWORD,
        new_pin=VALID_PIN,
    )

    pin_row = ParentPin.objects.get(user=parent)
    assert pin_row.pin_hash != VALID_PIN
    assert check_password(VALID_PIN, pin_row.pin_hash) is True
    assert pin_row.failed_attempts == 0
    assert pin_row.locked_until is None
    assert_withholds(pin_row.pin_hash, VALID_PIN)

    events = list(AuditEvent.objects.all())
    assert len(events) == 1
    event = events[0]
    assert event.household == household
    assert event.actor == parent
    assert event.action == PIN_SET_ACTION
    assert event.target_type == 'identity.User'
    assert event.target_id == str(parent.pk)
    assert event.context == {}
    assert before <= event.created_at <= timezone.now()
    assert_withholds(event.context, VALID_PIN)


@pytest.mark.django_db
def test_min_and_max_length_pins_are_both_accepted(household, parent):
    set_or_replace_pin(
        user=parent,
        household=household,
        current_password=SYNTHETIC_PASSWORD,
        new_pin=VALID_PIN,
    )
    assert len(VALID_PIN) == PIN_MIN_LENGTH

    set_or_replace_pin(
        user=parent,
        household=household,
        current_password=SYNTHETIC_PASSWORD,
        new_pin=LONG_VALID_PIN,
    )
    assert len(LONG_VALID_PIN) == PIN_MAX_LENGTH


@pytest.mark.django_db
def test_replacing_an_existing_pin_writes_pin_change_and_retires_the_old_value(
    household, parent
):
    set_or_replace_pin(
        user=parent,
        household=household,
        current_password=SYNTHETIC_PASSWORD,
        new_pin=VALID_PIN,
    )

    set_or_replace_pin(
        user=parent,
        household=household,
        current_password=SYNTHETIC_PASSWORD,
        new_pin=OTHER_VALID_PIN,
    )

    assert ParentPin.objects.filter(user=parent).count() == 1
    actions = list(
        AuditEvent.objects.order_by('created_at').values_list('action', flat=True)
    )
    assert actions == [PIN_SET_ACTION, PIN_CHANGE_ACTION]

    assert verify_pin(user=parent, household=household, submitted_pin=VALID_PIN) == (
        PinVerificationResult.NO_MATCH
    )
    assert verify_pin(
        user=parent, household=household, submitted_pin=OTHER_VALID_PIN
    ) == (PinVerificationResult.MATCH)


@pytest.mark.django_db
def test_a_pin_that_matches_a_different_parent_is_an_ordinary_no_match(
    household, parent, other_parent
):
    """No hint that "another parent's PIN matched" ever escapes this function.

    `other_parent`'s PIN is a real, valid PIN; checking it against `parent`
    must be indistinguishable from checking any other wrong guess.
    """
    set_or_replace_pin(
        user=parent,
        household=household,
        current_password=SYNTHETIC_PASSWORD,
        new_pin=VALID_PIN,
    )
    set_or_replace_pin(
        user=other_parent,
        household=household,
        current_password=SYNTHETIC_OTHER_PASSWORD,
        new_pin=OTHER_VALID_PIN,
    )
    marker = latest_event_id()

    result = verify_pin(user=parent, household=household, submitted_pin=OTHER_VALID_PIN)

    assert result == PinVerificationResult.NO_MATCH
    new_events = list(events_after(marker))
    assert len(new_events) == 1
    event = new_events[0]
    assert event.action == PIN_VERIFY_FAILED_ACTION
    assert event.context == {'failed_attempts': 1}
    assert 'other' not in str(event.context).lower()
    assert str(other_parent.pk) not in str(event.context)


@pytest.mark.django_db
def test_two_parents_may_share_the_same_pin_value(household, parent, other_parent):
    set_or_replace_pin(
        user=parent,
        household=household,
        current_password=SYNTHETIC_PASSWORD,
        new_pin=VALID_PIN,
    )
    set_or_replace_pin(
        user=other_parent,
        household=household,
        current_password=SYNTHETIC_OTHER_PASSWORD,
        new_pin=VALID_PIN,
    )

    assert verify_pin(user=parent, household=household, submitted_pin=VALID_PIN) == (
        PinVerificationResult.MATCH
    )
    assert verify_pin(
        user=other_parent, household=household, submitted_pin=VALID_PIN
    ) == (PinVerificationResult.MATCH)


# verify_pin: correct, incorrect, missing, changed, cross-household


@pytest.mark.django_db
def test_a_correct_pin_matches_and_writes_no_audit_event(household, parent):
    set_or_replace_pin(
        user=parent,
        household=household,
        current_password=SYNTHETIC_PASSWORD,
        new_pin=VALID_PIN,
    )
    marker = latest_event_id()

    result = verify_pin(user=parent, household=household, submitted_pin=VALID_PIN)

    assert result == PinVerificationResult.MATCH
    assert events_after(marker).count() == 0


@pytest.mark.django_db
def test_an_incorrect_pin_does_not_match_and_writes_one_verify_failed_event(
    household, parent
):
    set_or_replace_pin(
        user=parent,
        household=household,
        current_password=SYNTHETIC_PASSWORD,
        new_pin=VALID_PIN,
    )

    result = verify_pin(user=parent, household=household, submitted_pin=OTHER_VALID_PIN)

    assert result == PinVerificationResult.NO_MATCH
    event = AuditEvent.objects.get(action=PIN_VERIFY_FAILED_ACTION)
    assert event.actor is None
    assert event.household == household
    assert event.target_type == 'identity.User'
    assert event.target_id == str(parent.pk)
    assert event.context == {'failed_attempts': 1}
    assert_withholds(event.context, VALID_PIN, OTHER_VALID_PIN)
    assert ParentPin.objects.get(user=parent).failed_attempts == 1


@pytest.mark.django_db
def test_a_parent_with_no_pin_yet_is_a_silent_no_match(household, parent):
    result = verify_pin(user=parent, household=household, submitted_pin=VALID_PIN)

    assert result == PinVerificationResult.NO_MATCH
    assert AuditEvent.objects.count() == 0


@pytest.mark.django_db
def test_cross_household_verification_is_denied_and_touches_nothing(
    household, other_household, parent
):
    set_or_replace_pin(
        user=parent,
        household=household,
        current_password=SYNTHETIC_PASSWORD,
        new_pin=VALID_PIN,
    )
    marker = latest_event_id()

    result = verify_pin(user=parent, household=other_household, submitted_pin=VALID_PIN)

    assert result == PinVerificationResult.NO_MATCH
    assert events_after(marker).count() == 0
    assert ParentPin.objects.get(user=parent).failed_attempts == 0
    # The real household is unaffected: the correct PIN still matches there.
    assert verify_pin(user=parent, household=household, submitted_pin=VALID_PIN) == (
        PinVerificationResult.MATCH
    )


# Lockout (T033)


@pytest.mark.django_db
def test_five_consecutive_failures_lock_and_the_sixth_is_refused_without_a_new_event(
    household, parent
):
    set_or_replace_pin(
        user=parent,
        household=household,
        current_password=SYNTHETIC_PASSWORD,
        new_pin=VALID_PIN,
    )
    marker = latest_event_id()

    results = [
        verify_pin(user=parent, household=household, submitted_pin=OTHER_VALID_PIN)
        for _ in range(MAX_FAILED_ATTEMPTS)
    ]

    assert results == [PinVerificationResult.NO_MATCH] * (MAX_FAILED_ATTEMPTS - 1) + [
        PinVerificationResult.LOCKED
    ]
    pin_row = ParentPin.objects.get(user=parent)
    assert pin_row.failed_attempts == MAX_FAILED_ATTEMPTS
    assert pin_row.locked_until is not None

    actions = list(events_after(marker).values_list('action', flat=True))
    assert actions == [PIN_VERIFY_FAILED_ACTION] * MAX_FAILED_ATTEMPTS + [
        PIN_LOCKED_ACTION
    ]

    # A sixth attempt, even with the correct PIN, is refused while locked and
    # writes no further event: the lockout blocks verification, full stop.
    sixth = verify_pin(user=parent, household=household, submitted_pin=VALID_PIN)
    assert sixth == PinVerificationResult.LOCKED
    assert events_after(marker).count() == MAX_FAILED_ATTEMPTS + 1
    assert ParentPin.objects.get(user=parent).failed_attempts == MAX_FAILED_ATTEMPTS


@pytest.mark.django_db
def test_a_success_resets_the_counter(household, parent):
    set_or_replace_pin(
        user=parent,
        household=household,
        current_password=SYNTHETIC_PASSWORD,
        new_pin=VALID_PIN,
    )
    verify_pin(user=parent, household=household, submitted_pin=OTHER_VALID_PIN)
    verify_pin(user=parent, household=household, submitted_pin=OTHER_VALID_PIN)
    assert ParentPin.objects.get(user=parent).failed_attempts == 2

    result = verify_pin(user=parent, household=household, submitted_pin=VALID_PIN)

    assert result == PinVerificationResult.MATCH
    pin_row = ParentPin.objects.get(user=parent)
    assert pin_row.failed_attempts == 0
    assert pin_row.locked_until is None


@pytest.mark.django_db
def test_setting_a_new_pin_clears_an_existing_lockout(household, parent):
    set_or_replace_pin(
        user=parent,
        household=household,
        current_password=SYNTHETIC_PASSWORD,
        new_pin=VALID_PIN,
    )
    for _ in range(MAX_FAILED_ATTEMPTS):
        verify_pin(user=parent, household=household, submitted_pin=OTHER_VALID_PIN)
    assert ParentPin.objects.get(user=parent).locked_until is not None

    set_or_replace_pin(
        user=parent,
        household=household,
        current_password=SYNTHETIC_PASSWORD,
        new_pin=OTHER_VALID_PIN,
    )

    pin_row = ParentPin.objects.get(user=parent)
    assert pin_row.failed_attempts == 0
    assert pin_row.locked_until is None
    assert verify_pin(
        user=parent, household=household, submitted_pin=OTHER_VALID_PIN
    ) == (PinVerificationResult.MATCH)


@pytest.mark.django_db
def test_the_lock_clears_on_expiry_and_the_next_attempt_starts_a_fresh_window(
    household, parent
):
    set_or_replace_pin(
        user=parent,
        household=household,
        current_password=SYNTHETIC_PASSWORD,
        new_pin=VALID_PIN,
    )
    for _ in range(MAX_FAILED_ATTEMPTS):
        verify_pin(user=parent, household=household, submitted_pin=OTHER_VALID_PIN)
    pin_row = ParentPin.objects.get(user=parent)
    assert pin_row.locked_until is not None

    # The window has passed; nothing but time changed.
    pin_row.locked_until = timezone.now() - timedelta(seconds=1)
    pin_row.save(update_fields=('locked_until',))

    result = verify_pin(user=parent, household=household, submitted_pin=OTHER_VALID_PIN)

    assert result == PinVerificationResult.NO_MATCH
    pin_row.refresh_from_db()
    assert pin_row.failed_attempts == 1
    assert pin_row.locked_until is None


@pytest.mark.django_db(transaction=True)
def test_concurrent_failures_never_lose_an_increment(household, parent):
    if connection.vendor != 'postgresql':
        pytest.skip('requires the guarded PostgreSQL target')

    set_or_replace_pin(
        user=parent,
        household=household,
        current_password=SYNTHETIC_PASSWORD,
        new_pin=VALID_PIN,
    )
    barrier = Barrier(2)

    def attempt():
        barrier.wait(timeout=10)
        return verify_pin(
            user=parent, household=household, submitted_pin=OTHER_VALID_PIN
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            future.result(timeout=15)
            for future in (
                executor.submit(attempt),
                executor.submit(attempt),
            )
        ]

    assert sorted(result.value for result in results) == ['no_match', 'no_match']
    assert ParentPin.objects.get(user=parent).failed_attempts == 2
    assert AuditEvent.objects.filter(action=PIN_VERIFY_FAILED_ACTION).count() == 2


# change_own_password


@pytest.mark.django_db
def test_a_wrong_current_password_is_refused_and_the_password_is_unchanged(
    household, parent
):
    with pytest.raises(PasswordMismatchError):
        change_own_password(
            user=parent,
            household=household,
            current_password='not-the-real-password',
            new_password='a genuinely unusual passphrase 42',
        )

    parent.refresh_from_db()
    assert parent.check_password(SYNTHETIC_PASSWORD) is True
    assert AuditEvent.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize('weak_password', ('short', 'password', '11111111'))
def test_a_weak_new_password_is_refused_and_the_password_is_unchanged(
    household, parent, weak_password
):
    with pytest.raises(PasswordWeakError) as excinfo:
        change_own_password(
            user=parent,
            household=household,
            current_password=SYNTHETIC_PASSWORD,
            new_password=weak_password,
        )

    assert len(excinfo.value.messages) > 0
    parent.refresh_from_db()
    assert parent.check_password(SYNTHETIC_PASSWORD) is True
    assert AuditEvent.objects.count() == 0


@pytest.mark.django_db
def test_a_successful_change_stores_the_new_password_hashed_and_writes_one_event(
    household, parent
):
    new_password = 'a genuinely unusual passphrase 42'
    before = timezone.now()

    change_own_password(
        user=parent,
        household=household,
        current_password=SYNTHETIC_PASSWORD,
        new_password=new_password,
    )

    parent.refresh_from_db()
    assert parent.check_password(new_password) is True
    assert parent.check_password(SYNTHETIC_PASSWORD) is False
    assert_withholds(parent.password, new_password)

    events = list(AuditEvent.objects.all())
    assert len(events) == 1
    event = events[0]
    assert event.household == household
    assert event.actor == parent
    assert event.action == PASSWORD_CHANGE_ACTION
    assert event.target_type == 'identity.User'
    assert event.target_id == str(parent.pk)
    assert event.context == {}
    assert before <= event.created_at <= timezone.now()


@pytest.mark.django_db
def test_changing_one_parents_password_never_touches_another_parents(
    household, parent, other_parent
):
    change_own_password(
        user=parent,
        household=household,
        current_password=SYNTHETIC_PASSWORD,
        new_password='a genuinely unusual passphrase 42',
    )

    other_parent.refresh_from_db()
    assert other_parent.check_password(SYNTHETIC_OTHER_PASSWORD) is True

    events = list(AuditEvent.objects.filter(action=PASSWORD_CHANGE_ACTION))
    assert len(events) == 1
    assert events[0].actor == parent


# What this task is not allowed to introduce


def _import_roots(module):
    source = Path(module.__file__).read_text(encoding='utf-8')
    roots = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            roots.add((node.module or '').split('.')[0])
    return roots


def test_the_service_module_imports_only_the_standard_library_django_and_chorum_murohc():
    assert _import_roots(services_module) <= {
        'django',
        'chorum_murohc',
        're',
        'enum',
        'datetime',
        'itertools',
    }


def test_the_service_module_never_imports_the_api_layer():
    source = Path(services_module.__file__).read_text(encoding='utf-8')
    tree = ast.parse(source)
    offending_names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or '']
        else:
            continue
        offending_names.extend(
            name for name in names if name.startswith('chorum_murohc.api')
        )
    assert offending_names == []


def test_the_lockout_window_matches_the_approved_policy():
    # `_docs/approval-authentication.md`: "Five consecutive failures lock
    # that parent's PIN for fifteen minutes."
    assert MAX_FAILED_ATTEMPTS == 5
    assert LOCKOUT_DURATION == timedelta(minutes=15)
