"""Run the browser journeys: pinned container, headless Chrome, no service.

The shape is deliberately the same as the layout probe this repository
already uses. One disposable container from a pinned image serves the real
Django API and the real built frontend on one origin. One headless Chrome,
pinned by path, opens the driver page once per journey with a fresh profile,
so no journey inherits another's cookies. The container and every profile
are removed when the run ends, and nothing is installed on the machine.

    pnpm --dir frontend build          # the journeys drive the real build
    python3 -m browser_journeys.run_journeys /path/to/worktree

Add journey names to run a subset. The runner discovers Chrome or Chromium
from PATH and common local installations; use `--chrome` for another path.
"""

import argparse
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from browser_journeys.diagnostics import leaked_secrets, secret_values

# The same pinned image the backend gate uses, by digest.
IMAGE = (
    'python:3.13.12-slim-bookworm@sha256:'
    'a58daefb915e1e03ad48f3ca4df8832065412c5c35cacb9d39f4229184de12b6'
)
UV_VERSION = '0.12.10'
CHROME_COMMANDS = (
    'google-chrome',
    'google-chrome-stable',
    'chromium',
    'chromium-browser',
)
STANDARD_CHROME_PATHS = (
    Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
)
JOURNEYS = (
    'smoke',
    'child-submission',
    'parent-queue',
    'reward',
    'creature',
    'audit-accessibility',
    'audit-security',
)
# The two audits report findings rather than asserting there are none, so
# they are not part of the default set a change has to keep green.
AUDITS = ('audit-accessibility', 'audit-security')
DEFAULT_JOURNEYS = tuple(name for name in JOURNEYS if name not in AUDITS)
SERVER_TIMEOUT = 300
JOURNEY_TIMEOUT = 180

CONTAINER_COMMAND = (
    'set -e; '
    'pip install --quiet --disable-pip-version-check --user "uv=={uv}"; '
    'PATH=/tmp/.local/bin:$PATH; export PATH; '
    'uv sync --locked >/dev/null; '
    'exec uv run --locked --no-env-file python -m browser_journeys.serve_app '
    '{port} {token}'
)


def browser_file_candidates():
    """Yield host browser locations that are not normally exposed on PATH."""
    yield from STANDARD_CHROME_PATHS
    managed_browsers = Path.home() / '.agent-browser' / 'browsers'
    yield from sorted(managed_browsers.glob('chrome-*/chrome'), reverse=True)


def discover_chrome(commands=CHROME_COMMANDS, file_candidates=None):
    """Return the first usable Chrome or Chromium path on this host."""
    for command in commands:
        resolved = shutil.which(command)
        if resolved and Path(resolved).is_file():
            return resolved

    candidates = (
        browser_file_candidates() if file_candidates is None else file_candidates
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return str(candidate)
    return None


def default_uv_cache():
    """Return a writable host-neutral cache for disposable journey runs."""
    return Path(tempfile.gettempdir()) / 'chorum-murohc-uv-cache'


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def run_token():
    """A fresh token for this run, generated where the run starts."""
    import secrets

    return secrets.token_hex(5)


def get(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.read()
    except (urllib.error.URLError, OSError, TimeoutError):
        return None


def start_container(worktree, port, token, uv_cache):
    name = f'chorum-journeys-{token}'
    command = [
        'docker',
        'run',
        '--rm',
        '--detach',
        '--name',
        name,
        '--user',
        f'{_uid()}:{_gid()}',
        '--volume',
        f'{worktree}:/src:ro',
        '--volume',
        f'{uv_cache}:/uv-cache',
        '--publish',
        f'127.0.0.1:{port}:{port}',
        '--workdir',
        '/src',
        '--env',
        'HOME=/tmp',
        '--env',
        'UV_CACHE_DIR=/uv-cache',
        '--env',
        'UV_PROJECT_ENVIRONMENT=/tmp/venv',
        '--env',
        'UV_NO_PROGRESS=1',
        '--env',
        'PYTHONDONTWRITEBYTECODE=1',
        '--env',
        'DJANGO_ENVIRONMENT=development',
        '--env',
        f'DJANGO_DB_NAME=/tmp/journeys-{token}.sqlite3',
        IMAGE,
        'sh',
        '-c',
        CONTAINER_COMMAND.format(uv=UV_VERSION, port=port, token=token),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    return name


def _uid():
    import os

    return os.getuid()


def _gid():
    import os

    return os.getgid()


def stop_container(name):
    subprocess.run(
        ['docker', 'rm', '--force', name],
        capture_output=True,
        text=True,
        check=False,
    )


def wait_for_dataset(base_url, container):
    deadline = time.monotonic() + SERVER_TIMEOUT
    while time.monotonic() < deadline:
        body = get(f'{base_url}/__harness__/dataset')
        if body is not None:
            return json.loads(body)
        if not _container_running(container):
            raise RuntimeError(
                'the harness container stopped before it was ready:\n'
                + _container_logs(container)
            )
        time.sleep(2)
    raise RuntimeError('the harness server did not become ready in time')


def _container_running(name):
    result = subprocess.run(
        ['docker', 'inspect', '--format', '{{.State.Running}}', name],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() == 'true'


def _container_logs(name):
    result = subprocess.run(
        ['docker', 'logs', '--tail', '30', name],
        capture_output=True,
        text=True,
        check=False,
    )
    return (result.stdout + result.stderr).strip()


def run_journey(chrome, base_url, journey):
    """Open one journey in a browser of its own and wait for its report."""
    profile = tempfile.mkdtemp(prefix=f'chorum-{journey}-')
    url = f'{base_url}/__harness__/driver.html?journey={journey}'
    browser = subprocess.Popen(
        [
            chrome,
            '--headless=new',
            '--no-sandbox',
            '--disable-gpu',
            '--disable-dev-shm-usage',
            '--window-size=1280,900',
            f'--user-data-dir={profile}',
            url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + JOURNEY_TIMEOUT
        while time.monotonic() < deadline:
            body = get(f'{base_url}/__harness__/report?journey={journey}')
            if body is not None:
                return json.loads(body)
            if browser.poll() is not None:
                return {
                    'journey': journey,
                    'ok': False,
                    'failure': 'the browser exited before reporting',
                    'steps': [],
                }
            time.sleep(0.5)
        return {
            'journey': journey,
            'ok': False,
            'failure': f'no report within {JOURNEY_TIMEOUT} seconds',
            'steps': [],
        }
    finally:
        browser.terminate()
        try:
            browser.wait(timeout=10)
        except subprocess.TimeoutExpired:
            browser.kill()
        shutil.rmtree(profile, ignore_errors=True)


def describe(report):
    lines = [f'{"PASS" if report.get("ok") else "FAIL"} {report["journey"]}']
    for step in report.get('steps', []):
        lines.append(f'  - {step}')
    findings = report.get('findings') or []
    if findings:
        lines.append(f'  {len(findings)} finding(s):')
        for finding in findings:
            lines.append(
                f'  * [{finding["rule"]}] {finding["screen"]}: {finding["detail"]}'
            )
    if not report.get('ok'):
        lines.append(f'  failure: {report.get("failure")}')
        if report.get('screen'):
            lines.append('  screen at failure:')
            for line in report['screen'].splitlines():
                lines.append(f'    | {line}')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('worktree', help='the checkout to run, with a built frontend')
    parser.add_argument('journeys', nargs='*', default=None, help='names to run')
    parser.add_argument(
        '--chrome',
        default=None,
        help='browser executable; otherwise discover Chrome or Chromium',
    )
    parser.add_argument(
        '--uv-cache',
        default=str(default_uv_cache()),
        help='a directory to keep the container install cache in',
    )
    arguments = parser.parse_args(argv)

    worktree = Path(arguments.worktree).resolve()
    if not (worktree / 'frontend' / 'dist' / 'index.html').is_file():
        print(
            'no frontend build at frontend/dist; run the frontend gate first',
            file=sys.stderr,
        )
        return 2
    chrome = arguments.chrome or discover_chrome()
    if chrome is None:
        print('no browser found; pass --chrome PATH', file=sys.stderr)
        return 2
    if not Path(chrome).is_file():
        print(f'no browser at {chrome}', file=sys.stderr)
        return 2

    selected = arguments.journeys or list(DEFAULT_JOURNEYS)
    unknown = [name for name in selected if name not in JOURNEYS]
    if unknown:
        print(f'unknown journeys: {", ".join(unknown)}', file=sys.stderr)
        return 2

    Path(arguments.uv_cache).mkdir(parents=True, exist_ok=True)
    token = run_token()
    port = free_port()
    base_url = f'http://127.0.0.1:{port}'
    container = start_container(worktree, port, token, arguments.uv_cache)
    failures = 0
    try:
        dataset = wait_for_dataset(base_url, container)
        secrets_in_play = secret_values(dataset)
        print(f'harness ready on {base_url} for run {dataset["token"]}')
        for journey in selected:
            report = run_journey(chrome, base_url, journey)
            text = describe(report)
            leaked = leaked_secrets(text, secrets_in_play)
            if leaked:
                # A report that carries a credential is a failed run whatever
                # the journey said, because the diagnostics are the product
                # here just as much as the journey is.
                print(f'FAIL {journey}: the report leaked {len(leaked)} secret(s)')
                failures += 1
                continue
            print(text)
            if not report.get('ok'):
                failures += 1
    finally:
        stop_container(container)

    print(f'\n{len(selected) - failures}/{len(selected)} journeys passed')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
