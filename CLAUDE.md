# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FlowRoll is a **multi-tenant BJJ Academy Management SaaS** built with Django 5 + DRF. Each `Academy` is a tenant; all tenant-scoped models carry an `academy` FK via `TenantMixin`. Auth is JWT (SimpleJWT). The API is fully documented via drf-spectacular at `/api/docs/`.

Database: **MariaDB/MySQL** (`mysqlclient`). Configure via `.env` — see the `MARIADB_*` variables in `config/settings.py`.

## Commands

```bash
# Install
pip install -r requirements.txt

# Database
python manage.py makemigrations
python manage.py migrate

# Run dev server
python manage.py runserver

# Tests (pytest-django, no manage.py needed)
pytest                                      # all tests
pytest tatami/tests/test_matchmaking.py     # single file
pytest -k "TestTournamentPairing"           # single class
pytest --cov=. --cov-report=term-missing    # with coverage

# Linting / formatting
flake8 .
black .
isort .
```

## Architecture

### Multi-tenancy model

`TenantMixin` (`core/mixins.py`) adds `academy = FK(Academy)` to every tenant-scoped model. `TimestampMixin` adds `created_at` / `updated_at`. Combine both when a model is both tenant-owned and timestamped.

### Permission system (`core/permissions.py`)

Four classes resolve the academy from `view.kwargs["academy_pk"]` or `request.query_params["academy"]` and check `AcademyMembership`:

| Class | Allowed roles |
|---|---|
| `IsAcademyMember` | STUDENT, PROFESSOR, OWNER |
| `IsAcademyProfessor` | PROFESSOR, OWNER |
| `IsAcademyOwner` | OWNER only |
| `IsSuperAdmin` | Django superuser |

Default DRF permission is `IsAuthenticated`. Add tighter permissions at the view/action level.

### Services / Selectors pattern

Every domain app follows this split:

- **`services.py`** — all writes, state transitions, and business logic. Methods are `@staticmethod` and `@transaction.atomic` when they touch multiple tables.
- **`selectors.py`** — read-only querysets. No business logic; only filtering, annotation, and `select_related`.
- **ViewSets** are thin: validate input with a serializer, call a service or selector, return the result.

### Domain apps

| App | Purpose |
|---|---|
| `core` | `Belt`, `AcademyMembership`, `TimestampMixin`, `TenantMixin`, permissions |
| `academies` | `Academy` (tenant root) |
| `athletes` | `AthleteProfile` — one-to-one with `User`; tracks belt, stripes, weight, mat_hours, coach lineage |
| `techniques` | `Technique`, `TechniqueCategory`, `TechniqueFlow` (directed graph of transitions/counters/escapes), `TechniqueVariation`, `TechniqueVideo` |
| `attendance` | `TrainingClass`, `QRCode` (time-limited tokens), `CheckIn` (auto-increments `mat_hours`), `DropInVisitor` |
| `tatami` | Live session tools: `WeightClass`, `TimerPreset`/`TimerSession`, `Matchup`; `MatchmakingService` pairs athletes by (belt, stripes, weight) |
| `membership` | `MembershipPlan`, `Subscription`, `PromotionRequirement`, dojo tab (`DojoTabTransaction`/`DojoTabBalance`), `Seminar`/`SeminarRegistration` |
| `community` | `Achievement` (auto + manual badges), `AthleteAchievement`, `OpenMatSession`/`OpenMatRSVP`; streak computation |
| `learning` | `ClassTechniqueJournal` (what was drilled per class), `VideoLibraryItem` (private video links), `SparringNote` |
| `matches` / `competitions` / `stats` | Placeholder apps — stubs only |

### Key cross-app relationships

- `AthleteProfile.mat_hours` is updated atomically by `CheckInService` every time a check-in is created.
- `PromotionService` reads `mat_hours`, `stripes`, and a `PromotionRequirement` record to compute `PromotionReadiness`.
- `MatchmakingService` sorts athletes by `(belt_order, stripes, weight)` before pairing.
- `learning.ClassTechniqueJournal` links `attendance.TrainingClass` → `techniques.Technique`.
- `learning.SparringNote` and `learning.VideoLibraryItem` both optionally reference `attendance.TrainingClass`.

### Test fixtures (`conftest.py`)

Global pytest fixtures available in all test files:

- `belt_white`, `belt_blue`, `belt_purple`, `belt_brown`, `belt_black` — `Belt` instances
- `academy` — a single `Academy`
- `make_user` — factory that auto-generates unique usernames
- `make_athlete(belt, stripes, weight, **kwargs)` — factory combining `make_user` + `AthleteProfile`

### API structure

All endpoints live under `/api/<app>/`. JWT tokens:

```
POST /api/auth/token/          # obtain (username + password → access + refresh)
POST /api/auth/token/refresh/  # rotate refresh token
```

OpenAPI schema: `GET /api/schema/` — rendered at `/api/docs/` (Swagger) and `/api/redoc/`.
