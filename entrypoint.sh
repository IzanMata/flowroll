#!/bin/sh
set -e

ROLE="${1:-web}"

case "$ROLE" in
  web)
    echo "==> Running migrations..."
    python manage.py migrate --no-input

    echo "==> Collecting static files..."
    python manage.py collectstatic --no-input --clear

    echo "==> Starting Gunicorn..."
    exec gunicorn config.wsgi:application \
      --bind 0.0.0.0:8000 \
      --workers "${GUNICORN_WORKERS:-4}" \
      --worker-class "${GUNICORN_WORKER_CLASS:-gthread}" \
      --threads "${GUNICORN_THREADS:-2}" \
      --timeout "${GUNICORN_TIMEOUT:-30}" \
      --log-level "${GUNICORN_LOG_LEVEL:-info}" \
      --access-logfile - \
      --error-logfile -
    ;;

  celery)
    echo "==> Starting Celery worker..."
    exec celery -A config worker \
      --loglevel="${CELERY_LOG_LEVEL:-info}" \
      --concurrency="${CELERY_CONCURRENCY:-4}"
    ;;

  celery-beat)
    echo "==> Starting Celery beat..."
    exec celery -A config beat \
      --loglevel="${CELERY_LOG_LEVEL:-info}" \
      --scheduler django_celery_beat.schedulers:DatabaseScheduler
    ;;

  *)
    echo "Unknown role: $ROLE"
    echo "Usage: entrypoint.sh [web|celery|celery-beat]"
    exit 1
    ;;
esac
