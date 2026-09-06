import importlib.util
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / '.github' / 'scripts' / 'ci_postgresql.py'


def load_ci_postgresql_module():
    spec = importlib.util.spec_from_file_location('ci_postgresql', SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def ci_postgresql():
    return load_ci_postgresql_module()


def valid_environment(target='ci_123456789_1_backend01'):
    database_name = f'chorum_murohc_{target}'
    return {
        'CI_POSTGRES_TARGET': target,
        'CI_POSTGRES_HOST': 'postgres',
        'CI_POSTGRES_PORT': '5432',
        'CI_POSTGRES_EXPECTED_VERSION': '17.11',
        'CI_POSTGRES_BOOTSTRAP_ROLE': 'postgres',
        'CI_POSTGRES_BOOTSTRAP_DATABASE': 'postgres',
        'CI_POSTGRES_BOOTSTRAP_PASSWORD': 'synthetic-bootstrap-value',
        'CI_POSTGRES_BASE_DATABASE': database_name,
        'CI_POSTGRES_TEST_DATABASE': f'test_{database_name}',
        'CI_POSTGRES_RESTRICTED_ROLE': database_name,
        'CI_POSTGRES_EXPECT_DJANGO_CLEANUP': 'false',
        'DJANGO_ENVIRONMENT': 'development',
        'DJANGO_DB_ENGINE': 'postgresql',
        'DJANGO_DB_TARGET': target,
        'DJANGO_DB_NAME': database_name,
        'DJANGO_DB_USER': database_name,
        'DJANGO_DB_PASSWORD': 'synthetic-restricted-value',
        'DJANGO_DB_HOST': 'postgres',
        'DJANGO_DB_PORT': '5432',
    }


class FakeGateway:
    def __init__(self, module, *, include_resources=False, include_test=False):
        self.module = module
        self.events = []
        self.identity = ('17.11', '170011', 'postgres', 'postgres')
        self.role_states = {}
        self.database_owners = {}
        self.tables = {}

        if include_resources:
            contract, _ = module.configuration_from_environment(valid_environment())
            self.role_states[contract.role] = module.RoleState(
                superuser=False,
                createdb=True,
                createrole=False,
                replication=False,
                can_login=True,
                bypass_rls=False,
            )
            self.database_owners[contract.base_database] = contract.role
            self.tables[contract.base_database] = ()
            if include_test:
                self.database_owners[contract.test_database] = contract.role

    def server_identity(self):
        self.events.append(('server_identity',))
        return self.identity

    def role_state(self, name):
        self.events.append(('role_state', name))
        return self.role_states.get(name)

    def database_owner(self, name):
        self.events.append(('database_owner', name))
        return self.database_owners.get(name)

    def public_tables(self, database):
        self.events.append(('public_tables', database))
        return self.tables.get(database, ())

    def create_role(self, name, password):
        assert password == 'synthetic-restricted-value'
        self.events.append(('create_role', name))
        self.role_states[name] = self.module.RoleState(
            superuser=False,
            createdb=True,
            createrole=False,
            replication=False,
            can_login=True,
            bypass_rls=False,
        )

    def create_database(self, name, owner):
        self.events.append(('create_database', name, owner))
        self.database_owners[name] = owner
        self.tables[name] = ()

    def drop_database(self, name):
        self.events.append(('drop_database', name))
        self.database_owners.pop(name, None)
        self.tables.pop(name, None)

    def drop_role(self, name):
        self.events.append(('drop_role', name))
        self.role_states.pop(name, None)

    def close(self):
        self.events.append(('close',))


@pytest.mark.parametrize(
    'target',
    [
        'ci_1_1_abcdefgh',
        'ci_12345678901234567890_123_0123456789abcdef',
    ],
)
def test_configuration_derives_only_the_exact_ci_names(ci_postgresql, target):
    contract, credentials = ci_postgresql.configuration_from_environment(
        valid_environment(target)
    )

    expected_database = f'chorum_murohc_{target}'
    assert contract.target == target
    assert contract.host == 'postgres'
    assert contract.port == '5432'
    assert contract.bootstrap_role == 'postgres'
    assert contract.bootstrap_database == 'postgres'
    assert contract.base_database == expected_database
    assert contract.role == expected_database
    assert contract.test_database == f'test_{expected_database}'
    assert credentials.bootstrap_password
    assert credentials.restricted_password


@pytest.mark.parametrize(
    ('variable', 'invalid_value'),
    [
        ('CI_POSTGRES_HOST', 'database.invalid'),
        ('CI_POSTGRES_TEST_DATABASE', 'test_chorum_murohc_ci_1_1_other000'),
        ('DJANGO_DB_HOST', '127.0.0.1'),
        ('DJANGO_DB_NAME', 'chorum_murohc_ci_1_1_other000'),
        ('DJANGO_DB_USER', 'chorum_murohc_ci_1_1_other000'),
    ],
)
def test_invalid_non_secret_expectation_stops_before_gateway_or_mutation(
    ci_postgresql,
    variable,
    invalid_value,
):
    environment = valid_environment()
    environment[variable] = invalid_value
    gateway_factory_calls = []

    def gateway_factory(*args):
        gateway_factory_calls.append(args)
        pytest.fail('validation must finish before connecting', pytrace=False)

    with pytest.raises(ci_postgresql.ContractError):
        ci_postgresql.prepare(environment, gateway_factory=gateway_factory)

    assert gateway_factory_calls == []


@pytest.mark.parametrize(
    'target',
    [
        'ci_1_1_abcdefg',
        'ci_1_1_abcdefghijklmnopq',
        'ci_123456789012345678901_1_abcdefgh',
        'ci_1_1234_abcdefgh',
        'ci_1_1_ABCDefgh',
        'ci_1_1_abcd_efg',
        'task_t017_abcdefgh',
        'production',
        ' ci_1_1_abcdefgh',
    ],
)
def test_configuration_rejects_every_non_contract_target(ci_postgresql, target):
    environment = valid_environment()
    environment['CI_POSTGRES_TARGET'] = target
    environment['DJANGO_DB_TARGET'] = target

    with pytest.raises(ci_postgresql.ContractError):
        ci_postgresql.configuration_from_environment(environment)


def test_prepare_creates_and_verifies_only_the_derived_resources(ci_postgresql):
    gateway = FakeGateway(ci_postgresql)

    ci_postgresql.prepare(valid_environment(), gateway_factory=lambda *_: gateway)

    contract, _ = ci_postgresql.configuration_from_environment(valid_environment())
    assert ('create_role', contract.role) in gateway.events
    assert (
        'create_database',
        contract.base_database,
        contract.role,
    ) in gateway.events
    assert ('database_owner', contract.test_database) in gateway.events
    assert ('public_tables', contract.base_database) in gateway.events
    assert gateway.events[-1] == ('close',)


@pytest.mark.parametrize(
    'identity',
    [
        ('17.10', '170010', 'postgres', 'postgres'),
        ('17.11', '170011', 'unexpected_role', 'postgres'),
        ('17.11', '170011', 'postgres', 'unexpected_database'),
    ],
)
def test_prepare_rejects_unexpected_server_identity_without_mutation(
    ci_postgresql,
    identity,
):
    gateway = FakeGateway(ci_postgresql)
    gateway.identity = identity

    with pytest.raises(ci_postgresql.ContractError):
        ci_postgresql.prepare(valid_environment(), gateway_factory=lambda *_: gateway)

    assert not any(
        event[0] in {'create_role', 'create_database'} for event in gateway.events
    )


@pytest.mark.parametrize(
    'existing_resource', ['role', 'base_database', 'test_database']
)
def test_prepare_requires_fresh_exact_resources_before_mutation(
    ci_postgresql,
    existing_resource,
):
    gateway = FakeGateway(ci_postgresql)
    contract, _ = ci_postgresql.configuration_from_environment(valid_environment())
    if existing_resource == 'role':
        gateway.role_states[contract.role] = ci_postgresql.EXPECTED_ROLE_STATE
    elif existing_resource == 'base_database':
        gateway.database_owners[contract.base_database] = contract.role
    else:
        gateway.database_owners[contract.test_database] = contract.role

    with pytest.raises(ci_postgresql.ContractError):
        ci_postgresql.prepare(valid_environment(), gateway_factory=lambda *_: gateway)

    assert not any(
        event[0] in {'create_role', 'create_database'} for event in gateway.events
    )


def test_cleanup_validates_every_identity_before_exact_name_mutation(ci_postgresql):
    gateway = FakeGateway(
        ci_postgresql,
        include_resources=True,
        include_test=True,
    )
    contract, _ = ci_postgresql.configuration_from_environment(valid_environment())

    ci_postgresql.cleanup(valid_environment(), gateway_factory=lambda *_: gateway)

    first_mutation = next(
        index
        for index, event in enumerate(gateway.events)
        if event[0] in {'drop_database', 'drop_role'}
    )
    assert ('role_state', contract.role) in gateway.events[:first_mutation]
    assert (
        'database_owner',
        contract.base_database,
    ) in gateway.events[:first_mutation]
    assert (
        'database_owner',
        contract.test_database,
    ) in gateway.events[:first_mutation]
    assert (
        'public_tables',
        contract.base_database,
    ) in gateway.events[:first_mutation]
    assert [
        event for event in gateway.events if event[0] in {'drop_database', 'drop_role'}
    ] == [
        ('drop_database', contract.test_database),
        ('drop_database', contract.base_database),
        ('drop_role', contract.role),
    ]
    assert gateway.events[-1] == ('close',)


def test_cleanup_does_not_touch_similarly_named_neighbour_resources(ci_postgresql):
    gateway = FakeGateway(ci_postgresql, include_resources=True, include_test=True)
    neighbouring_role = 'chorum_murohc_ci_123456789_1_backend02'
    neighbouring_database = neighbouring_role
    gateway.role_states[neighbouring_role] = ci_postgresql.EXPECTED_ROLE_STATE
    gateway.database_owners[neighbouring_database] = neighbouring_role

    ci_postgresql.cleanup(valid_environment(), gateway_factory=lambda *_: gateway)

    assert neighbouring_role in gateway.role_states
    assert neighbouring_database in gateway.database_owners
    assert ('drop_database', neighbouring_database) not in gateway.events
    assert ('drop_role', neighbouring_role) not in gateway.events


@pytest.mark.parametrize('unsafe_state', ['owner', 'flags'])
def test_cleanup_refuses_unsafe_state_without_mutation(
    ci_postgresql,
    unsafe_state,
):
    gateway = FakeGateway(
        ci_postgresql,
        include_resources=True,
        include_test=True,
    )
    contract, _ = ci_postgresql.configuration_from_environment(valid_environment())
    if unsafe_state == 'owner':
        gateway.database_owners[contract.test_database] = 'unexpected_owner'
    elif unsafe_state == 'flags':
        gateway.role_states[contract.role] = ci_postgresql.RoleState(
            superuser=True,
            createdb=True,
            createrole=False,
            replication=False,
            can_login=True,
            bypass_rls=False,
        )

    with pytest.raises(ci_postgresql.ContractError):
        ci_postgresql.cleanup(valid_environment(), gateway_factory=lambda *_: gateway)

    assert not any(
        event[0] in {'drop_database', 'drop_role'} for event in gateway.events
    )
    assert gateway.events[-1] == ('close',)


@pytest.mark.parametrize('dirty_resource', ['test_database', 'base_schema'])
def test_success_path_cleanup_removes_exact_resources_then_reports_django_leak(
    ci_postgresql,
    dirty_resource,
):
    gateway = FakeGateway(ci_postgresql, include_resources=True)
    contract, _ = ci_postgresql.configuration_from_environment(valid_environment())
    if dirty_resource == 'test_database':
        gateway.database_owners[contract.test_database] = contract.role
    else:
        gateway.tables[contract.base_database] = ('unexpected_table',)
    environment = valid_environment()
    environment['CI_POSTGRES_EXPECT_DJANGO_CLEANUP'] = 'true'

    with pytest.raises(ci_postgresql.ContractError):
        ci_postgresql.cleanup(environment, gateway_factory=lambda *_: gateway)

    assert ('drop_database', contract.base_database) in gateway.events
    assert ('drop_role', contract.role) in gateway.events
    assert gateway.events[-1] == ('close',)


def test_lifecycle_output_contains_only_non_secret_contract_evidence(
    ci_postgresql,
    capsys,
):
    gateway = FakeGateway(ci_postgresql)

    ci_postgresql.prepare(valid_environment(), gateway_factory=lambda *_: gateway)

    output = capsys.readouterr().out
    assert 'PostgreSQL 17.11' in output
    assert 'ci_123456789_1_backend01' in output
    assert 'NOSUPERUSER CREATEDB NOCREATEROLE NOREPLICATION' in output
    assert 'synthetic-bootstrap-value' not in output
    assert 'synthetic-restricted-value' not in output
