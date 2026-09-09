"""Tests for the `LevelAcknowledgement` model.

These prove the schema and its constraints only: the level arithmetic lives
in `services.py` and is proved in `test_services.py`, and the HTTP shape is
proved in `chorum_murohc/api/test_progression.py`.

Every fixture is synthetic. No credential, PIN, token, cookie or personal
datum appears in the data, the assertions or the failure output: the test
users are created without a usable password, so there is nothing sensitive to
print.
"""

from pathlib import Path

import pytest
from django.contrib import admin
from django.db import IntegrityError, connection, models, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError

from chorum_murohc.identity.models import Household, Membership, User
from chorum_murohc.progression.models import MAX_LEVEL, LevelAcknowledgement

TABLE = 'progression_levelacknowledgement'


def _migration_signature(model):
    return tuple(
        sorted(
            (field.name, field.deconstruct()[1:]) for field in model._meta.local_fields
        )
    )


def _household(name='Progression household'):
    return Household.objects.create(name=name)


def _child(household, username='child'):
    user = User.objects.create_user(username=username)
    Membership.objects.create(
        household=household, user=user, role=Membership.Role.CHILD
    )
    return user


def test_the_model_has_the_exact_runtime_contract():
    fields = LevelAcknowledgement._meta.local_fields

    assert LevelAcknowledgement.__bases__ == (models.Model,)
    assert tuple(field.name for field in fields) == (
        'id',
        'household',
        'user',
        'highest_level_shown',
        'updated_at',
    )

    implicit_id, household, user, highest_level_shown, updated_at = fields

    assert isinstance(implicit_id, models.BigAutoField)
    assert implicit_id.primary_key is True

    assert isinstance(household, models.ForeignKey)
    assert household.related_model is Household
    assert household.remote_field.on_delete is models.PROTECT
    assert household.remote_field.related_name == 'level_acknowledgements'

    assert isinstance(user, models.ForeignKey)
    assert user.related_model is User
    assert user.remote_field.on_delete is models.CASCADE
    assert user.remote_field.related_name == 'level_acknowledgements'

    assert type(highest_level_shown) is models.PositiveSmallIntegerField
    assert highest_level_shown.default == 0
    assert highest_level_shown.null is False

    assert isinstance(updated_at, models.DateTimeField)
    assert updated_at.auto_now is True


def test_models_module_imports_only_django():
    source = Path(LevelAcknowledgement.__module__.replace('.', '/') + '.py').read_text(
        encoding='utf-8'
    )
    assert 'rest_framework' not in source
    assert 'django.urls' not in source


@pytest.mark.django_db
def test_creating_a_row_defaults_the_marker_to_zero(db):
    household = _household()
    child = _child(household)

    row = LevelAcknowledgement.objects.create(household=household, user=child)

    assert row.highest_level_shown == 0


@pytest.mark.django_db
def test_a_household_and_user_pair_is_unique():
    household = _household()
    child = _child(household)
    LevelAcknowledgement.objects.create(household=household, user=child)

    with pytest.raises(IntegrityError), transaction.atomic():
        LevelAcknowledgement.objects.create(household=household, user=child)


@pytest.mark.django_db
def test_the_same_user_may_hold_one_row_per_household():
    household_a = _household('Household A')
    household_b = _household('Household B')
    child = User.objects.create_user(username='two-household-child')
    Membership.objects.create(
        household=household_a, user=child, role=Membership.Role.CHILD
    )
    Membership.objects.create(
        household=household_b, user=child, role=Membership.Role.CHILD
    )

    LevelAcknowledgement.objects.create(household=household_a, user=child)
    LevelAcknowledgement.objects.create(household=household_b, user=child)

    assert LevelAcknowledgement.objects.filter(user=child).count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize('value', (-1, MAX_LEVEL + 1))
def test_the_marker_must_stay_within_the_valid_level_range_at_the_database(value):
    household = _household()
    child = _child(household)

    with pytest.raises(IntegrityError), transaction.atomic():
        LevelAcknowledgement.objects.create(
            household=household, user=child, highest_level_shown=value
        )


@pytest.mark.django_db
@pytest.mark.parametrize('value', (0, MAX_LEVEL))
def test_the_marker_accepts_its_own_boundary_values(value):
    household = _household()
    child = _child(household)

    row = LevelAcknowledgement.objects.create(
        household=household, user=child, highest_level_shown=value
    )

    assert row.highest_level_shown == value


@pytest.mark.django_db
def test_deleting_the_household_is_protected():
    household = _household()
    child = _child(household)
    LevelAcknowledgement.objects.create(household=household, user=child)

    with pytest.raises(ProtectedError):
        household.delete()

    assert LevelAcknowledgement.objects.count() == 1


@pytest.mark.django_db
def test_deleting_the_child_removes_their_row():
    household = _household()
    child = _child(household)
    LevelAcknowledgement.objects.create(household=household, user=child)

    child.delete()

    assert LevelAcknowledgement.objects.count() == 0


def test_the_model_is_not_registered_in_the_django_admin():
    assert admin.site.is_registered(LevelAcknowledgement) is False


@pytest.mark.django_db
def test_migration_graph_is_applied_and_runtime_matches_migration_state():
    executor = MigrationExecutor(connection)
    leaf_nodes = executor.loader.graph.leaf_nodes()

    executor.loader.graph.ensure_not_cyclic()
    assert executor.loader.detect_conflicts() == {}
    assert executor.migration_plan(leaf_nodes) == []

    migration_model = executor.loader.project_state().apps.get_model(
        'progression',
        'LevelAcknowledgement',
    )
    assert migration_model._meta.db_table == LevelAcknowledgement._meta.db_table
    assert _migration_signature(migration_model) == _migration_signature(
        LevelAcknowledgement
    )
    assert migration_model._meta.constraints == LevelAcknowledgement._meta.constraints


@pytest.mark.django_db
def test_schema_has_exactly_the_one_expected_table():
    progression_tables = {
        table
        for table in connection.introspection.table_names()
        if table.startswith('progression_')
    }
    assert progression_tables == {TABLE}


@pytest.mark.django_db
def test_postgresql_reports_the_named_check_constraint():
    if connection.vendor != 'postgresql':
        pytest.skip('requires the guarded PostgreSQL target')

    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, TABLE)

    assert {
        name for name, constraint in constraints.items() if constraint['check']
    } == {'progression_levelacknowledgement_shown_level_range'}
