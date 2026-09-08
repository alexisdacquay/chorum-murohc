"""Model-layer tests for `Reward` and `Redemption`.

`Reward` is proved against the same contract `chorum_murohc/chores/tests.py`
proves for `Chore`, since the two models are deliberately shaped alike.
`Redemption` is proved against the same contract
`chorum_murohc/submissions/tests.py` proves for `Submission`, for the same
reason. The write-service transaction, ledger, and audit behaviour live in
`test_services.py`; this file is schema, constraints, and state transitions
only.
"""

from importlib import import_module
from pathlib import Path

import pytest
from django.contrib import admin
from django.db import IntegrityError, connection, models, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from chorum_murohc.identity.models import Household, Membership, User
from chorum_murohc.rewards.models import Redemption, RedemptionTransitionError, Reward

REWARD_TABLE = 'rewards_reward'
REDEMPTION_TABLE = 'rewards_redemption'


def _migration_signature(model):
    return tuple(
        sorted(
            (field.name, field.deconstruct()[1:]) for field in model._meta.local_fields
        )
    )


def _index_signature(model):
    return tuple(index.deconstruct()[1:] for index in model._meta.indexes)


def _household(name='Reward household'):
    return Household.objects.create(name=name)


def _child(household, username='child'):
    user = User.objects.create_user(username=username)
    Membership.objects.create(
        household=household, user=user, role=Membership.Role.CHILD
    )
    return user


def _parent(household, username='parent'):
    user = User.objects.create_user(username=username)
    Membership.objects.create(
        household=household, user=user, role=Membership.Role.PARENT
    )
    return user


def _reward(household, name='Screen time', points=15):
    return Reward.objects.create(household=household, name=name, points=points)


def _redemption_kwargs(household, child, reward, **overrides):
    values = {
        'household': household,
        'child': child,
        'reward': reward,
        'reward_name': reward.name,
        'reward_points': reward.points,
        'idempotency_key': f'{child.username}-{reward.name}-1',
    }
    values.update(overrides)
    return values


# --- Reward: schema and constraints -----------------------------------------


def test_reward_has_the_exact_runtime_model_contract():
    fields = Reward._meta.local_fields

    assert Reward.__bases__ == (models.Model,)
    assert tuple(field.name for field in fields) == (
        'id',
        'household',
        'name',
        'points',
        'is_active',
        'created_at',
        'updated_at',
    )
    assert Reward._meta.db_table == REWARD_TABLE
    assert Reward._meta.ordering == ('name', 'id')


def test_reward_named_database_constraints_are_declared_once_each():
    constraints = Reward._meta.constraints
    assert [constraint.name for constraint in constraints] == [
        'reward_hh_name_ci_unique',
        'reward_points_positive',
        'reward_name_not_blank',
    ]


@pytest.mark.django_db
def test_a_reward_is_created_active_by_default():
    reward = _reward(_household())
    assert reward.is_active is True


@pytest.mark.django_db
def test_reward_names_collide_case_insensitively_within_one_household():
    household = _household()
    Reward.objects.create(household=household, name='Movie night', points=100)

    with pytest.raises(IntegrityError), transaction.atomic():
        Reward.objects.create(household=household, name='MOVIE NIGHT', points=50)


@pytest.mark.django_db
def test_the_same_reward_name_is_free_in_another_household():
    first = _household('First')
    second = _household('Second')
    Reward.objects.create(household=first, name='Movie night', points=100)

    reward = Reward.objects.create(household=second, name='Movie night', points=50)
    assert reward.pk is not None


@pytest.mark.django_db
def test_reward_points_must_stay_positive_at_the_database():
    household = _household()
    with pytest.raises(IntegrityError), transaction.atomic():
        Reward.objects.create(household=household, name='Free reward', points=0)


@pytest.mark.django_db
def test_a_blank_reward_name_is_refused_and_surrounding_whitespace_is_trimmed():
    household = _household()
    with pytest.raises(IntegrityError), transaction.atomic():
        Reward.objects.create(household=household, name='   ', points=1)

    reward = Reward.objects.create(
        household=household, name='  Movie night  ', points=1
    )
    assert reward.name == 'Movie night'


def test_the_rewards_models_are_not_registered_in_the_django_admin():
    assert admin.site.is_registered(Reward) is False
    assert admin.site.is_registered(Redemption) is False


# --- Redemption: schema, constraints, and transitions -----------------------


def test_redemption_has_the_exact_runtime_model_contract():
    fields = Redemption._meta.local_fields

    assert Redemption.__bases__ == (models.Model,)
    assert tuple(field.name for field in fields) == (
        'id',
        'household',
        'child',
        'reward',
        'reward_name',
        'reward_points',
        'status',
        'idempotency_key',
        'decided_by',
        'created_at',
        'decided_at',
    )
    assert Redemption._meta.db_table == REDEMPTION_TABLE
    assert Redemption._meta.ordering == ('-created_at', '-id')


def test_redemption_status_enum_has_exactly_the_three_policy_states():
    assert Redemption.Status.values == ['pending', 'fulfilled', 'cancelled']


def test_redemption_named_database_constraints_are_declared_once_each():
    constraints = Redemption._meta.constraints
    assert [constraint.name for constraint in constraints] == [
        'redemption_child_idempotency_key_unique',
        'redemption_status_valid',
        'redemption_decision_matches_status',
        'redemption_decided_by_unset_while_pending',
        'redemption_reward_points_positive',
    ]


@pytest.mark.django_db
def test_a_redemption_is_created_pending_with_null_decision_fields():
    household = _household()
    child = _child(household)
    reward = _reward(household)
    before = timezone.now()

    redemption = Redemption.objects.create(
        **_redemption_kwargs(household, child, reward)
    )
    redemption.refresh_from_db()

    assert redemption.status == Redemption.Status.PENDING
    assert redemption.decided_at is None
    assert redemption.decided_by_id is None
    assert redemption.reward_name == 'Screen time'
    assert redemption.reward_points == 15
    assert before <= redemption.created_at <= timezone.now()


@pytest.mark.django_db
def test_creating_a_redemption_in_a_non_pending_state_is_denied():
    household = _household()
    child = _child(household)
    reward = _reward(household)

    with pytest.raises(RedemptionTransitionError):
        Redemption.objects.create(
            **_redemption_kwargs(
                household, child, reward, status=Redemption.Status.FULFILLED
            )
        )
    assert Redemption.objects.count() == 0


@pytest.mark.parametrize('target', ['fulfilled', 'cancelled'])
@pytest.mark.django_db
def test_each_of_the_two_legal_transitions_out_of_pending_succeeds(target):
    household = _household()
    child = _child(household)
    parent = _parent(household)
    reward = _reward(household)
    redemption = Redemption.objects.create(
        **_redemption_kwargs(household, child, reward)
    )

    redemption.status = target
    redemption.decided_at = timezone.now()
    redemption.decided_by = parent
    redemption.save()
    redemption.refresh_from_db()

    assert redemption.status == target
    assert redemption.decided_at is not None
    assert redemption.decided_by_id == parent.pk


@pytest.mark.django_db
def test_deciding_an_already_decided_redemption_a_second_time_is_denied():
    household = _household()
    child = _child(household)
    parent = _parent(household)
    reward = _reward(household)
    redemption = Redemption.objects.create(
        **_redemption_kwargs(household, child, reward)
    )
    redemption.status = Redemption.Status.FULFILLED
    redemption.decided_at = timezone.now()
    redemption.decided_by = parent
    redemption.save()

    for next_status in ('cancelled', 'pending'):
        redemption.status = next_status
        redemption.decided_by = parent
        redemption.decided_at = timezone.now()
        with pytest.raises(RedemptionTransitionError):
            redemption.save()

    redemption.refresh_from_db()
    assert redemption.status == Redemption.Status.FULFILLED


@pytest.mark.django_db
def test_a_transition_out_of_pending_without_a_deciding_actor_is_denied():
    household = _household()
    child = _child(household)
    reward = _reward(household)
    redemption = Redemption.objects.create(
        **_redemption_kwargs(household, child, reward)
    )

    redemption.status = Redemption.Status.CANCELLED
    redemption.decided_at = timezone.now()
    with pytest.raises(RedemptionTransitionError):
        redemption.save()


@pytest.mark.django_db
def test_queryset_update_is_blocked_in_favour_of_save():
    household = _household()
    child = _child(household)
    reward = _reward(household)
    Redemption.objects.create(**_redemption_kwargs(household, child, reward))

    with pytest.raises(RedemptionTransitionError):
        Redemption.objects.filter(child=child).update(
            status=Redemption.Status.FULFILLED
        )


@pytest.mark.django_db
def test_decision_fields_must_be_null_exactly_while_pending_at_the_database():
    household = _household()
    child = _child(household)
    reward = _reward(household)

    with pytest.raises(IntegrityError), transaction.atomic():
        Redemption.objects.create(
            **_redemption_kwargs(household, child, reward, decided_at=timezone.now())
        )
    assert Redemption.objects.count() == 0


@pytest.mark.django_db
def test_redemption_reward_points_must_stay_positive_at_the_database():
    household = _household()
    child = _child(household)
    reward = _reward(household)

    with pytest.raises(IntegrityError), transaction.atomic():
        Redemption.objects.create(
            **_redemption_kwargs(household, child, reward, reward_points=0)
        )


@pytest.mark.django_db
def test_an_idempotency_key_is_unique_per_child_not_globally():
    household = _household()
    first_child = _child(household, username='key-child-one')
    second_child = _child(household, username='key-child-two')
    reward = _reward(household)

    Redemption.objects.create(
        **_redemption_kwargs(household, first_child, reward, idempotency_key='same-key')
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        Redemption.objects.create(
            **_redemption_kwargs(
                household, first_child, reward, idempotency_key='same-key'
            )
        )

    other = Redemption.objects.create(
        **_redemption_kwargs(
            household, second_child, reward, idempotency_key='same-key'
        )
    )
    assert other.idempotency_key == 'same-key'
    assert Redemption.objects.count() == 2


@pytest.mark.django_db
def test_the_snapshot_survives_a_later_edit_to_the_reward():
    household = _household()
    child = _child(household)
    reward = _reward(household, name='Screen time', points=15)
    redemption = Redemption.objects.create(
        **_redemption_kwargs(household, child, reward)
    )

    reward.name = 'Renamed'
    reward.points = 999
    reward.save()

    redemption.refresh_from_db()
    assert redemption.reward_name == 'Screen time'
    assert redemption.reward_points == 15


@pytest.mark.django_db
def test_deleting_the_reward_nulls_the_reference_and_keeps_the_snapshot():
    household = _household()
    child = _child(household)
    parent = _parent(household)
    reward = _reward(household, name='Screen time', points=15)
    redemption = Redemption.objects.create(
        **_redemption_kwargs(household, child, reward)
    )
    redemption.status = Redemption.Status.FULFILLED
    redemption.decided_at = timezone.now()
    redemption.decided_by = parent
    redemption.save()

    reward.delete()
    redemption.refresh_from_db()

    assert redemption.reward_id is None
    assert redemption.reward_name == 'Screen time'
    assert redemption.reward_points == 15
    assert redemption.status == Redemption.Status.FULFILLED


@pytest.mark.django_db
def test_households_are_isolated_and_may_hold_matching_child_and_reward_names():
    first_household = _household('First')
    second_household = _household('Second')
    first_child = _child(first_household, username='shared-name')
    second_child = _child(second_household, username='shared-name-2')
    first_reward = _reward(first_household)
    second_reward = _reward(second_household)

    first = Redemption.objects.create(
        **_redemption_kwargs(first_household, first_child, first_reward)
    )
    second = Redemption.objects.create(
        **_redemption_kwargs(second_household, second_child, second_reward)
    )

    assert list(Redemption.objects.filter(household=first_household)) == [first]
    assert list(Redemption.objects.filter(household=second_household)) == [second]


@pytest.mark.django_db
def test_deleting_a_household_with_redemptions_is_protected_and_changes_nothing():
    household = _household()
    child = _child(household)
    reward = _reward(household)
    redemption = Redemption.objects.create(
        **_redemption_kwargs(household, child, reward)
    )
    original = Redemption.objects.values().get(pk=redemption.pk)

    with pytest.raises(ProtectedError):
        household.delete()

    assert Household.objects.filter(pk=household.pk).exists()
    assert Redemption.objects.values().get(pk=redemption.pk) == original


@pytest.mark.django_db
def test_deleting_the_child_removes_every_one_of_their_redemptions():
    household = _household()
    child = _child(household)
    other_child = _child(household, username='other-child')
    reward = _reward(household)
    Redemption.objects.create(**_redemption_kwargs(household, child, reward))
    surviving = Redemption.objects.create(
        **_redemption_kwargs(household, other_child, reward, idempotency_key='keep-me')
    )
    deleted_child_pk = child.pk

    child.delete()

    assert Redemption.objects.filter(child_id=deleted_child_pk).count() == 0
    assert list(Redemption.objects.all()) == [surviving]


@pytest.mark.django_db
def test_deleting_the_decided_by_parent_leaves_a_null_actor_and_the_row_intact():
    household = _household()
    child = _child(household)
    parent = _parent(household)
    reward = _reward(household)
    redemption = Redemption.objects.create(
        **_redemption_kwargs(household, child, reward)
    )
    redemption.status = Redemption.Status.FULFILLED
    redemption.decided_at = timezone.now()
    redemption.decided_by = parent
    redemption.save()

    parent.delete()
    redemption.refresh_from_db()

    assert redemption.decided_by_id is None
    assert redemption.status == Redemption.Status.FULFILLED


# --- Module hygiene and migration consistency -------------------------------


def test_models_module_imports_only_django():
    module = import_module('chorum_murohc.rewards.models')
    source_lines = Path(module.__file__).resolve().read_text().splitlines()

    assert [line for line in source_lines if line.startswith(('import ', 'from '))] == [
        'from django.conf import settings',
        'from django.core.exceptions import ValidationError',
        'from django.db import models',
        'from django.db.models.functions import Lower',
    ]


@pytest.mark.django_db
def test_migration_graph_is_applied_and_runtime_matches_migration_state():
    executor = MigrationExecutor(connection)
    leaf_nodes = executor.loader.graph.leaf_nodes()

    executor.loader.graph.ensure_not_cyclic()
    assert executor.loader.detect_conflicts() == {}
    assert executor.migration_plan(leaf_nodes) == []

    project_state = executor.loader.project_state()
    for model in (Reward, Redemption):
        migration_model = project_state.apps.get_model('rewards', model.__name__)
        assert migration_model._meta.db_table == model._meta.db_table
        assert migration_model._meta.ordering == model._meta.ordering
        assert _migration_signature(migration_model) == _migration_signature(model)
        assert _index_signature(migration_model) == _index_signature(model)
        assert migration_model._meta.constraints == model._meta.constraints


@pytest.mark.django_db
def test_reward_and_redemption_schema_have_exact_table_columns_and_foreign_keys():
    tables = {
        table
        for table in connection.introspection.table_names()
        if table.startswith('rewards_')
    }
    assert tables == {REWARD_TABLE, REDEMPTION_TABLE}

    with connection.cursor() as cursor:
        reward_columns = connection.introspection.get_table_description(
            cursor, REWARD_TABLE
        )
        redemption_columns = connection.introspection.get_table_description(
            cursor, REDEMPTION_TABLE
        )
        redemption_constraints = connection.introspection.get_constraints(
            cursor, REDEMPTION_TABLE
        )

    assert {column.name for column in reward_columns} == {
        'id',
        'household_id',
        'name',
        'points',
        'is_active',
        'created_at',
        'updated_at',
    }
    assert {column.name for column in redemption_columns} == {
        'id',
        'household_id',
        'child_id',
        'reward_id',
        'reward_name',
        'reward_points',
        'status',
        'idempotency_key',
        'decided_by_id',
        'created_at',
        'decided_at',
    }
    assert any(
        constraint['columns'] == ['reward_id']
        and constraint['foreign_key'] == (REWARD_TABLE, 'id')
        for constraint in redemption_constraints.values()
    )
    assert any(
        constraint['unique']
        and constraint['columns'] == ['child_id', 'idempotency_key']
        for constraint in redemption_constraints.values()
    )


@pytest.mark.django_db
def test_postgresql_reports_the_named_check_constraints():
    if connection.vendor != 'postgresql':
        pytest.skip('requires the guarded PostgreSQL target')

    with connection.cursor() as cursor:
        reward_constraints = connection.introspection.get_constraints(
            cursor, REWARD_TABLE
        )
        redemption_constraints = connection.introspection.get_constraints(
            cursor, REDEMPTION_TABLE
        )

    assert {
        name for name, constraint in reward_constraints.items() if constraint['check']
    } == {'reward_points_positive', 'reward_name_not_blank'}
    assert {
        name
        for name, constraint in redemption_constraints.items()
        if constraint['check']
    } == {
        'redemption_status_valid',
        'redemption_decision_matches_status',
        'redemption_decided_by_unset_while_pending',
        'redemption_reward_points_positive',
    }
