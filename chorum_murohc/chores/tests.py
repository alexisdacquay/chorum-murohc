from decimal import Decimal
from importlib import import_module
from pathlib import Path

import pytest
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import (
    DataError,
    IntegrityError,
    connection,
    migrations,
    models,
    transaction,
)
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Lower
from django.utils import timezone

from chorum_murohc.chores.models import Chore
from chorum_murohc.identity.models import Household, Membership, User

TABLE = 'chores_chore'


def _migration_signature(model):
    return tuple(
        sorted(
            (field.name, field.deconstruct()[1:]) for field in model._meta.local_fields
        )
    )


def _index_signature(model):
    return tuple(index.deconstruct()[1:] for index in model._meta.indexes)


def test_chore_has_the_exact_runtime_model_contract():
    fields = Chore._meta.local_fields

    assert Chore.__bases__ == (models.Model,)
    assert tuple(field.name for field in fields) == (
        'id',
        'household',
        'name',
        'points',
        'is_active',
        'created_at',
        'updated_at',
    )

    implicit_id, household, name, points, is_active, created_at, updated_at = fields
    assert isinstance(implicit_id, models.BigAutoField)
    assert implicit_id.primary_key is True
    assert implicit_id.auto_created is True

    assert isinstance(household, models.ForeignKey)
    assert household.related_model is Household
    assert household.remote_field.on_delete is models.PROTECT
    assert household.remote_field.related_name == 'chores'
    assert household.null is False
    assert household.has_default() is False

    assert type(name) is models.CharField
    assert name.max_length == 100
    assert name.null is False
    assert name.blank is False
    assert name.choices is None
    assert name.unique is False
    assert name.has_default() is False

    assert type(points) is models.IntegerField
    assert points.null is False
    assert points.has_default() is False

    assert type(is_active) is models.BooleanField
    assert is_active.default is True
    assert is_active.null is False

    assert isinstance(created_at, models.DateTimeField)
    assert created_at.auto_now_add is True
    assert created_at.auto_now is False
    assert created_at.editable is False
    assert created_at.null is False

    assert isinstance(updated_at, models.DateTimeField)
    assert updated_at.auto_now is True
    assert updated_at.auto_now_add is False
    assert updated_at.editable is False
    assert updated_at.null is False

    assert Chore._meta.db_table == TABLE
    assert Chore._meta.ordering == ('name', 'id')
    assert [(index.name, index.fields) for index in Chore._meta.indexes] == [
        ('chore_hh_active_name_idx', ['household', 'is_active', 'name'])
    ]


def test_the_model_carries_no_scheduling_claiming_or_soft_delete_field():
    field_names = {field.name for field in Chore._meta.get_fields()}

    assert field_names.isdisjoint(
        {
            'deleted_at',
            'created_by',
            'category',
            'schedule',
            'due_at',
            'claimed_by',
            'assigned_to',
        }
    )
    assert not any(
        isinstance(field, models.FloatField | models.DecimalField)
        for field in Chore._meta.local_fields
    )
    assert type(Chore.objects) is models.Manager


def test_models_module_imports_only_django():
    module = import_module('chorum_murohc.chores.models')
    source_lines = Path(module.__file__).resolve().read_text().splitlines()

    assert [line for line in source_lines if line.startswith(('import ', 'from '))] == [
        'from django.core.exceptions import ValidationError',
        'from django.db import models',
        'from django.db.models.functions import Lower',
    ]


def test_named_database_constraints_are_declared_once_each():
    constraints = Chore._meta.constraints
    assert [constraint.name for constraint in constraints] == [
        'chore_hh_name_ci_unique',
        'chore_points_positive',
        'chore_name_not_blank',
    ]

    unique, points_positive, name_not_blank = constraints
    assert unique == models.UniqueConstraint(
        Lower('name'),
        'household',
        name='chore_hh_name_ci_unique',
    )
    assert isinstance(points_positive, models.CheckConstraint)
    assert points_positive.condition == models.Q(points__gte=1)
    assert isinstance(name_not_blank, models.CheckConstraint)
    assert name_not_blank.condition == ~models.Q(name='')


@pytest.mark.django_db
def test_a_valid_chore_inserts_and_reads_back_active_by_default():
    household = Household.objects.create(name='Valid household')
    before = timezone.now()

    chore = Chore.objects.create(household=household, name='Dishes', points=5)
    chore.refresh_from_db()

    assert chore.household_id == household.pk
    assert chore.name == 'Dishes'
    assert chore.points == 5
    assert type(chore.points) is int
    assert chore.is_active is True
    assert before <= chore.created_at <= timezone.now()
    assert before <= chore.updated_at <= timezone.now()
    assert timezone.is_aware(chore.created_at)
    assert timezone.is_aware(chore.updated_at)
    assert list(household.chores.all()) == [chore]


@pytest.mark.django_db
def test_zero_and_negative_points_are_rejected_and_one_point_inserts():
    household = Household.objects.create(name='Points household')

    for index, points in enumerate((0, -5)):
        with pytest.raises(IntegrityError), transaction.atomic():
            Chore.objects.create(
                household=household,
                name=f'Rejected {index}',
                points=points,
            )

    assert Chore.objects.count() == 0
    assert (
        Chore.objects.create(household=household, name='Minimum', points=1).points == 1
    )


@pytest.mark.django_db
def test_points_stay_whole_with_the_column_ceiling_as_the_only_upper_bound():
    household = Household.objects.create(name='Whole-points household')
    field = Chore._meta.get_field('points')

    for fractional in (2.5, '2.5', Decimal('2.5'), -0.5):
        with pytest.raises(ValidationError) as rejected:
            Chore(household=household, name='Fraction', points=fractional).full_clean()
        assert 'points' in rejected.value.message_dict

    # A whole value in a floating-point wrapper is not fractional, so validation
    # accepts it and the column stores a plain whole number.
    whole = Chore(household=household, name='Whole float', points=3.0)
    whole.full_clean()
    whole.save()
    whole.refresh_from_db()
    assert whole.points == 3
    assert type(whole.points) is int

    # Rejecting the fraction does not swallow the other fields' errors.
    with pytest.raises(ValidationError) as both_wrong:
        Chore(household=household, name='', points=2.5).full_clean()
    assert sorted(both_wrong.value.message_dict) == ['name', 'points']

    # No business maximum: the only bounds are the ones the backend derives
    # from the 32-bit integer column.
    assert field.get_internal_type() == 'IntegerField'
    assert field._validators == []
    minimum, maximum = connection.ops.integer_field_range('IntegerField')
    assert [validator.limit_value for validator in field.validators] == [
        minimum,
        maximum,
    ]
    generous = Chore.objects.create(household=household, name='Generous', points=100000)
    assert generous.points == 100000


@pytest.mark.django_db
def test_postgresql_refuses_a_point_value_above_the_32_bit_column():
    if connection.vendor != 'postgresql':
        pytest.skip('requires the guarded PostgreSQL target')

    household = Household.objects.create(name='Ceiling household')

    assert (
        Chore.objects.create(
            household=household,
            name='At the ceiling',
            points=2147483647,
        ).points
        == 2147483647
    )
    with pytest.raises(DataError), transaction.atomic():
        Chore.objects.create(
            household=household,
            name='Above the ceiling',
            points=2147483648,
        )


@pytest.mark.django_db
def test_names_are_trimmed_and_a_blank_name_is_rejected_by_the_database():
    household = Household.objects.create(name='Name household')

    for name in ('', '   ', '\t\n'):
        with pytest.raises(IntegrityError), transaction.atomic():
            Chore.objects.create(household=household, name=name, points=3)

    assert Chore.objects.count() == 0
    trimmed = Chore.objects.create(household=household, name=' Dishes ', points=3)
    trimmed.refresh_from_db()
    assert trimmed.name == 'Dishes'


@pytest.mark.django_db
def test_a_hundred_character_name_inserts_and_a_longer_one_is_never_truncated():
    household = Household.objects.create(name='Length household')

    longest = Chore.objects.create(household=household, name='a' * 100, points=2)
    longest.refresh_from_db()
    assert longest.name == 'a' * 100

    with pytest.raises(ValidationError) as rejected:
        Chore(household=household, name='b' * 101, points=2).full_clean()
    assert 'name' in rejected.value.message_dict

    if connection.vendor == 'postgresql':
        with pytest.raises(DataError), transaction.atomic():
            Chore.objects.create(household=household, name='b' * 101, points=2)
        assert Chore.objects.filter(name__startswith='b').count() == 0
    else:
        # SQLite does not enforce varchar length. Nothing is truncated there
        # either: the row keeps every character it was given.
        overlong = Chore.objects.create(household=household, name='b' * 101, points=2)
        overlong.refresh_from_db()
        assert overlong.name == 'b' * 101


@pytest.mark.django_db
def test_a_name_is_unique_per_household_case_insensitively_including_inactive():
    household = Household.objects.create(name='Duplicate household')
    dishes = Chore.objects.create(household=household, name='Dishes', points=5)

    for duplicate in ('Dishes', 'dishes', 'DISHES', ' Dishes '):
        with pytest.raises(IntegrityError), transaction.atomic():
            Chore.objects.create(household=household, name=duplicate, points=9)

    dishes.is_active = False
    dishes.save()
    with pytest.raises(IntegrityError), transaction.atomic():
        Chore.objects.create(household=household, name='dishes', points=9)
    assert Chore.objects.count() == 1

    dishes.delete()
    reused = Chore.objects.create(household=household, name='Dishes', points=9)
    assert reused.pk != dishes.pk
    assert list(Chore.objects.all()) == [reused]


@pytest.mark.django_db
def test_households_are_isolated_and_may_hold_the_same_chore_name():
    first_household = Household.objects.create(name='First household')
    second_household = Household.objects.create(name='Second household')

    first = Chore.objects.create(household=first_household, name='Dishes', points=5)
    second = Chore.objects.create(household=second_household, name='Dishes', points=8)

    assert first.pk != second.pk
    assert list(Chore.objects.filter(household=first_household)) == [first]
    assert list(Chore.objects.filter(household=second_household)) == [second]
    assert list(first_household.chores.all()) == [first]
    assert list(second_household.chores.all()) == [second]
    assert Chore.objects.filter(household=first_household, name='Dishes').get() == first


@pytest.mark.django_db
def test_the_pool_reads_back_alphabetically_with_an_identifier_tie_break():
    first_household = Household.objects.create(name='Ordering household')
    second_household = Household.objects.create(name='Ordering household two')

    alpha = Chore.objects.create(household=first_household, name='Alpha', points=1)
    bravo = Chore.objects.create(household=first_household, name='Bravo', points=1)
    shared_alpha = Chore.objects.create(
        household=second_household,
        name='Alpha',
        points=1,
    )

    assert list(Chore.objects.values_list('pk', flat=True)) == [
        alpha.pk,
        shared_alpha.pk,
        bravo.pk,
    ]


@pytest.mark.django_db
def test_deactivate_and_reactivate_keep_the_row_and_every_field():
    household = Household.objects.create(name='Reversible household')
    chore = Chore.objects.create(household=household, name='Bins', points=7)
    created_at = chore.created_at

    chore.is_active = False
    chore.save()
    chore.refresh_from_db()
    assert chore.is_active is False
    assert chore.name == 'Bins'
    assert chore.points == 7
    assert chore.household_id == household.pk
    assert chore.created_at == created_at
    assert Chore.objects.filter(pk=chore.pk).count() == 1
    assert list(Chore.objects.filter(household=household, is_active=True)) == []

    chore.is_active = True
    chore.save()
    chore.refresh_from_db()
    assert chore.is_active is True
    assert chore.name == 'Bins'
    assert chore.points == 7
    assert chore.created_at == created_at


@pytest.mark.django_db
def test_editing_a_chore_moves_updated_at_and_keeps_created_at_and_no_history():
    household = Household.objects.create(name='Editable household')
    chore = Chore.objects.create(household=household, name='Bins', points=7)
    created_at = chore.created_at
    first_updated_at = chore.updated_at

    chore.name = 'Recycling'
    chore.points = 12
    chore.save()
    chore.refresh_from_db()

    assert chore.name == 'Recycling'
    assert chore.points == 12
    assert chore.created_at == created_at
    assert chore.updated_at > first_updated_at
    # No previous value is kept here on purpose: the before-and-after record of
    # a chore.update belongs to the audit event owned by issue #35.
    stored = Chore.objects.values().get(pk=chore.pk)
    assert set(stored) == {
        'id',
        'household_id',
        'name',
        'points',
        'is_active',
        'created_at',
        'updated_at',
    }
    assert stored['name'] == 'Recycling'
    assert stored['points'] == 12
    text_values = {value for value in stored.values() if isinstance(value, str)}
    assert 'Bins' not in text_values


@pytest.mark.django_db
def test_a_chore_can_simply_be_deleted_with_nothing_on_this_side_protecting_it():
    household = Household.objects.create(name='Deletable household')
    chore = Chore.objects.create(household=household, name='Windows', points=4)
    surviving = Chore.objects.create(household=household, name='Floors', points=6)
    chore_pk = chore.pk

    deleted_count, deleted_by_model = chore.delete()

    assert deleted_count == 1
    assert deleted_by_model == {'chores.Chore': 1}
    assert Chore.objects.filter(pk=chore_pk).exists() is False
    assert list(Chore.objects.all()) == [surviving]
    assert Household.objects.filter(pk=household.pk).exists()
    # Removing the pending submissions of a deleted chore and nulling the
    # reference held by decided ones is the transaction owned by issues #41 and
    # #35. It is deliberately not a chores-side on_delete rule, so nothing here
    # stands between a parent and a real deletion.
    assert [
        related.name
        for related in Chore._meta.related_objects
        if related.on_delete in (models.PROTECT, models.RESTRICT)
    ] == []


@pytest.mark.django_db
def test_deleting_a_household_with_chores_is_protected_and_changes_nothing():
    household = Household.objects.create(name='Protected household')
    chore = Chore.objects.create(household=household, name='Dishes', points=5)
    original = Chore.objects.values().get(pk=chore.pk)

    with pytest.raises(ProtectedError):
        household.delete()

    assert Household.objects.filter(pk=household.pk).exists()
    assert Chore.objects.values().get(pk=chore.pk) == original


@pytest.mark.django_db
def test_deleting_a_parent_leaves_every_chore_untouched():
    household = Household.objects.create(name='Parent household')
    parent = User.objects.create_user(username='chore-owning-parent')
    Membership.objects.create(
        household=household,
        user=parent,
        role=Membership.Role.PARENT,
    )
    chore = Chore.objects.create(household=household, name='Dishes', points=5)
    original = Chore.objects.values().get(pk=chore.pk)

    parent.delete()

    assert Chore.objects.values().get(pk=chore.pk) == original
    assert Chore.objects.count() == 1
    assert not any(
        field.related_model is User
        for field in Chore._meta.local_fields
        if field.is_relation
    )


def test_initial_migration_has_the_exact_schema_only_contract():
    initial_migration = import_module('chorum_murohc.chores.migrations.0001_initial')
    migration = initial_migration.Migration('0001_initial', 'chores')

    assert migration.initial is True
    assert migration.dependencies == [('identity', '0002_household_membership')]
    assert len(migration.operations) == 1
    operation = migration.operations[0]
    assert isinstance(operation, migrations.CreateModel)
    assert operation.name == 'Chore'
    assert tuple(name for name, _ in operation.fields) == (
        'id',
        'name',
        'points',
        'is_active',
        'created_at',
        'updated_at',
        'household',
    )
    assert operation.options == {
        'ordering': ('name', 'id'),
        'indexes': [
            models.Index(
                fields=['household', 'is_active', 'name'],
                name='chore_hh_active_name_idx',
            )
        ],
        'constraints': [
            models.UniqueConstraint(
                Lower('name'),
                'household',
                name='chore_hh_name_ci_unique',
            ),
            models.CheckConstraint(
                condition=models.Q(points__gte=1),
                name='chore_points_positive',
            ),
            models.CheckConstraint(
                condition=~models.Q(name=''),
                name='chore_name_not_blank',
            ),
        ],
    }
    assert operation.managers == []


def test_the_chores_app_adds_exactly_one_migration():
    migrations_directory = (
        Path(import_module('chorum_murohc.chores.migrations').__file__).resolve().parent
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
    assert ('chores', '0001_initial') in executor.loader.disk_migrations
    assert set(executor.loader.disk_migrations) <= set(
        executor.loader.applied_migrations
    )

    migration_model = executor.loader.project_state().apps.get_model('chores', 'Chore')
    assert migration_model._meta.db_table == Chore._meta.db_table
    assert migration_model._meta.ordering == Chore._meta.ordering
    assert _migration_signature(migration_model) == _migration_signature(Chore)
    assert _index_signature(migration_model) == _index_signature(Chore)
    assert migration_model._meta.constraints == Chore._meta.constraints


@pytest.mark.django_db
def test_chore_schema_has_exact_table_columns_foreign_keys_and_indexes():
    chore_tables = {
        table
        for table in connection.introspection.table_names()
        if table.startswith('chores_')
    }
    assert chore_tables == {TABLE}

    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, TABLE)
        constraints = connection.introspection.get_constraints(cursor, TABLE)

    assert {column.name: column.null_ok for column in description} == {
        'id': False,
        'household_id': False,
        'name': False,
        'points': False,
        'is_active': False,
        'created_at': False,
        'updated_at': False,
    }
    assert any(
        constraint['columns'] == ['household_id']
        and constraint['foreign_key'] == ('identity_household', 'id')
        for constraint in constraints.values()
    )

    unique_index = constraints['chore_hh_name_ci_unique']
    assert unique_index['unique'] is True
    assert unique_index['columns'][-1] == 'household_id'

    explicit_index = constraints['chore_hh_active_name_idx']
    assert explicit_index['index'] is True
    assert explicit_index['unique'] is False
    assert explicit_index['columns'] == ['household_id', 'is_active', 'name']


@pytest.mark.django_db
def test_postgresql_reports_the_named_check_constraints():
    if connection.vendor != 'postgresql':
        pytest.skip('requires the guarded PostgreSQL target')

    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, TABLE)

    assert {
        name for name, constraint in constraints.items() if constraint['check']
    } == {
        'chore_points_positive',
        'chore_name_not_blank',
    }


def test_the_chores_package_holds_schema_modules_only():
    package_root = Path(import_module('chorum_murohc.chores').__file__).resolve().parent
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
    assert admin.site.is_registered(Chore) is False
