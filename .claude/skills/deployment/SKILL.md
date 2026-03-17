---
name: deployment
triggers: ["deploy", "docker", "podman", "compose", "container", "production", "start", "levant", "run server", "gunicorn", "nginx", "celery", "worker"]
description: "Invoke when starting the app locally or deploying to production."
---

# Deployment

## Local dev (no containers)

```bash
source venv/bin/activate
python manage.py runserver
```

## Docker / Podman (production stack)

This system uses **Podman** (rootless). Use `podman-compose` (installed in venv):

```bash
source venv/bin/activate

# First time / after code changes
podman-compose up -d --build

# Subsequent starts (no rebuild)
podman-compose up -d

# Stop everything
podman-compose down

# View logs
podman-compose logs -f web
podman logs flowroll_web_1

# Status
podman-compose ps
```

## Services

| Service | Image | Port |
|---|---|---|
| `postgres` | `docker.io/library/postgres:16-alpine` | internal |
| `redis` | `docker.io/library/redis:7-alpine` | internal |
| `web` | `localhost/flowroll_web` (Gunicorn) | 8000 (internal) |
| `worker` | `localhost/flowroll_worker` (Celery) | — |
| `beat` | `localhost/flowroll_beat` (Celery beat) | — |
| `nginx` | `docker.io/library/nginx:1.25-alpine` | **8080→80** |

> Port is **8080** (not 80) — Podman rootless cannot bind privileged ports.

## Access

- API: `http://localhost:8080/api/`
- Swagger: `http://localhost:8080/api/docs/`
- Admin: `http://localhost:8080/admin/`

## Post-deploy tasks

```bash
# Run migrations
podman-compose exec web python manage.py migrate

# Create superuser
podman-compose exec web python manage.py createsuperuser

# Collect static (done automatically by entrypoint.sh)
podman-compose exec web python manage.py collectstatic --noinput
```

## Scaling

```bash
podman-compose up -d --scale worker=3   # scale Celery workers
# Never scale beat — only ONE instance allowed
```

## Environment (.env)

Required vars: `SECRET_KEY`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `REDIS_URL`.
Copy from `.env.example` and fill in values. `DJANGO_ENV=production` loads `config/settings/production.py`.

## Install dependencies (venv)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
