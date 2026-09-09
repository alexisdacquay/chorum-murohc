# The household application in one image: the built interface, the API and
# the admin, served from one origin by `manage.py serve`.
#
# Both stages are pinned by digest, to the same images the two gates already
# use, so a rebuild months from now is the build that was tested.

# The interface. Vite writes content-hashed files into frontend/dist.
FROM node:24.15.0-bookworm-slim@sha256:4e6b70dd6cbfc88c8157ba19aa3d9f9cce6ba4703576d55459e45efcbc9c5f5d AS interface

ENV CI=1
WORKDIR /build
RUN npm install --silent --global pnpm@11.19.0

# The lockfile alone first, so a source-only change reuses the install layer.
COPY frontend/package.json frontend/pnpm-lock.yaml ./frontend/
RUN pnpm --dir frontend install --frozen-lockfile

COPY frontend ./frontend
RUN pnpm --dir frontend build


# The application.
FROM python:3.13.12-slim-bookworm@sha256:a58daefb915e1e03ad48f3ca4df8832065412c5c35cacb9d39f4229184de12b6

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_NO_PROGRESS=1 \
    PATH=/opt/venv/bin:$PATH

RUN pip install --quiet --disable-pip-version-check --no-cache-dir "uv==0.12.10"

WORKDIR /app

# Locked, and only what production runs: no test or lint packages.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-cache

COPY manage.py ./
COPY config ./config
COPY chorum_murohc ./chorum_murohc
COPY --from=interface /build/frontend/dist ./frontend/dist
COPY docker/entrypoint.sh /usr/local/bin/chorum-entrypoint

# The admin's own CSS, gathered at build time so no writable directory is
# needed at run time. Development settings are enough to collect files, and
# nothing here touches a database.
RUN python manage.py collectstatic --noinput --clear >/dev/null

# Nothing in the image is writable by the account that serves it, except the
# state directory, which is where the volume goes.
RUN useradd --system --create-home --home-dir /home/household --uid 10001 household \
    && mkdir -p /var/lib/chorum \
    && chown household:household /var/lib/chorum
USER household

EXPOSE 8000
VOLUME ["/var/lib/chorum"]

# Any answer at all means the server is up. A redirect counts: with
# DJANGO_HTTPS=true the health path is redirected to the address the proxy
# holds, and the container is still perfectly healthy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import http.client; c = http.client.HTTPConnection('127.0.0.1', 8000, timeout=4); c.request('GET', '/api/v1/health/'); raise SystemExit(0 if c.getresponse().status < 500 else 1)"]

ENTRYPOINT ["chorum-entrypoint"]
CMD ["python", "manage.py", "serve"]
