#!/bin/sh
# entrypoint.sh — unified startup script for web, worker, and beat roles.
# Usage: ./entrypoint.sh [web|worker|beat]
set -e

MODE="${1:-web}"
echo "[entrypoint] Starting in mode: $MODE"

# ─── Wait helpers ─────────────────────────────────────────────────────────────

wait_for_postgres() {
    echo "[entrypoint] Waiting for PostgreSQL at ${POSTGRES_HOST}:${POSTGRES_PORT:-5432} ..."
    until python - <<'PYEOF'
import sys, os
try:
    import psycopg
    conn = psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ.get("POSTGRES_PORT", 5432)),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        connect_timeout=3,
    )
    conn.close()
    sys.exit(0)
except Exception as exc:
    print(f"  postgres not ready: {exc}", file=sys.stderr)
    sys.exit(1)
PYEOF
    do
        sleep 2
    done
    echo "[entrypoint] PostgreSQL is ready."
}

wait_for_redis() {
    echo "[entrypoint] Waiting for Redis at ${REDIS_URL} ..."
    until python - <<'PYEOF'
import sys, os, redis as r
try:
    r.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0")).ping()
    sys.exit(0)
except Exception as exc:
    print(f"  redis not ready: {exc}", file=sys.stderr)
    sys.exit(1)
PYEOF
    do
        sleep 2
    done
    echo "[entrypoint] Redis is ready."
}

# ─── Roles ────────────────────────────────────────────────────────────────────

case "$MODE" in

    web)
        wait_for_postgres
        wait_for_redis

        echo "[entrypoint] Applying database migrations ..."
        python manage.py migrate --noinput

        echo "[entrypoint] Collecting static files ..."
        python manage.py collectstatic --noinput --clear

        echo "[entrypoint] Starting Gunicorn ..."
        exec gunicorn config.wsgi:application \
            --bind 0.0.0.0:8000 \
            --workers "${GUNICORN_WORKERS}" \
            --worker-class "${GUNICORN_WORKER_CLASS}" \
            --threads "${GUNICORN_THREADS}" \
            --timeout "${GUNICORN_TIMEOUT}" \
            --keep-alive 5 \
            --max-requests 1000 \
            --max-requests-jitter 100 \
            --log-level "${GUNICORN_LOG_LEVEL}" \
            --access-logfile - \
            --error-logfile -
        ;;

    worker)
        wait_for_postgres
        wait_for_redis

        echo "[entrypoint] Starting Celery worker ..."
        exec celery -A config worker \
            --loglevel="${CELERY_LOG_LEVEL}" \
            --concurrency="${CELERY_CONCURRENCY}" \
            --without-gossip \
            --without-mingle
        ;;

    beat)
        wait_for_postgres
        wait_for_redis

        echo "[entrypoint] Starting Celery beat ..."
        exec celery -A config beat \
            --loglevel="${CELERY_LOG_LEVEL}" \
            --scheduler django_celery_beat.schedulers:DatabaseScheduler
        ;;

    *)
        echo "[entrypoint] Unknown mode: '$MODE'. Valid: web | worker | beat"
        exit 1
        ;;

esac
