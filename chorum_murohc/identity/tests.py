from importlib import import_module

import pytest
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import AbstractUser, UserManager
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import IntegrityError, connection, migrations, transaction
from django.db.migrations.executor import MigrationExecutor

from chorum_murohc.identity.models import User

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


def _user_fields(model):
    return (*model._meta.local_fields, *model._meta.local_many_to_many)


def _migration_signature(model):
    return tuple(field.deconstruct()[1:] for field in _user_fields(model))


def test_user_is_the_minimal_configured_abstract_user_subclass():
    assert User.__bases__ == (AbstractUser,)
    assert settings.AUTH_USER_MODEL == 'identity.User'
    assert get_user_model() is User
    assert settings.AUTHENTICATION_BACKENDS == [
        'django.contrib.auth.backends.ModelBackend'
    ]


def test_user_has_only_the_inherited_django_user_fields():
    fields = _user_fields(User)

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

    migration_user = executor.loader.project_state().apps.get_model(
        'identity',
        'User',
    )
    assert migration_user._meta.db_table == User._meta.db_table
    assert _migration_signature(migration_user) == _migration_signature(User)


@pytest.mark.django_db
def test_identity_user_and_permission_relation_tables_exist():
    tables = set(connection.introspection.table_names())

    assert User._meta.db_table == 'identity_user'
    assert {
        'identity_user',
        'identity_user_groups',
        'identity_user_user_permissions',
    } <= tables
