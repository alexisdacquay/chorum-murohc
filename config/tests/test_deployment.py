"""The deployment files have to keep the promises README.md makes.

Nothing here starts a container; these are the few facts about `Dockerfile`,
`compose.yaml` and the entrypoint that a later edit could quietly drop, and
that nothing else would notice: a pinned image, a non-root account, a
database that is not published, and every variable the production settings
profile refuses to start without.
"""

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = (PROJECT_ROOT / 'Dockerfile').read_text()
COMPOSE = (PROJECT_ROOT / 'compose.yaml').read_text()
ENTRYPOINT = (PROJECT_ROOT / 'docker' / 'entrypoint.sh').read_text()

# What `config.settings` refuses to start production without.
REQUIRED_IN_PRODUCTION = (
    'DJANGO_ENVIRONMENT',
    'DJANGO_ALLOWED_HOSTS',
    'DJANGO_DB_ENGINE',
    'DJANGO_DB_NAME',
    'DJANGO_DB_USER',
    'DJANGO_DB_PASSWORD',
    'DJANGO_DB_HOST',
    'DJANGO_DB_PORT',
)


@pytest.mark.parametrize('variable', REQUIRED_IN_PRODUCTION)
def test_compose_sets_every_variable_production_demands(variable):
    assert f'{variable}:' in COMPOSE


def test_compose_runs_the_production_profile():
    assert 'DJANGO_ENVIRONMENT: production' in COMPOSE


def test_the_secret_key_is_a_generated_file_not_a_compose_value():
    assert 'DJANGO_SECRET_KEY:' not in COMPOSE
    assert 'DJANGO_SECRET_KEY_FILE: /var/lib/chorum/secret_key' in COMPOSE
    # The entrypoint generates that file, once, without printing it.
    assert 'DJANGO_SECRET_KEY_FILE' in ENTRYPOINT
    assert 'secrets.token_urlsafe' in ENTRYPOINT


def test_the_database_publishes_no_port_and_the_app_binds_locally():
    assert COMPOSE.count('ports:') == 1
    assert '${CHORUM_BIND:-127.0.0.1}:${CHORUM_PORT:-8000}:8000' in COMPOSE


def test_the_state_volume_survives_a_restart():
    assert '- state:/var/lib/chorum' in COMPOSE
    assert '- database:/var/lib/postgresql/data' in COMPOSE


@pytest.mark.parametrize('image', ['node:', 'python:', 'postgres:'])
def test_every_base_image_is_pinned_by_digest(image):
    source = COMPOSE if image == 'postgres:' else DOCKERFILE
    lines = [
        line for line in source.splitlines() if image in line and 'sha256:' in line
    ]

    assert lines, f'{image} is not pinned by digest'


def test_the_application_does_not_run_as_root():
    assert '\nUSER household\n' in DOCKERFILE


def test_the_entrypoint_migrates_before_it_serves():
    assert ENTRYPOINT.index('manage.py migrate') < ENTRYPOINT.index('exec "$@"')
