#!/bin/sh
# Entrypoint for the `scheduler` service in podman-compose.yml.
# Waits for the database, fixes ownership of the (volume-mounted, so
# root-owned by default) ml_models directory, drops to the unprivileged
# `codelearn` user, then loops `retrain_models` every
# RETRAIN_INTERVAL_SECONDS (default 86400 = once a day) forever.
#
# This is intentionally simple — a shell loop, not a cron daemon or
# Celery beat — since a single periodic job doesn't need that
# machinery. If more scheduled jobs get added later, swapping this for
# real Celery beat + a worker would be the natural next step.
set -e

echo "Fixing ownership of volume-mounted directories..."
chown -R codelearn:codelearn /app/ml_models

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

INTERVAL="${RETRAIN_INTERVAL_SECONDS:-86400}"

while true; do
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) — running retrain_models ==="
  gosu codelearn python manage.py retrain_models || echo "retrain_models failed this cycle — will retry next interval"
  echo "Sleeping ${INTERVAL}s until next run..."
  sleep "$INTERVAL"
done
