"""S-03: the scheduled advisory scan is the test.

There is no live network call in the suite (`testing-guidelines.md` forbids
it), so this checks the one thing a unit test can prove about a scheduled
workflow: it exists, it runs on a pull request as well as on a schedule, it
is pinned exactly like `ci.yml`, and its two steps actually invoke an audit
rather than a command that always exits zero.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = PROJECT_ROOT / '.github' / 'workflows' / 'dependency-audit.yml'

CHECKOUT = 'actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1'
SETUP_UV = 'astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d'
SETUP_PNPM = 'pnpm/setup@703c52620218391530e48b9e8870d5c0082e1b9b'
PYTHON_IMAGE = (
    'python:3.13.12-slim-bookworm@sha256:'
    'a58daefb915e1e03ad48f3ca4df8832065412c5c35cacb9d39f4229184de12b6'
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


def test_the_workflow_runs_on_a_schedule_and_on_every_pull_request():
    text = workflow_text()

    assert text.startswith('name: Dependency audit\n\n')
    on_block = indented_block(text, 'on:')
    assert 'schedule:' in on_block
    assert '- cron:' in on_block
    assert (
        """  pull_request:
    branches:
      - main
    types:
      - opened
      - synchronize
      - reopened
      - ready_for_review"""
        in on_block
    )
    assert 'workflow_dispatch:' in on_block
    assert 'pull_request_target' not in text


def test_permissions_and_concurrency_match_the_backend_gate():
    text = workflow_text()

    assert (
        indented_block(text, 'permissions:')
        == """permissions:
  contents: read"""
    )
    assert (
        indented_block(text, 'concurrency:')
        == """concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}"""
    )
    assert '${{ secrets.' not in text
    assert 'continue-on-error:' not in text
    assert '|| true' not in text


def test_both_jobs_pin_the_same_image_and_actions_as_ci():
    text = workflow_text()

    assert PYTHON_IMAGE in text
    for action in (CHECKOUT, SETUP_UV, SETUP_PNPM):
        assert f'uses: {action}' in text
    assert text.count('persist-credentials: false') == 2


def test_the_backend_job_audits_the_locked_environment_without_a_new_dependency():
    job = job_block(workflow_text(), 'backend')

    assert 'uv sync --locked' in job
    assert 'pip-audit' in job
    # An ephemeral tool run, never added to the project's own dependencies.
    assert '--with pip-audit' in job
    manifest = (PROJECT_ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    assert 'pip-audit' not in manifest


def test_the_frontend_job_audits_the_lockfile_with_pnpms_own_command():
    job = job_block(workflow_text(), 'frontend')

    assert 'pnpm --dir frontend install --frozen-lockfile' in job
    assert 'pnpm --dir frontend audit' in job
