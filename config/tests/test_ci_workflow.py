import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIRECTORY = PROJECT_ROOT / '.github' / 'workflows'
WORKFLOW_PATH = WORKFLOWS_DIRECTORY / 'ci.yml'

CHECKOUT = (
    'actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1',
    'v7.0.1',
)
SETUP_UV = (
    'astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d',
    'v10.0.1',
)
SETUP_PNPM = (
    'pnpm/setup@703c52620218391530e48b9e8870d5c0082e1b9b',
    'v2.1.0',
)
PYTHON_IMAGE = (
    'python:3.13.12-slim-bookworm@sha256:'
    'a58daefb915e1e03ad48f3ca4df8832065412c5c35cacb9d39f4229184de12b6'
)
POSTGRES_IMAGE = (
    'postgres:17.11-alpine@sha256:'
    '18cfe3ef5e6815560c98237d6216d1e5119702fb0f3894c8785dd58b8bbe5d73'
)


def workflow_text():
    return WORKFLOW_PATH.read_text(encoding='utf-8')


def indented_block(text, header):
    lines = text.splitlines()
    start = lines.index(header)
    indentation = len(header) - len(header.lstrip())
    block = [lines[start]]
    for line in lines[start + 1 :]:
        if line and len(line) - len(line.lstrip()) <= indentation:
            break
        block.append(line)
    return '\n'.join(block).rstrip()


def job_block(text, job_id):
    return indented_block(text, f'  {job_id}:')


def step_blocks(job):
    starts = [
        match.start()
        for match in re.finditer(r'^      - name: .+$', job, flags=re.MULTILINE)
    ]
    blocks = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(job)
        blocks.append(job[start:end].rstrip())
    return blocks


def test_ci_is_the_only_workflow_with_exact_triggers():
    assert sorted(path.name for path in WORKFLOWS_DIRECTORY.iterdir()) == ['ci.yml']
    text = workflow_text()

    assert text.startswith('name: CI\n\n')
    assert (
        indented_block(text, 'on:')
        == """on:
  pull_request:
    branches:
      - main
    types:
      - opened
      - synchronize
      - reopened
      - ready_for_review
  push:
    branches:
      - main
  workflow_dispatch:"""
    )
    for forbidden in (
        'pull_request_target',
        'workflow_run',
        'schedule:',
        'paths:',
        'paths-ignore:',
        'branches-ignore:',
    ):
        assert forbidden not in text


def test_permissions_and_concurrency_are_exact_and_cannot_be_widened():
    text = workflow_text()

    assert (
        indented_block(text, 'permissions:')
        == """permissions:
  contents: read"""
    )
    assert len(re.findall(r'^\s*permissions:', text, flags=re.MULTILINE)) == 1
    assert (
        indented_block(text, 'concurrency:')
        == """concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}"""
    )
    assert '${{ secrets.' not in text
    assert 'continue-on-error:' not in text
    assert '|| true' not in text


def test_jobs_have_stable_names_runner_timeouts_and_no_matrix():
    text = workflow_text()
    jobs = indented_block(text, 'jobs:')

    assert re.findall(r'^  ([a-z][a-z0-9_-]*):$', jobs, flags=re.MULTILINE) == [
        'backend',
        'frontend',
    ]
    assert re.findall(r'^    name: (.+)$', jobs, flags=re.MULTILINE) == [
        'Backend',
        'Frontend',
    ]
    assert jobs.count('    runs-on: ubuntu-24.04') == 2
    assert re.findall(r'^    timeout-minutes: ([0-9]+)$', jobs, re.MULTILINE) == [
        '20',
        '15',
    ]
    assert 'matrix:' not in jobs
    assert 'needs:' not in jobs


def test_every_action_and_image_uses_the_exact_reviewed_immutable_pin():
    text = workflow_text()
    action_lines = re.findall(
        r'^\s+uses: (\S+) # (\S+)$',
        text,
        flags=re.MULTILINE,
    )
    every_uses_line = re.findall(r'^\s+uses: (.+)$', text, flags=re.MULTILINE)

    assert action_lines == [CHECKOUT, SETUP_UV, CHECKOUT, SETUP_PNPM]
    assert every_uses_line == [
        f'{action} # {release}' for action, release in action_lines
    ]
    assert all(
        re.fullmatch(r'[a-z0-9-]+/[a-z0-9-]+@[0-9a-f]{40}', action)
        for action, _ in action_lines
    )
    assert text.count(PYTHON_IMAGE) == 1
    assert text.count(POSTGRES_IMAGE) == 1
    assert not re.search(r'^\s+uses: \./', text, flags=re.MULTILINE)


def test_backend_uses_the_guarded_service_and_exact_command_sequence():
    backend = job_block(workflow_text(), 'backend')

    assert indented_block(backend, '    container:') == (
        f'    container:\n      image: {PYTHON_IMAGE}'
    )
    service = indented_block(backend, '    services:')
    assert f'        image: {POSTGRES_IMAGE}' in service
    assert 'POSTGRES_USER: postgres' in service
    assert 'POSTGRES_DB: postgres' in service
    assert '--health-cmd' in service
    assert '--health-interval' in service
    assert '--health-timeout' in service
    assert '--health-retries' in service
    assert 'ports:' not in service
    assert 'volumes:' not in service

    run_commands = re.findall(r'^        run: (.+)$', backend, flags=re.MULTILINE)
    assert run_commands == [
        'python --version',
        'uv --version',
        'uv sync --locked',
        'uv run --locked ruff format --check .',
        'uv run --locked ruff check .',
        'uv run --locked python .github/scripts/ci_postgresql.py prepare',
        'uv run --locked python manage.py check',
        'uv run --locked python manage.py makemigrations --check --dry-run',
        'uv run --locked pytest',
        'uv run --locked python .github/scripts/ci_postgresql.py cleanup',
    ]

    steps = step_blocks(backend)
    assert 'version: 0.12.10' in backend
    assert 'enable-cache: false' in backend
    assert "github-token: ''" in backend
    assert backend.count('persist-credentials: false') == 1
    assert steps[-1].startswith('      - name: Clean isolated PostgreSQL resources')
    assert 'if: ${{ always() }}' in steps[-1]
    assert (
        "CI_POSTGRES_EXPECT_DJANGO_CLEANUP: ${{ job.status == 'success' }}"
        in (steps[-1])
    )


def test_credentials_are_scoped_only_to_the_required_backend_steps():
    backend = job_block(workflow_text(), 'backend')
    steps = step_blocks(backend)
    bootstrap_value = (
        't017-bootstrap-${{ github.run_id }}-${{ github.run_attempt }}-'
        "${{ github.job || 'backend' }}-synthetic"
    )
    bootstrap_steps = [
        step for step in steps if 'CI_POSTGRES_BOOTSTRAP_PASSWORD:' in step
    ]
    restricted_steps = [step for step in steps if 'DJANGO_DB_PASSWORD:' in step]

    assert len(bootstrap_steps) == 2
    assert backend.count(bootstrap_value) == 3
    assert f'POSTGRES_PASSWORD: {bootstrap_value}' in backend
    assert bootstrap_steps[0].startswith('      - name: Prepare isolated PostgreSQL')
    assert bootstrap_steps[1].startswith(
        '      - name: Clean isolated PostgreSQL resources'
    )
    assert len(restricted_steps) == 4
    assert restricted_steps[0].startswith('      - name: Prepare isolated PostgreSQL')
    assert [step.splitlines()[0] for step in restricted_steps[1:]] == [
        '      - name: Run Django system checks',
        '      - name: Check migration drift',
        '      - name: Run backend tests',
    ]
    for step in restricted_steps[1:]:
        assert 'CI_POSTGRES_BOOTSTRAP_PASSWORD:' not in step


def test_frontend_setup_disables_install_and_store_cache_then_runs_exact_commands():
    frontend = job_block(workflow_text(), 'frontend')

    assert 'version: 11.19.0' in frontend
    assert 'runtime: node@24.15.0' in frontend
    assert 'working-directory: frontend' in frontend
    assert 'cache: false' in frontend
    assert 'install: false' in frontend
    assert frontend.count('persist-credentials: false') == 1
    assert re.findall(r'^        run: (.+)$', frontend, flags=re.MULTILINE) == [
        'node --version',
        'pnpm --version',
        'pnpm --dir frontend install --frozen-lockfile',
        'pnpm --dir frontend test',
        'pnpm --dir frontend build',
    ]


def test_workflow_has_no_cache_artifact_anchor_or_override_escape_hatches():
    text = workflow_text()

    for forbidden in (
        'actions/cache',
        'actions/upload-artifact',
        'node_modules',
        'fetch-depth: 0',
    ):
        assert forbidden not in text
    assert not re.search(r'(^|\s)[&*][A-Za-z_][A-Za-z0-9_-]*', text)
    for top_level_key in ('name:', 'on:', 'permissions:', 'concurrency:', 'jobs:'):
        assert len(re.findall(rf'^{re.escape(top_level_key)}', text, re.MULTILINE)) == 1
