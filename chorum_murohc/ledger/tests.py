from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from importlib import import_module
from pathlib import Path
from threading import Barrier

import psycopg
import pytest
from django.conf import settings
from django.contrib import admin
from django.db import IntegrityError, connection, migrations, models, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models import Sum
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from chorum_murohc.audit.models import AuditEvent
from chorum_murohc.identity.models import Household, Membership, User
from chorum_murohc.ledger.models import LedgerEntry, LedgerEntryImmutableError

TABLE = 'ledger_ledgerentry'


def _entry_kwargs(household, user, **overrides):
    values = {
        'household': household,
        'user': user,
        'amount': 25,
        'reason': LedgerEntry.Reason.CHORE_CREDIT,
        'source_type': 'submissions.Submission',
        'source_id': 'submission-7',
        'idempotency_key': 'submission-7-approved',
    }
    values.update(overrides)
    return values


def _migration_signature(model):
    return tuple(
        sorted(
            (field.name, field.deconstruct()[1:]) for field in model._meta.local_fields
        )
    )


def _index_signature(model):
    return tuple(index.deconstruct()[1:] for index in model._meta.indexes)


def _connection_parameters():
    return {
        'dbname': connection.settings_dict['NAME'],
        'user': connection.settings_dict['USER'],
        'password': connection.settings_dict['PASSWORD'],
        'host': connection.settings_dict['HOST'],
        'port': connection.settings_dict['PORT'],
    }


def _insert_over_a_separate_connection(household, user, amount, key, barrier):
    backend_pid = None
    try:
        with (
            psycopg.connect(**_connection_parameters()) as raw_connection,
            raw_connection.cursor() as cursor,
        ):
            cursor.execute('SELECT pg_backend_pid()')
            backend_pid = cursor.fetchone()[0]
            barrier.wait(timeout=10)
            cursor.execute(
                f'INSERT INTO {TABLE} (household_id, user_id, amount, reason, '
                'source_type, source_id, idempotency_key, created_at) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                (
                    household.pk,
                    user.pk,
                    amount,
                    LedgerEntry.Reason.CHORE_CREDIT.value,
                    'submissions.Submission',
                    'submission-7',
                    key,
                    timezone.now(),
                ),
            )
        return 'committed', backend_pid, None
    except psycopg.errors.UniqueViolation as error:
        return 'rejected', backend_pid, error.diag.constraint_name


def test_ledger_entry_has_the_exact_runtime_model_contract():
    fields = LedgerEntry._meta.local_fields

    assert LedgerEntry.__bases__ == (models.Model,)
    assert tuple(field.name for field in fields) == (
        'id',
        'household',
        'user',
        'amount',
        'reason',
        'source_type',
        'source_id',
        'idempotency_key',
        'created_at',
    )

    (
        implicit_id,
        household,
        user,
        amount,
        reason,
        source_type,
        source_id,
        idempotency_key,
        created_at,
    ) = fields
    assert isinstance(implicit_id, models.BigAutoField)
    assert implicit_id.primary_key is True
    assert implicit_id.auto_created is True

    assert isinstance(household, models.ForeignKey)
    assert household.related_model is Household
    assert household.remote_field.on_delete is models.PROTECT
    assert household.remote_field.related_name == 'ledger_entries'
    assert household.null is False
    assert household.has_default() is False

    assert isinstance(user, models.ForeignKey)
    assert user.related_model is User
    assert user.remote_field.on_delete is models.CASCADE
    assert user.remote_field.related_name == 'ledger_entries'
    assert user.null is False
    assert user.has_default() is False

    assert type(amount) is models.BigIntegerField
    assert amount.null is False
    assert amount.has_default() is False

    assert type(reason) is models.CharField
    assert reason.max_length == 32
    assert reason.choices == LedgerEntry.Reason.choices
    assert reason.null is False
    assert reason.has_default() is False

    for field, limit in ((source_type, 100), (source_id, 255), (idempotency_key, 255)):
        assert type(field) is models.CharField
        assert field.max_length == limit
        assert field.null is False
        assert field.choices is None
        assert field.unique is False

    assert isinstance(created_at, models.DateTimeField)
    assert created_at.auto_now_add is True
    assert created_at.editable is False
    assert created_at.null is False

    assert LedgerEntry._meta.db_table == TABLE
    assert LedgerEntry._meta.ordering == ('-created_at', '-id')
    assert [(index.name, index.fields) for index in LedgerEntry._meta.indexes] == [
        ('ledger_entry_user_time_idx', ['user', '-created_at', '-id']),
        ('ledger_entry_hh_time_idx', ['household', '-created_at', '-id']),
    ]


def test_the_model_stores_no_balance_and_no_floating_point_value():
    assert not any('balance' in field.name for field in LedgerEntry._meta.get_fields())
    assert not any(
        isinstance(field, models.FloatField | models.DecimalField)
        for field in LedgerEntry._meta.local_fields
    )


def test_models_module_imports_only_django():
    module = import_module('chorum_murohc.ledger.models')
    source_lines = Path(module.__file__).resolve().read_text().splitlines()

    assert [line for line in source_lines if line.startswith(('import ', 'from '))] == [
        'from django.conf import settings',
        'from django.db import models',
    ]


def test_reason_enum_has_exactly_the_four_planned_kinds():
    assert LedgerEntry.Reason.values == [
        'chore_credit',
        'interest',
        'reward_debit',
        'level_debit',
    ]
    assert LedgerEntry.Reason.CHORE_CREDIT == 'chore_credit'
    assert LedgerEntry.Reason.INTEREST == 'interest'
    assert LedgerEntry.Reason.REWARD_DEBIT == 'reward_debit'
    assert LedgerEntry.Reason.LEVEL_DEBIT == 'level_debit'


def test_named_database_constraints_are_declared_once_each():
    constraints = LedgerEntry._meta.constraints
    assert [constraint.name for constraint in constraints] == [
        'ledger_entry_user_idempotency_key_unique',
        'ledger_entry_amount_not_zero',
        'ledger_entry_reason_valid',
    ]

    unique, amount_not_zero, reason_valid = constraints
    assert isinstance(unique, models.UniqueConstraint)
    assert unique.fields == ('user', 'idempotency_key')
    assert isinstance(amount_not_zero, models.CheckConstraint)
    assert amount_not_zero.condition == ~models.Q(amount=0)
    assert isinstance(reason_valid, models.CheckConstraint)
    assert reason_valid.condition == models.Q(
        reason__in=tuple(LedgerEntry.Reason.values)
    )


@pytest.mark.django_db
def test_a_credit_and_a_debit_both_persist_as_exact_signed_integers():
    household = Household.objects.create(name='Exact-value household')
    user = User.objects.create_user(username='exact-value-user')
    before = timezone.now()

    credit = LedgerEntry.objects.create(
        **_entry_kwargs(household, user, amount=125, idempotency_key='credit-1')
    )
    debit = LedgerEntry.objects.create(
        **_entry_kwargs(
            household,
            user,
            amount=-40,
            reason=LedgerEntry.Reason.REWARD_DEBIT,
            source_type='rewards.Redemption',
            source_id='redemption-3',
            idempotency_key='debit-1',
        )
    )

    for entry, amount in ((credit, 125), (debit, -40)):
        entry.refresh_from_db()
        assert entry.amount == amount
        assert type(entry.amount) is int
        assert entry.household_id == household.pk
        assert entry.user_id == user.pk
        assert before <= entry.created_at <= timezone.now()
        assert timezone.is_aware(entry.created_at)

    assert credit.reason == 'chore_credit'
    assert debit.reason == 'reward_debit'
    assert debit.source_type == 'rewards.Redemption'
    assert debit.source_id == 'redemption-3'


@pytest.mark.django_db
def test_balance_is_derived_by_summing_and_is_absent_without_entries():
    household = Household.objects.create(name='Balance household')
    user = User.objects.create_user(username='balance-user')
    quiet_user = User.objects.create_user(username='quiet-user')

    assert LedgerEntry.objects.filter(household=household, user=quiet_user).aggregate(
        balance=Sum('amount')
    ) == {'balance': None}
    assert (
        list(
            LedgerEntry.objects.filter(household=household, user=quiet_user)
            .values('household', 'user')
            .annotate(balance=Sum('amount'))
        )
        == []
    )

    for index, amount in enumerate((100, -30, 5)):
        LedgerEntry.objects.create(
            **_entry_kwargs(
                household,
                user,
                amount=amount,
                idempotency_key=f'balance-{index}',
            )
        )

    assert LedgerEntry.objects.filter(household=household, user=user).aggregate(
        balance=Sum('amount')
    ) == {'balance': 75}
    assert LedgerEntry.objects.filter(household=household, user=quiet_user).aggregate(
        balance=Sum('amount')
    ) == {'balance': None}


@pytest.mark.django_db
def test_a_zero_amount_is_rejected_by_the_database():
    household = Household.objects.create(name='Zero-amount household')
    user = User.objects.create_user(username='zero-amount-user')

    with pytest.raises(IntegrityError), transaction.atomic():
        LedgerEntry.objects.create(**_entry_kwargs(household, user, amount=0))

    assert LedgerEntry.objects.count() == 0
    assert (
        LedgerEntry.objects.create(**_entry_kwargs(household, user, amount=1)).amount
        == 1
    )


@pytest.mark.django_db
def test_an_unknown_reason_is_rejected_by_the_database():
    household = Household.objects.create(name='Unknown-reason household')
    user = User.objects.create_user(username='unknown-reason-user')

    with pytest.raises(IntegrityError), transaction.atomic():
        LedgerEntry.objects.create(
            **_entry_kwargs(household, user, reason='reward_reversal')
        )

    assert LedgerEntry.objects.count() == 0


@pytest.mark.django_db
def test_a_repeated_idempotency_key_is_rejected_per_user_not_globally():
    household = Household.objects.create(name='Idempotency household')
    user = User.objects.create_user(username='idempotency-user')
    other_user = User.objects.create_user(username='idempotency-other-user')
    first = LedgerEntry.objects.create(
        **_entry_kwargs(household, user, idempotency_key='retryable-append')
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        LedgerEntry.objects.create(
            **_entry_kwargs(
                household,
                user,
                amount=99,
                idempotency_key='retryable-append',
            )
        )

    assert list(LedgerEntry.objects.filter(user=user)) == [first]
    second = LedgerEntry.objects.create(
        **_entry_kwargs(household, other_user, idempotency_key='retryable-append')
    )
    assert second.pk != first.pk
    assert LedgerEntry.objects.count() == 2


@pytest.mark.django_db(transaction=True)
def test_postgresql_concurrent_duplicate_key_commits_exactly_one_row():
    if connection.vendor != 'postgresql':
        pytest.skip('requires the guarded PostgreSQL target')

    household = Household.objects.create(name='Concurrent household')
    user = User.objects.create_user(username='concurrent-user')
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                _insert_over_a_separate_connection,
                household,
                user,
                amount,
                'same-key',
                barrier,
            )
            for amount in (10, 20)
        ]
        results = [future.result(timeout=15) for future in futures]

    assert sorted(result[0] for result in results) == ['committed', 'rejected']
    assert len({result[1] for result in results}) == 2
    rejected = next(result for result in results if result[0] == 'rejected')
    assert rejected[2] == 'ledger_entry_user_idempotency_key_unique'
    assert LedgerEntry.objects.filter(user=user).count() == 1


@pytest.mark.django_db(transaction=True)
def test_postgresql_concurrent_distinct_keys_both_commit_and_sum_correctly():
    if connection.vendor != 'postgresql':
        pytest.skip('requires the guarded PostgreSQL target')

    household = Household.objects.create(name='Parallel household')
    user = User.objects.create_user(username='parallel-user')
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                _insert_over_a_separate_connection,
                household,
                user,
                amount,
                key,
                barrier,
            )
            for amount, key in ((70, 'key-a'), (-25, 'key-b'))
        ]
        results = [future.result(timeout=15) for future in futures]

    assert [result[0] for result in results] == ['committed', 'committed']
    assert LedgerEntry.objects.filter(user=user).count() == 2
    assert LedgerEntry.objects.filter(household=household, user=user).aggregate(
        balance=Sum('amount')
    ) == {'balance': 45}


@pytest.mark.django_db
def test_rows_appended_in_one_transaction_read_back_newest_first_with_id_tie_break():
    household = Household.objects.create(name='Ordering household')
    user = User.objects.create_user(username='ordering-user')

    with transaction.atomic():
        first = LedgerEntry.objects.create(
            **_entry_kwargs(household, user, idempotency_key='ordering-1')
        )
        second = LedgerEntry.objects.create(
            **_entry_kwargs(household, user, idempotency_key='ordering-2')
        )
        third = LedgerEntry.objects.create(
            **_entry_kwargs(household, user, idempotency_key='ordering-3')
        )

    assert list(LedgerEntry.objects.values_list('pk', flat=True)) == [
        third.pk,
        second.pk,
        first.pk,
    ]

    tied_time = timezone.now() - timedelta(days=1)
    with connection.cursor() as cursor:
        cursor.execute(
            f'UPDATE {TABLE} SET created_at = %s WHERE id IN (%s, %s, %s)',
            [tied_time, first.pk, second.pk, third.pk],
        )

    assert list(LedgerEntry.objects.values_list('pk', flat=True)) == [
        third.pk,
        second.pk,
        first.pk,
    ]


@pytest.mark.django_db
def test_households_are_isolated_and_summed_independently_for_one_user():
    first_household = Household.objects.create(name='First household')
    second_household = Household.objects.create(name='Second household')
    user = User.objects.create_user(username='shared-user')
    first_entry = LedgerEntry.objects.create(
        **_entry_kwargs(first_household, user, amount=60, idempotency_key='first-1')
    )
    second_entry = LedgerEntry.objects.create(
        **_entry_kwargs(second_household, user, amount=-15, idempotency_key='second-1')
    )

    assert list(LedgerEntry.objects.filter(household=first_household)) == [first_entry]
    assert list(LedgerEntry.objects.filter(household=second_household)) == [
        second_entry
    ]
    assert LedgerEntry.objects.filter(household=first_household, user=user).aggregate(
        balance=Sum('amount')
    ) == {'balance': 60}
    assert LedgerEntry.objects.filter(household=second_household, user=user).aggregate(
        balance=Sum('amount')
    ) == {'balance': -15}
    assert list(first_household.ledger_entries.all()) == [first_entry]
    assert list(user.ledger_entries.order_by('pk')) == [first_entry, second_entry]


@pytest.mark.django_db
def test_membership_is_a_service_invariant_and_not_a_database_rule():
    # Belonging to the household is enforced by the appending services in
    # T045, T052, T056 and T063, never by this schema: moving a child out of a
    # household must not destroy the points already recorded for them.
    household = Household.objects.create(name='Non-member household')
    user = User.objects.create_user(username='non-member-user')
    assert Membership.objects.filter(household=household, user=user).count() == 0

    entry = LedgerEntry.objects.create(**_entry_kwargs(household, user))

    assert LedgerEntry.objects.filter(household=household, user=user).count() == 1
    assert 'membership' not in {field.name for field in LedgerEntry._meta.local_fields}

    membership = Membership.objects.create(
        household=household,
        user=user,
        role=Membership.Role.CHILD,
    )
    membership.delete()
    entry.refresh_from_db()
    assert entry.amount == 25


@pytest.mark.django_db
def test_deleting_a_user_cascades_their_rows_and_leaves_the_audit_trail():
    household = Household.objects.create(name='Cascade household')
    user = User.objects.create_user(username='cascade-user')
    other_user = User.objects.create_user(username='cascade-other-user')
    event = AuditEvent.objects.create(
        household=household,
        actor=user,
        action='ledger.entry.appended',
        target_type='ledger.LedgerEntry',
        target_id='entry-1',
        context={'reason': 'chore_credit'},
    )
    LedgerEntry.objects.create(**_entry_kwargs(household, user))
    surviving = LedgerEntry.objects.create(**_entry_kwargs(household, other_user))
    deleted_user_pk = user.pk

    user.delete()

    assert LedgerEntry.objects.filter(user_id=deleted_user_pk).count() == 0
    assert list(LedgerEntry.objects.all()) == [surviving]
    assert Household.objects.filter(pk=household.pk).exists()
    event.refresh_from_db()
    assert event.actor_id is None
    assert event.action == 'ledger.entry.appended'
    assert event.target_type == 'ledger.LedgerEntry'
    assert event.target_id == 'entry-1'


@pytest.mark.django_db
def test_deleting_a_household_with_entries_is_protected_and_changes_nothing():
    household = Household.objects.create(name='Protected household')
    user = User.objects.create_user(username='protected-user')
    entry = LedgerEntry.objects.create(**_entry_kwargs(household, user))
    original = LedgerEntry.objects.values().get(pk=entry.pk)

    with pytest.raises(ProtectedError):
        household.delete()

    assert Household.objects.filter(pk=household.pk).exists()
    assert LedgerEntry.objects.values().get(pk=entry.pk) == original


@pytest.mark.django_db
def test_every_supported_mutation_api_is_blocked_before_a_write(
    django_assert_num_queries,
):
    household = Household.objects.create(name='Immutable household')
    user = User.objects.create_user(username='immutable-user')
    entry = LedgerEntry.objects.create(**_entry_kwargs(household, user))
    original = LedgerEntry.objects.values().get(pk=entry.pk)

    entry.amount = 9999
    blocked_operations = (
        lambda: entry.save(),
        lambda: entry.save(update_fields=['amount']),
        lambda: entry.delete(),
        lambda: LedgerEntry.objects.filter(pk=entry.pk).update(amount=9999),
        lambda: LedgerEntry.objects.filter(pk=entry.pk).delete(),
        lambda: LedgerEntry.objects.all().delete(),
        lambda: LedgerEntry.objects.bulk_update([entry], ['amount']),
        lambda: LedgerEntry.objects.bulk_create(
            [LedgerEntry(**_entry_kwargs(household, user, idempotency_key='bulk'))]
        ),
    )
    for operation in blocked_operations:
        with django_assert_num_queries(0), pytest.raises(LedgerEntryImmutableError):
            operation()

    entry.refresh_from_db()
    assert LedgerEntry.objects.count() == 1
    assert LedgerEntry.objects.values().get(pk=entry.pk) == original


@pytest.mark.django_db
def test_a_fresh_instance_cannot_overwrite_an_existing_row():
    household = Household.objects.create(name='Primary-key household')
    user = User.objects.create_user(username='primary-key-user')
    existing = LedgerEntry.objects.create(**_entry_kwargs(household, user))
    replacement = LedgerEntry(
        id=existing.pk,
        **_entry_kwargs(household, user, amount=-1, idempotency_key='replacement'),
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        replacement.save()

    existing.refresh_from_db()
    assert existing.amount == 25


@pytest.mark.django_db
def test_immutability_is_application_level_without_a_database_trigger():
    with connection.cursor() as cursor:
        if connection.vendor == 'postgresql':
            cursor.execute(
                """
                SELECT tgname
                FROM pg_trigger
                WHERE tgrelid = 'ledger_ledgerentry'::regclass
                  AND NOT tgisinternal
                """
            )
        else:
            cursor.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'trigger' AND tbl_name = 'ledger_ledgerentry'
                """
            )
        assert cursor.fetchall() == []


def test_initial_migration_has_the_exact_schema_only_contract():
    initial_migration = import_module('chorum_murohc.ledger.migrations.0001_initial')
    migration = initial_migration.Migration('0001_initial', 'ledger')

    assert migration.initial is True
    assert migration.dependencies == [
        ('identity', '0002_household_membership'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    assert len(migration.operations) == 1
    operation = migration.operations[0]
    assert isinstance(operation, migrations.CreateModel)
    assert operation.name == 'LedgerEntry'
    assert tuple(name for name, _ in operation.fields) == (
        'id',
        'amount',
        'reason',
        'source_type',
        'source_id',
        'idempotency_key',
        'created_at',
        'household',
        'user',
    )
    assert operation.options == {
        'ordering': ('-created_at', '-id'),
        'indexes': [
            models.Index(
                fields=['user', '-created_at', '-id'],
                name='ledger_entry_user_time_idx',
            ),
            models.Index(
                fields=['household', '-created_at', '-id'],
                name='ledger_entry_hh_time_idx',
            ),
        ],
        'constraints': [
            models.UniqueConstraint(
                fields=('user', 'idempotency_key'),
                name='ledger_entry_user_idempotency_key_unique',
            ),
            models.CheckConstraint(
                condition=~models.Q(amount=0),
                name='ledger_entry_amount_not_zero',
            ),
            models.CheckConstraint(
                condition=models.Q(
                    reason__in=(
                        'chore_credit',
                        'interest',
                        'reward_debit',
                        'level_debit',
                    )
                ),
                name='ledger_entry_reason_valid',
            ),
        ],
    }
    assert operation.managers == []


def test_the_ledger_app_adds_exactly_one_migration():
    migrations_directory = (
        Path(import_module('chorum_murohc.ledger.migrations').__file__).resolve().parent
    )
    assert sorted(
        path.name
        for path in migrations_directory.glob('*.py')
        if path.name != '__init__.py'
    ) == ['0001_initial.py']


@pytest.mark.django_db
def test_migration_graph_is_applied_and_runtime_matches_migration_state():
    executor = MigrationExecutor(connection)
    leaf_nodes = executor.loader.graph.leaf_nodes()

    executor.loader.graph.ensure_not_cyclic()
    assert executor.loader.detect_conflicts() == {}
    assert executor.migration_plan(leaf_nodes) == []
    assert set(executor.loader.disk_migrations) <= set(
        executor.loader.applied_migrations
    )

    migration_model = executor.loader.project_state().apps.get_model(
        'ledger',
        'LedgerEntry',
    )
    assert migration_model._meta.db_table == LedgerEntry._meta.db_table
    assert migration_model._meta.ordering == LedgerEntry._meta.ordering
    assert _migration_signature(migration_model) == _migration_signature(LedgerEntry)
    assert _index_signature(migration_model) == _index_signature(LedgerEntry)
    assert migration_model._meta.constraints == LedgerEntry._meta.constraints


@pytest.mark.django_db
def test_ledger_schema_has_exact_table_columns_foreign_keys_and_indexes():
    ledger_tables = {
        table
        for table in connection.introspection.table_names()
        if table.startswith('ledger_')
    }
    assert ledger_tables == {TABLE}

    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, TABLE)
        constraints = connection.introspection.get_constraints(cursor, TABLE)

    assert {column.name for column in description} == {
        'id',
        'household_id',
        'user_id',
        'amount',
        'reason',
        'source_type',
        'source_id',
        'idempotency_key',
        'created_at',
    }
    assert {column.name: column.null_ok for column in description} == {
        'id': False,
        'household_id': False,
        'user_id': False,
        'amount': False,
        'reason': False,
        'source_type': False,
        'source_id': False,
        'idempotency_key': False,
        'created_at': False,
    }
    assert any(
        constraint['columns'] == ['household_id']
        and constraint['foreign_key'] == ('identity_household', 'id')
        for constraint in constraints.values()
    )
    assert any(
        constraint['columns'] == ['user_id']
        and constraint['foreign_key'] == ('identity_user', 'id')
        for constraint in constraints.values()
    )
    assert any(
        constraint['unique'] and constraint['columns'] == ['user_id', 'idempotency_key']
        for constraint in constraints.values()
    )

    for name, columns in (
        ('ledger_entry_user_time_idx', ['user_id', 'created_at', 'id']),
        ('ledger_entry_hh_time_idx', ['household_id', 'created_at', 'id']),
    ):
        explicit_index = constraints[name]
        assert explicit_index['index'] is True
        assert explicit_index['unique'] is False
        assert explicit_index['columns'] == columns
        assert explicit_index['orders'] == ['ASC', 'DESC', 'DESC']


@pytest.mark.django_db
def test_postgresql_reports_the_named_check_constraints():
    if connection.vendor != 'postgresql':
        pytest.skip('requires the guarded PostgreSQL target')

    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, TABLE)

    assert {
        name for name, constraint in constraints.items() if constraint['check']
    } == {
        'ledger_entry_amount_not_zero',
        'ledger_entry_reason_valid',
    }


def test_the_ledger_package_holds_schema_modules_only():
    package_root = Path(import_module('chorum_murohc.ledger').__file__).resolve().parent
    modules = sorted(
        path.relative_to(package_root).as_posix()
        for path in package_root.rglob('*.py')
        if '__pycache__' not in path.parts
    )

    assert modules == [
        '__init__.py',
        'apps.py',
        'migrations/0001_initial.py',
        'migrations/__init__.py',
        'models.py',
        'tests.py',
    ]
    assert admin.site.is_registered(LedgerEntry) is False
