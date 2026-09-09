#!/bin/sh
# Everything that has to be true before the household application runs, done
# on every start because all of it is safe to repeat.
#
# 1. The file named by DJANGO_SECRET_KEY_FILE holds a key. Sessions are
#    signed with it, so it has to survive a restart: it lives in the state
#    volume, is generated once, and is never printed. Settings reads the file
#    itself, so every process in the container sees the same key, not just
#    the one started from here. An operator holding their own key sets
#    DJANGO_SECRET_KEY instead and this step does nothing.
# 2. The database schema is current.
#
# Then the command runs. `docker compose run --rm app python manage.py
# bootstrap_household` arrives here too, which is why first-run setup never
# has to remember to migrate first.
set -eu

KEY_FILE=${DJANGO_SECRET_KEY_FILE:-}

if [ -z "${DJANGO_SECRET_KEY:-}" ] && [ -n "$KEY_FILE" ] && [ ! -s "$KEY_FILE" ]; then
    candidate="$KEY_FILE.$$"
    (umask 177; python -c 'import secrets; print(secrets.token_urlsafe(64))' > "$candidate")
    # A hard link fails if the name is taken, so two containers starting at
    # once still agree on one key: the loser drops its candidate.
    ln "$candidate" "$KEY_FILE" 2>/dev/null || true
    rm -f "$candidate"
fi

python manage.py migrate --noinput

exec "$@"
