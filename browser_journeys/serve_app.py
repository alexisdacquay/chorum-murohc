"""Serve the real product, plus the journey driver, on one origin.

This module runs inside the pinned Python container that
`run_journeys.py` starts. It creates a throwaway SQLite database named after
the run token, migrates it, seeds one household per journey, and then serves
three things from a single port:

- `/api/` and `/admin/` go to Django, exactly as they would in production;
- `/__harness__/` is the driver page, the journey scripts, the seeded
  dataset and the report inbox;
- everything else is the built frontend from `frontend/dist`, with the
  single-page fallback to `index.html`.

One origin is the point. Django session cookies and CSRF only work when the
interface and the API share an origin, so a harness that proxied the API
from somewhere else would be testing a different application.

Nothing here is imported by product code, and no product file is changed to
make it work.
"""

import json
import mimetypes
import os
import sys
import threading
from pathlib import Path
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

HARNESS_PREFIX = '/__harness__/'
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST = BASE_DIR / 'frontend' / 'dist'
STATIC_DIR = Path(__file__).resolve().parent / 'static'


class _Reports:
    """The journey reports posted back by the browser, one per journey."""

    def __init__(self):
        self._lock = threading.Lock()
        self._reports = {}

    def store(self, journey, body):
        with self._lock:
            self._reports[journey] = body

    def get(self, journey):
        with self._lock:
            return self._reports.get(journey)


def _query(environ, name):
    raw = environ.get('QUERY_STRING', '')
    for pair in raw.split('&'):
        key, _, value = pair.partition('=')
        if key == name:
            return value
    return ''


def _respond(start_response, status, content_type, body):
    if isinstance(body, str):
        body = body.encode()
    start_response(
        status,
        [
            ('Content-Type', content_type),
            ('Content-Length', str(len(body))),
            ('Cache-Control', 'no-store'),
        ],
    )
    return [body]


def _read_file(path):
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or 'application/octet-stream', path.read_bytes()


def _safe_child(root, relative):
    """Resolve `relative` under `root`, or `None` if it escapes."""
    candidate = (root / relative.lstrip('/')).resolve()
    if candidate == root.resolve() or root.resolve() in candidate.parents:
        return candidate
    return None


def _harness_app(dataset, reports):
    def harness(environ, start_response):
        path = environ['PATH_INFO'][len(HARNESS_PREFIX) :]
        method = environ['REQUEST_METHOD']

        if path == 'dataset':
            return _respond(
                start_response,
                '200 OK',
                'application/json',
                json.dumps(dataset),
            )

        if path == 'report':
            journey = _query(environ, 'journey')
            if method == 'POST':
                length = int(environ.get('CONTENT_LENGTH') or 0)
                reports.store(journey, environ['wsgi.input'].read(length))
                return _respond(start_response, '200 OK', 'text/plain', 'stored')
            stored = reports.get(journey)
            if stored is None:
                return _respond(start_response, '404 Not Found', 'text/plain', '')
            return _respond(start_response, '200 OK', 'application/json', stored)

        asset = _safe_child(STATIC_DIR, path)
        if asset is not None and asset.is_file():
            content_type, body = _read_file(asset)
            return _respond(start_response, '200 OK', content_type, body)

        return _respond(start_response, '404 Not Found', 'text/plain', 'no such thing')

    return harness


def _frontend_app(environ, start_response):
    path = environ['PATH_INFO']
    candidate = _safe_child(FRONTEND_DIST, path)
    if candidate is not None and candidate.is_file():
        content_type, body = _read_file(candidate)
        return _respond(start_response, '200 OK', content_type, body)

    index = FRONTEND_DIST / 'index.html'
    if not index.is_file():
        return _respond(
            start_response,
            '500 Internal Server Error',
            'text/plain',
            'no frontend build; run the frontend gate first',
        )
    content_type, body = _read_file(index)
    return _respond(start_response, '200 OK', content_type, body)


def build_application(django_app, dataset, reports):
    """Compose Django, the harness and the built frontend behind one port."""
    harness = _harness_app(dataset, reports)

    def application(environ, start_response):
        path = environ.get('PATH_INFO', '/')
        if path.startswith(('/api/', '/admin/')):
            return django_app(environ, start_response)
        if path.startswith(HARNESS_PREFIX):
            return harness(environ, start_response)
        return _frontend_app(environ, start_response)

    return application


class _QuietHandler(WSGIRequestHandler):
    """One request per journey step is noise; failures come back in the report."""

    def log_message(self, *args):
        return


class _ThreadingServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


def main(argv):
    port = int(argv[0])
    token = argv[1]

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    from django.core.management import call_command
    from django.core.wsgi import get_wsgi_application

    django.setup()
    call_command('migrate', verbosity=0, interactive=False)

    from browser_journeys.seed import seed_dataset

    dataset = seed_dataset(token)
    django_app = get_wsgi_application()
    application = build_application(django_app, dataset, _Reports())

    # Bound on every interface inside the container, and published by the
    # runner to 127.0.0.1 alone, so nothing outside this machine can reach it.
    server = make_server(
        '0.0.0.0',
        port,
        application,
        server_class=_ThreadingServer,
        handler_class=_QuietHandler,
    )
    print(f'harness ready on {port} for run {token}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main(sys.argv[1:])
