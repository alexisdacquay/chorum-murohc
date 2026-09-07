import getpass
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.management import CommandError, call_command, get_commands
from django.db import close_old_connections, connection, connections

from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity.models import Household, Membership, User

ENVIRONMENT_KEYS = (
    'CHORUM_BOOTSTRAP_HOUSEHOLD_NAME',
    'CHORUM_BOOTSTRAP_USERNAME',
    'CHORUM_BOOTSTRAP_PASSWORD',
)
HOUSEHOLD_VALUE = 'Synthetic Bootstrap Household'
USERNAME_VALUE = 'synthetic-bootstrap-parent'
PASSWORD_VALUE = 'Synthetic-only-Delta-82-Vector'
OTHER_HOUSEHOLD_VALUE = 'Different Synthetic Household'
OTHER_USERNAME_VALUE = 'different-synthetic-parent'
OTHER_PASSWORD_VALUE = 'Different-Synthetic-73-Vector'
GENERIC_ERROR = 'Bootstrap could not be completed.'
GENERIC_SUCCESS = 'Bootstrap completed.'
GENERIC_NO_CHANGE = 'Bootstrap already completed; no changes made.'


def _clear_bootstrap_environment(monkeypatch):
    for key in ENVIRONMENT_KEYS:
        monkeypatch.delenv(key, raising=False)


def _set_bootstrap_environment(
    monkeypatch,
    *,
    household=HOUSEHOLD_VALUE,
    username=USERNAME_VALUE,
    password=PASSWORD_VALUE,
):
    _clear_bootstrap_environment(monkeypatch)
    monkeypatch.setenv(ENVIRONMENT_KEYS[0], household)
    monkeypatch.setenv(ENVIRONMENT_KEYS[1], username)
    monkeypatch.setenv(ENVIRONMENT_KEYS[2], password)


def _invoke_no_input(
    monkeypatch,
    *,
    household=HOUSEHOLD_VALUE,
    username=USERNAME_VALUE,
    password=PASSWORD_VALUE,
):
    _set_bootstrap_environment(
        monkeypatch,
        household=household,
        username=username,
        password=password,
    )
    stdout = StringIO()
    stderr = StringIO()
    with (
        patch('builtins.input', side_effect=AssertionError('unexpected prompt')),
        patch.object(
            getpass,
            'getpass',
            side_effect=AssertionError('unexpected password prompt'),
        ),
    ):
        call_command(
            'bootstrap_household',
            '--no-input',
            stdout=stdout,
            stderr=stderr,
        )
    return stdout.getvalue(), stderr.getvalue()


def _captured_failure(callable_):
    with pytest.raises(CommandError) as error:
        callable_()
    return str(error.value)


def _contains_any_sensitive_value(text, extra_values=()):
    values = (
        HOUSEHOLD_VALUE,
        USERNAME_VALUE,
        PASSWORD_VALUE,
        OTHER_HOUSEHOLD_VALUE,
        OTHER_USERNAME_VALUE,
        OTHER_PASSWORD_VALUE,
        *extra_values,
    )
    database_value = settings.DATABASES['default'].get('PASSWORD')
    if database_value:
        values = (*values, str(database_value))
    return any(value and value in text for value in values)


def _assert_generic_safe_output(text, expected):
    assert text.strip() == expected
    assert _contains_any_sensitive_value(text) is False


def _state_counts():
    return (
        User.objects.count(),
        Household.objects.count(),
        Membership.objects.count(),
        AuditEvent.objects.count(),
    )


def _state_digest():
    state = (
        tuple(User.objects.order_by('pk').values()),
        tuple(Household.objects.order_by('pk').values()),
        tuple(Membership.objects.order_by('pk').values()),
        tuple(AuditEvent.objects.order_by('pk').values()),
    )
    return hashlib.sha256(repr(state).encode()).hexdigest()


def _assert_exact_bootstrap_state(
    *,
    household_name=HOUSEHOLD_VALUE,
    username=USERNAME_VALUE,
    password=PASSWORD_VALUE,
):
    assert _state_counts() == (1, 1, 1, 2)
    user = User.objects.get()
    household = Household.objects.get()
    membership = Membership.objects.get()
    assert user.username == User.normalize_username(username)
    assert user.password != password
    assert user.check_password(password) is True
    assert user.check_password(OTHER_PASSWORD_VALUE) is False
    assert user.is_active is True
    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.first_name == ''
    assert user.last_name == ''
    assert user.email == ''
    assert user.last_login is None
    assert household.name == household_name
    assert membership.household == household
    assert membership.user == user
    assert membership.role == Membership.Role.PARENT

    events = {event.action: event for event in AuditEvent.objects.all()}
    assert set(events) == {
        'bootstrap.household.created',
        'bootstrap.parent.created',
    }
    household_event = events['bootstrap.household.created']
    parent_event = events['bootstrap.parent.created']
    assert household_event.household == household
    assert household_event.actor is None
    assert household_event.target_type == 'identity.Household'
    assert household_event.target_id == str(household.pk)
    assert household_event.context == {}
    assert parent_event.household == household
    assert parent_event.actor is None
    assert parent_event.target_type == 'identity.User'
    assert parent_event.target_id == str(user.pk)
    assert parent_event.context == {'role': 'parent'}
    serialized_contexts = json.dumps([event.context for event in events.values()])
    assert _contains_any_sensitive_value(serialized_contexts) is False
    return user, household


def _delete_audit_event(event):
    with connection.cursor() as cursor:
        cursor.execute('DELETE FROM audit_auditevent WHERE id = %s', [event.pk])


def test_command_is_discoverable_with_only_the_no_input_custom_option():
    assert get_commands()['bootstrap_household'] == 'chorum_murohc.identity'

    from chorum_murohc.identity.management.commands.bootstrap_household import (
        Command,
    )

    parser = Command().create_parser('manage.py', 'bootstrap_household')
    no_input_actions = [
        action for action in parser._actions if action.dest == 'no_input'
    ]
    assert len(no_input_actions) == 1
    assert no_input_actions[0].option_strings == ['--no-input']
    assert no_input_actions[0].nargs == 0
    assert all(
        'password' not in option
        for action in parser._actions
        for option in action.option_strings
    )
    assert not any(
        not action.option_strings and action.dest != 'args'
        for action in parser._actions
    )


@pytest.mark.django_db
def test_interactive_mode_uses_exact_prompts_and_ignores_environment(monkeypatch):
    _set_bootstrap_environment(
        monkeypatch,
        household=OTHER_HOUSEHOLD_VALUE,
        username=OTHER_USERNAME_VALUE,
        password=OTHER_PASSWORD_VALUE,
    )
    stdout = StringIO()
    stderr = StringIO()
    with (
        patch(
            'builtins.input',
            side_effect=[HOUSEHOLD_VALUE, USERNAME_VALUE],
        ) as input_prompt,
        patch.object(
            getpass,
            'getpass',
            side_effect=[PASSWORD_VALUE, PASSWORD_VALUE],
        ) as password_prompt,
    ):
        call_command('bootstrap_household', stdout=stdout, stderr=stderr)

    assert [call.args for call in input_prompt.call_args_list] == [
        ('Household name: ',),
        ('Parent username: ',),
    ]
    assert [call.args for call in password_prompt.call_args_list] == [
        ('Password: ',),
        ('Confirm password: ',),
    ]
    _assert_generic_safe_output(stdout.getvalue(), GENERIC_SUCCESS)
    assert stderr.getvalue() == ''
    _assert_exact_bootstrap_state()


@pytest.mark.django_db
def test_interactive_password_mismatch_fails_before_any_write(monkeypatch):
    _clear_bootstrap_environment(monkeypatch)
    stdout = StringIO()
    stderr = StringIO()
    with (
        patch('builtins.input', side_effect=[HOUSEHOLD_VALUE, USERNAME_VALUE]),
        patch.object(
            getpass,
            'getpass',
            side_effect=[PASSWORD_VALUE, OTHER_PASSWORD_VALUE],
        ),
    ):
        error_text = _captured_failure(
            lambda: call_command(
                'bootstrap_household',
                stdout=stdout,
                stderr=stderr,
            )
        )

    _assert_generic_safe_output(error_text, GENERIC_ERROR)
    assert _contains_any_sensitive_value(stdout.getvalue() + stderr.getvalue()) is False
    assert _state_counts() == (0, 0, 0, 0)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('missing_key', 'replacement'),
    [
        (ENVIRONMENT_KEYS[0], None),
        (ENVIRONMENT_KEYS[1], None),
        (ENVIRONMENT_KEYS[2], None),
        (ENVIRONMENT_KEYS[0], ''),
        (ENVIRONMENT_KEYS[1], ''),
        (ENVIRONMENT_KEYS[2], ''),
    ],
)
def test_no_input_requires_every_exact_nonempty_environment_value(
    monkeypatch,
    missing_key,
    replacement,
):
    _set_bootstrap_environment(monkeypatch)
    if replacement is None:
        monkeypatch.delenv(missing_key)
    else:
        monkeypatch.setenv(missing_key, replacement)
    stdout = StringIO()
    stderr = StringIO()

    with (
        patch('builtins.input', side_effect=AssertionError('unexpected prompt')),
        patch.object(
            getpass,
            'getpass',
            side_effect=AssertionError('unexpected password prompt'),
        ),
    ):
        error_text = _captured_failure(
            lambda: call_command(
                'bootstrap_household',
                '--no-input',
                stdout=stdout,
                stderr=stderr,
            )
        )

    _assert_generic_safe_output(error_text, GENERIC_ERROR)
    assert _contains_any_sensitive_value(stdout.getvalue() + stderr.getvalue()) is False
    assert _state_counts() == (0, 0, 0, 0)


@pytest.mark.django_db
def test_first_no_input_run_creates_exact_state_and_secret_safe_output(
    monkeypatch,
    caplog,
):
    stdout, stderr = _invoke_no_input(monkeypatch)

    _assert_generic_safe_output(stdout, GENERIC_SUCCESS)
    assert stderr == ''
    user, _ = _assert_exact_bootstrap_state()
    captured = (
        stdout + stderr + ''.join(record.getMessage() for record in caplog.records)
    )
    assert _contains_any_sensitive_value(captured, (user.password,)) is False


@pytest.mark.django_db
def test_exact_repeat_is_a_no_op_even_with_later_unrelated_product_rows(monkeypatch):
    _invoke_no_input(monkeypatch)
    user, household = _assert_exact_bootstrap_state()
    other_user = User.objects.create_user(username='later-unrelated-user')
    other_household = Household.objects.create(name='Later unrelated household')
    Membership.objects.create(
        user=other_user,
        household=other_household,
        role=Membership.Role.CHILD,
    )
    AuditEvent.objects.create(
        household=household,
        actor=None,
        action='unrelated.event',
        target_type='identity.User',
        target_id=str(user.pk),
        context={'safe': True},
    )
    before_counts = _state_counts()
    before_digest = _state_digest()
    before_hash = user.password
    before_dates = (
        user.date_joined,
        tuple(AuditEvent.objects.order_by('pk').values_list('created_at', flat=True)),
    )

    stdout, stderr = _invoke_no_input(monkeypatch)

    _assert_generic_safe_output(stdout, GENERIC_NO_CHANGE)
    assert stderr == ''
    assert _state_counts() == before_counts
    assert _state_digest() == before_digest
    user.refresh_from_db()
    assert user.password == before_hash
    assert (
        user.date_joined,
        tuple(AuditEvent.objects.order_by('pk').values_list('created_at', flat=True)),
    ) == before_dates


@pytest.mark.django_db
@pytest.mark.parametrize('different_field', ['household', 'username', 'password'])
def test_different_repeat_input_fails_without_changing_state(
    monkeypatch,
    different_field,
):
    _invoke_no_input(monkeypatch)
    before_counts = _state_counts()
    before_digest = _state_digest()
    values = {
        'household': HOUSEHOLD_VALUE,
        'username': USERNAME_VALUE,
        'password': PASSWORD_VALUE,
    }
    values[different_field] = {
        'household': OTHER_HOUSEHOLD_VALUE,
        'username': OTHER_USERNAME_VALUE,
        'password': OTHER_PASSWORD_VALUE,
    }[different_field]

    error_text = _captured_failure(lambda: _invoke_no_input(monkeypatch, **values))

    _assert_generic_safe_output(error_text, GENERIC_ERROR)
    assert _state_counts() == before_counts
    assert _state_digest() == before_digest


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('field_name', 'changed_value'),
    [('is_active', False), ('is_staff', True), ('is_superuser', True)],
)
def test_changed_user_flags_make_repeat_a_read_only_conflict(
    monkeypatch,
    field_name,
    changed_value,
):
    _invoke_no_input(monkeypatch)
    User.objects.update(**{field_name: changed_value})
    before_digest = _state_digest()

    error_text = _captured_failure(lambda: _invoke_no_input(monkeypatch))

    _assert_generic_safe_output(error_text, GENERIC_ERROR)
    assert _state_digest() == before_digest


@pytest.mark.django_db
def test_changed_membership_role_makes_repeat_a_read_only_conflict(monkeypatch):
    _invoke_no_input(monkeypatch)
    Membership.objects.update(role=Membership.Role.CHILD)
    before_digest = _state_digest()

    error_text = _captured_failure(lambda: _invoke_no_input(monkeypatch))

    _assert_generic_safe_output(error_text, GENERIC_ERROR)
    assert _state_digest() == before_digest


@pytest.mark.django_db
@pytest.mark.parametrize(
    'marker_problem', ['missing', 'duplicate', 'malformed', 'extra']
)
def test_invalid_bootstrap_markers_make_repeat_a_read_only_conflict(
    monkeypatch,
    marker_problem,
):
    _invoke_no_input(monkeypatch)
    user = User.objects.get()
    household = Household.objects.get()
    if marker_problem == 'missing':
        _delete_audit_event(AuditEvent.objects.get(action='bootstrap.parent.created'))
    elif marker_problem == 'duplicate':
        AuditEvent.objects.create(
            household=household,
            actor=None,
            action='bootstrap.parent.created',
            target_type='identity.User',
            target_id=str(user.pk),
            context={'role': 'parent'},
        )
    elif marker_problem == 'malformed':
        _delete_audit_event(AuditEvent.objects.get(action='bootstrap.parent.created'))
        AuditEvent.objects.create(
            household=household,
            actor=None,
            action='bootstrap.parent.created',
            target_type='identity.User',
            target_id=str(user.pk),
            context={},
        )
    else:
        AuditEvent.objects.create(
            household=household,
            actor=None,
            action='bootstrap.unexpected',
            target_type='identity.Household',
            target_id=str(household.pk),
            context={},
        )
    before_digest = _state_digest()

    error_text = _captured_failure(lambda: _invoke_no_input(monkeypatch))

    _assert_generic_safe_output(error_text, GENERIC_ERROR)
    assert _state_digest() == before_digest


@pytest.mark.django_db
@pytest.mark.parametrize('partial_state', ['user', 'household', 'membership', 'event'])
def test_partial_or_manual_product_state_is_never_adopted_or_repaired(
    monkeypatch,
    partial_state,
):
    if partial_state == 'user':
        User.objects.create_user(username='manual-user')
    elif partial_state == 'household':
        Household.objects.create(name='Manual household')
    elif partial_state == 'membership':
        user = User.objects.create_user(username='manual-member')
        household = Household.objects.create(name='Manual member household')
        Membership.objects.create(
            user=user,
            household=household,
            role=Membership.Role.PARENT,
        )
    else:
        household = Household.objects.create(name='Manual event household')
        AuditEvent.objects.create(
            household=household,
            actor=None,
            action='manual.event',
            target_type='identity.Household',
            target_id=str(household.pk),
            context={},
        )
    before_counts = _state_counts()
    before_digest = _state_digest()

    error_text = _captured_failure(lambda: _invoke_no_input(monkeypatch))

    _assert_generic_safe_output(error_text, GENERIC_ERROR)
    assert _state_counts() == before_counts
    assert _state_digest() == before_digest


@pytest.mark.django_db
def test_failures_after_every_creation_stage_roll_back_all_product_rows(monkeypatch):
    from chorum_murohc.identity.management.commands import bootstrap_household

    _set_bootstrap_environment(monkeypatch)
    for failure_stage in range(1, 6):
        original_audit_create = AuditEvent.objects.create
        audit_calls = 0

        def audit_create(
            *args,
            _failure_stage=failure_stage,
            _original_audit_create=original_audit_create,
            **kwargs,
        ):
            nonlocal audit_calls
            audit_calls += 1
            if _failure_stage == 3:
                raise RuntimeError('synthetic stage failure')
            if _failure_stage == 4 and audit_calls == 2:
                raise RuntimeError('synthetic stage failure')
            event = _original_audit_create(*args, **kwargs)
            if _failure_stage == 5 and audit_calls == 2:
                raise RuntimeError('synthetic stage failure')
            return event

        household_effect = (
            RuntimeError('synthetic stage failure') if failure_stage == 1 else None
        )
        membership_effect = (
            RuntimeError('synthetic stage failure') if failure_stage == 2 else None
        )
        with (
            patch.object(
                bootstrap_household.Household.objects,
                'create',
                side_effect=household_effect,
                wraps=bootstrap_household.Household.objects.create,
            ),
            patch.object(
                bootstrap_household.Membership.objects,
                'create',
                side_effect=membership_effect,
                wraps=bootstrap_household.Membership.objects.create,
            ),
            patch.object(
                bootstrap_household.AuditEvent.objects,
                'create',
                side_effect=audit_create,
            ),
        ):
            error_text = _captured_failure(
                lambda: call_command('bootstrap_household', '--no-input')
            )

        _assert_generic_safe_output(error_text, GENERIC_ERROR)
        assert _state_counts() == (0, 0, 0, 0)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('household', 'username', 'password'),
    [
        ('', USERNAME_VALUE, PASSWORD_VALUE),
        ('   ', USERNAME_VALUE, PASSWORD_VALUE),
        (f' {HOUSEHOLD_VALUE}', USERNAME_VALUE, PASSWORD_VALUE),
        (f'{HOUSEHOLD_VALUE} ', USERNAME_VALUE, PASSWORD_VALUE),
        ('h' * 151, USERNAME_VALUE, PASSWORD_VALUE),
        (HOUSEHOLD_VALUE, '', PASSWORD_VALUE),
        (HOUSEHOLD_VALUE, '   ', PASSWORD_VALUE),
        (HOUSEHOLD_VALUE, f' {USERNAME_VALUE}', PASSWORD_VALUE),
        (HOUSEHOLD_VALUE, f'{USERNAME_VALUE} ', PASSWORD_VALUE),
        (HOUSEHOLD_VALUE, 'u' * 151, PASSWORD_VALUE),
        (HOUSEHOLD_VALUE, 'invalid/name', PASSWORD_VALUE),
        (HOUSEHOLD_VALUE, USERNAME_VALUE, 'short'),
        (HOUSEHOLD_VALUE, USERNAME_VALUE, '12345678'),
    ],
    ids=(
        'blank-household',
        'whitespace-household',
        'leading-household-space',
        'trailing-household-space',
        'long-household',
        'blank-username',
        'whitespace-username',
        'leading-username-space',
        'trailing-username-space',
        'long-username',
        'invalid-native-username',
        'short-password',
        'numeric-password',
    ),
)
def test_invalid_native_input_and_password_validation_fail_before_writes(
    monkeypatch,
    household,
    username,
    password,
):
    error_text = _captured_failure(
        lambda: _invoke_no_input(
            monkeypatch,
            household=household,
            username=username,
            password=password,
        )
    )

    _assert_generic_safe_output(error_text, GENERIC_ERROR)
    assert _state_counts() == (0, 0, 0, 0)


@pytest.mark.django_db
def test_boundary_lengths_and_native_username_normalisation_are_preserved(
    monkeypatch,
):
    household = 'h' * Household._meta.get_field('name').max_length
    raw_username = 'Ｐ' + ('u' * 149)
    normalized_username = User.normalize_username(raw_username)

    stdout, _ = _invoke_no_input(
        monkeypatch,
        household=household,
        username=raw_username,
    )

    _assert_generic_safe_output(stdout, GENERIC_SUCCESS)
    user, created_household = _assert_exact_bootstrap_state(
        household_name=household,
        username=normalized_username,
    )
    assert user.username == normalized_username
    assert user.username != raw_username
    assert created_household.name == household


def _threaded_command(barrier, values):
    close_old_connections()
    stdout = StringIO()
    stderr = StringIO()
    try:
        barrier.wait(timeout=10)
        with patch.dict(
            'os.environ',
            {
                ENVIRONMENT_KEYS[0]: values[0],
                ENVIRONMENT_KEYS[1]: values[1],
                ENVIRONMENT_KEYS[2]: values[2],
            },
        ):
            call_command(
                'bootstrap_household',
                '--no-input',
                stdout=stdout,
                stderr=stderr,
            )
        return 'success', stdout.getvalue(), stderr.getvalue()
    except CommandError as error:
        return 'error', str(error), stderr.getvalue()
    finally:
        connections.close_all()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('different_inputs', [False, True])
def test_postgresql_concurrent_bootstrap_is_serialized_without_partial_state(
    different_inputs,
):
    if connection.vendor != 'postgresql':
        pytest.skip('requires the guarded PostgreSQL target')
    barrier = Barrier(2)
    first_values = (HOUSEHOLD_VALUE, USERNAME_VALUE, PASSWORD_VALUE)
    second_values = (
        (OTHER_HOUSEHOLD_VALUE, OTHER_USERNAME_VALUE, OTHER_PASSWORD_VALUE)
        if different_inputs
        else first_values
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_threaded_command, barrier, first_values),
            executor.submit(_threaded_command, barrier, second_values),
        ]
        results = [future.result(timeout=20) for future in futures]

    if different_inputs:
        assert sorted(result[0] for result in results) == ['error', 'success']
        complete_states = []
        for household, username, password in (first_values, second_values):
            user = User.objects.filter(
                username=User.normalize_username(username)
            ).first()
            if user is not None:
                complete_states.append((household, username, password))
        assert len(complete_states) == 1
        _assert_exact_bootstrap_state(
            household_name=complete_states[0][0],
            username=complete_states[0][1],
            password=complete_states[0][2],
        )
    else:
        assert [result[0] for result in results] == ['success', 'success']
        outputs = {result[1].strip() for result in results}
        assert outputs == {GENERIC_SUCCESS, GENERIC_NO_CHANGE}
        _assert_exact_bootstrap_state()
    combined_output = ''.join(part for result in results for part in result[1:])
    assert _contains_any_sensitive_value(combined_output) is False
