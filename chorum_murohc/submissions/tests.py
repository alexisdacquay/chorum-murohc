from importlib import import_module
from pathlib import Path

import pytest
from django.contrib import admin
from django.db import IntegrityError, connection, models, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from chorum_murohc.chores.models import Chore
from chorum_murohc.identity.models import Household, Membership, User
from chorum_murohc.submissions.models import Submission, SubmissionTransitionError

TABLE = 'submissions_submission'


def _migration_signature(model):
    return tuple(
        sorted(
            (field.name, field.deconstruct()[1:]) for field in model._meta.local_fields
        )
    )


def _index_signature(model):
    return tuple(index.deconstruct()[1:] for index in model._meta.indexes)


def _household():
    return Household.objects.create(name='Chore household')


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


def _chore(household, name='Dishes', points=10):
    return Chore.objects.create(household=household, name=name, points=points)


def _submission_kwargs(household, child, chore, **overrides):
    values = {
        'household': household,
        'child': child,
        'chore': chore,
        'chore_name': chore.name,
        'chore_points': chore.points,
        'idempotency_key': f'{child.username}-{chore.name}-1',
    }
    values.update(overrides)
    return values


def test_submission_has_the_exact_runtime_model_contract():
    fields = Submission._meta.local_fields

    assert Submission.__bases__ == (models.Model,)
    assert tuple(field.name for field in fields) == (
        'id',
        'household',
        'child',
        'chore',
        'chore_name',
        'chore_points',
        'note',
        'status',
        'idempotency_key',
        'rejection_reason',
        'decided_by',
        'created_at',
        'decided_at',
    )

    (
        implicit_id,
        household,
        child,
        chore,
        chore_name,
        chore_points,
        note,
        status,
        idempotency_key,
        rejection_reason,
        decided_by,
        created_at,
        decided_at,
    ) = fields

    assert isinstance(implicit_id, models.BigAutoField)
    assert implicit_id.primary_key is True

    assert type(chore_name) is models.CharField
    assert chore_name.max_length == 100
    assert chore_name.null is False

    assert type(chore_points) is models.IntegerField
    assert chore_points.null is False

    assert type(note) is models.CharField
    assert note.max_length == 280
    assert note.blank is True
    assert note.default == ''

    assert type(status) is models.CharField
    assert status.max_length == 9
    assert status.choices == Submission.Status.choices
    assert status.default == Submission.Status.PENDING

    assert type(idempotency_key) is models.CharField
    assert idempotency_key.max_length == 255
    assert idempotency_key.null is False

    assert type(rejection_reason) is models.CharField
    assert rejection_reason.max_length == 200
    assert rejection_reason.blank is True
    assert rejection_reason.default == ''

    assert isinstance(created_at, models.DateTimeField)
    assert created_at.auto_now_add is True
    assert created_at.editable is False

    assert isinstance(decided_at, models.DateTimeField)
    assert decided_at.auto_now_add is False
    assert decided_at.auto_now is False
    assert decided_at.null is True
    assert decided_at.blank is True

    assert isinstance(child, models.ForeignKey)
    assert child.related_model is User
    assert child.remote_field.on_delete is models.CASCADE
    assert child.remote_field.related_name == 'submissions'
    assert child.null is False

    assert isinstance(chore, models.ForeignKey)
    assert chore.related_model is Chore
    assert chore.remote_field.on_delete is models.SET_NULL
    assert chore.remote_field.related_name == 'submissions'
    assert chore.null is True

    assert isinstance(decided_by, models.ForeignKey)
    assert decided_by.related_model is User
    assert decided_by.remote_field.on_delete is models.SET_NULL
    assert decided_by.remote_field.related_name == 'decided_submissions'
    assert decided_by.null is True
    assert decided_by.blank is True

    assert isinstance(household, models.ForeignKey)
    assert household.related_model is Household
    assert household.remote_field.on_delete is models.PROTECT
    assert household.remote_field.related_name == 'submissions'
    assert household.null is False

    assert Submission._meta.db_table == TABLE
    assert Submission._meta.ordering == ('-created_at', '-id')


def test_models_module_imports_only_django():
    module = import_module('chorum_murohc.submissions.models')
    source_lines = Path(module.__file__).resolve().read_text().splitlines()

    assert [line for line in source_lines if line.startswith(('import ', 'from '))] == [
        'from django.conf import settings',
        'from django.db import models',
    ]


def test_status_enum_has_exactly_the_four_policy_states():
    assert Submission.Status.values == ['pending', 'approved', 'rejected', 'withdrawn']
    assert Submission.Status.PENDING == 'pending'
    assert Submission.Status.APPROVED == 'approved'
    assert Submission.Status.REJECTED == 'rejected'
    assert Submission.Status.WITHDRAWN == 'withdrawn'


def test_named_database_constraints_are_declared_once_each():
    constraints = Submission._meta.constraints
    assert [constraint.name for constraint in constraints] == [
        'submission_child_idempotency_key_unique',
        'submission_one_pending_per_child_chore',
        'submission_status_valid',
        'submission_decision_matches_status',
        'submission_decided_by_unset_while_pending',
        'submission_chore_points_positive',
    ]


# --- state constraints and valid transitions ---------------------------------


@pytest.mark.django_db
def test_a_submission_is_created_pending_with_null_decision_fields():
    household = _household()
    child = _child(household)
    chore = _chore(household)
    before = timezone.now()

    submission = Submission.objects.create(
        **_submission_kwargs(household, child, chore)
    )
    submission.refresh_from_db()

    assert submission.status == Submission.Status.PENDING
    assert submission.decided_at is None
    assert submission.decided_by_id is None
    assert submission.chore_name == 'Dishes'
    assert submission.chore_points == 10
    assert submission.note == ''
    assert before <= submission.created_at <= timezone.now()
    assert timezone.is_aware(submission.created_at)


@pytest.mark.django_db
def test_a_submission_keeps_the_note_it_was_created_with():
    household = _household()
    child = _child(household)
    chore = _chore(household)

    submission = Submission.objects.create(
        **_submission_kwargs(household, child, chore, note='Left the mop out')
    )
    submission.refresh_from_db()

    assert submission.note == 'Left the mop out'


@pytest.mark.django_db
def test_creating_a_submission_in_a_non_pending_state_is_denied():
    household = _household()
    child = _child(household)
    chore = _chore(household)

    with pytest.raises(SubmissionTransitionError):
        Submission.objects.create(
            **_submission_kwargs(
                household, child, chore, status=Submission.Status.APPROVED
            )
        )
    assert Submission.objects.count() == 0


@pytest.mark.django_db
def test_an_unknown_status_is_rejected_by_the_database():
    household = _household()
    child = _child(household)
    chore = _chore(household)
    submission = Submission.objects.create(
        **_submission_kwargs(household, child, chore)
    )

    with (
        connection.cursor() as cursor,
        pytest.raises(IntegrityError),
        transaction.atomic(),
    ):
        cursor.execute(
            f"UPDATE {TABLE} SET status = 'in_review' WHERE id = %s",
            [submission.pk],
        )


@pytest.mark.parametrize('target', ['approved', 'rejected', 'withdrawn'])
@pytest.mark.django_db
def test_each_of_the_three_legal_transitions_out_of_pending_succeeds(target):
    household = _household()
    child = _child(household)
    parent = _parent(household)
    chore = _chore(household)
    submission = Submission.objects.create(
        **_submission_kwargs(household, child, chore)
    )
    actor = parent if target in ('approved', 'rejected') else child

    submission.status = target
    submission.decided_at = timezone.now()
    submission.decided_by = actor
    submission.save()
    submission.refresh_from_db()

    assert submission.status == target
    assert submission.decided_at is not None
    assert submission.decided_by_id == actor.pk


@pytest.mark.django_db
def test_deciding_an_already_decided_submission_a_second_time_is_denied():
    household = _household()
    child = _child(household)
    parent = _parent(household)
    chore = _chore(household)
    submission = Submission.objects.create(
        **_submission_kwargs(household, child, chore)
    )
    submission.status = Submission.Status.APPROVED
    submission.decided_at = timezone.now()
    submission.decided_by = parent
    submission.save()

    for next_status in ('rejected', 'pending', 'withdrawn'):
        submission.status = next_status
        submission.decided_by = parent
        submission.decided_at = timezone.now()
        with pytest.raises(SubmissionTransitionError):
            submission.save()

    submission.refresh_from_db()
    assert submission.status == Submission.Status.APPROVED


@pytest.mark.django_db
def test_resaving_a_pending_submission_unchanged_is_denied():
    household = _household()
    child = _child(household)
    chore = _chore(household)
    submission = Submission.objects.create(
        **_submission_kwargs(household, child, chore)
    )

    with pytest.raises(SubmissionTransitionError):
        submission.save()


@pytest.mark.django_db
def test_editing_a_decided_submissions_content_is_denied():
    household = _household()
    child = _child(household)
    parent = _parent(household)
    chore = _chore(household)
    submission = Submission.objects.create(
        **_submission_kwargs(household, child, chore)
    )
    submission.status = Submission.Status.REJECTED
    submission.decided_at = timezone.now()
    submission.decided_by = parent
    submission.save()

    submission.rejection_reason = 'Not tidy enough'
    with pytest.raises(SubmissionTransitionError):
        submission.save()


@pytest.mark.django_db
def test_queryset_update_is_blocked_in_favour_of_save():
    household = _household()
    child = _child(household)
    chore = _chore(household)
    Submission.objects.create(**_submission_kwargs(household, child, chore))

    with pytest.raises(SubmissionTransitionError):
        Submission.objects.filter(child=child).update(status=Submission.Status.APPROVED)


@pytest.mark.django_db
def test_decision_fields_must_be_null_exactly_while_pending_at_the_database():
    household = _household()
    child = _child(household)
    chore = _chore(household)

    with pytest.raises(IntegrityError), transaction.atomic():
        Submission.objects.create(
            **_submission_kwargs(
                household,
                child,
                chore,
                decided_at=timezone.now(),
            )
        )
    assert Submission.objects.count() == 0

    with (
        connection.cursor() as cursor,
        pytest.raises(IntegrityError),
        transaction.atomic(),
    ):
        submission = Submission.objects.create(
            **_submission_kwargs(household, child, chore)
        )
        cursor.execute(
            f'UPDATE {TABLE} SET status = %s WHERE id = %s',
            ['approved', submission.pk],
        )
    # The bad row from the failed transaction never commits.
    assert list(Submission.objects.values_list('status', flat=True)) == []


@pytest.mark.django_db
def test_chore_points_must_stay_positive_at_the_database():
    household = _household()
    child = _child(household)
    chore = _chore(household)

    with pytest.raises(IntegrityError), transaction.atomic():
        Submission.objects.create(
            **_submission_kwargs(household, child, chore, chore_points=0)
        )
    assert Submission.objects.count() == 0


# --- duplicate policy ----------------------------------------------------------


@pytest.mark.django_db
def test_a_second_pending_submission_for_the_same_child_and_chore_is_refused():
    household = _household()
    child = _child(household)
    chore = _chore(household)
    Submission.objects.create(**_submission_kwargs(household, child, chore))

    with pytest.raises(IntegrityError), transaction.atomic():
        Submission.objects.create(
            **_submission_kwargs(household, child, chore, idempotency_key='second-try')
        )
    assert Submission.objects.filter(child=child, chore=chore).count() == 1


@pytest.mark.django_db
def test_two_different_children_may_each_hold_a_pending_claim_on_the_same_chore():
    household = _household()
    first_child = _child(household, username='first-child')
    second_child = _child(household, username='second-child')
    chore = _chore(household)

    first = Submission.objects.create(
        **_submission_kwargs(household, first_child, chore)
    )
    second = Submission.objects.create(
        **_submission_kwargs(household, second_child, chore)
    )

    assert Submission.objects.filter(chore=chore).count() == 2
    assert {first.pk, second.pk} == set(
        Submission.objects.filter(chore=chore).values_list('pk', flat=True)
    )


@pytest.mark.django_db
def test_a_new_pending_submission_is_allowed_once_the_prior_one_is_decided():
    household = _household()
    child = _child(household)
    parent = _parent(household)
    chore = _chore(household)
    first = Submission.objects.create(**_submission_kwargs(household, child, chore))
    first.status = Submission.Status.REJECTED
    first.decided_at = timezone.now()
    first.decided_by = parent
    first.save()

    second = Submission.objects.create(
        **_submission_kwargs(
            household, child, chore, idempotency_key='retry-after-reject'
        )
    )

    assert Submission.objects.filter(child=child, chore=chore).count() == 2
    assert second.status == Submission.Status.PENDING


@pytest.mark.django_db
def test_an_idempotency_key_is_unique_per_child_not_globally():
    household = _household()
    first_child = _child(household, username='key-child-one')
    second_child = _child(household, username='key-child-two')
    first_chore = _chore(household, name='Dishes')
    second_chore = _chore(household, name='Bins')

    Submission.objects.create(
        **_submission_kwargs(
            household, first_child, first_chore, idempotency_key='same-key'
        )
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        Submission.objects.create(
            **_submission_kwargs(
                household, first_child, second_chore, idempotency_key='same-key'
            )
        )

    other = Submission.objects.create(
        **_submission_kwargs(
            household, second_child, first_chore, idempotency_key='same-key'
        )
    )
    assert other.idempotency_key == 'same-key'
    assert Submission.objects.count() == 2


# --- immutable chore name and point snapshots ----------------------------------


@pytest.mark.django_db
def test_the_snapshot_survives_a_later_edit_to_the_chore():
    household = _household()
    child = _child(household)
    chore = _chore(household, name='Dishes', points=10)
    submission = Submission.objects.create(
        **_submission_kwargs(household, child, chore)
    )

    chore.name = 'Recycling'
    chore.points = 99
    chore.save()

    submission.refresh_from_db()
    assert submission.chore_name == 'Dishes'
    assert submission.chore_points == 10


@pytest.mark.django_db
def test_deleting_the_chore_nulls_the_reference_and_keeps_the_snapshot():
    household = _household()
    child = _child(household)
    parent = _parent(household)
    chore = _chore(household, name='Dishes', points=10)
    submission = Submission.objects.create(
        **_submission_kwargs(household, child, chore)
    )
    submission.status = Submission.Status.APPROVED
    submission.decided_at = timezone.now()
    submission.decided_by = parent
    submission.save()

    chore.delete()
    submission.refresh_from_db()

    assert submission.chore_id is None
    assert submission.chore_name == 'Dishes'
    assert submission.chore_points == 10
    assert submission.status == Submission.Status.APPROVED


# --- household isolation --------------------------------------------------------


@pytest.mark.django_db
def test_households_are_isolated_and_may_hold_matching_child_and_chore_names():
    first_household = _household()
    second_household = Household.objects.create(name='Second household')
    first_child = _child(first_household, username='shared-name')
    second_child = _child(second_household, username='shared-name-2')
    first_chore = _chore(first_household, name='Dishes')
    second_chore = _chore(second_household, name='Dishes')

    first = Submission.objects.create(
        **_submission_kwargs(first_household, first_child, first_chore)
    )
    second = Submission.objects.create(
        **_submission_kwargs(second_household, second_child, second_chore)
    )

    assert list(Submission.objects.filter(household=first_household)) == [first]
    assert list(Submission.objects.filter(household=second_household)) == [second]
    assert list(first_household.submissions.all()) == [first]
    assert list(second_household.submissions.all()) == [second]


@pytest.mark.django_db
def test_deleting_a_household_with_submissions_is_protected_and_changes_nothing():
    household = _household()
    child = _child(household)
    chore = _chore(household)
    submission = Submission.objects.create(
        **_submission_kwargs(household, child, chore)
    )
    original = Submission.objects.values().get(pk=submission.pk)

    with pytest.raises(ProtectedError):
        household.delete()

    assert Household.objects.filter(pk=household.pk).exists()
    assert Submission.objects.values().get(pk=submission.pk) == original


# --- deletion cascades -----------------------------------------------------------


@pytest.mark.django_db
def test_deleting_the_child_removes_every_one_of_their_submissions():
    household = _household()
    child = _child(household)
    other_child = _child(household, username='other-child')
    chore = _chore(household)
    Submission.objects.create(**_submission_kwargs(household, child, chore))
    surviving = Submission.objects.create(
        **_submission_kwargs(household, other_child, chore, idempotency_key='keep-me')
    )
    deleted_child_pk = child.pk

    child.delete()

    assert Submission.objects.filter(child_id=deleted_child_pk).count() == 0
    assert list(Submission.objects.all()) == [surviving]


@pytest.mark.django_db
def test_deleting_the_decided_by_parent_leaves_a_null_actor_and_the_row_intact():
    household = _household()
    child = _child(household)
    parent = _parent(household)
    chore = _chore(household)
    submission = Submission.objects.create(
        **_submission_kwargs(household, child, chore)
    )
    submission.status = Submission.Status.APPROVED
    submission.decided_at = timezone.now()
    submission.decided_by = parent
    submission.save()

    parent.delete()
    submission.refresh_from_db()

    assert submission.decided_by_id is None
    assert submission.status == Submission.Status.APPROVED


def test_the_submissions_models_are_not_registered_in_the_django_admin():
    assert admin.site.is_registered(Submission) is False


@pytest.mark.django_db
def test_migration_graph_is_applied_and_runtime_matches_migration_state():
    executor = MigrationExecutor(connection)
    leaf_nodes = executor.loader.graph.leaf_nodes()

    executor.loader.graph.ensure_not_cyclic()
    assert executor.loader.detect_conflicts() == {}
    assert executor.migration_plan(leaf_nodes) == []

    migration_model = executor.loader.project_state().apps.get_model(
        'submissions',
        'Submission',
    )
    assert migration_model._meta.db_table == Submission._meta.db_table
    assert migration_model._meta.ordering == Submission._meta.ordering
    assert _migration_signature(migration_model) == _migration_signature(Submission)
    assert _index_signature(migration_model) == _index_signature(Submission)
    assert migration_model._meta.constraints == Submission._meta.constraints


@pytest.mark.django_db
def test_submission_schema_has_exact_table_columns_foreign_keys_and_indexes():
    submission_tables = {
        table
        for table in connection.introspection.table_names()
        if table.startswith('submissions_')
    }
    assert submission_tables == {TABLE}

    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, TABLE)
        constraints = connection.introspection.get_constraints(cursor, TABLE)

    assert {column.name for column in description} == {
        'id',
        'household_id',
        'child_id',
        'chore_id',
        'chore_name',
        'chore_points',
        'note',
        'status',
        'idempotency_key',
        'rejection_reason',
        'decided_by_id',
        'created_at',
        'decided_at',
    }
    assert {column.name: column.null_ok for column in description} == {
        'id': False,
        'household_id': False,
        'child_id': False,
        'chore_id': True,
        'chore_name': False,
        'chore_points': False,
        'note': False,
        'status': False,
        'idempotency_key': False,
        'rejection_reason': False,
        'decided_by_id': True,
        'created_at': False,
        'decided_at': True,
    }
    assert any(
        constraint['columns'] == ['household_id']
        and constraint['foreign_key'] == ('identity_household', 'id')
        for constraint in constraints.values()
    )
    assert any(
        constraint['columns'] == ['child_id']
        and constraint['foreign_key'] == ('identity_user', 'id')
        for constraint in constraints.values()
    )
    assert any(
        constraint['columns'] == ['chore_id']
        and constraint['foreign_key'] == ('chores_chore', 'id')
        for constraint in constraints.values()
    )
    assert any(
        constraint['unique']
        and constraint['columns'] == ['child_id', 'idempotency_key']
        for constraint in constraints.values()
    )


@pytest.mark.django_db
def test_postgresql_reports_the_named_check_constraints():
    if connection.vendor != 'postgresql':
        pytest.skip('requires the guarded PostgreSQL target')

    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, TABLE)

    assert {
        name for name, constraint in constraints.items() if constraint['check']
    } == {
        'submission_status_valid',
        'submission_decision_matches_status',
        'submission_decided_by_unset_while_pending',
        'submission_chore_points_positive',
    }


@pytest.mark.django_db
def test_postgresql_partial_unique_index_only_covers_pending_rows():
    if connection.vendor != 'postgresql':
        pytest.skip('requires the guarded PostgreSQL target')

    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT indexdef FROM pg_indexes WHERE tablename = %s AND indexname = %s',
            [TABLE, 'submission_one_pending_per_child_chore'],
        )
        (index_definition,) = cursor.fetchone()

    assert 'WHERE' in index_definition
    assert 'pending' in index_definition
