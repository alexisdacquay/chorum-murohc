"""Proofs for the one-origin WSGI composition in `config.spa`.

Session cookies and CSRF depend on the API and the interface sharing an
origin, so these tests hold the routing rules that keep them together: what
Django owns, what the built interface owns, and what neither of them may
ever serve.
"""

import pytest

from config import spa

INDEX = b'<!doctype html><title>Chorum-murohc</title>'


class Recorder:
    """The `start_response` a WSGI server would pass in."""

    def __init__(self):
        self.status = None
        self.headers = None

    def __call__(self, status, headers):
        self.status = status
        self.headers = dict(headers)


def django_stub(environ, start_response):
    start_response('200 OK', [('Content-Type', 'application/json')])
    return [b'{"from": "django"}']


@pytest.fixture
def dist(tmp_path, settings):
    """A built interface, exactly as `pnpm --dir frontend build` leaves it."""
    root = tmp_path / 'dist'
    (root / 'assets').mkdir(parents=True)
    (root / 'index.html').write_bytes(INDEX)
    (root / 'assets' / 'index-abc123.js').write_text('export default 1\n')
    settings.FRONTEND_DIST = root
    return root


@pytest.fixture
def collected(tmp_path, settings):
    """A `collectstatic` output, which is the admin's own files."""
    root = tmp_path / 'staticfiles'
    (root / 'admin').mkdir(parents=True)
    (root / 'admin' / 'base.css').write_text('body{}\n')
    settings.STATIC_ROOT = root
    return root


def call(path, method='GET'):
    recorder = Recorder()
    application = spa.build_application(django_stub)
    body = b''.join(
        application({'PATH_INFO': path, 'REQUEST_METHOD': method}, recorder)
    )
    return recorder, body


@pytest.mark.parametrize('path', ['/api/v1/health/', '/admin/', '/admin/login/'])
def test_django_answers_its_own_prefixes(dist, path):
    recorder, body = call(path)

    assert recorder.status == '200 OK'
    assert body == b'{"from": "django"}'


def test_a_built_file_is_served_with_its_own_type(dist):
    recorder, body = call('/assets/index-abc123.js')

    assert recorder.status == '200 OK'
    assert body == b'export default 1\n'
    assert recorder.headers['Content-Type'] == 'text/javascript; charset=utf-8'
    assert recorder.headers['Cache-Control'] == spa.IMMUTABLE_CACHE


def test_an_unknown_path_falls_back_to_the_single_page(dist):
    recorder, body = call('/chores')

    assert recorder.status == '200 OK'
    assert body == INDEX
    assert recorder.headers['Content-Type'] == 'text/html; charset=utf-8'
    assert recorder.headers['Cache-Control'] == spa.NO_CACHE


def test_every_served_file_carries_the_security_headers(dist):
    recorder, _ = call('/')

    for name, value in spa.SECURITY_HEADERS:
        assert recorder.headers[name] == value


def test_a_path_climbing_out_of_the_build_gets_the_page_not_the_file(dist, tmp_path):
    (tmp_path / 'secret.txt').write_text('not yours')

    recorder, body = call('/../secret.txt')

    assert recorder.status == '200 OK'
    assert body == INDEX


def test_a_collected_admin_file_is_served(dist, collected):
    recorder, body = call('/static/admin/base.css')

    assert recorder.status == '200 OK'
    assert body == b'body{}\n'
    assert recorder.headers['Content-Type'] == 'text/css; charset=utf-8'


def test_a_missing_collected_file_is_not_the_single_page(dist, collected):
    recorder, body = call('/static/admin/missing.css')

    assert recorder.status == '404 Not Found'
    assert body == b''


def test_a_head_request_answers_with_headers_and_no_body(dist):
    recorder, body = call('/', method='HEAD')

    assert recorder.status == '200 OK'
    assert body == b''
    assert recorder.headers['Content-Length'] == str(len(INDEX))


def test_an_unsafe_method_never_reaches_the_filesystem(dist):
    recorder, body = call('/chores', method='POST')

    assert recorder.status == '405 Method Not Allowed'
    assert body == b''


def test_an_unsafe_method_still_reaches_django(dist):
    recorder, body = call('/api/v1/auth/login/', method='POST')

    assert recorder.status == '200 OK'
    assert body == b'{"from": "django"}'


def test_a_missing_build_says_how_to_build_it(tmp_path, settings):
    settings.FRONTEND_DIST = tmp_path / 'never-built'

    recorder, body = call('/')

    assert recorder.status == '500 Internal Server Error'
    assert b'pnpm --dir frontend build' in body
