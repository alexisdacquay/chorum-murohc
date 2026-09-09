"""Serve the JSON API and the built interface from one origin.

Django session cookies and CSRF only work when the interface and the API
share an origin. A deployment that served the built files from somewhere
else would be a different application: the browser would hold no session
cookie for the API, and every unsafe call would be refused. So one WSGI
application answers everything on one port:

- `/api/` and `/admin/` are Django;
- `STATIC_URL` is the `collectstatic` output in `STATIC_ROOT`, which is the
  admin's own CSS and nothing else;
- everything else is the Vite build in `settings.FRONTEND_DIST`, with the
  single-page fallback to `index.html` so a reloaded `/chores` still works.

`config.spa.application` is what the container serves.
`config.wsgi.application` stays plain Django, for an operator who would
rather put a web server in front of `frontend/dist` themselves.

The same shape is what `browser_journeys/serve_app.py` drives every journey
through, so the interface is exercised in a browser exactly as it is served
here.
"""

import mimetypes
import os
from pathlib import Path

from django.conf import settings
from django.core.wsgi import get_wsgi_application

# Everything Django owns. A path that starts with one of these never touches
# the filesystem below.
DJANGO_PREFIXES = ('/api/', '/admin/')

# Vite writes content-hashed filenames into this directory, so a cached copy
# can never be the wrong one. Every other response is revalidated.
IMMUTABLE_PREFIX = '/assets/'
IMMUTABLE_CACHE = 'public, max-age=31536000, immutable'
NO_CACHE = 'no-store'

# Sent with every file this module serves. Django's middleware sends these
# on Django's own responses; the static half has to send them itself.
#
# `Content-Security-Policy` is deliberately not among them. `config.middleware`
# adds it to Django's responses, and the interface document is the response
# that policy would actually protect - but driving the real build under
# `default-src 'self'` blocks two things it does today: the `data:` favicon
# Vite inlines, and an inline `<style>` element that appears when a dialog
# opens. Sending it here would silently drop styles, so the header waits for
# S-01's owner to decide between allowing those two and removing them
# (`_docs/audit-security.md`).
SECURITY_HEADERS = (
    ('X-Content-Type-Options', 'nosniff'),
    ('X-Frame-Options', 'DENY'),
    ('Referrer-Policy', 'same-origin'),
)

TEXTUAL_TYPES = frozenset(
    {
        'application/javascript',
        'application/json',
        'image/svg+xml',
        'text/javascript',
    }
)

NO_BUILD_MESSAGE = 'The interface has not been built. Run: pnpm --dir frontend build\n'


def _content_type(path):
    guessed, _ = mimetypes.guess_type(path.name)
    content_type = guessed or 'application/octet-stream'
    if content_type.startswith('text/') or content_type in TEXTUAL_TYPES:
        return f'{content_type}; charset=utf-8'
    return content_type


def _safe_child(root, relative):
    """Resolve `relative` under `root`, or `None` if it escapes."""
    candidate = (root / relative.lstrip('/')).resolve()
    root = root.resolve()
    if candidate == root or root in candidate.parents:
        return candidate
    return None


def _respond(start_response, status, content_type, body, cache, method):
    headers = [
        ('Content-Type', content_type),
        ('Content-Length', str(len(body))),
        ('Cache-Control', cache),
        *SECURITY_HEADERS,
    ]
    start_response(status, headers)
    # A HEAD answers with the headers of the GET and no body at all.
    return [] if method == 'HEAD' else [body]


def _serve_file(start_response, path, method, cache):
    return _respond(
        start_response,
        '200 OK',
        _content_type(path),
        path.read_bytes(),
        cache,
        method,
    )


def _plain(start_response, status, text, method):
    return _respond(
        start_response,
        status,
        'text/plain; charset=utf-8',
        text.encode(),
        NO_CACHE,
        method,
    )


def _static_root():
    root = getattr(settings, 'STATIC_ROOT', None)
    return None if root is None else Path(root)


def _static_prefix():
    return f'/{settings.STATIC_URL.strip("/")}/'


def build_application(django_application):
    """Compose Django and the built interface behind one WSGI callable."""

    def application(environ, start_response):
        path = environ.get('PATH_INFO', '/')
        method = environ.get('REQUEST_METHOD', 'GET')

        if path.startswith(DJANGO_PREFIXES):
            return django_application(environ, start_response)

        if method not in {'GET', 'HEAD'}:
            return _plain(start_response, '405 Method Not Allowed', '', method)

        static_prefix = _static_prefix()
        static_root = _static_root()
        if static_root is not None and path.startswith(static_prefix):
            collected = _safe_child(static_root, path[len(static_prefix) :])
            if collected is not None and collected.is_file():
                return _serve_file(start_response, collected, method, IMMUTABLE_CACHE)
            return _plain(start_response, '404 Not Found', '', method)

        dist = Path(settings.FRONTEND_DIST)
        built = _safe_child(dist, path)
        if built is not None and built.is_file():
            cache = IMMUTABLE_CACHE if path.startswith(IMMUTABLE_PREFIX) else NO_CACHE
            return _serve_file(start_response, built, method, cache)

        index = dist / 'index.html'
        if not index.is_file():
            return _plain(
                start_response,
                '500 Internal Server Error',
                NO_BUILD_MESSAGE,
                method,
            )
        return _serve_file(start_response, index, method, NO_CACHE)

    return application


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = build_application(get_wsgi_application())
