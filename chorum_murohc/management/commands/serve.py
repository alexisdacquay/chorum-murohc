"""Serve the household application on one port.

This is the container's foreground process. It puts the composed WSGI
application from `config.spa` - the API, the admin and the built interface on
one origin - behind the standard library's threaded WSGI server.

That server is a deliberate choice, not an oversight. This product is two
parents and their children on one small machine; a handful of requests at a
time from devices on the same network is the whole load, and the same server
already carries every browser journey in `browser_journeys/`. It is not
built for the public internet: put a reverse proxy in front of it, set
`DJANGO_HTTPS=true`, and let the proxy hold the certificate and the world.
"""

from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

from django.conf import settings
from django.core.management.base import BaseCommand

from config.spa import application

# Every interface inside the container. The container publishes one port,
# and the compose file decides which address that port is reachable on.
DEFAULT_HOST = '0.0.0.0'
DEFAULT_PORT = 8000


class ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
    """One thread per request, so a slow reader cannot block the household."""

    daemon_threads = True


class Command(BaseCommand):
    help = 'Serve the API, the admin and the built interface on one origin.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--host',
            default=DEFAULT_HOST,
            help=f'Address to bind. Default {DEFAULT_HOST}.',
        )
        parser.add_argument(
            '--port',
            type=int,
            default=DEFAULT_PORT,
            help=f'Port to bind. Default {DEFAULT_PORT}.',
        )

    def handle(self, *args, **options):
        host = options['host']
        port = options['port']

        index = settings.FRONTEND_DIST / 'index.html'
        if not index.is_file():
            # Loud, and still serving: the API answers, and every interface
            # request says the same thing rather than showing a blank page.
            self.stderr.write(f'No interface build at {settings.FRONTEND_DIST}.')

        server = make_server(
            host,
            port,
            application,
            server_class=ThreadedWSGIServer,
        )
        self.stdout.write(f'Serving the household on {host}:{port}.')
        server.serve_forever()
