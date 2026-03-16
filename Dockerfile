# ─── Stage 1: compile dependencies into wheels ───────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Build tools needed to compile C extensions (psycopg binary wheel is
# self-contained, but other packages like Pillow still need headers).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libjpeg-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .

RUN pip install --upgrade pip \
 && pip wheel \
        --no-cache-dir \
        --wheel-dir /build/wheels \
        -r requirements.txt


# ─── Stage 2: lean production runtime ────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings \
    # Gunicorn tuning — override via docker-compose environment
    GUNICORN_WORKERS=4 \
    GUNICORN_WORKER_CLASS=gthread \
    GUNICORN_THREADS=2 \
    GUNICORN_TIMEOUT=30 \
    GUNICORN_LOG_LEVEL=info \
    # Celery tuning
    CELERY_CONCURRENCY=4 \
    CELERY_LOG_LEVEL=info

# Minimal runtime system deps (libjpeg/zlib for Pillow at runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libjpeg62-turbo \
        zlib1g \
    && rm -rf /var/lib/apt/lists/* \
    # Create a non-root user for security
    && addgroup --system django \
    && adduser --system --ingroup django --no-create-home --disabled-password django

WORKDIR /app

# Install from pre-built wheels — no compiler needed here
COPY --from=builder /build/wheels /tmp/wheels
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels /tmp/wheels/*.whl \
 && rm -rf /tmp/wheels

# Copy application source
COPY --chown=django:django . .

# Make the entrypoint executable before switching user
RUN chmod +x entrypoint.sh

# Directories that need to be writable by the django user
RUN mkdir -p /app/staticfiles /app/mediafiles \
 && chown -R django:django /app/staticfiles /app/mediafiles

USER django

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
# Default role; overridden per-service in docker-compose.yml
CMD ["web"]
