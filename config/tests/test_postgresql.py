import os

import pytest
from django.conf import settings
from django.db import connection

database_configuration = settings.DATABASES['default']
configured_base_database = database_configuration['NAME']
configured_test_database = database_configuration.get('TEST', {}).get('NAME')
requested_database_target = os.environ.get('DJANGO_DB_TARGET')


@pytest.mark.django_db
@pytest.mark.skipif(
    requested_database_target is None,
    reason='requires a requested PostgreSQL test target',
)
def test_django_uses_only_the_derived_postgresql_test_database():
    target = requested_database_target
    base_database = f'chorum_murohc_{target}'
    expected_test_database = f'test_{base_database}'

    assert database_configuration['ENGINE'] == 'django.db.backends.postgresql'
    assert connection.vendor == 'postgresql'
    assert configured_base_database == base_database
    assert configured_test_database == expected_test_database

    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database()')
        connected_database = cursor.fetchone()[0]

    assert connected_database == expected_test_database
    assert connected_database != base_database
