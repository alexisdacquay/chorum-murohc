import json
import math
from copy import deepcopy
from datetime import timedelta
from importlib import import_module

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, migrations, models, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from chorum_murohc.audit.models import AuditEvent, AuditEventImmutableError
from chorum_murohc.identity.models import Household, User

SYNTHETIC_MARKERS = {
    'synthetic-sensitive-marker-a',
    'synthetic-sensitive-marker-b',
    'synthetic-sensitive-marker-c',
}
SENSITIVE_KEYS = (
    'password',
    'passwordconfirmation',
    'currentpassword',
    'oldpassword',
    'newpassword',
    'passphrase',
    'secret',
    'clientsecret',
    'secretkey',
    'privatekey',
    'token',
    'accesstoken',
    'refreshtoken',
    'idtoken',
    'apitoken',
    'apikey',
    'authorization',
    'cookie',
    'cookies',
    'sessionid',
    'sessionkey',
    'csrfmiddlewaretoken',
    'pin',
    'parentpin',
    'pinhash',
    'credential',
    'credentials',
)


def _event_fields(model=AuditEvent):
    return model._meta.local_fields


def _event_kwargs(household, actor=None, **overrides):
    values = {
        'household': household,
        'actor': actor,
        'action': 'account.updated',
        'target_type': 'identity.User',
        'target_id': 'user-42',
        'context': {'changed_fields': ['display_name']},
    }
    values.update(overrides)
    return values


def _contains_synthetic_marker(value):
    return any(
        marker in json.dumps(value, sort_keys=True) for marker in SYNTHETIC_MARKERS
    )


def _migration_signature(model):
    return tuple(
        sorted(
            (field.name, field.deconstruct()[1:]) for field in model._meta.local_fields
        )
    )


def _index_signature(model):
    return tuple(index.deconstruct()[1:] for index in model._meta.indexes)


def test_audit_event_has_the_exact_runtime_model_contract():
    fields = _event_fields()

    assert AuditEvent.__bases__ == (models.Model,)
    assert tuple(field.name for field in fields) == (
        'id',
        'household',
        'actor',
        'action',
        'target_type',
        'target_id',
        'created_at',
        'context',
    )

    (
        implicit_id,
        household,
        actor,
        action,
        target_type,
        target_id,
        created_at,
        context,
    ) = fields
    assert isinstance(implicit_id, models.BigAutoField)
    assert implicit_id.primary_key is True
    assert implicit_id.auto_created is True

    assert isinstance(household, models.ForeignKey)
    assert household.related_model is Household
    assert household.remote_field.on_delete is models.PROTECT
    assert household.remote_field.related_name == 'audit_events'
    assert household.null is False
    assert household.blank is False
    assert household.has_default() is False

    assert isinstance(actor, models.ForeignKey)
    assert actor.related_model is User
    assert actor.remote_field.on_delete is models.SET_NULL
    assert actor.remote_field.related_name == 'audit_events'
    assert actor.null is True
    assert actor.blank is True
    assert actor.has_default() is False

    for field, limit in ((action, 100), (target_type, 100), (target_id, 255)):
        assert isinstance(field, models.CharField)
        assert field.max_length == limit
        assert field.null is False
        assert field.blank is False
        assert field.has_default() is False
        assert field.choices is None
        assert field.unique is False

    assert isinstance(created_at, models.DateTimeField)
    assert created_at.auto_now_add is True
    assert created_at.editable is False
    assert created_at.null is False
    assert created_at.has_default() is False

    assert isinstance(context, models.JSONField)
    assert context.default is dict
    assert context.blank is True
    assert context.null is False

    assert AuditEvent._meta.db_table == 'audit_auditevent'
    assert AuditEvent._meta.ordering == ('-created_at', '-id')
    assert AuditEvent._meta.constraints == []
    assert [(index.name, index.fields) for index in AuditEvent._meta.indexes] == [
        ('audit_event_hh_time_id_idx', ['household', '-created_at', '-id'])
    ]


@pytest.mark.django_db
def test_supported_create_persists_exact_values_without_mutating_context():
    household = Household.objects.create(name='Audit household')
    actor = User.objects.create_user(username='audit-actor')
    submitted_context = {
        'changed_fields': ['display_name'],
        'metadata': {'attempt': 2, 'approved': True, 'note': None},
    }
    original_context = deepcopy(submitted_context)
    before = timezone.now()

    event = AuditEvent.objects.create(
        **_event_kwargs(household, actor, context=submitted_context)
    )

    assert event.household == household
    assert event.actor == actor
    assert event.action == 'account.updated'
    assert event.target_type == 'identity.User'
    assert event.target_id == 'user-42'
    assert event.context == original_context
    assert event.context is not submitted_context
    assert event.context['metadata'] is not submitted_context['metadata']
    assert submitted_context == original_context
    assert before <= event.created_at <= timezone.now()
    assert timezone.is_aware(event.created_at)
    event.refresh_from_db()
    assert event.context == original_context


@pytest.mark.django_db
def test_actor_is_optional_without_implicit_user_or_event_creation():
    household = Household.objects.create(name='Bootstrap household')

    assert AuditEvent.objects.count() == 0
    assert User.objects.count() == 0

    event = AuditEvent.objects.create(**_event_kwargs(household))

    assert event.actor is None
    assert event.actor_id is None
    assert User.objects.count() == 0
    assert list(AuditEvent.objects.filter(actor=None)) == [event]


@pytest.mark.django_db
def test_context_redaction_is_recursive_separator_insensitive_and_non_mutating():
    household = Household.objects.create(name='Redaction household')
    submitted_context = {
        'Parent-PIN': 'synthetic-sensitive-marker-a',
        'safe': {
            'API_key': 'synthetic-sensitive-marker-b',
            'items': [
                {'Authorization': 'synthetic-sensitive-marker-c'},
                {'ordinary': 'preserved'},
            ],
        },
        'already_redacted': {'cookie': '[REDACTED]'},
        'finite': [0, -1.5, True, None],
    }
    original_context = deepcopy(submitted_context)

    event = AuditEvent.objects.create(
        **_event_kwargs(household, context=submitted_context)
    )
    event.refresh_from_db()

    assert event.context == {
        'Parent-PIN': '[REDACTED]',
        'safe': {
            'API_key': '[REDACTED]',
            'items': [
                {'Authorization': '[REDACTED]'},
                {'ordinary': 'preserved'},
            ],
        },
        'already_redacted': {'cookie': '[REDACTED]'},
        'finite': [0, -1.5, True, None],
    }
    assert _contains_synthetic_marker(event.context) is False
    assert submitted_context == original_context


@pytest.mark.django_db
def test_every_exact_sensitive_key_is_redacted_without_traversing_its_value():
    household = Household.objects.create(name='Exact-key household')
    unencodable_value = object()
    submitted_context = {
        **{key: 'synthetic-sensitive-marker-a' for key in SENSITIVE_KEYS},
        'ToKeN': 'synthetic-sensitive-marker-b',
        'parent pin': 'synthetic-sensitive-marker-c',
        'secret-key': unencodable_value,
    }

    event = AuditEvent.objects.create(
        **_event_kwargs(household, context=submitted_context)
    )
    event.refresh_from_db()

    assert set(event.context) == set(submitted_context)
    assert set(event.context.values()) == {'[REDACTED]'}
    assert _contains_synthetic_marker(event.context) is False
    assert submitted_context['secret-key'] is unencodable_value


@pytest.mark.django_db
def test_one_initial_instance_save_uses_the_same_redaction_boundary():
    household = Household.objects.create(name='Initial-save household')
    submitted_context = {'nested': [{'session_key': 'synthetic-sensitive-marker-a'}]}
    event = AuditEvent(**_event_kwargs(household, context=submitted_context))

    event.save()
    event.refresh_from_db()

    assert event.context == {'nested': [{'session_key': '[REDACTED]'}]}
    assert _contains_synthetic_marker(event.context) is False
    assert submitted_context == {
        'nested': [{'session_key': 'synthetic-sensitive-marker-a'}]
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    'invalid_context',
    [
        [],
        'scalar',
        {'nested': {1: 'value'}},
        {'not_json': {1, 2}},
        {'not_json': (1, 2)},
        {'number': math.nan},
        {'number': math.inf},
        {'number': -math.inf},
    ],
)
def test_invalid_context_raises_validation_error_without_inserting(invalid_context):
    household = Household.objects.create(name='Validation household')

    with pytest.raises(ValidationError):
        AuditEvent.objects.create(**_event_kwargs(household, context=invalid_context))

    assert AuditEvent.objects.count() == 0


@pytest.mark.django_db
def test_full_clean_enforces_character_limits_and_context_shape():
    household = Household.objects.create(name='Clean household')

    for field_name, invalid_value in (
        ('action', ''),
        ('action', 'a' * 101),
        ('target_type', ''),
        ('target_type', 't' * 101),
        ('target_id', ''),
        ('target_id', 'i' * 256),
    ):
        event = AuditEvent(**_event_kwargs(household, **{field_name: invalid_value}))
        with pytest.raises(ValidationError) as error:
            event.full_clean()
        assert field_name in error.value.message_dict

    for field_name, valid_value in (
        ('action', 'a' * 100),
        ('target_type', 't' * 100),
        ('target_id', 'i' * 255),
    ):
        event = AuditEvent(**_event_kwargs(household, **{field_name: valid_value}))
        event.full_clean()

    invalid_event = AuditEvent(**_event_kwargs(household, context=['not-object']))
    with pytest.raises(ValidationError) as error:
        invalid_event.full_clean()
    assert 'context' in error.value.message_dict


@pytest.mark.django_db
def test_household_is_protected_and_actor_deletion_only_nulls_actor():
    household = Household.objects.create(name='Referenced household')
    actor = User.objects.create_user(username='referenced-actor')
    event = AuditEvent.objects.create(**_event_kwargs(household, actor))
    original_values = {
        'household_id': event.household_id,
        'action': event.action,
        'target_type': event.target_type,
        'target_id': event.target_id,
        'created_at': event.created_at,
        'context': event.context,
    }

    with pytest.raises(ProtectedError):
        household.delete()
    event.refresh_from_db()
    assert event.actor_id == actor.pk
    assert {
        'household_id': event.household_id,
        'action': event.action,
        'target_type': event.target_type,
        'target_id': event.target_id,
        'created_at': event.created_at,
        'context': event.context,
    } == original_values

    actor.delete()
    event.refresh_from_db()
    assert event.actor_id is None
    assert {
        'household_id': event.household_id,
        'action': event.action,
        'target_type': event.target_type,
        'target_id': event.target_id,
        'created_at': event.created_at,
        'context': event.context,
    } == original_values


@pytest.mark.django_db
def test_default_ordering_is_newest_first_with_descending_id_tie_breaker():
    household = Household.objects.create(name='Ordering household')
    first = AuditEvent.objects.create(**_event_kwargs(household, target_id='first'))
    second = AuditEvent.objects.create(**_event_kwargs(household, target_id='second'))
    third = AuditEvent.objects.create(**_event_kwargs(household, target_id='third'))
    tied_time = timezone.now() - timedelta(days=1)

    with connection.cursor() as cursor:
        cursor.execute(
            'UPDATE audit_auditevent SET created_at = %s WHERE id IN (%s, %s)',
            [tied_time, first.pk, second.pk],
        )

    assert list(AuditEvent.objects.values_list('pk', flat=True)) == [
        third.pk,
        second.pk,
        first.pk,
    ]


@pytest.mark.django_db
def test_every_supported_mutation_api_is_blocked_before_a_write(
    django_assert_num_queries,
):
    household = Household.objects.create(name='Immutable household')
    event = AuditEvent.objects.create(**_event_kwargs(household))
    original = AuditEvent.objects.values().get(pk=event.pk)

    event.action = 'changed'
    blocked_operations = (
        lambda: event.save(),
        lambda: event.save(update_fields=['action']),
        lambda: event.delete(),
        lambda: AuditEvent.objects.filter(pk=event.pk).update(action='changed'),
        lambda: AuditEvent.objects.filter(pk=event.pk).delete(),
        lambda: AuditEvent.objects.bulk_update([event], ['action']),
        lambda: AuditEvent.objects.bulk_create(
            [AuditEvent(**_event_kwargs(household, target_id='bulk'))]
        ),
    )
    for operation in blocked_operations:
        with django_assert_num_queries(0), pytest.raises(AuditEventImmutableError):
            operation()

    event.refresh_from_db()
    assert AuditEvent.objects.count() == 1
    assert AuditEvent.objects.values().get(pk=event.pk) == original


@pytest.mark.django_db
def test_immutability_boundary_is_application_level_without_a_database_trigger():
    household = Household.objects.create(name='Boundary household')
    event = AuditEvent.objects.create(**_event_kwargs(household))
    original_action = event.action

    with connection.cursor() as cursor:
        cursor.execute(
            'UPDATE audit_auditevent SET action = %s WHERE id = %s',
            ['test-only-direct-write', event.pk],
        )
        cursor.execute(
            'UPDATE audit_auditevent SET action = %s WHERE id = %s',
            [original_action, event.pk],
        )

    event.refresh_from_db()
    assert event.action == original_action


def test_initial_migration_has_the_exact_schema_only_contract():
    initial_migration = import_module('chorum_murohc.audit.migrations.0001_initial')
    migration = initial_migration.Migration('0001_initial', 'audit')

    assert migration.initial is True
    assert migration.dependencies == [
        ('identity', '0002_household_membership'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    assert len(migration.operations) == 1
    operation = migration.operations[0]
    assert isinstance(operation, migrations.CreateModel)
    assert operation.name == 'AuditEvent'
    assert tuple(name for name, _ in operation.fields) == (
        'id',
        'action',
        'target_type',
        'target_id',
        'created_at',
        'context',
        'actor',
        'household',
    )
    assert operation.options == {
        'ordering': ('-created_at', '-id'),
        'indexes': [
            models.Index(
                fields=['household', '-created_at', '-id'],
                name='audit_event_hh_time_id_idx',
            )
        ],
    }
    assert operation.managers == []


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
        'audit',
        'AuditEvent',
    )
    assert migration_model._meta.db_table == AuditEvent._meta.db_table
    assert migration_model._meta.ordering == AuditEvent._meta.ordering
    assert _migration_signature(migration_model) == _migration_signature(AuditEvent)
    assert _index_signature(migration_model) == _index_signature(AuditEvent)
    assert migration_model._meta.constraints == AuditEvent._meta.constraints == []


@pytest.mark.django_db
def test_audit_schema_has_exact_table_columns_foreign_keys_and_indexes():
    audit_tables = {
        table
        for table in connection.introspection.table_names()
        if table.startswith('audit_')
    }
    assert audit_tables == {'audit_auditevent'}

    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(
            cursor,
            'audit_auditevent',
        )
        constraints = connection.introspection.get_constraints(
            cursor,
            'audit_auditevent',
        )

    assert {column.name for column in description} == {
        'id',
        'household_id',
        'actor_id',
        'action',
        'target_type',
        'target_id',
        'created_at',
        'context',
    }
    nullability = {column.name: column.null_ok for column in description}
    assert nullability == {
        'id': False,
        'household_id': False,
        'actor_id': True,
        'action': False,
        'target_type': False,
        'target_id': False,
        'created_at': False,
        'context': False,
    }
    assert any(
        constraint['columns'] == ['household_id']
        and constraint['foreign_key'] == ('identity_household', 'id')
        for constraint in constraints.values()
    )
    assert any(
        constraint['columns'] == ['actor_id']
        and constraint['foreign_key'] == ('identity_user', 'id')
        for constraint in constraints.values()
    )
    explicit_index = constraints['audit_event_hh_time_id_idx']
    assert explicit_index['index'] is True
    assert explicit_index['unique'] is False
    assert explicit_index['columns'] == ['household_id', 'created_at', 'id']
    assert explicit_index['orders'] == ['ASC', 'DESC', 'DESC']
    indexed_column_sets = {
        tuple(constraint['columns'])
        for constraint in constraints.values()
        if constraint['index'] and not constraint['primary_key']
    }
    assert indexed_column_sets == {
        ('actor_id',),
        ('household_id',),
        ('household_id', 'created_at', 'id'),
    }


@pytest.mark.django_db
def test_audit_table_has_no_trigger():
    with connection.cursor() as cursor:
        if connection.vendor == 'postgresql':
            cursor.execute(
                """
                SELECT tgname
                FROM pg_trigger
                WHERE tgrelid = 'audit_auditevent'::regclass
                  AND NOT tgisinternal
                """
            )
        else:
            cursor.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'trigger' AND tbl_name = 'audit_auditevent'
                """
            )
        assert cursor.fetchall() == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('field_name', 'invalid_value'),
    [
        ('action', 'a' * 101),
        ('target_type', 't' * 101),
        ('target_id', 'i' * 256),
    ],
)
def test_postgresql_enforces_character_storage_limits(field_name, invalid_value):
    if connection.vendor != 'postgresql':
        pytest.skip('requires the guarded PostgreSQL target')
    household = Household.objects.create(name='Storage-limit household')

    with pytest.raises(IntegrityError), transaction.atomic():
        AuditEvent.objects.create(
            **_event_kwargs(household, **{field_name: invalid_value})
        )

    assert AuditEvent.objects.count() == 0


@pytest.mark.django_db
def test_postgresql_enforces_required_column_storage():
    if connection.vendor != 'postgresql':
        pytest.skip('requires the guarded PostgreSQL target')
    household = Household.objects.create(name='Required-column household')

    with pytest.raises(IntegrityError), transaction.atomic():
        AuditEvent.objects.create(**_event_kwargs(household, action=None))

    assert AuditEvent.objects.count() == 0
