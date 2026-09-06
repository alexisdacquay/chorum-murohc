from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from threading import Barrier

import psycopg
import pytest
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import AbstractUser, UserManager
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, migrations, models, transaction
from django.db.migrations.executor import MigrationExecutor

from chorum_murohc.identity.models import Household, Membership, User

USER_FIELD_NAMES = (
    'id',
    'password',
    'last_login',
    'is_superuser',
    'username',
    'first_name',
    'last_name',
    'email',
    'is_staff',
    'is_active',
    'date_joined',
    'groups',
    'user_permissions',
)


def _model_fields(model):
    return (*model._meta.local_fields, *model._meta.local_many_to_many)


def _migration_signature(model):
    return tuple(
        sorted((field.name, field.deconstruct()[1:]) for field in _model_fields(model))
    )


def _constraint_signature(model):
    return tuple(constraint.deconstruct()[1:] for constraint in model._meta.constraints)


def test_user_is_the_minimal_configured_abstract_user_subclass():
    assert User.__bases__ == (AbstractUser,)
    assert settings.AUTH_USER_MODEL == 'identity.User'
    assert get_user_model() is User
    assert settings.AUTHENTICATION_BACKENDS == [
        'django.contrib.auth.backends.ModelBackend'
    ]


def test_user_has_only_the_inherited_django_user_fields():
    fields = _model_fields(User)

    assert tuple(field.name for field in fields) == USER_FIELD_NAMES
    assert all(field.model is User for field in fields)


def test_user_preserves_native_username_and_email_configuration():
    username_field = User._meta.get_field('username')
    email_field = User._meta.get_field('email')

    assert User.USERNAME_FIELD == 'username'
    assert User.REQUIRED_FIELDS == ['email']
    assert username_field.blank is False
    assert username_field.null is False
    assert username_field.unique is True
    assert username_field.max_length == 150
    assert any(
        isinstance(validator, UnicodeUsernameValidator)
        for validator in username_field.validators
    )
    assert email_field.blank is True
    assert email_field.unique is False
    assert User.USERNAME_FIELD != 'email'


def test_user_uses_djangos_inherited_user_manager():
    assert type(User.objects) is UserManager
    assert User._meta.local_managers == []


@pytest.mark.django_db
def test_create_user_preserves_native_flags_and_password_behaviour():
    submitted_password = 'fixture-only-ordinary-password'

    user = User.objects.create_user(
        username='ordinary-user',
        password=submitted_password,
    )

    assert user.is_active is True
    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.password != submitted_password
    assert user.check_password(submitted_password) is True
    assert user.check_password('fixture-only-wrong-password') is False

    replacement_password = 'fixture-only-replacement-password'
    user.set_password(replacement_password)

    assert user.password != replacement_password
    assert user.check_password(replacement_password) is True
    assert user.check_password(submitted_password) is False


@pytest.mark.django_db
def test_create_superuser_preserves_native_flags():
    superuser = User.objects.create_superuser(
        username='superuser',
        email='superuser@example.invalid',
        password='fixture-only-superuser-password',
    )

    assert superuser.is_active is True
    assert superuser.is_staff is True
    assert superuser.is_superuser is True


@pytest.mark.django_db
@pytest.mark.parametrize('required_flag', ['is_staff', 'is_superuser'])
def test_create_superuser_rejects_false_required_flags(required_flag):
    flags = {required_flag: False}

    with pytest.raises(ValueError):
        User.objects.create_superuser(
            username=f'invalid-{required_flag}',
            email='invalid@example.invalid',
            password='fixture-only-invalid-superuser-password',
            **flags,
        )


@pytest.mark.django_db
def test_default_backend_authenticates_custom_user_by_exact_username():
    password = 'fixture-only-authentication-password'
    user = User.objects.create_user(username='exact-user', password=password)

    assert authenticate(username='exact-user', password=password) == user
    assert (
        authenticate(
            username='exact-user',
            password='fixture-only-incorrect-password',
        )
        is None
    )


@pytest.mark.django_db
def test_exact_duplicate_username_violates_database_uniqueness():
    User.objects.create_user(username='duplicate-user')

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user(username='duplicate-user')

    assert User.objects.filter(username='duplicate-user').count() == 1


def test_initial_identity_migration_has_the_expected_shape():
    initial_migration = import_module('chorum_murohc.identity.migrations.0001_initial')

    migration = initial_migration.Migration('0001_initial', 'identity')

    assert migration.initial is True
    assert migration.dependencies == [('auth', '0012_alter_user_first_name_max_length')]
    assert len(migration.operations) == 1

    operation = migration.operations[0]
    assert isinstance(operation, migrations.CreateModel)
    assert operation.name == 'User'
    assert tuple(name for name, _ in operation.fields) == USER_FIELD_NAMES
    assert len(operation.managers) == 1
    manager_name, manager = operation.managers[0]
    assert manager_name == 'objects'
    assert type(manager) is UserManager


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

    migration_apps = executor.loader.project_state().apps
    for runtime_model in (User, Household, Membership):
        migration_model = migration_apps.get_model(
            'identity',
            runtime_model.__name__,
        )
        assert migration_model._meta.db_table == runtime_model._meta.db_table
        assert _migration_signature(migration_model) == _migration_signature(
            runtime_model
        )
        assert _constraint_signature(migration_model) == _constraint_signature(
            runtime_model
        )


@pytest.mark.django_db
def test_identity_user_and_permission_relation_tables_exist():
    tables = set(connection.introspection.table_names())

    assert User._meta.db_table == 'identity_user'
    assert {
        'identity_user',
        'identity_user_groups',
        'identity_user_user_permissions',
    } <= tables


def test_household_and_membership_models_have_the_exact_runtime_shape():
    household_fields = _model_fields(Household)
    membership_fields = _model_fields(Membership)

    assert Household.__bases__ == (models.Model,)
    assert Membership.__bases__ == (models.Model,)
    assert tuple(field.name for field in household_fields) == (
        'id',
        'name',
        'members',
    )
    assert tuple(field.name for field in membership_fields) == (
        'id',
        'household',
        'user',
        'role',
    )

    household_id = Household._meta.get_field('id')
    household_name = Household._meta.get_field('name')
    members = Household._meta.get_field('members')
    membership_id = Membership._meta.get_field('id')
    household = Membership._meta.get_field('household')
    user = Membership._meta.get_field('user')

    for implicit_id in (household_id, membership_id):
        assert isinstance(implicit_id, models.BigAutoField)
        assert implicit_id.primary_key is True
        assert implicit_id.auto_created is True

    assert isinstance(household_name, models.CharField)
    assert household_name.max_length == 150
    assert household_name.blank is False
    assert household_name.null is False
    assert household_name.unique is False
    assert household_name.has_default() is False

    assert isinstance(members, models.ManyToManyField)
    assert members.related_model is User
    assert members.remote_field.through is Membership
    assert members.remote_field.through_fields == ('household', 'user')
    assert members.remote_field.related_name == 'households'

    assert isinstance(household, models.ForeignKey)
    assert household.related_model is Household
    assert household.remote_field.on_delete is models.CASCADE
    assert household.remote_field.related_name == 'memberships'
    assert isinstance(user, models.ForeignKey)
    assert user.related_model is User
    assert user.remote_field.on_delete is models.CASCADE
    assert user.remote_field.related_name == 'household_memberships'

    assert Household._meta.db_table == 'identity_household'
    assert Membership._meta.db_table == 'identity_membership'


def test_membership_role_has_the_exact_choices_and_field_contract():
    role = Membership._meta.get_field('role')

    assert issubclass(Membership.Role, models.TextChoices)
    assert list(Membership.Role.choices) == [
        ('parent', 'Parent'),
        ('child', 'Child'),
    ]
    assert list(Membership.Role.values) == ['parent', 'child']
    assert Membership.Role.PARENT.value == 'parent'
    assert Membership.Role.CHILD.value == 'child'
    assert isinstance(role, models.CharField)
    assert role.max_length == 6
    assert list(role.choices) == list(Membership.Role.choices)
    assert role.blank is False
    assert role.null is False
    assert role.has_default() is False


def test_membership_has_only_the_two_exact_named_constraints():
    constraints = {
        constraint.name: constraint for constraint in Membership._meta.constraints
    }

    assert set(constraints) == {
        'identity_membership_household_user_unique',
        'identity_membership_role_valid',
    }
    unique = constraints['identity_membership_household_user_unique']
    role_check = constraints['identity_membership_role_valid']
    assert isinstance(unique, models.UniqueConstraint)
    assert unique.fields == ('household', 'user')
    assert isinstance(role_check, models.CheckConstraint)
    assert role_check.condition == models.Q(role__in=('parent', 'child'))


def test_household_models_define_no_implicit_policy_or_custom_convenience():
    overridden_methods = {'save', 'clean', '__str__', '__repr__'}

    for model in (Household, Membership):
        assert overridden_methods.isdisjoint(model.__dict__)
        assert len(model._meta.local_managers) == 1
        assert type(model.objects) is models.Manager
        assert model.objects.auto_created is True


@pytest.mark.django_db
def test_two_parent_two_child_household_supports_every_navigation_path():
    household = Household.objects.create(name='Four-person household')
    parents = [
        User.objects.create_user(username='parent-one'),
        User.objects.create_user(username='parent-two'),
    ]
    children = [
        User.objects.create_user(username='child-one'),
        User.objects.create_user(username='child-two'),
    ]

    memberships = [
        Membership.objects.create(
            household=household,
            user=user,
            role=role,
        )
        for user, role in (
            (parents[0], Membership.Role.PARENT),
            (parents[1], Membership.Role.PARENT),
            (children[0], Membership.Role.CHILD),
            (children[1], Membership.Role.CHILD),
        )
    ]

    assert set(household.members.all()) == {*parents, *children}
    assert set(household.memberships.all()) == set(memberships)
    for user, membership in zip((*parents, *children), memberships, strict=True):
        assert list(user.households.all()) == [household]
        assert list(user.household_memberships.all()) == [membership]


@pytest.mark.django_db
def test_households_are_empty_by_default_and_support_other_compositions():
    assert Household.objects.count() == 0
    assert Membership.objects.count() == 0

    parent = User.objects.create_user(username='flexible-parent')
    assert Household.objects.count() == 0
    assert Membership.objects.count() == 0

    household = Household.objects.create(name='Flexible household')
    assert household.members.count() == 0
    assert household.memberships.count() == 0

    children = [
        User.objects.create_user(username=f'flexible-child-{index}')
        for index in range(1, 4)
    ]
    Membership.objects.create(
        household=household,
        user=parent,
        role=Membership.Role.PARENT,
    )
    for child in children:
        Membership.objects.create(
            household=household,
            user=child,
            role=Membership.Role.CHILD,
        )

    assert household.members.count() == 4
    assert household.memberships.filter(role=Membership.Role.PARENT).count() == 1
    assert household.memberships.filter(role=Membership.Role.CHILD).count() == 3


@pytest.mark.django_db
def test_one_user_can_have_different_roles_in_two_households_without_leakage():
    user = User.objects.create_user(username='multi-household-user')
    first_household = Household.objects.create(name='First household')
    second_household = Household.objects.create(name='Second household')
    parent_membership = Membership.objects.create(
        household=first_household,
        user=user,
        role=Membership.Role.PARENT,
    )
    child_membership = Membership.objects.create(
        household=second_household,
        user=user,
        role=Membership.Role.CHILD,
    )

    assert set(user.households.all()) == {first_household, second_household}
    assert set(user.household_memberships.all()) == {
        parent_membership,
        child_membership,
    }
    assert list(first_household.members.all()) == [user]
    assert list(second_household.members.all()) == [user]
    assert list(first_household.memberships.values_list('role', flat=True)) == [
        'parent'
    ]
    assert list(second_household.memberships.values_list('role', flat=True)) == [
        'child'
    ]


@pytest.mark.django_db
def test_duplicate_household_user_pair_is_rejected_and_transaction_recovers():
    household = Household.objects.create(name='Unique-pair household')
    user = User.objects.create_user(username='unique-pair-user')
    Membership.objects.create(
        household=household,
        user=user,
        role=Membership.Role.PARENT,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        Membership.objects.create(
            household=household,
            user=user,
            role=Membership.Role.CHILD,
        )

    assert Membership.objects.filter(household=household, user=user).count() == 1
    assert Household.objects.filter(pk=household.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_postgresql_concurrent_duplicate_pair_allows_exactly_one_commit():
    if connection.vendor != 'postgresql':
        pytest.skip('requires the guarded PostgreSQL target')

    household = Household.objects.create(name='Concurrent household')
    user = User.objects.create_user(username='concurrent-user')
    connection_parameters = {
        'dbname': connection.settings_dict['NAME'],
        'user': connection.settings_dict['USER'],
        'password': connection.settings_dict['PASSWORD'],
        'host': connection.settings_dict['HOST'],
        'port': connection.settings_dict['PORT'],
    }
    barrier = Barrier(2)

    def insert_membership(role):
        backend_pid = None
        try:
            with (
                psycopg.connect(**connection_parameters) as raw_connection,
                raw_connection.cursor() as cursor,
            ):
                cursor.execute('SELECT pg_backend_pid()')
                backend_pid = cursor.fetchone()[0]
                barrier.wait(timeout=10)
                cursor.execute(
                    'INSERT INTO identity_membership '
                    '(household_id, user_id, role) VALUES (%s, %s, %s)',
                    (household.pk, user.pk, role),
                )
            return 'committed', backend_pid, None
        except psycopg.errors.UniqueViolation as error:
            return 'rejected', backend_pid, error.diag.constraint_name

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(insert_membership, Membership.Role.PARENT),
            executor.submit(insert_membership, Membership.Role.CHILD),
        ]
        results = [future.result(timeout=15) for future in futures]

    assert sorted(result[0] for result in results) == ['committed', 'rejected']
    assert len({result[1] for result in results}) == 2
    rejected = next(result for result in results if result[0] == 'rejected')
    assert rejected[2] == 'identity_membership_household_user_unique'
    assert Membership.objects.filter(household=household, user=user).count() == 1


@pytest.mark.django_db
def test_native_full_clean_rejects_invalid_fields_and_duplicate_pair():
    household = Household.objects.create(name='Validation household')
    user = User.objects.create_user(username='validation-user')
    Membership.objects.create(
        household=household,
        user=user,
        role=Membership.Role.PARENT,
    )

    with pytest.raises(ValidationError) as blank_name_error:
        Household(name='').full_clean()
    assert 'name' in blank_name_error.value.message_dict

    with pytest.raises(ValidationError) as long_name_error:
        Household(name='x' * 151).full_clean()
    assert 'name' in long_name_error.value.message_dict

    with pytest.raises(ValidationError) as invalid_role_error:
        Membership(household=household, user=user, role='guest').full_clean(
            validate_constraints=False
        )
    assert 'role' in invalid_role_error.value.message_dict

    with pytest.raises(ValidationError) as duplicate_error:
        Membership(
            household=household,
            user=user,
            role=Membership.Role.CHILD,
        ).full_clean()
    assert '__all__' in duplicate_error.value.message_dict


@pytest.mark.django_db
def test_direct_invalid_role_write_is_rejected_by_the_database_check():
    household = Household.objects.create(name='Role-check household')
    user = User.objects.create_user(username='role-check-user')

    with pytest.raises(IntegrityError), transaction.atomic():
        Membership.objects.create(household=household, user=user, role='guest')

    assert Membership.objects.filter(household=household, user=user).count() == 0


@pytest.mark.django_db
def test_membership_user_and_household_deletions_have_bounded_cascades():
    household = Household.objects.create(name='Cascade household')
    first_user = User.objects.create_user(username='cascade-first')
    second_user = User.objects.create_user(username='cascade-second')
    membership = Membership.objects.create(
        household=household,
        user=first_user,
        role=Membership.Role.PARENT,
    )

    membership.delete()
    assert Household.objects.filter(pk=household.pk).exists()
    assert User.objects.filter(pk=first_user.pk).exists()
    assert Membership.objects.count() == 0

    Membership.objects.create(
        household=household,
        user=first_user,
        role=Membership.Role.PARENT,
    )
    second_membership = Membership.objects.create(
        household=household,
        user=second_user,
        role=Membership.Role.CHILD,
    )
    first_user.delete()
    assert Household.objects.filter(pk=household.pk).exists()
    assert User.objects.filter(pk=second_user.pk).exists()
    assert list(Membership.objects.all()) == [second_membership]

    household.delete()
    assert Membership.objects.count() == 0
    assert User.objects.filter(pk=second_user.pk).exists()


@pytest.mark.django_db
def test_household_schema_tables_columns_constraints_and_foreign_keys():
    tables = set(connection.introspection.table_names())

    assert 'identity_household' in tables
    assert 'identity_membership' in tables
    assert 'identity_household_members' not in tables

    with connection.cursor() as cursor:
        household_columns = {
            column.name
            for column in connection.introspection.get_table_description(
                cursor,
                'identity_household',
            )
        }
        membership_columns = {
            column.name
            for column in connection.introspection.get_table_description(
                cursor,
                'identity_membership',
            )
        }
        constraints = connection.introspection.get_constraints(
            cursor,
            'identity_membership',
        )

    assert household_columns == {'id', 'name'}
    assert membership_columns == {'id', 'household_id', 'user_id', 'role'}
    unique = constraints['identity_membership_household_user_unique']
    role_check = constraints['identity_membership_role_valid']
    assert unique['unique'] is True
    assert unique['columns'] == ['household_id', 'user_id']
    assert role_check['check'] is True
    assert role_check['columns'] == ['role']
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


def test_household_membership_migration_has_the_exact_schema_only_shape():
    migration_module = import_module(
        'chorum_murohc.identity.migrations.0002_household_membership'
    )
    migration = migration_module.Migration('0002_household_membership', 'identity')

    assert migration.dependencies == [('identity', '0001_initial')]
    assert tuple(type(operation) for operation in migration.operations) == (
        migrations.CreateModel,
        migrations.CreateModel,
        migrations.AddField,
        migrations.AddConstraint,
        migrations.AddConstraint,
    )

    household, membership, members, unique, role_check = migration.operations
    assert household.name == 'Household'
    assert tuple(name for name, _ in household.fields) == ('id', 'name')
    assert membership.name == 'Membership'
    assert tuple(name for name, _ in membership.fields) == (
        'id',
        'role',
        'household',
        'user',
    )
    assert members.model_name == 'household'
    assert members.name == 'members'
    assert unique.model_name == 'membership'
    assert unique.constraint.name == 'identity_membership_household_user_unique'
    assert unique.constraint.fields == ('household', 'user')
    assert role_check.model_name == 'membership'
    assert role_check.constraint.name == 'identity_membership_role_valid'
    assert role_check.constraint.condition == models.Q(role__in=('parent', 'child'))
