import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE = PROJECT_ROOT / 'db.sqlite3'
CHILD_ENVIRONMENT = {
    'PYTHONDONTWRITEBYTECODE': '1',
    'PYTHONIOENCODING': 'utf-8',
}

SETTINGS_PROBE = r"""
import json
import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

try:
    import config.settings as settings
except ImproperlyConfigured as error:
    result = {
        'status': 'error',
        'error_type': type(error).__name__,
        'message': str(error),
    }
else:
    database = settings.DATABASES['default']
    result = {
        'status': 'ok',
        'environment': settings.DJANGO_ENVIRONMENT,
        'uses_local_secret_fallback': (
            settings.SECRET_KEY == 'django-insecure-local-development-only'
        ),
        'secret_matches_environment': (
            'DJANGO_SECRET_KEY' in os.environ
            and settings.SECRET_KEY == os.environ['DJANGO_SECRET_KEY']
        ),
        'debug': settings.DEBUG,
        'allowed_hosts': settings.ALLOWED_HOSTS,
        'database_engine': database['ENGINE'],
        'database_name': str(database['NAME']),
        'database_name_is_path': isinstance(database['NAME'], Path),
        'database_keys': sorted(database),
        'database_fields_match_environment': {
            key: environment_name in os.environ
            and database.get(key) == os.environ[environment_name]
            for key, environment_name in {
                'NAME': 'DJANGO_DB_NAME',
                'USER': 'DJANGO_DB_USER',
                'PASSWORD': 'DJANGO_DB_PASSWORD',
                'HOST': 'DJANGO_DB_HOST',
            }.items()
        },
        'database_port': database.get('PORT'),
        'postgresql_driver_loaded': any(
            module_name == 'psycopg'
            or module_name.startswith('psycopg.')
            or module_name == 'psycopg2'
            or module_name.startswith('psycopg2.')
            for module_name in sys.modules
        ),
    }

print(json.dumps(result, sort_keys=True))
"""


def settings_probe(overrides=None):
    environment = CHILD_ENVIRONMENT.copy()
    environment.update(overrides or {})
    completed = subprocess.run(
        [sys.executable, '-c', SETTINGS_PROBE],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    for sensitive_variable in ('DJANGO_SECRET_KEY', 'DJANGO_DB_PASSWORD'):
        sensitive_value = environment.get(sensitive_variable)
        if sensitive_value and sensitive_value in (completed.stdout + completed.stderr):
            pytest.fail(
                'The isolated settings probe disclosed a controlled '
                'sensitive value; output withheld.',
                pytrace=False,
            )
    if completed.returncode:
        pytest.fail(
            'The isolated settings probe exited unexpectedly; output withheld.',
            pytrace=False,
        )
    if completed.stderr:
        pytest.fail(
            'The isolated settings probe wrote unexpected diagnostic output; '
            'output withheld.',
            pytrace=False,
        )
    return json.loads(completed.stdout)


def production_environment():
    return {
        'DJANGO_ENVIRONMENT': 'production',
        'DJANGO_SECRET_KEY': 'replace-at-runtime',
        'DJANGO_DEBUG': 'false',
        'DJANGO_ALLOWED_HOSTS': 'app.invalid',
        'DJANGO_DB_ENGINE': 'postgresql',
        'DJANGO_DB_NAME': 'app_database',
        'DJANGO_DB_USER': 'app_user',
        'DJANGO_DB_PASSWORD': 'replace-at-runtime',
        'DJANGO_DB_HOST': 'database.invalid',
        'DJANGO_DB_PORT': '5432',
    }


def assert_configuration_error(overrides, expected_message):
    result = settings_probe(overrides)

    assert result == {
        'status': 'error',
        'error_type': 'ImproperlyConfigured',
        'message': expected_message,
    }


def test_missing_variables_use_safe_development_defaults_without_creating_db():
    assert not DEFAULT_DATABASE.exists()

    result = settings_probe()

    assert result['status'] == 'ok'
    assert result['environment'] == 'development'
    assert result['uses_local_secret_fallback'] is True
    assert result['debug'] is True
    assert result['allowed_hosts'] == [
        'localhost',
        '127.0.0.1',
        '[::1]',
        'testserver',
    ]
    assert result['database_engine'] == 'django.db.backends.sqlite3'
    assert result['database_name'] == str(DEFAULT_DATABASE)
    assert result['database_name_is_path'] is True
    assert not DEFAULT_DATABASE.exists()


def test_probe_does_not_inherit_ambient_django_variables(monkeypatch):
    monkeypatch.setenv('DJANGO_DEBUG', 'not-valid')

    result = settings_probe()

    assert result['status'] == 'ok'
    assert result['debug'] is True


@pytest.mark.parametrize(
    'environment_value',
    ['development', ' DeVeLoPmEnT '],
)
def test_development_environment_accepts_normalised_values(environment_value):
    result = settings_probe({'DJANGO_ENVIRONMENT': environment_value})

    assert result['status'] == 'ok'
    assert result['environment'] == 'development'


@pytest.mark.parametrize(
    'environment_value',
    ['production', ' PrOdUcTiOn '],
)
def test_production_environment_accepts_normalised_values(environment_value):
    environment = production_environment()
    environment['DJANGO_ENVIRONMENT'] = environment_value
    environment.pop('DJANGO_DEBUG')

    result = settings_probe(environment)

    assert result['status'] == 'ok'
    assert result['environment'] == 'production'
    assert result['debug'] is False


@pytest.mark.parametrize('environment_value', ['', '   ', 'preview'])
def test_environment_rejects_empty_and_unknown_values(environment_value):
    assert_configuration_error(
        {'DJANGO_ENVIRONMENT': environment_value},
        'DJANGO_ENVIRONMENT is invalid.',
    )


def test_secret_key_is_used_verbatim_without_entering_probe_output():
    result = settings_probe({'DJANGO_SECRET_KEY': ' replace-at-runtime '})

    assert result['status'] == 'ok'
    assert result['uses_local_secret_fallback'] is False
    assert result['secret_matches_environment'] is True


def test_development_rejects_an_explicitly_blank_secret_key():
    assert_configuration_error(
        {'DJANGO_SECRET_KEY': '   '},
        'DJANGO_SECRET_KEY is invalid.',
    )


@pytest.mark.parametrize('secret_state', ['missing', 'blank'])
def test_production_rejects_missing_or_blank_secret_key(secret_state):
    environment = production_environment()
    if secret_state == 'missing':
        environment.pop('DJANGO_SECRET_KEY')
        expected_message = 'DJANGO_SECRET_KEY is required.'
    else:
        environment['DJANGO_SECRET_KEY'] = '   '
        expected_message = 'DJANGO_SECRET_KEY is invalid.'

    assert_configuration_error(environment, expected_message)


@pytest.mark.parametrize(
    ('debug_value', 'expected'),
    [
        ('1', True),
        ('true', True),
        ('yes', True),
        ('on', True),
        ('0', False),
        ('false', False),
        ('no', False),
        ('off', False),
        (' TrUe ', True),
        (' FaLsE ', False),
    ],
)
def test_debug_accepts_strict_case_insensitive_boolean_values(
    debug_value,
    expected,
):
    result = settings_probe({'DJANGO_DEBUG': debug_value})

    assert result['status'] == 'ok'
    assert result['debug'] is expected


@pytest.mark.parametrize('debug_value', ['', '   ', 'enabled', '2'])
def test_debug_rejects_empty_and_unknown_values(debug_value):
    assert_configuration_error(
        {'DJANGO_DEBUG': debug_value},
        'DJANGO_DEBUG is invalid.',
    )


@pytest.mark.parametrize('debug_value', ['1', 'true', 'yes', 'on', ' TRUE '])
def test_production_rejects_every_true_debug_value(debug_value):
    environment = production_environment()
    environment['DJANGO_DEBUG'] = debug_value

    assert_configuration_error(environment, 'DJANGO_DEBUG is invalid.')


def test_allowed_hosts_trim_whitespace_and_preserve_order():
    result = settings_probe(
        {
            'DJANGO_ALLOWED_HOSTS': (
                'first.invalid, second.invalid , [::1],first.invalid'
            )
        }
    )

    assert result['status'] == 'ok'
    assert result['allowed_hosts'] == [
        'first.invalid',
        'second.invalid',
        '[::1]',
        'first.invalid',
    ]


@pytest.mark.parametrize(
    'allowed_hosts',
    ['', '   ', ',', 'first.invalid,', ',first.invalid', 'first.invalid,,last.invalid'],
)
def test_allowed_hosts_reject_empty_lists_and_segments(allowed_hosts):
    assert_configuration_error(
        {'DJANGO_ALLOWED_HOSTS': allowed_hosts},
        'DJANGO_ALLOWED_HOSTS is invalid.',
    )


@pytest.mark.parametrize(
    'allowed_hosts',
    ['*', ' * ', 'first.invalid,*', '*,last.invalid'],
)
def test_allowed_hosts_reject_wildcards(allowed_hosts):
    assert_configuration_error(
        {'DJANGO_ALLOWED_HOSTS': allowed_hosts},
        'DJANGO_ALLOWED_HOSTS is invalid.',
    )


def test_production_requires_allowed_hosts():
    environment = production_environment()
    environment.pop('DJANGO_ALLOWED_HOSTS')

    assert_configuration_error(
        environment,
        'DJANGO_ALLOWED_HOSTS is required.',
    )


@pytest.mark.parametrize('engine_value', ['sqlite', ' SqLiTe '])
def test_sqlite_engine_accepts_normalised_values(engine_value):
    result = settings_probe({'DJANGO_DB_ENGINE': engine_value})

    assert result['status'] == 'ok'
    assert result['database_engine'] == 'django.db.backends.sqlite3'


@pytest.mark.parametrize('engine_value', ['', '   ', 'mysql'])
def test_database_engine_rejects_empty_and_unknown_values(engine_value):
    assert_configuration_error(
        {'DJANGO_DB_ENGINE': engine_value},
        'DJANGO_DB_ENGINE is invalid.',
    )


def test_sqlite_memory_name_remains_literal():
    result = settings_probe({'DJANGO_DB_NAME': ':memory:'})

    assert result['status'] == 'ok'
    assert result['database_name'] == ':memory:'
    assert result['database_name_is_path'] is False


def test_sqlite_relative_name_resolves_beneath_project_root():
    result = settings_probe({'DJANGO_DB_NAME': 'var/alternate.sqlite3'})

    assert result['status'] == 'ok'
    assert result['database_name'] == str(PROJECT_ROOT / 'var' / 'alternate.sqlite3')
    assert result['database_name_is_path'] is True


def test_sqlite_relative_name_normalises_contained_parent_segments():
    result = settings_probe({'DJANGO_DB_NAME': 'var/../alternate.sqlite3'})

    assert result['status'] == 'ok'
    assert result['database_name'] == str(PROJECT_ROOT / 'alternate.sqlite3')
    assert result['database_name_is_path'] is True


@pytest.mark.parametrize(
    'database_name',
    ['../outside.sqlite3', 'nested/../../outside.sqlite3'],
)
def test_sqlite_rejects_relative_names_that_escape_project_root(database_name):
    assert_configuration_error(
        {'DJANGO_DB_NAME': database_name},
        'DJANGO_DB_NAME is invalid.',
    )


def test_sqlite_absolute_name_remains_absolute():
    database_name = '/tmp/chorum-murohc-test.sqlite3'

    result = settings_probe({'DJANGO_DB_NAME': database_name})

    assert result['status'] == 'ok'
    assert result['database_name'] == database_name
    assert result['database_name_is_path'] is True


def test_sqlite_rejects_explicitly_empty_name():
    assert_configuration_error(
        {'DJANGO_DB_NAME': '   '},
        'DJANGO_DB_NAME is invalid.',
    )


@pytest.mark.parametrize(
    'conflicting_variable',
    [
        'DJANGO_DB_USER',
        'DJANGO_DB_PASSWORD',
        'DJANGO_DB_HOST',
        'DJANGO_DB_PORT',
    ],
)
def test_sqlite_rejects_present_postgresql_only_variables(
    conflicting_variable,
):
    assert_configuration_error(
        {conflicting_variable: ''},
        f'{conflicting_variable} conflicts with DJANGO_DB_ENGINE.',
    )


def test_postgresql_maps_required_fields_without_loading_driver():
    result = settings_probe(production_environment())

    assert result['status'] == 'ok'
    assert result['database_engine'] == 'django.db.backends.postgresql'
    assert result['database_keys'] == [
        'ENGINE',
        'HOST',
        'NAME',
        'PASSWORD',
        'PORT',
        'USER',
    ]
    assert all(result['database_fields_match_environment'].values())
    assert result['database_port'] == '5432'
    assert result['postgresql_driver_loaded'] is False


def test_postgresql_engine_accepts_normalised_value_in_development():
    environment = production_environment()
    environment['DJANGO_ENVIRONMENT'] = 'development'
    environment['DJANGO_DB_ENGINE'] = ' PoStGrEsQl '

    result = settings_probe(environment)

    assert result['status'] == 'ok'
    assert result['database_engine'] == 'django.db.backends.postgresql'


@pytest.mark.parametrize(
    'database_variable',
    [
        'DJANGO_DB_NAME',
        'DJANGO_DB_USER',
        'DJANGO_DB_PASSWORD',
        'DJANGO_DB_HOST',
        'DJANGO_DB_PORT',
    ],
)
@pytest.mark.parametrize('field_state', ['missing', 'blank'])
def test_postgresql_requires_each_non_blank_field(
    database_variable,
    field_state,
):
    environment = production_environment()
    if field_state == 'missing':
        environment.pop(database_variable)
    else:
        environment[database_variable] = '   '

    assert_configuration_error(
        environment,
        f'{database_variable} is required.',
    )


@pytest.mark.parametrize(
    'port_value',
    ['0', '65536', '-1', '+5432', '1.0', '54x2', ' 5432 ', '\u0665\u0664\u0663\u0662'],
)
def test_postgresql_rejects_out_of_range_and_non_decimal_ports(port_value):
    environment = production_environment()
    environment['DJANGO_DB_PORT'] = port_value

    assert_configuration_error(environment, 'DJANGO_DB_PORT is invalid.')


def test_postgresql_rejects_oversized_decimal_port_with_controlled_error():
    environment = production_environment()
    environment['DJANGO_DB_PORT'] = '9' * 5000

    assert_configuration_error(environment, 'DJANGO_DB_PORT is invalid.')


@pytest.mark.parametrize(
    ('port_value', 'normalised_port'),
    [('1', '1'), ('0005432', '5432'), ('65535', '65535')],
)
def test_postgresql_normalises_valid_ports(port_value, normalised_port):
    environment = production_environment()
    environment['DJANGO_DB_PORT'] = port_value

    result = settings_probe(environment)

    assert result['status'] == 'ok'
    assert result['database_port'] == normalised_port


def test_postgresql_normalises_many_leading_zeroes_without_integer_conversion():
    environment = production_environment()
    environment['DJANGO_DB_PORT'] = ('0' * 5000) + '5432'

    result = settings_probe(environment)

    assert result['status'] == 'ok'
    assert result['database_port'] == '5432'


def test_production_rejects_explicit_sqlite_engine():
    environment = production_environment()
    environment['DJANGO_DB_ENGINE'] = 'sqlite'

    assert_configuration_error(environment, 'DJANGO_DB_ENGINE is invalid.')


@pytest.mark.parametrize(
    'critical_variable',
    [
        'DJANGO_SECRET_KEY',
        'DJANGO_ALLOWED_HOSTS',
        'DJANGO_DB_ENGINE',
        'DJANGO_DB_NAME',
        'DJANGO_DB_USER',
        'DJANGO_DB_PASSWORD',
        'DJANGO_DB_HOST',
        'DJANGO_DB_PORT',
    ],
)
def test_production_fails_closed_when_critical_variable_is_missing(
    critical_variable,
):
    environment = production_environment()
    environment.pop(critical_variable)

    assert_configuration_error(
        environment,
        f'{critical_variable} is required.',
    )
