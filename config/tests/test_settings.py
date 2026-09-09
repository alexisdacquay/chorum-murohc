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
        'secret_matches_file': (
            'DJANGO_SECRET_KEY_FILE' in os.environ
            and Path(os.environ['DJANGO_SECRET_KEY_FILE']).read_text().strip()
            == settings.SECRET_KEY
        ),
        'debug': settings.DEBUG,
        'allowed_hosts': settings.ALLOWED_HOSTS,
        'database_engine': database['ENGINE'],
        'database_name': str(database['NAME']),
        'database_name_is_path': isinstance(database['NAME'], Path),
        'database_keys': sorted(database),
        'database_target': os.environ.get('DJANGO_DB_TARGET'),
        'test_database_name': database.get('TEST', {}).get('NAME'),
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
        'session_cookie_age': settings.SESSION_COOKIE_AGE,
        'session_save_every_request': settings.SESSION_SAVE_EVERY_REQUEST,
        'session_expire_at_browser_close': settings.SESSION_EXPIRE_AT_BROWSER_CLOSE,
        'session_cookie_httponly': settings.SESSION_COOKIE_HTTPONLY,
        'session_cookie_samesite': settings.SESSION_COOKIE_SAMESITE,
        'session_cookie_secure': settings.SESSION_COOKIE_SECURE,
        'csrf_cookie_httponly': settings.CSRF_COOKIE_HTTPONLY,
        'csrf_cookie_samesite': settings.CSRF_COOKIE_SAMESITE,
        'csrf_cookie_secure': settings.CSRF_COOKIE_SECURE,
        'secure_ssl_redirect': settings.SECURE_SSL_REDIRECT,
        'secure_hsts_seconds': settings.SECURE_HSTS_SECONDS,
        'secure_hsts_include_subdomains': settings.SECURE_HSTS_INCLUDE_SUBDOMAINS,
        'secure_proxy_ssl_header': settings.SECURE_PROXY_SSL_HEADER,
        'silenced_system_checks': settings.SILENCED_SYSTEM_CHECKS,
        'use_https': settings.USE_HTTPS,
        'x_frame_options': settings.X_FRAME_OPTIONS,
        'static_root': str(settings.STATIC_ROOT),
        'frontend_dist': str(settings.FRONTEND_DIST),
        'cache_aliases': sorted(settings.CACHES),
        'login_throttle_cache': settings.CACHES.get('login_throttle'),
        'rest_framework_keys': sorted(settings.REST_FRAMEWORK),
        'exception_handler': settings.REST_FRAMEWORK['EXCEPTION_HANDLER'],
        'throttle_rates': settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'],
        'num_proxies': settings.REST_FRAMEWORK['NUM_PROXIES'],
        'security_logger_handlers': settings.LOGGING['loggers'][
            'chorum_murohc.security'
        ]['handlers'],
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


def guarded_postgresql_environment(target='task_t005_0123abcd'):
    database_name = f'chorum_murohc_{target}'
    return {
        'DJANGO_ENVIRONMENT': 'development',
        'DJANGO_DB_ENGINE': 'postgresql',
        'DJANGO_DB_TARGET': target,
        'DJANGO_DB_NAME': database_name,
        'DJANGO_DB_USER': database_name,
        'DJANGO_DB_PASSWORD': 'replace-at-runtime',
        'DJANGO_DB_HOST': ('127.0.0.1' if target.startswith('task_') else 'postgres'),
        'DJANGO_DB_PORT': '0005432',
    }


def assert_configuration_error(overrides, expected_message):
    result = settings_probe(overrides)

    assert result == {
        'status': 'error',
        'error_type': 'ImproperlyConfigured',
        'message': expected_message,
    }


def test_missing_variables_use_safe_development_defaults():
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


def test_loading_settings_does_not_create_the_configured_sqlite_database(tmp_path):
    database = tmp_path / 'settings-probe.sqlite3'

    assert not database.exists()

    result = settings_probe({'DJANGO_DB_NAME': str(database)})

    assert result['status'] == 'ok'
    assert result['database_engine'] == 'django.db.backends.sqlite3'
    assert result['database_name'] == str(database)
    assert result['database_name_is_path'] is True
    assert not database.exists()


def test_probe_does_not_inherit_ambient_django_variables(monkeypatch):
    monkeypatch.setenv('DJANGO_DEBUG', 'not-valid')
    monkeypatch.setenv('DJANGO_DB_TARGET', 'production')
    monkeypatch.setenv('DJANGO_DB_PASSWORD', 'ambient-value-that-must-not-escape')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://ambient.invalid/forbidden')

    result = settings_probe()

    assert result['status'] == 'ok'
    assert result['debug'] is True
    assert result['database_engine'] == 'django.db.backends.sqlite3'
    assert result['database_target'] is None


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


@pytest.mark.parametrize('target_value', ['', 'task_t005_0123abcd'])
def test_sqlite_rejects_every_present_database_target(target_value):
    assert_configuration_error(
        {'DJANGO_DB_TARGET': target_value},
        'DJANGO_DB_TARGET is invalid.',
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
    assert result['database_target'] is None
    assert result['test_database_name'] is None
    assert result['postgresql_driver_loaded'] is False


def test_postgresql_engine_accepts_normalised_value_in_development():
    environment = guarded_postgresql_environment()
    environment['DJANGO_DB_ENGINE'] = ' PoStGrEsQl '

    result = settings_probe(environment)

    assert result['status'] == 'ok'
    assert result['database_engine'] == 'django.db.backends.postgresql'


@pytest.mark.parametrize(
    'target',
    [
        'task_t000_abcdefgh',
        'task_t999_0123456789abcdef',
        'ci_1_1_abcdefgh',
        'ci_00000000000000000000_000_0123456789abcdef',
    ],
)
def test_development_postgresql_accepts_exact_target_boundaries(target):
    result = settings_probe(guarded_postgresql_environment(target))

    expected_database_name = f'chorum_murohc_{target}'
    assert result['status'] == 'ok'
    assert result['database_target'] == target
    assert result['database_name'] == expected_database_name
    assert result['test_database_name'] == f'test_{expected_database_name}'


def test_maximum_ci_target_keeps_every_derived_identifier_within_postgresql_limit():
    target = 'ci_12345678901234567890_123_0123456789abcdef'

    result = settings_probe(guarded_postgresql_environment(target))

    assert result['status'] == 'ok'
    assert len(target.encode('ascii')) == 44
    assert len(result['database_name'].encode('ascii')) == 58
    assert len(result['test_database_name'].encode('ascii')) == 63


def test_maximum_task_target_has_the_expected_derived_identifier_lengths():
    target = 'task_t005_0123456789abcdef'

    result = settings_probe(guarded_postgresql_environment(target))

    assert result['status'] == 'ok'
    assert len(target.encode('ascii')) == 26
    assert len(result['database_name'].encode('ascii')) == 40
    assert len(result['test_database_name'].encode('ascii')) == 45


def test_development_postgresql_requires_database_target():
    environment = guarded_postgresql_environment()
    environment.pop('DJANGO_DB_TARGET')

    assert_configuration_error(
        environment,
        'DJANGO_DB_TARGET is required.',
    )


@pytest.mark.parametrize(
    'target',
    [
        '',
        '   ',
        ' task_t005_0123abcd',
        'task_t005_0123abcd ',
        'task_t005_0123abcd\n',
        'TASK_t005_0123abcd',
        'task_T005_0123abcd',
        'task_t005_ABCDefgh',
        'task_t005_abcdefg',
        'task_t005_abcdefghijklmnopq',
        'task_t05_0123abcd',
        'task_t0005_0123abcd',
        'task_t005_',
        'task_t005_0123_abcd',
        'task_t005_0123-abcd',
        'task_t005_0123.abcd',
        'task_t005_0123abcé',
        'task_t٠٠٥_0123abcd',
        'ci__1_0123abcd',
        'ci_123456789012345678901_1_0123abcd',
        'ci_1__0123abcd',
        'ci_1_1234_0123abcd',
        'ci_1_1_abcdefg',
        'ci_1_1_abcdefghijklmnopq',
        'ci_1_1_0123_abcd',
        'ci_١_1_0123abcd',
        'unknown_1_1_0123abcd',
        'prod',
        'production',
        'stage',
        'staging',
        'shared',
        'main',
        'default',
        'x' * 5000,
    ],
)
def test_development_postgresql_rejects_non_contract_database_targets(target):
    environment = guarded_postgresql_environment()
    environment['DJANGO_DB_TARGET'] = target

    assert_configuration_error(environment, 'DJANGO_DB_TARGET is invalid.')


@pytest.mark.parametrize(
    ('target', 'allowed_host'),
    [
        ('task_t005_0123abcd', '127.0.0.1'),
        ('ci_123456789_1_backend01', 'postgres'),
    ],
)
def test_guarded_postgresql_accepts_only_the_host_for_its_target_lineage(
    target,
    allowed_host,
):
    result = settings_probe(guarded_postgresql_environment(target))

    assert result['status'] == 'ok'
    assert result['database_fields_match_environment']['HOST'] is True
    assert guarded_postgresql_environment(target)['DJANGO_DB_HOST'] == allowed_host


@pytest.mark.parametrize(
    'rejected_host',
    [
        '',
        ' ',
        ' 127.0.0.1',
        '127.0.0.1 ',
        'localhost',
        'postgres',
        'database.invalid',
        '/var/run/postgresql',
        'postgresql://127.0.0.1',
        '0.0.0.0',
        '::',
        '::1',
        '[::1]',
        '127.0.0.2',
        '*',
    ],
)
def test_task_target_rejects_every_non_loopback_contract_host(rejected_host):
    environment = guarded_postgresql_environment()
    environment['DJANGO_DB_HOST'] = rejected_host

    expected_message = (
        'DJANGO_DB_HOST is required.'
        if not rejected_host.strip()
        else 'DJANGO_DB_HOST is invalid.'
    )
    assert_configuration_error(environment, expected_message)


@pytest.mark.parametrize(
    'rejected_host',
    [
        '',
        ' ',
        ' postgres',
        'postgres ',
        '127.0.0.1',
        'localhost',
        'database.invalid',
        '/var/run/postgresql',
        'postgresql://postgres',
        '0.0.0.0',
        '::',
        '::1',
        '[::1]',
        '127.0.0.2',
        '*',
    ],
)
def test_ci_target_rejects_every_non_service_alias_contract_host(rejected_host):
    environment = guarded_postgresql_environment('ci_1_1_0123abcd')
    environment['DJANGO_DB_HOST'] = rejected_host

    expected_message = (
        'DJANGO_DB_HOST is required.'
        if not rejected_host.strip()
        else 'DJANGO_DB_HOST is invalid.'
    )
    assert_configuration_error(environment, expected_message)


@pytest.mark.parametrize(
    ('database_variable', 'mismatched_value'),
    [
        ('DJANGO_DB_NAME', 'chorum_murohc_task_t005_other000'),
        ('DJANGO_DB_USER', 'chorum_murohc_task_t005_other000'),
    ],
)
def test_guarded_postgresql_rejects_mismatched_derived_fields(
    database_variable,
    mismatched_value,
):
    environment = guarded_postgresql_environment()
    environment[database_variable] = mismatched_value

    assert_configuration_error(
        environment,
        f'{database_variable} is invalid.',
    )


def test_guarded_postgresql_maps_exact_derived_fields_and_normalised_port():
    environment = guarded_postgresql_environment()

    result = settings_probe(environment)

    assert result['status'] == 'ok'
    assert result['database_keys'] == [
        'ENGINE',
        'HOST',
        'NAME',
        'PASSWORD',
        'PORT',
        'TEST',
        'USER',
    ]
    assert all(result['database_fields_match_environment'].values())
    assert result['database_port'] == '5432'
    assert result['test_database_name'] == ('test_chorum_murohc_task_t005_0123abcd')


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
def test_guarded_postgresql_requires_each_non_blank_connection_field(
    database_variable,
    field_state,
):
    environment = guarded_postgresql_environment()
    if field_state == 'missing':
        environment.pop(database_variable)
    else:
        environment[database_variable] = '   '

    assert_configuration_error(
        environment,
        f'{database_variable} is required.',
    )


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


@pytest.mark.parametrize('target_value', ['', 'task_t005_0123abcd'])
def test_production_rejects_every_present_database_target(target_value):
    environment = production_environment()
    environment['DJANGO_DB_TARGET'] = target_value

    assert_configuration_error(environment, 'DJANGO_DB_TARGET is invalid.')


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


# Sessions, CSRF, and the login-abuse control (T027).


def test_session_and_csrf_cookies_are_hardened_outside_production():
    result = settings_probe()

    assert result['status'] == 'ok'
    # Script may never read the session cookie.
    assert result['session_cookie_httponly'] is True
    assert result['session_cookie_samesite'] == 'Lax'
    # The interface must read the CSRF cookie to echo its value back.
    assert result['csrf_cookie_httponly'] is False
    assert result['csrf_cookie_samesite'] == 'Lax'
    # Development serves plain HTTP, so Secure would suppress both cookies.
    assert result['session_cookie_secure'] is False
    assert result['csrf_cookie_secure'] is False
    # Forcing HTTPS or advertising HSTS on plain HTTP would break the dev
    # server, exactly like marking the cookies Secure would (S-02).
    assert result['secure_ssl_redirect'] is False
    assert result['secure_hsts_seconds'] == 0
    assert result['secure_hsts_include_subdomains'] is False


def test_production_marks_both_cookies_secure_and_keeps_every_other_rule():
    result = settings_probe(production_environment())

    assert result['status'] == 'ok'
    assert result['session_cookie_secure'] is True
    assert result['csrf_cookie_secure'] is True
    assert result['session_cookie_httponly'] is True
    assert result['csrf_cookie_httponly'] is False
    assert result['session_cookie_samesite'] == 'Lax'
    assert result['csrf_cookie_samesite'] == 'Lax'


def test_production_forces_https_and_advertises_hsts():
    """S-02: `manage.py check --deploy` warns W004 and W008 without these."""
    result = settings_probe(production_environment())

    assert result['status'] == 'ok'
    assert result['secure_ssl_redirect'] is True
    assert result['secure_hsts_seconds'] == 60 * 60 * 24 * 365
    assert result['secure_hsts_include_subdomains'] is True


def test_exactly_one_deploy_check_is_deliberately_silenced():
    """S-02: `check --deploy` is otherwise clean. W021 (HSTS preload) asks
    for submission to the browser vendors' hardcoded list, a step this
    project has not decided to take, so it is silenced rather than set."""
    result = settings_probe()

    assert result['silenced_system_checks'] == ['security.W021']


def test_session_lasts_fourteen_days_without_idle_extension():
    result = settings_probe()

    assert result['session_cookie_age'] == 60 * 60 * 24 * 14
    assert result['session_save_every_request'] is False
    assert result['session_expire_at_browser_close'] is False


def test_login_throttle_has_its_own_named_database_backed_cache():
    """Database-backed (issue 128) so every process shares one counter."""
    result = settings_probe()

    assert result['cache_aliases'] == ['default', 'login_throttle']
    assert result['login_throttle_cache'] == {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'login_throttle_cache',
    }


def test_both_login_throttle_rates_are_configured_and_nothing_else_is():
    result = settings_probe()

    assert result['throttle_rates'] == {
        'login_burst': '10/minute',
        'login_sustained': '100/hour',
    }
    # No default throttle class, so only the login view is throttled, and no
    # authentication or permission default is declared here either.
    assert result['rest_framework_keys'] == [
        'DEFAULT_THROTTLE_RATES',
        'EXCEPTION_HANDLER',
        'NUM_PROXIES',
    ]


def test_client_address_ignores_forwarding_headers():
    result = settings_probe()

    assert result['num_proxies'] == 0


def test_refusals_are_logged_through_the_security_exception_handler():
    """S-04: every refusal DRF raises goes through one logged handler."""
    result = settings_probe()

    assert result['exception_handler'] == (
        'chorum_murohc.api.security_logging.logging_exception_handler'
    )
    # Always on, not gated by DEBUG the way Django's own default console
    # handler is: a refusal in production is exactly what this is for.
    assert result['security_logger_handlers'] == ['security_console']


# The deployment settings (issue #158): one switch for the transport, and a
# secret key the container can generate for itself.


def test_the_https_switch_owns_every_transport_rule_in_production():
    result = settings_probe(production_environment())

    assert result['use_https'] is True
    assert result['session_cookie_secure'] is True
    assert result['csrf_cookie_secure'] is True
    assert result['secure_ssl_redirect'] is True
    assert result['secure_hsts_seconds'] == 60 * 60 * 24 * 365
    assert result['secure_hsts_include_subdomains'] is True
    assert result['secure_proxy_ssl_header'] == ['HTTP_X_FORWARDED_PROTO', 'https']
    # Preload is left unset on purpose by S-02, which silences W021 instead.
    assert result['silenced_system_checks'] == ['security.W021']


def test_a_plain_http_deployment_turns_every_transport_rule_off_together():
    # A household on its own network over plain HTTP, which is what the
    # shipped compose file is. A Secure cookie is never sent over HTTP and
    # the redirect would loop, so all of it goes together or not at all.
    environment = production_environment()
    environment['DJANGO_HTTPS'] = 'false'

    result = settings_probe(environment)

    assert result['use_https'] is False
    assert result['session_cookie_secure'] is False
    assert result['csrf_cookie_secure'] is False
    assert result['secure_ssl_redirect'] is False
    assert result['secure_hsts_seconds'] == 0
    assert result['secure_hsts_include_subdomains'] is False
    assert result['secure_proxy_ssl_header'] is None


def test_development_can_be_asked_for_https():
    result = settings_probe({'DJANGO_HTTPS': 'on'})

    assert result['use_https'] is True
    assert result['session_cookie_secure'] is True


@pytest.mark.parametrize('https_value', ['', ' ', 'maybe', 'True ok', '2'])
def test_an_unknown_https_value_is_rejected(https_value):
    environment = production_environment()
    environment['DJANGO_HTTPS'] = https_value

    result = settings_probe(environment)

    assert result['status'] == 'error'
    assert result['message'] == 'DJANGO_HTTPS is invalid.'


def test_nothing_may_be_framed():
    assert settings_probe()['x_frame_options'] == 'DENY'


def test_the_deployment_paths_are_where_the_build_writes():
    result = settings_probe()

    assert result['static_root'] == str(PROJECT_ROOT / 'staticfiles')
    assert result['frontend_dist'] == str(PROJECT_ROOT / 'frontend' / 'dist')


def test_the_production_default_satisfies_the_deployment_check():
    environment = production_environment()
    # The deployment check reads the key itself: it wants at least fifty
    # characters and real variety, which is what the container generates.
    environment['DJANGO_SECRET_KEY'] = (
        'deployment-check-secret-of-a-realistic-length-0123456789'
    )

    completed = subprocess.run(
        [sys.executable, 'manage.py', 'check', '--deploy'],
        cwd=PROJECT_ROOT,
        env=CHILD_ENVIRONMENT | environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    # One silenced check, W021, and nothing else to say.
    assert 'System check identified no issues (1 silenced).' in (
        completed.stdout + completed.stderr
    )


def test_production_reads_the_secret_key_from_the_named_file(tmp_path):
    key_file = tmp_path / 'secret_key'
    key_file.write_text('a-generated-key-from-the-state-volume\n')
    environment = production_environment()
    del environment['DJANGO_SECRET_KEY']
    environment['DJANGO_SECRET_KEY_FILE'] = str(key_file)

    result = settings_probe(environment)

    assert result['status'] == 'ok'
    # The trailing newline the generator writes is not part of the key.
    assert result['secret_matches_file'] is True
    assert result['uses_local_secret_fallback'] is False


def test_the_secret_key_variable_wins_when_both_are_given(tmp_path):
    key_file = tmp_path / 'secret_key'
    key_file.write_text('the-file-key')
    environment = production_environment()
    environment['DJANGO_SECRET_KEY_FILE'] = str(key_file)

    result = settings_probe(environment)

    assert result['secret_matches_environment'] is True
    assert result['secret_matches_file'] is False


@pytest.mark.parametrize('contents', ['', '   \n'])
def test_an_empty_secret_key_file_is_rejected(tmp_path, contents):
    key_file = tmp_path / 'secret_key'
    key_file.write_text(contents)
    environment = production_environment()
    del environment['DJANGO_SECRET_KEY']
    environment['DJANGO_SECRET_KEY_FILE'] = str(key_file)

    result = settings_probe(environment)

    assert result['status'] == 'error'
    assert result['message'] == 'DJANGO_SECRET_KEY_FILE is invalid.'


def test_a_missing_secret_key_file_is_rejected(tmp_path):
    environment = production_environment()
    del environment['DJANGO_SECRET_KEY']
    environment['DJANGO_SECRET_KEY_FILE'] = str(tmp_path / 'never-written')

    result = settings_probe(environment)

    assert result['status'] == 'error'
    assert result['message'] == 'DJANGO_SECRET_KEY_FILE is invalid.'
