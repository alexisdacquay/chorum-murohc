# ruff: noqa: RUF012
"""Create the table backing the shared login-throttle cache (issue 128).

`createcachetable` is a standalone management command, not something
`migrate` runs on its own, so nothing creates a `DatabaseCache` table unless
told to. Calling it here, in a migration, keeps that table on the same
schedule as every other schema change: applied once by
`docker/entrypoint.sh`'s `migrate --noinput` on first start, and by
pytest-django when it builds a test database. No table name is passed, so
this creates a table for every cache in `settings.CACHES` that uses the
database backend - today that is `login_throttle` alone.
"""

from django.core.management import call_command
from django.db import migrations


def create_database_cache_tables(apps, schema_editor):
    call_command(
        'createcachetable', database=schema_editor.connection.alias, verbosity=0
    )


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.RunPython(
            create_database_cache_tables,
            # Nothing else depends on this table, and `createcachetable` has
            # no matching "drop" command, so the reverse is a no-op: reversing
            # this migration leaves an unused, harmless table behind.
            migrations.RunPython.noop,
        ),
    ]
