# FlowRoll

A multi-tenant BJJ Academy Management SaaS built with Django 5 and Django REST Framework. Each `Academy` is an isolated tenant. Athletes, coaches, schedules, competitions, and billing all live under a single API with JWT authentication.

Live API docs: `GET /api/docs/` (Swagger) — `GET /api/redoc/` (ReDoc) — `GET /api/schema/` (OpenAPI JSON)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Django 5.2, Django REST Framework 3.16 |
| Auth | SimpleJWT (access 1 h, refresh 7 d, rotation + blacklist) |
| Database | PostgreSQL 16 (`psycopg[binary]`) |
| Cache / Broker | Redis 7 (`django-redis`, Celery) |
| Task queue | Celery 5.4 + django-celery-beat |
| API schema | drf-spectacular 0.28 (OpenAPI 3.1) |
| Server | Gunicorn + Nginx |
| Testing | pytest-django, factory-boy, pytest-cov |

---

## Architecture

### Multi-tenancy

Every tenant-scoped model inherits `TenantMixin` (`core/mixins.py`), which adds `academy = FK(Academy)`. Requests are scoped by passing `?academy=<id>` as a query parameter or via a URL kwarg `academy_pk`. The permission classes in `core/permissions.py` verify the requesting user has an active `AcademyMembership` before any data is returned.

### Permission hierarchy

| Class | Allowed roles |
|---|---|
| `IsAcademyMember` | STUDENT, PROFESSOR, OWNER |
| `IsAcademyProfessor` | PROFESSOR, OWNER |
| `IsAcademyOwner` | OWNER only |
| `IsSuperAdmin` | Django superuser |
| `ReadOnlyOrSuperAdmin` | reads: any authenticated user; writes: superuser only |

Default DRF permission is `IsAuthenticated`.

### Services / Selectors pattern

| Module | Responsibility |
|---|---|
| `services.py` | All writes and state transitions. Methods are `@staticmethod` + `@transaction.atomic` when touching multiple tables. |
| `selectors.py` | Read-only querysets. Filtering, annotation, `select_related` — no business logic. |
| ViewSets | Thin: validate input via serializer → call service or selector → return result. |

### Domain apps

| App | Purpose |
|---|---|
| `core` | `Belt`, `AcademyMembership`, mixins, permission classes |
| `academies` | `Academy` — tenant root |
| `athletes` | `AthleteProfile` — belt, stripes, weight, mat_hours, coach lineage |
| `techniques` | Platform-wide BJJ library: `Technique`, `TechniqueCategory`, `TechniqueFlow` (directed graph), `TechniqueVariation` |
| `attendance` | `TrainingClass`, `QRCode`, `CheckIn`, `DropInVisitor` |
| `tatami` | Live session tools: `WeightClass`, `TimerPreset`/`TimerSession`, `Matchup`, matchmaking algorithm |
| `membership` | `MembershipPlan`, `Subscription`, `PromotionRequirement`, `DojoTabTransaction`/`DojoTabBalance`, `Seminar`/`SeminarRegistration` |
| `community` | `Achievement` (auto + manual badges), `AthleteAchievement`, `OpenMatSession`/`OpenMatRSVP`, streak computation |
| `learning` | `ClassTechniqueJournal`, `VideoLibraryItem`, `SparringNote` |
| `matches` | Match scoring and events (PROFESSOR-only) |
| `competitions`, `stats` | Placeholder apps — stubs only |

---

## Local Setup

### Prerequisites

- Python 3.12+
- PostgreSQL 16
- Redis 7

```bash
# 1. Clone and create virtual environment
git clone <repo-url> flowroll
cd flowroll
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — see Environment Variables section below

# 4. Apply migrations
python manage.py migrate

# 5. Create a superuser
python manage.py createsuperuser

# 6. Run the development server
python manage.py runserver
```

The API is now available at `http://localhost:8000/api/`.

### Celery (background tasks)

Open two additional terminals:

```bash
# Worker
celery -A config worker -l info

# Beat scheduler
celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

---

## Docker Setup

```bash
# 1. Copy and edit environment file
cp .env.example .env
# Set DJANGO_ENV=production and all required variables

# 2. Build and start all services
docker compose up -d --build

# 3. Run migrations inside the web container
docker compose exec web python manage.py migrate

# 4. Create a superuser
docker compose exec web python manage.py createsuperuser
```

### Service overview

| Service | Image | Description |
|---|---|---|
| `postgres` | postgres:16-alpine | Primary database |
| `redis` | redis:7-alpine | Cache + Celery broker |
| `web` | Dockerfile (runtime) | Django / Gunicorn on port 8000 |
| `worker` | Dockerfile (runtime) | Celery worker (scalable: `--scale worker=3`) |
| `beat` | Dockerfile (runtime) | Celery beat — **run exactly one instance** |
| `nginx` | nginx:1.25-alpine | Reverse proxy, serves static/media (port 80) |

### Useful Docker commands

```bash
# View logs
docker compose logs -f web

# Scale workers
docker compose up -d --scale worker=3

# Run management commands
docker compose exec web python manage.py <command>

# Open a shell
docker compose exec web bash
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in all values. Variables marked **required in production** have no fallback in `config/settings/production.py` and will raise `KeyError` at startup if missing.

| Variable | Default | Required in prod | Description |
|---|---|---|---|
| `DJANGO_ENV` | `development` | — | Settings module selector: `development` or `production` |
| `SECRET_KEY` | *(dev fallback)* | **Yes** | Django secret key. Generate: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `DEBUG` | `False` | — | Always `False` in production (enforced by `production.py`) |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | **Yes** | Comma-separated hostnames |
| `POSTGRES_DB` | `flowroll` | **Yes** | Database name |
| `POSTGRES_USER` | `flowroll_user` | **Yes** | Database user |
| `POSTGRES_PASSWORD` | `change-me` | **Yes** | Database password |
| `POSTGRES_HOST` | `postgres` | **Yes** | Database host (Docker service name or IP) |
| `POSTGRES_PORT` | `5432` | — | Database port |
| `DB_CONN_MAX_AGE` | `60` | — | Seconds to keep a DB connection alive between requests |
| `REDIS_URL` | `redis://:change-me@redis:6379/0` | **Yes** | Full Redis URL including password in production |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | **Yes** | Comma-separated allowed CORS origins |
| `GUNICORN_WORKERS` | `4` | — | Gunicorn worker processes |
| `GUNICORN_WORKER_CLASS` | `gthread` | — | Gunicorn worker class |
| `GUNICORN_THREADS` | `2` | — | Threads per worker |
| `GUNICORN_TIMEOUT` | `30` | — | Worker timeout in seconds |
| `CELERY_CONCURRENCY` | `4` | — | Celery worker concurrency |
| `EMAIL_BACKEND` | `smtp.EmailBackend` | — | Django email backend class |
| `EMAIL_HOST` | — | — | SMTP host |
| `EMAIL_PORT` | `587` | — | SMTP port |
| `EMAIL_USE_TLS` | `True` | — | TLS for outgoing mail |
| `EMAIL_HOST_USER` | — | — | SMTP username |
| `EMAIL_HOST_PASSWORD` | — | — | SMTP password |
| `DEFAULT_FROM_EMAIL` | `noreply@example.com` | — | Default sender address |

---

## Running Tests

```bash
# Run all tests
pytest

# Run a single test file
pytest attendance/tests/test_security.py

# Run a single test class
pytest -k "TestMatHoursAtomicity"

# Run with coverage report
pytest --cov=. --cov-report=term-missing

# Run with HTML coverage report
pytest --cov=. --cov-report=html
```

### Test configuration (`pytest.ini`)

- Settings module: `config.settings`
- Test discovery: `tests/test_*.py`, class prefix `Test*`, function prefix `test_*`
- Default flags: `-v --tb=short`

### Key fixtures (available in all test files)

| Fixture | Type | Description |
|---|---|---|
| `api_client` | `APIClient` | Unauthenticated DRF test client |
| `auth_client` | `APIClient` | Authenticated as a default athlete |
| `professor_client` | `APIClient` | Authenticated as a black-belt professor |
| `owner_client` | `APIClient` | Authenticated as an academy owner |
| `academy` | `Academy` | A single test academy |
| `belt_white` … `belt_black` | `Belt` | Belt reference objects |
| `make_user(username, **kwargs)` | factory | Creates `User` with unique username |
| `make_athlete(belt, stripes, weight, **kwargs)` | factory | Creates `User` + `AthleteProfile` |

---

## API Overview

### Base URL

All endpoints are under `/api/`. For local development: `http://localhost:8000/api/`.

### Authentication

FlowRoll uses JWT Bearer tokens (SimpleJWT).

```http
# Obtain tokens
POST /api/auth/token/
Content-Type: application/json

{"username": "alice", "password": "secret"}

# Response
{"access": "<access_token>", "refresh": "<refresh_token>"}

# Authenticate subsequent requests
Authorization: Bearer <access_token>

# Rotate refresh token
POST /api/auth/token/refresh/
{"refresh": "<refresh_token>"}
```

Token lifetimes:
- Access token: **1 hour**
- Refresh token: **7 days** (rotated and blacklisted on each use)

Rate limits:
- `POST /api/auth/token/`: 10 requests/minute per IP
- `POST /api/auth/token/refresh/`: 20 requests/minute per user

### Pagination

All list endpoints use `PageNumberPagination` (default page size: 20).

```json
{
  "count": 42,
  "next": "http://localhost:8000/api/techniques/techniques/?page=2",
  "previous": null,
  "results": [...]
}
```

### Common query parameters

| Parameter | Used by | Description |
|---|---|---|
| `?academy=<id>` | Most tenant-scoped endpoints | Scopes the response to a specific academy |
| `?academy_id=<id>` | Athletes endpoint | Alias used by `/api/athletes/` |
| `?search=<term>` | Endpoints with `SearchFilter` | Full-text search across configured fields |
| `?ordering=<field>` | Endpoints with `OrderingFilter` | Sort results; prefix with `-` for descending |
| `?page=<n>` | All list endpoints | Pagination page number |

### Standard error responses

| Status | When |
|---|---|
| `400 Bad Request` | Validation error; body contains field-level error dict |
| `401 Unauthorized` | Missing or invalid JWT token |
| `403 Forbidden` | Valid token but insufficient role/membership |
| `404 Not Found` | Resource not found or outside tenant scope |
| `405 Method Not Allowed` | HTTP method not supported by this endpoint |
| `429 Too Many Requests` | Rate limit exceeded |

---

## API Endpoints

### Authentication

#### `POST /api/auth/token/`

Obtain a JWT access + refresh token pair.

- **Auth required**: No
- **Rate limit**: 10/min per IP

**Request body**

| Field | Type | Required |
|---|---|---|
| `username` | string | Yes |
| `password` | string | Yes |

**Success `200`**
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

**Error `401`**
```json
{"detail": "No active account found with the given credentials"}
```

---

#### `POST /api/auth/token/refresh/`

Rotate a refresh token. The submitted token is immediately blacklisted.

- **Auth required**: No
- **Rate limit**: 20/min per user

**Request body**

| Field | Type | Required |
|---|---|---|
| `refresh` | string | Yes |

**Success `200`**
```json
{"access": "eyJ...", "refresh": "eyJ..."}
```

---

### Academies — `/api/academies/`

#### `GET /api/academies/`

List academies the authenticated user is a member of. Superusers see all.

- **Auth required**: Yes

**Success `200`**
```json
{
  "count": 1,
  "results": [
    {"id": 1, "name": "Alpha BJJ", "city": "Madrid", "created_at": "2025-01-10T09:00:00Z"}
  ]
}
```

#### `POST /api/academies/`

Create a new academy.

**Request body**

| Field | Type | Required | Constraints |
|---|---|---|---|
| `name` | string | Yes | max 150 chars |
| `city` | string | No | max 100 chars |

#### `GET /api/academies/{id}/`

Retrieve a single academy (user must be a member).

#### `PUT /api/academies/{id}/` / `PATCH /api/academies/{id}/`

Update an academy.

- **Permissions**: `IsAcademyOwner`

#### `DELETE /api/academies/{id}/`

Delete an academy.

- **Permissions**: `IsAcademyOwner`

---

### Athletes — `/api/athletes/`

All list/detail endpoints require `?academy_id=<id>`. Without this parameter an empty list is returned silently (tenant isolation, not a 403).

#### `GET /api/athletes/?academy_id=<id>`

List athlete profiles for an academy. Requires active membership.

- **Auth required**: Yes

**Query parameters**

| Parameter | Description |
|---|---|
| `?academy_id=<id>` | Required — scopes results to this academy |
| `?search=<term>` | Search by username |
| `?ordering=belt,stripes` | Sort results |

**Success `200`**
```json
{
  "count": 1,
  "results": [
    {
      "id": 5,
      "user": 12,
      "username": "alice",
      "email": "alice@example.com",
      "academy": 1,
      "academy_detail": {"id": 1, "name": "Alpha BJJ", "city": "Madrid", "created_at": "..."},
      "role": "STUDENT",
      "belt": "blue",
      "stripes": 2
    }
  ]
}
```

#### `PUT /api/athletes/{id}/` / `PATCH /api/athletes/{id}/`

Update an athlete profile. Only the athlete themselves or a PROFESSOR/OWNER of their academy may edit.

**Request body fields** (PATCH — all optional)

| Field | Type | Description |
|---|---|---|
| `belt` | string enum | `white`, `blue`, `purple`, `brown`, `black` |
| `stripes` | integer | 0–4 |
| `role` | string enum | `STUDENT`, `PROFESSOR` |

---

### Techniques — `/api/techniques/`

Platform-wide BJJ library. No academy scoping. Reads require authentication; writes require superuser.

#### `GET /api/techniques/techniques/`

List all techniques.

- **Auth required**: Yes
- **Permissions**: `ReadOnlyOrSuperAdmin`

**Query parameters**

| Parameter | Description |
|---|---|
| `?search=<term>` | Search name, description, categories__name |
| `?ordering=difficulty,name` | Sort |

**Success `200`**
```json
{
  "count": 1,
  "results": [
    {
      "id": 1,
      "name": "Armbar",
      "description": "Classic submission from guard.",
      "difficulty": 2,
      "min_belt": "white",
      "categories": [{"id": 1, "name": "Submissions", "description": ""}],
      "variations": [{"id": 1, "name": "Flying Armbar", "description": ""}],
      "leads_to": [{"id": 1, "to_technique": "Triangle Choke", "description": ""}]
    }
  ]
}
```

#### `POST /api/techniques/techniques/`

Create a technique. Superuser only. Returns `201`.

**Request body**

| Field | Type | Required | Constraints |
|---|---|---|---|
| `name` | string | Yes | Unique, max 200 chars |
| `description` | string | No | |
| `difficulty` | integer | No | Default 1 |
| `min_belt` | string enum | No | `white`\|`blue`\|`purple`\|`brown`\|`black` |

**Error `403`** for non-superusers. **Error `405`** for POST on `/api/techniques/belts/` (read-only).

#### `GET /api/techniques/belts/`

List belt reference records (WHITE → BLACK). Read-only; POST returns `405` for everyone.

#### `GET /api/techniques/categories/`

List and create technique categories. Reads open to all; writes superuser only.

#### `GET /api/techniques/variations/`

List and create technique variations. Reads open to all; writes superuser only.

---

### Attendance — `/api/attendance/`

#### `GET /api/attendance/classes/?academy=<id>`

List training classes for an academy. User must be an active member.

**Query parameters**

| Parameter | Description |
|---|---|
| `?academy=<id>` | Required |
| `?class_type=GI\|NOGI\|OPEN_MAT\|KIDS\|COMPETITION` | Filter by type |
| `?professor=<user_id>` | Filter by professor |
| `?scheduled_after=<ISO 8601>` | Lower bound on scheduled_at |
| `?scheduled_before=<ISO 8601>` | Upper bound on scheduled_at |
| `?ordering=scheduled_at,duration_minutes` | Sort |

**Success `200`**
```json
{
  "count": 1,
  "results": [
    {
      "id": 3,
      "academy": 1,
      "title": "Monday Evening Gi",
      "class_type": "GI",
      "professor": 12,
      "professor_username": "alice",
      "scheduled_at": "2026-03-20T19:00:00Z",
      "duration_minutes": 90,
      "max_capacity": 30,
      "notes": "",
      "attendance_count": 14,
      "created_at": "2026-03-01T10:00:00Z"
    }
  ]
}
```

#### `POST /api/attendance/classes/`

Create a training class.

**Request body**

| Field | Type | Required | Constraints |
|---|---|---|---|
| `academy` | integer | Yes | |
| `title` | string | Yes | max 120 chars |
| `class_type` | string enum | No | Default `GI` |
| `professor` | integer | No | User ID |
| `scheduled_at` | datetime | Yes | ISO 8601 |
| `duration_minutes` | integer | No | Default 60 |
| `max_capacity` | integer | No | null = unlimited |
| `notes` | string | No | |

#### `POST /api/attendance/classes/{id}/generate_qr/?academy=<id>`

Generate (or refresh) the QR code for a class. Old token is replaced on refresh.

- **Permissions**: `IsAcademyProfessor`

**Request body**

| Field | Type | Description |
|---|---|---|
| `expiry_minutes` | integer | Desired expiry. Clamped to [1, 1440] (max 24 h). Default 30. |

**Success `200`**
```json
{
  "id": 7,
  "training_class": 3,
  "token": "abc123xyz...",
  "expires_at": "2026-03-20T19:30:00Z",
  "is_active": true,
  "is_valid": true
}
```

#### `POST /api/attendance/classes/qr_checkin/`

Athlete self-check-in by scanning a QR code. The athlete profile is resolved from the JWT token.

**Request body**

| Field | Type | Required |
|---|---|---|
| `token` | string | Yes |

**Success `201`**
```json
{
  "id": 42,
  "athlete": 5,
  "athlete_username": "alice",
  "training_class": 3,
  "method": "QR",
  "checked_in_at": "2026-03-20T19:05:00Z"
}
```

**Error `400`** — expired/invalid token or duplicate check-in

#### `POST /api/attendance/classes/manual_checkin/?academy=<id>`

Professor records a check-in on behalf of an athlete. Both athlete and training class must belong to the specified academy (IDOR prevention).

- **Permissions**: `IsAcademyProfessor`

**Request body**

| Field | Type | Required |
|---|---|---|
| `athlete_id` | integer | Yes |
| `training_class_id` | integer | Yes |

**Error `404`** — if athlete or class does not belong to `?academy`

#### `GET /api/attendance/drop-ins/?academy=<id>`

List drop-in visitors for an academy.

- **Permissions**: `IsAcademyMember`

#### `POST /api/attendance/drop-ins/`

Register a drop-in visitor.

- **Permissions**: `IsAcademyProfessor`

**Request body**

| Field | Type | Required | Constraints |
|---|---|---|---|
| `academy` | integer | Yes | |
| `first_name` | string | Yes | max 60 chars |
| `last_name` | string | Yes | max 60 chars |
| `email` | string | Yes | Valid email |
| `phone` | string | No | max 20 chars |
| `training_class` | integer | No | Optional class association |
| `expires_at` | datetime | Yes | When the access token expires |

---

### Matches — `/api/matches/`

All endpoints require `?academy=<id>` and `IsAcademyProfessor`.

#### `GET /api/matches/?academy=<id>`

List matches for an academy.

#### `POST /api/matches/`

Create a match.

**Request body**

| Field | Type | Required |
|---|---|---|
| `academy` | integer | Yes |
| `athlete_a` | integer | Yes (User ID) |
| `athlete_b` | integer | Yes (User ID) |
| `duration_seconds` | integer | No (default 300) |

**Success `201`**
```json
{
  "id": 1,
  "athlete_a": 10,
  "athlete_b": 11,
  "athlete_a_detail": {"id": 10, "username": "bob"},
  "athlete_b_detail": {"id": 11, "username": "carol"},
  "date": "2026-03-20T20:00:00Z",
  "duration_seconds": 300,
  "is_finished": false,
  "score_a": 0,
  "score_b": 0,
  "winner": null,
  "winner_detail": null,
  "events": []
}
```

#### `POST /api/matches/{id}/add_event/?academy=<id>`

Record a scoring event. `athlete` must be one of the two participants.

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `athlete` | integer | Yes | User ID — must be `athlete_a` or `athlete_b` |
| `timestamp` | integer | Yes | Elapsed seconds in the match |
| `event_type` | string enum | Yes | `POINTS`, `ADVANTAGE`, `PENALTY`, `SUBMISSION` |
| `points_awarded` | integer | No | Default 0 |
| `action_description` | string | Yes | max 100 chars |

**Error `400`** — athlete not a participant

#### `POST /api/matches/{id}/finish_match/?academy=<id>`

Finish a match and declare the winner. `winner_id` must be `athlete_a` or `athlete_b`.

**Request body**

| Field | Type | Required |
|---|---|---|
| `winner_id` | integer | Yes |

**Error `400`** — `winner_id` is not a participant

---

### Tatami — `/api/tatami/`

#### `GET /api/tatami/weight-classes/`

List all weight class divisions (platform-wide, read-only).

- **Auth required**: Yes

**Query parameters**: `?search=<name>`, `?ordering=min_weight`

#### `GET /api/tatami/timer-presets/?academy=<id>`

List timer presets for an academy.

- **Permissions**: `IsAcademyMember`

**Query parameters**: `?format=IBJJF|ADCC|POSITIONAL|CUSTOM`

#### `POST /api/tatami/timer-presets/`

Create a timer preset.

- **Permissions**: `IsAcademyProfessor`

**Request body**

| Field | Type | Required | Constraints |
|---|---|---|---|
| `academy` | integer | Yes | |
| `name` | string | Yes | max 80 chars; unique per academy |
| `format` | string enum | No | `IBJJF`, `ADCC`, `POSITIONAL`, `CUSTOM`. Default `CUSTOM` |
| `round_duration_seconds` | integer | No | Default 300 |
| `rest_duration_seconds` | integer | No | Default 60 |
| `overtime_seconds` | integer | No | Default 0 |
| `rounds` | integer | No | Default 1 |

#### `POST /api/tatami/timer-presets/{id}/start_session/`

Create and immediately start a `TimerSession` from this preset.

- **Permissions**: `IsAcademyProfessor`

**Success `201`**
```json
{
  "id": 10,
  "preset": 3,
  "preset_name": "IBJJF Blue Belt",
  "status": "RUNNING",
  "current_round": 1,
  "started_at": "2026-03-20T19:10:00Z",
  "paused_at": null,
  "elapsed_seconds": 0
}
```

#### `POST /api/tatami/timer-sessions/{id}/pause/`

Pause a running timer. Accumulates elapsed seconds.

- **Permissions**: `IsAcademyMember`

**Error `400`** — timer is not in RUNNING state

#### `POST /api/tatami/timer-sessions/{id}/finish/`

Mark a timer session as FINISHED.

#### `GET /api/tatami/matchups/?academy=<id>`

List matchups for an academy.

- **Permissions**: `IsAcademyMember`

**Query parameters**: `?match_format=TOURNAMENT|SURVIVAL`, `?status=PENDING|IN_PROGRESS|COMPLETED|CANCELLED`, `?ordering=round_number,created_at`

#### `POST /api/tatami/matchups/pair_athletes/`

Run the matchmaking algorithm and create `Matchup` records.

- **Permissions**: `IsAcademyProfessor`

**Algorithm**: Athletes are sorted by `(belt_order, stripes, weight)` and paired sequentially with their nearest neighbour to minimise skill gap. Odd athletes receive a bye.

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `academy_id` | integer | Yes | All athletes must belong to this academy |
| `athlete_ids` | integer[] | Yes | Min 2 AthleteProfile PKs |
| `match_format` | string enum | Yes | `TOURNAMENT` or `SURVIVAL` |
| `weight_class_id` | integer | No | Optional weight class assignment |

**Success `201`** — array of created `Matchup` objects

**Error `400`** — an athlete does not belong to the specified academy

---

### Community — `/api/community/`

Endpoints not yet implemented. The following service and selector layer is complete:

- `AchievementService.evaluate_and_award(athlete)` — awards newly earned auto-achievements
- `AchievementService.award_manual(athlete, achievement, awarded_by)` — professor manual award
- `StatsAggregationService.compute_current_streak(athlete)` — consecutive training days
- `StatsAggregationService.get_summary(athlete)` — stats dict (check-ins, mat hours, streak, achievements)
- `OpenMatService.rsvp(athlete, session, status)` — GOING / NOT_GOING / MAYBE
- `get_upcoming_open_mats(academy_id)` — annotated with `going_count`

---

### Membership — `/api/membership/`

Endpoints not yet implemented. The following service layer is complete:

- `SubscriptionService.subscribe(athlete, plan)` — create and activate a subscription
- `SubscriptionService.consume_class_pass(subscription)` — decrement a class-pass
- `PromotionService.check_readiness(athlete, belt_awarded_date, academy_id)` — promotion eligibility report
- `DojoTabService.charge/credit(athlete, academy, amount, description)` — atomic tab transactions
- `SeminarService.register(athlete, seminar)` — reserve a seminar spot (overbooking-safe via `select_for_update`)
- `SeminarService.cancel_registration(registration)` — cancel and promote first waitlisted athlete

---

### Learning — `/api/learning/`

Endpoints not yet implemented. The following service and selector layer is complete:

- `TechniqueJournalService.log_technique(training_class, technique, notes)` — record what was drilled
- `SparringNoteService.create_note(athlete, **kwargs)` — log a sparring session note
- `get_journal_for_class(training_class_id)` — techniques drilled in a class
- `get_video_library(academy_id)` — video library items
- `get_sparring_notes_for_athlete(athlete)` — athlete sparring history

---

## OpenAPI Schema

drf-spectacular generates the OpenAPI 3.1 schema automatically from ViewSet declarations and `@extend_schema` decorators.

| URL | Description |
|---|---|
| `GET /api/schema/` | Raw OpenAPI JSON/YAML |
| `GET /api/docs/` | Swagger UI |
| `GET /api/redoc/` | ReDoc |

Schema metadata is configured in `SPECTACULAR_SETTINGS` inside `config/settings/base.py` (title, version, JWT security scheme).

---

## Code Quality

```bash
# Format
black .

# Sort imports
isort .

# Lint
flake8 .
```
