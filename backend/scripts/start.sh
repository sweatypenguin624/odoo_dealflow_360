#!/usr/bin/env sh
# Container entrypoint: wait for the database, run migrations, optionally seed, start the API.
set -e
cd /app

echo "Waiting for database..."
python - <<'PY'
import os, time, sys
import psycopg2
url = os.environ["DATABASE_URL"]
for attempt in range(60):
    try:
        psycopg2.connect(url).close()
        sys.exit(0)
    except Exception as exc:
        time.sleep(1)
print("database not reachable", file=sys.stderr)
sys.exit(1)
PY

echo "Applying migrations..."
alembic upgrade head

if [ "${SEED_ON_START:-false}" = "true" ]; then
  echo "Seeding demo data (only if the database is empty)..."
  python -m app.seed
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 ${UVICORN_EXTRA_ARGS:-}
