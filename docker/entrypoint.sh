#!/bin/sh
# Entrypoint for the CodeLearn web container.
# Runs as root initially so it can fix ownership of volume-mounted
# directories (Podman/Docker mount named volumes as root-owned at
# runtime, regardless of the image's build-time chown), then waits for
# the database, applies migrations, collects static files, and finally
# drops privileges to the unprivileged `codelearn` user via gosu before
# exec'ing whatever CMD was passed (normally gunicorn — see Dockerfile).
set -e

echo "Fixing ownership of volume-mounted directories..."
chown -R codelearn:codelearn /app/staticfiles /app/media

if [ "$DB_ENGINE" = "mysql" ]; then
  echo "Waiting for MySQL at ${DB_HOST:-db}:${DB_PORT:-3306}..."
  until python - <<'PYEOF'
import os, socket, sys
host = os.environ.get("DB_HOST", "db")
port = int(os.environ.get("DB_PORT", "3306"))
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.connect((host, port))
    sys.exit(0)
except OSError:
    sys.exit(1)
PYEOF
  do
    sleep 2
  done
  echo "Database is up."
fi

echo "Applying migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Dropping to unprivileged user 'codelearn'..."
exec gosu codelearn "$@"
