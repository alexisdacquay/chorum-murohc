import hashlib
import os
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import psycopg
from psycopg import sql

CI_TARGET_PATTERN = re.compile(r'ci_[0-9]{1,20}_[0-9]{1,3}_[a-z0-9]{8,16}')
IDENTIFIER_PATTERN = re.compile(r'[a-z0-9_]{1,63}')
BOOT_ID_PATTERN = re.compile(
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
)
DERIVED_CREDENTIAL_PATTERN = re.compile(r'[0-9a-f]{64}')
RUN_ID_PATTERN = re.compile(r'[0-9]{1,20}')
RUN_ATTEMPT_PATTERN = re.compile(r'[0-9]{1,3}')
BOOT_ID_PATH = Path('/proc/sys/kernel/random/boot_id')
EXPECTED_RUNNER_JOB = 'backend'
EXPECTED_TARGET_JOB = 'backend01'
EXPECTED_HOST = 'postgres'
EXPECTED_PORT = '5432'
EXPECTED_SERVER_VERSION = '17.11'
EXPECTED_SERVER_VERSION_NUMBER = '170011'
EXPECTED_BOOTSTRAP_ROLE = 'postgres'
EXPECTED_BOOTSTRAP_DATABASE = 'postgres'
EXPECTED_ROLE_FLAGS_TEXT = 'NOSUPERUSER CREATEDB NOCREATEROLE NOREPLICATION'


class ContractError(RuntimeError):
    """The requested lifecycle operation is outside the exact CI contract."""


@dataclass(frozen=True)
class Contract:
    target: str
    host: str
    port: str
    expected_server_version: str
    bootstrap_role: str
    bootstrap_database: str
    base_database: str
    test_database: str
    role: str


@dataclass(frozen=True)
class Credentials:
    initial_password: str | None = field(repr=False)
    bootstrap_password: str | None = field(repr=False)
    restricted_password: str | None = field(repr=False)


@dataclass(frozen=True)
class RoleState:
    superuser: bool
    createdb: bool
    createrole: bool
    replication: bool
    can_login: bool
    bypass_rls: bool


EXPECTED_ROLE_STATE = RoleState(
    superuser=False,
    createdb=True,
    createrole=False,
    replication=False,
    can_login=True,
    bypass_rls=False,
)


class Gateway(Protocol):
    def rotate_bootstrap(self, password): ...

    def server_identity(self): ...

    def role_state(self, name): ...

    def database_owner(self, name): ...

    def public_tables(self, database): ...

    def create_role(self, name, password): ...

    def create_database(self, name, owner): ...

    def drop_database(self, name): ...

    def drop_role(self, name): ...

    def close(self): ...


GatewayFactory = Callable[[Contract, Credentials], Gateway]


def _required(environment, variable):
    value = environment.get(variable)
    if value is None or not value.strip():
        raise ContractError(f'{variable} is required by the CI contract.')
    return value


def _require_exact(environment, variable, expected):
    value = _required(environment, variable)
    if value != expected:
        raise ContractError(f'{variable} does not match the CI contract.')
    return value


def contract_from_environment(environment: Mapping[str, str]):
    target = _required(environment, 'CI_POSTGRES_TARGET')
    if CI_TARGET_PATTERN.fullmatch(target) is None:
        raise ContractError('CI_POSTGRES_TARGET does not match the CI contract.')

    host = _require_exact(environment, 'CI_POSTGRES_HOST', EXPECTED_HOST)
    port = _require_exact(environment, 'CI_POSTGRES_PORT', EXPECTED_PORT)
    expected_server_version = _require_exact(
        environment,
        'CI_POSTGRES_EXPECTED_VERSION',
        EXPECTED_SERVER_VERSION,
    )
    bootstrap_role = _require_exact(
        environment,
        'CI_POSTGRES_BOOTSTRAP_ROLE',
        EXPECTED_BOOTSTRAP_ROLE,
    )
    bootstrap_database = _require_exact(
        environment,
        'CI_POSTGRES_BOOTSTRAP_DATABASE',
        EXPECTED_BOOTSTRAP_DATABASE,
    )

    base_database = f'chorum_murohc_{target}'
    test_database = f'test_{base_database}'
    role = base_database
    for resource_name in (base_database, test_database, role):
        if IDENTIFIER_PATTERN.fullmatch(resource_name) is None:
            raise ContractError('A derived PostgreSQL identifier is invalid.')

    _require_exact(environment, 'CI_POSTGRES_BASE_DATABASE', base_database)
    _require_exact(environment, 'CI_POSTGRES_TEST_DATABASE', test_database)
    _require_exact(environment, 'CI_POSTGRES_RESTRICTED_ROLE', role)

    _require_exact(environment, 'DJANGO_ENVIRONMENT', 'development')
    _require_exact(environment, 'DJANGO_DB_ENGINE', 'postgresql')
    _require_exact(environment, 'DJANGO_DB_TARGET', target)
    _require_exact(environment, 'DJANGO_DB_NAME', base_database)
    _require_exact(environment, 'DJANGO_DB_USER', role)
    _require_exact(environment, 'DJANGO_DB_HOST', host)
    _require_exact(environment, 'DJANGO_DB_PORT', port)

    return Contract(
        target=target,
        host=host,
        port=port,
        expected_server_version=expected_server_version,
        bootstrap_role=bootstrap_role,
        bootstrap_database=bootstrap_database,
        base_database=base_database,
        test_database=test_database,
        role=role,
    )


def _derived_credential_from_environment(environment, variable, *, required):
    if not required:
        return None
    value = _required(environment, variable)
    if DERIVED_CREDENTIAL_PATTERN.fullmatch(value) is None:
        raise ContractError(f'{variable} does not match the CI contract.')
    return value


def configuration_from_environment(
    environment: Mapping[str, str],
    *,
    require_bootstrap_password=True,
    require_restricted_password=True,
):
    contract = contract_from_environment(environment)
    bootstrap_password = _derived_credential_from_environment(
        environment,
        'CI_POSTGRES_BOOTSTRAP_PASSWORD',
        required=require_bootstrap_password,
    )
    restricted_password = _derived_credential_from_environment(
        environment,
        'DJANGO_DB_PASSWORD',
        required=require_restricted_password,
    )
    if (
        bootstrap_password is not None
        and restricted_password is not None
        and bootstrap_password == restricted_password
    ):
        raise ContractError('The two synthetic CI credentials must differ.')

    return (
        contract,
        Credentials(
            initial_password=None,
            bootstrap_password=bootstrap_password,
            restricted_password=restricted_password,
        ),
    )


def _read_boot_id():
    try:
        raw_value = BOOT_ID_PATH.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as error:
        raise ContractError('The CI bootstrap seed could not be read.') from error

    value = raw_value.removesuffix('\n')
    if raw_value != f'{value}\n' or BOOT_ID_PATTERN.fullmatch(value) is None:
        raise ContractError('The CI bootstrap seed does not match the contract.')
    return value


def _runner_context(environment, contract):
    run_id = _required(environment, 'GITHUB_RUN_ID')
    run_attempt = _required(environment, 'GITHUB_RUN_ATTEMPT')
    job = _require_exact(environment, 'GITHUB_JOB', EXPECTED_RUNNER_JOB)
    if RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise ContractError('GITHUB_RUN_ID does not match the CI contract.')
    if RUN_ATTEMPT_PATTERN.fullmatch(run_attempt) is None:
        raise ContractError('GITHUB_RUN_ATTEMPT does not match the CI contract.')
    expected_target = f'ci_{run_id}_{run_attempt}_{EXPECTED_TARGET_JOB}'
    if contract.target != expected_target:
        raise ContractError('Runner identity does not match CI_POSTGRES_TARGET.')
    return f't017:{run_id}:{run_attempt}:{job}'


def _mask_value(value):
    print(f'::add-mask::{value}', flush=True)


def _write_runner_output(environment, name, value):
    output_path = _required(environment, 'GITHUB_OUTPUT')
    try:
        with Path(output_path).open('a', encoding='utf-8') as output_file:
            output_file.write(f'{name}={value}\n')
    except OSError as error:
        raise ContractError(
            'A masked CI credential could not be transferred.'
        ) from error


def initialise_credentials(
    environment: Mapping[str, str],
    contract: Contract,
    *,
    boot_id_reader=_read_boot_id,
    mask_writer=_mask_value,
    output_writer=None,
):
    boot_id = boot_id_reader()
    if BOOT_ID_PATTERN.fullmatch(boot_id) is None:
        raise ContractError('The CI bootstrap seed does not match the contract.')
    context = _runner_context(environment, contract)

    mask_writer(boot_id)
    bootstrap_password = hashlib.sha256(
        f'{context}:bootstrap:{boot_id}'.encode()
    ).hexdigest()
    restricted_password = hashlib.sha256(
        f'{context}:restricted:{boot_id}'.encode()
    ).hexdigest()
    if bootstrap_password == restricted_password:
        raise ContractError('The derived CI credentials must differ.')

    mask_writer(bootstrap_password)
    mask_writer(restricted_password)

    if output_writer is None:
        output_writer = lambda name, value: _write_runner_output(
            environment,
            name,
            value,
        )
    output_writer('rotated_bootstrap', bootstrap_password)
    output_writer('restricted', restricted_password)

    return Credentials(
        initial_password=boot_id,
        bootstrap_password=bootstrap_password,
        restricted_password=restricted_password,
    )


def _identifier(name):
    if IDENTIFIER_PATTERN.fullmatch(name) is None:
        raise ContractError('Refusing an invalid PostgreSQL identifier.')
    return sql.Identifier(name)


class PsycopgGateway:
    def __init__(self, contract, credentials, connector=psycopg.connect):
        connection_password = (
            credentials.initial_password or credentials.bootstrap_password
        )
        if connection_password is None:
            raise ContractError('The bootstrap credential is required for connection.')
        self.contract = contract
        self.credentials = credentials
        self.connector = connector
        self.admin_connection = connector(
            host=contract.host,
            port=contract.port,
            dbname=contract.bootstrap_database,
            user=contract.bootstrap_role,
            password=connection_password,
            autocommit=True,
            connect_timeout=10,
        )

    def _fetchone(self, query, parameters=()):
        with self.admin_connection.cursor() as cursor:
            cursor.execute(query, parameters)
            return cursor.fetchone()

    def rotate_bootstrap(self, password):
        if password is None:
            raise ContractError('The rotated bootstrap credential is required.')
        query = sql.SQL('ALTER ROLE {} WITH PASSWORD %s').format(
            _identifier(self.contract.bootstrap_role)
        )
        with psycopg.ClientCursor(self.admin_connection) as cursor:
            cursor.execute(query, (password,))

    def server_identity(self):
        row = self._fetchone(
            """
            SELECT current_setting('server_version'),
                   current_setting('server_version_num'),
                   current_user,
                   current_database()
            """
        )
        if row is None:
            raise ContractError('PostgreSQL did not report its server identity.')
        return row

    def role_state(self, name):
        row = self._fetchone(
            """
            SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication,
                   rolcanlogin, rolbypassrls
            FROM pg_catalog.pg_roles
            WHERE rolname = %s
            """,
            (name,),
        )
        if row is None:
            return None
        return RoleState(*row)

    def database_owner(self, name):
        row = self._fetchone(
            """
            SELECT owner.rolname
            FROM pg_catalog.pg_database AS database
            JOIN pg_catalog.pg_roles AS owner ON owner.oid = database.datdba
            WHERE database.datname = %s
            """,
            (name,),
        )
        return None if row is None else row[0]

    def public_tables(self, database):
        if self.credentials.bootstrap_password is None:
            raise ContractError('The rotated bootstrap credential is required.')
        connection = self.connector(
            host=self.contract.host,
            port=self.contract.port,
            dbname=database,
            user=self.contract.bootstrap_role,
            password=self.credentials.bootstrap_password,
            autocommit=True,
            connect_timeout=10,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT tablename
                    FROM pg_catalog.pg_tables
                    WHERE schemaname = 'public'
                    ORDER BY tablename
                    """
                )
                return tuple(row[0] for row in cursor.fetchall())
        finally:
            connection.close()

    def create_role(self, name, password):
        if password is None:
            raise ContractError('The restricted credential is required for prepare.')
        query = sql.SQL(
            'CREATE ROLE {} WITH LOGIN PASSWORD %s '
            'NOSUPERUSER CREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS'
        ).format(_identifier(name))
        with psycopg.ClientCursor(self.admin_connection) as cursor:
            cursor.execute(query, (password,))

    def create_database(self, name, owner):
        query = sql.SQL(
            "CREATE DATABASE {} WITH OWNER {} TEMPLATE template0 ENCODING 'UTF8'"
        ).format(
            _identifier(name),
            _identifier(owner),
        )
        with self.admin_connection.cursor() as cursor:
            cursor.execute(query)

    def drop_database(self, name):
        query = sql.SQL('DROP DATABASE {} WITH (FORCE)').format(_identifier(name))
        with self.admin_connection.cursor() as cursor:
            cursor.execute(query)

    def drop_role(self, name):
        query = sql.SQL('DROP ROLE {}').format(_identifier(name))
        with self.admin_connection.cursor() as cursor:
            cursor.execute(query)

    def close(self):
        self.admin_connection.close()


def _default_gateway(contract, credentials):
    return PsycopgGateway(contract, credentials)


def _validate_server(gateway, contract):
    server_version, version_number, current_role, current_database = (
        gateway.server_identity()
    )
    if (
        server_version != contract.expected_server_version
        or version_number != EXPECTED_SERVER_VERSION_NUMBER
    ):
        raise ContractError('PostgreSQL server version does not match the CI contract.')
    if current_role != contract.bootstrap_role:
        raise ContractError('PostgreSQL bootstrap role does not match the CI contract.')
    if current_database != contract.bootstrap_database:
        raise ContractError(
            'PostgreSQL bootstrap database does not match the CI contract.'
        )
    return server_version


def _validate_role_state(role_state):
    if role_state != EXPECTED_ROLE_STATE:
        raise ContractError('The restricted PostgreSQL role flags are unsafe.')


def _validate_ready_resources(gateway, contract):
    role_state = gateway.role_state(contract.role)
    _validate_role_state(role_state)

    base_owner = gateway.database_owner(contract.base_database)
    if base_owner != contract.role:
        raise ContractError('The base PostgreSQL database owner is unsafe.')

    if gateway.database_owner(contract.test_database) is not None:
        raise ContractError('The derived test database already exists.')

    if gateway.public_tables(contract.base_database):
        raise ContractError('The base PostgreSQL public schema is not empty.')


def _report(phase, contract, server_version, resource_state):
    print(
        f'CI PostgreSQL {phase}: PostgreSQL {server_version}; '
        f'target={contract.target}; host={contract.host}; port={contract.port}; '
        f'base_database={contract.base_database}; '
        f'test_database={contract.test_database}; role={contract.role}; '
        f'role_flags={EXPECTED_ROLE_FLAGS_TEXT}; {resource_state}'
    )


def prepare(
    environment: Mapping[str, str],
    *,
    gateway_factory: GatewayFactory = _default_gateway,
    credential_initializer=initialise_credentials,
):
    contract = contract_from_environment(environment)
    credentials = credential_initializer(environment, contract)
    gateway = gateway_factory(contract, credentials)
    try:
        server_version = _validate_server(gateway, contract)
        gateway.rotate_bootstrap(credentials.bootstrap_password)
        if gateway.role_state(contract.role) is not None:
            raise ContractError('The derived restricted role already exists.')
        if gateway.database_owner(contract.base_database) is not None:
            raise ContractError('The derived base database already exists.')
        if gateway.database_owner(contract.test_database) is not None:
            raise ContractError('The derived test database already exists.')

        gateway.create_role(contract.role, credentials.restricted_password)
        gateway.create_database(contract.base_database, contract.role)
        _validate_ready_resources(gateway, contract)
        _report(
            'prepare',
            contract,
            server_version,
            'bootstrap_rotation=complete; base_public_schema=empty; '
            'test_database_state=absent',
        )
    finally:
        gateway.close()


def cleanup(
    environment: Mapping[str, str],
    *,
    gateway_factory: GatewayFactory = _default_gateway,
):
    contract, credentials = configuration_from_environment(
        environment,
        require_restricted_password=False,
    )
    expect_django_cleanup = _required(
        environment,
        'CI_POSTGRES_EXPECT_DJANGO_CLEANUP',
    )
    if expect_django_cleanup not in {'true', 'false'}:
        raise ContractError(
            'CI_POSTGRES_EXPECT_DJANGO_CLEANUP does not match the CI contract.'
        )
    gateway = gateway_factory(contract, credentials)
    try:
        server_version = _validate_server(gateway, contract)
        role_state = gateway.role_state(contract.role)
        base_owner = gateway.database_owner(contract.base_database)
        test_owner = gateway.database_owner(contract.test_database)

        if role_state is None:
            if base_owner is not None or test_owner is not None:
                raise ContractError('A derived database has no validated owner role.')
        else:
            _validate_role_state(role_state)

        base_tables = ()
        if base_owner is not None:
            if base_owner != contract.role:
                raise ContractError('The base PostgreSQL database owner is unsafe.')
            base_tables = gateway.public_tables(contract.base_database)

        if test_owner is not None and test_owner != contract.role:
            raise ContractError('The test PostgreSQL database owner is unsafe.')

        django_cleanup_failed = expect_django_cleanup == 'true' and (
            test_owner is not None or bool(base_tables)
        )

        if test_owner is not None:
            gateway.drop_database(contract.test_database)
        if base_owner is not None:
            gateway.drop_database(contract.base_database)
        if role_state is not None:
            gateway.drop_role(contract.role)

        if gateway.database_owner(contract.test_database) is not None:
            raise ContractError('The derived test database cleanup was incomplete.')
        if gateway.database_owner(contract.base_database) is not None:
            raise ContractError('The derived base database cleanup was incomplete.')
        if gateway.role_state(contract.role) is not None:
            raise ContractError('The derived role cleanup was incomplete.')

        _report(
            'cleanup',
            contract,
            server_version,
            'test_database_state=absent; base_database_state=absent; role_state=absent',
        )
        if django_cleanup_failed:
            raise ContractError(
                'Django cleanup did not leave an absent test database and empty base.'
            )
    finally:
        gateway.close()


def main(arguments=None):
    arguments = sys.argv[1:] if arguments is None else arguments
    if len(arguments) != 1 or arguments[0] not in {'prepare', 'cleanup'}:
        print(
            'Usage: ci_postgresql.py {prepare|cleanup}',
            file=sys.stderr,
        )
        return 2

    operation = {
        'prepare': prepare,
        'cleanup': cleanup,
    }[arguments[0]]
    try:
        operation(os.environ)
    except ContractError as error:
        print(f'CI PostgreSQL contract rejected: {error}', file=sys.stderr)
        return 1
    except psycopg.Error:
        print(
            'CI PostgreSQL operation failed; credential details withheld.',
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
