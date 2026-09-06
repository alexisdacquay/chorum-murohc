import importlib.util
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / '.github' / 'scripts' / 'ci_postgresql.py'
BOOT_ID = '12345678-1234-5678-9abc-123456789abc'
BOOTSTRAP_PASSWORD = '38a5b79e4b2579989b1571bee17b0a3916304b54c5611b46125934e53d513178'
RESTRICTED_PASSWORD = 'e2a52a710f1e9c95153cd56f14cce14d9fe65d1e8364bac1992658ab49f456bb'


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
        'CI_POSTGRES_BOOTSTRAP_PASSWORD': BOOTSTRAP_PASSWORD,
        'CI_POSTGRES_BASE_DATABASE': database_name,
        'CI_POSTGRES_TEST_DATABASE': f'test_{database_name}',
        'CI_POSTGRES_RESTRICTED_ROLE': database_name,
        'CI_POSTGRES_EXPECT_DJANGO_CLEANUP': 'false',
        'DJANGO_ENVIRONMENT': 'development',
        'DJANGO_DB_ENGINE': 'postgresql',
        'DJANGO_DB_TARGET': target,
        'DJANGO_DB_NAME': database_name,
        'DJANGO_DB_USER': database_name,
        'DJANGO_DB_PASSWORD': RESTRICTED_PASSWORD,
        'DJANGO_DB_HOST': 'postgres',
        'DJANGO_DB_PORT': '5432',
        'GITHUB_RUN_ID': '123456789',
        'GITHUB_RUN_ATTEMPT': '1',
        'GITHUB_JOB': 'backend',
        'GITHUB_OUTPUT': '/runner/managed/output',
    }


def fixed_credentials(module):
    return module.Credentials(
        initial_password=BOOT_ID,
        bootstrap_password=BOOTSTRAP_PASSWORD,
        restricted_password=RESTRICTED_PASSWORD,
    )


def fixed_credential_initializer(module):
    def initialise(environment, contract):
        assert environment['CI_POSTGRES_TARGET'] == contract.target
        return fixed_credentials(module)

    return initialise


class FakeGateway:
    def __init__(
        self,
        module,
        *,
        include_resources=False,
        include_test=False,
        events=None,
    ):
        self.module = module
        self.events = [] if events is None else events
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

    def rotate_bootstrap(self, password):
        assert password == BOOTSTRAP_PASSWORD
        self.events.append(('rotate_bootstrap',))

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
        assert password == RESTRICTED_PASSWORD
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
    assert credentials.initial_password is None
    assert credentials.bootstrap_password
    assert credentials.restricted_password


def test_boot_id_reader_accepts_only_the_exact_lowercase_uuid_content(
    ci_postgresql,
    tmp_path,
    monkeypatch,
):
    seed_path = tmp_path / 'boot_id'
    seed_path.write_text(f'{BOOT_ID}\n', encoding='utf-8')
    monkeypatch.setattr(ci_postgresql, 'BOOT_ID_PATH', seed_path)

    assert ci_postgresql._read_boot_id() == BOOT_ID


@pytest.mark.parametrize(
    'content',
    [
        '12345678-1234-5678-9ABC-123456789abc',
        '12345678123456789abc123456789abc',
        f' {BOOT_ID}',
        f'{BOOT_ID} ',
        BOOT_ID,
        f'{BOOT_ID}\n\n',
    ],
)
def test_boot_id_reader_rejects_non_contract_content(
    ci_postgresql,
    tmp_path,
    monkeypatch,
    content,
):
    seed_path = tmp_path / 'boot_id'
    seed_path.write_text(content, encoding='utf-8')
    monkeypatch.setattr(ci_postgresql, 'BOOT_ID_PATH', seed_path)

    with pytest.raises(ci_postgresql.ContractError):
        ci_postgresql._read_boot_id()


def test_credentials_use_exact_context_domains_and_mask_before_transfer(
    ci_postgresql,
):
    environment = valid_environment()
    contract = ci_postgresql.contract_from_environment(environment)
    events = []

    credentials = ci_postgresql.initialise_credentials(
        environment,
        contract,
        boot_id_reader=lambda: BOOT_ID,
        mask_writer=lambda value: events.append(('mask', value)),
        output_writer=lambda name, value: events.append(('output', name, value)),
    )

    assert credentials.initial_password == BOOT_ID
    assert credentials.bootstrap_password == BOOTSTRAP_PASSWORD
    assert credentials.restricted_password == RESTRICTED_PASSWORD
    assert credentials.bootstrap_password != credentials.restricted_password
    assert events == [
        ('mask', BOOT_ID),
        ('mask', BOOTSTRAP_PASSWORD),
        ('mask', RESTRICTED_PASSWORD),
        ('output', 'rotated_bootstrap', BOOTSTRAP_PASSWORD),
        ('output', 'restricted', RESTRICTED_PASSWORD),
    ]
    assert all(BOOT_ID not in event[1:] for event in events[3:])


@pytest.mark.parametrize(
    ('variable', 'invalid_value'),
    [
        ('GITHUB_RUN_ID', '987654321'),
        ('GITHUB_RUN_ID', '123456789x'),
        ('GITHUB_RUN_ATTEMPT', '2'),
        ('GITHUB_RUN_ATTEMPT', '01x'),
        ('GITHUB_JOB', 'Backend'),
        ('GITHUB_JOB', 'frontend'),
    ],
)
def test_credential_initialisation_rejects_mismatched_runner_context_before_masking(
    ci_postgresql,
    variable,
    invalid_value,
):
    environment = valid_environment()
    environment[variable] = invalid_value
    contract = ci_postgresql.contract_from_environment(environment)
    events = []

    with pytest.raises(ci_postgresql.ContractError):
        ci_postgresql.initialise_credentials(
            environment,
            contract,
            boot_id_reader=lambda: BOOT_ID,
            mask_writer=lambda value: events.append(('mask', value)),
            output_writer=lambda name, value: events.append(('output', name, value)),
        )

    assert events == []


@pytest.mark.parametrize(
    'boot_id',
    [
        '12345678-1234-5678-9ABC-123456789abc',
        'not-a-uuid',
        f'{BOOT_ID}\n',
    ],
)
def test_credential_initialisation_rejects_invalid_seed_before_mask_or_output(
    ci_postgresql,
    boot_id,
):
    environment = valid_environment()
    contract = ci_postgresql.contract_from_environment(environment)
    events = []

    with pytest.raises(ci_postgresql.ContractError):
        ci_postgresql.initialise_credentials(
            environment,
            contract,
            boot_id_reader=lambda: boot_id,
            mask_writer=lambda value: events.append(('mask', value)),
            output_writer=lambda name, value: events.append(('output', name, value)),
        )

    assert events == []


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

    ci_postgresql.prepare(
        valid_environment(),
        gateway_factory=lambda *_: gateway,
        credential_initializer=fixed_credential_initializer(ci_postgresql),
    )

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


def test_create_role_uses_client_parameter_binding_required_by_postgresql_ddl(
    ci_postgresql,
    monkeypatch,
):
    recorded = []
    connection = object()

    class RecordingClientCursor:
        def __init__(self, supplied_connection):
            assert supplied_connection is connection

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, query, parameters):
            recorded.append((query, parameters))

    monkeypatch.setattr(
        ci_postgresql.psycopg,
        'ClientCursor',
        RecordingClientCursor,
    )
    gateway = object.__new__(ci_postgresql.PsycopgGateway)
    gateway.admin_connection = connection

    gateway.create_role(
        'chorum_murohc_ci_1_1_backend01',
        RESTRICTED_PASSWORD,
    )

    assert len(recorded) == 1
    query, parameters = recorded[0]
    assert 'CREATE ROLE' in query.as_string(None)
    assert parameters == (RESTRICTED_PASSWORD,)


def test_initial_gateway_connection_uses_seed_exactly_once(
    ci_postgresql,
):
    recorded = []
    connection = object()
    contract = ci_postgresql.contract_from_environment(valid_environment())

    def connector(**kwargs):
        recorded.append(kwargs)
        return connection

    gateway = ci_postgresql.PsycopgGateway(
        contract,
        fixed_credentials(ci_postgresql),
        connector=connector,
    )

    assert gateway.admin_connection is connection
    assert len(recorded) == 1
    assert recorded[0]['password'] == BOOT_ID
    assert recorded[0]['host'] == 'postgres'
    assert recorded[0]['dbname'] == 'postgres'
    assert recorded[0]['user'] == 'postgres'


def test_rotate_bootstrap_uses_client_parameter_binding(
    ci_postgresql,
    monkeypatch,
):
    recorded = []
    connection = object()

    class RecordingClientCursor:
        def __init__(self, supplied_connection):
            assert supplied_connection is connection

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, query, parameters):
            recorded.append((query, parameters))

    monkeypatch.setattr(
        ci_postgresql.psycopg,
        'ClientCursor',
        RecordingClientCursor,
    )
    gateway = object.__new__(ci_postgresql.PsycopgGateway)
    gateway.contract = ci_postgresql.contract_from_environment(valid_environment())
    gateway.admin_connection = connection

    gateway.rotate_bootstrap(BOOTSTRAP_PASSWORD)

    assert len(recorded) == 1
    query, parameters = recorded[0]
    assert 'ALTER ROLE' in query.as_string(None)
    assert parameters == (BOOTSTRAP_PASSWORD,)


def test_prepare_masks_transfers_connects_validates_and_rotates_in_order(
    ci_postgresql,
):
    events = []
    gateway = FakeGateway(ci_postgresql, events=events)

    def initialise(environment, contract):
        return ci_postgresql.initialise_credentials(
            environment,
            contract,
            boot_id_reader=lambda: BOOT_ID,
            mask_writer=lambda value: events.append(('mask', value)),
            output_writer=lambda name, value: events.append(('output', name, value)),
        )

    def gateway_factory(contract, credentials):
        assert contract.target == 'ci_123456789_1_backend01'
        assert credentials.initial_password == BOOT_ID
        events.append(('connect_initial',))
        return gateway

    ci_postgresql.prepare(
        valid_environment(),
        gateway_factory=gateway_factory,
        credential_initializer=initialise,
    )

    assert events[:8] == [
        ('mask', BOOT_ID),
        ('mask', BOOTSTRAP_PASSWORD),
        ('mask', RESTRICTED_PASSWORD),
        ('output', 'rotated_bootstrap', BOOTSTRAP_PASSWORD),
        ('output', 'restricted', RESTRICTED_PASSWORD),
        ('connect_initial',),
        ('server_identity',),
        ('rotate_bootstrap',),
    ]
    first_mutation = next(
        event
        for event in events
        if event[0] in {'rotate_bootstrap', 'create_role', 'create_database'}
    )
    assert first_mutation == ('rotate_bootstrap',)


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
        ci_postgresql.prepare(
            valid_environment(),
            gateway_factory=lambda *_: gateway,
            credential_initializer=fixed_credential_initializer(ci_postgresql),
        )

    assert not any(
        event[0] in {'rotate_bootstrap', 'create_role', 'create_database'}
        for event in gateway.events
    )


@pytest.mark.parametrize(
    'existing_resource', ['role', 'base_database', 'test_database']
)
def test_prepare_requires_fresh_exact_resources_before_creation(
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
        ci_postgresql.prepare(
            valid_environment(),
            gateway_factory=lambda *_: gateway,
            credential_initializer=fixed_credential_initializer(ci_postgresql),
        )

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

    ci_postgresql.prepare(
        valid_environment(),
        gateway_factory=lambda *_: gateway,
        credential_initializer=fixed_credential_initializer(ci_postgresql),
    )

    output = capsys.readouterr().out
    assert 'PostgreSQL 17.11' in output
    assert 'ci_123456789_1_backend01' in output
    assert 'NOSUPERUSER CREATEDB NOCREATEROLE NOREPLICATION' in output
    assert BOOT_ID not in output
    assert BOOTSTRAP_PASSWORD not in output
    assert RESTRICTED_PASSWORD not in output
