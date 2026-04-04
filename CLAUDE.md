# CLAUDE.md

FlowRoll is a **multi-tenant BJJ Academy Management SaaS** — Django 5.2.7 + DRF 3.16.1, JWT auth (SimpleJWT with token blacklisting), PostgreSQL, Redis, Celery. API schema at `/api/docs/` (drf-spectacular).

> Skills: `/test` → testing | `/deploy` → deployment | `/db` → database | `/api-review` → API review

---

## Stack

| Layer | Technology |
|---|---|
| Framework | Django 5.2.7, DRF 3.16.1 |
| Auth | SimpleJWT 5.3.1 (Bearer, 1h access / 7d refresh, rotation + blacklist) |
| Database | PostgreSQL via psycopg3, CONN_MAX_AGE=60 |
| Cache/Queue | Redis + Celery 5.4 (django-celery-beat) |
| Social auth | django-allauth 65.12 + google-auth (Google OAuth) |
| API docs | drf-spectacular (Swagger at `/api/docs/`, ReDoc at `/api/redoc/`) |
| Static files | WhiteNoise |
| Server | Gunicorn |
| Testing | pytest-django, factory-boy, Faker |

---

## Project Layout

```
config/
  settings/base.py       # All settings (split by env via DJANGO_SETTINGS_MODULE)
  urls.py                # Root URLs: /api/auth/, /api/v1/, /api/docs/, /admin/
  urls_v1.py             # All domain app routers mounted at /api/v1/
  celery.py              # Celery app config
core/
  mixins.py              # TenantMixin, TimestampMixin, SwaggerSafeMixin, AcademyFilterMixin
  permissions.py         # IsAcademyMember, IsAcademyProfessor, IsAcademyOwner, IsSuperAdmin
  management/commands/
    seed_db.py           # Dev/staging seed: --env, --fresh, --count
    setup_perf_data.py   # Performance test dataset generator
<app>/
  models.py
  services.py            # All writes — @staticmethod + @transaction.atomic
  selectors.py           # Read-only querysets — filtering, annotation, select_related
  serializers.py
  views.py               # Thin ViewSets: validate → service/selector → respond
  urls.py
  tests/
    test_api.py
    test_services.py
    test_models.py
    test_security.py
tests/                   # Cross-app integration tests
  test_concurrent_api.py
  test_filtering.py
  test_integration.py
  test_state_machines.py
  test_validation.py
conftest.py              # Shared fixtures (belts, factories, API clients)
```

---

## URL Structure

```
/                               → api_root (AllowAny)
/api/auth/token/                → TokenObtainPairView (throttle: 10/min)
/api/auth/token/refresh/        → TokenRefreshView (throttle: 20/min)
/api/auth/me/                   → current user (IsAuthenticated)
/api/auth/register/             → RegistrationService (throttle: 10/min)
/api/auth/logout/               → blacklists refresh token
/api/auth/password-reset/       → PasswordResetService (throttle: 5/min)
/api/auth/verify-email/         → EmailVerificationService
/api/auth/social/google/        → Google OAuth
/api/v1/academies/              → AcademyViewSet + member management + public list
/api/v1/athletes/               → AthleteProfileViewSet
/api/v1/techniques/             → TechniqueViewSet, TechniqueCategoryViewSet, BeltViewSet, TechniqueVariationViewSet
/api/v1/matches/                → MatchViewSet (+ add_event, finish_match actions)
/api/v1/attendance/             → TrainingClassViewSet (+ generate_qr, qr_checkin, manual_checkin), DropInVisitorViewSet
/api/v1/tatami/                 → WeightClassViewSet, TimerPresetViewSet, TimerSessionViewSet, MatchupViewSet
/api/v1/membership/             → MembershipPlan, Subscription, PromotionRequirement, DojoTab, Seminar endpoints
/api/v1/community/              → Achievement, AthleteAchievement, OpenMatSession/RSVP endpoints
/api/v1/learning/               → ClassTechniqueJournal, VideoLibraryItem, SparringNote endpoints
/api/v1/competitions/           → TournamentViewSet (stub)
/api/v1/stats/                  → AthleteStatsViewSet (stub)
```

---

## Multi-tenancy

Every tenant-scoped model inherits `TenantMixin` (`academy = FK(Academy)`) and `TimestampMixin` (`created_at`/`updated_at`).

**Rules:**
- `get_queryset()` **must** return `.none()` when the `academy` query param is absent
- Academy is always derived from `request.query_params["academy"]` or `view.kwargs["academy_pk"]` — **never** from the request body (IDOR prevention)
- `AcademyFilterMixin` provides: `get_academy_id()`, `filter_by_academy()`, `get_academy_scoped_queryset()`

---

## Permissions (`core/permissions.py`)

Resolves academy from `view.kwargs["academy_pk"]` or `request.query_params["academy"]`, then checks `AcademyMembership.is_active`:

| Class | Allowed roles |
|---|---|
| `IsAcademyMember` | STUDENT, PROFESSOR, OWNER |
| `IsAcademyProfessor` | PROFESSOR, OWNER |
| `IsAcademyOwner` | OWNER only |
| `IsSuperAdmin` | Django superuser |
| `ReadOnlyOrSuperAdmin` | Safe methods for authenticated users; writes for superusers only |

Default DRF permission is `IsAuthenticated`. Add tighter permissions at the view/action level.

**Typical ViewSet pattern:**
```python
# list/retrieve → IsAcademyMember
# create/update/destroy → IsAcademyProfessor
# owner-only → IsAcademyOwner (get_permissions or has_object_permission)
```

---

## Services / Selectors Pattern

- **`services.py`** — all writes. Use `@staticmethod` + `@transaction.atomic` when touching multiple tables.
- **`selectors.py`** — read-only querysets only. Filtering, annotation, `select_related`/`prefetch_related`. No writes.
- **ViewSets** are thin: `serializer.is_valid(raise_exception=True)` → call service/selector → return response.

### Services reference

| Module | Key methods |
|---|---|
| `accounts/services.py` | `RegistrationService.register_with_email()`, `register_or_login_with_google()` |
| | `EmailVerificationService.send_verification(user)`, `verify(uid, token)` |
| | `PasswordResetService.request_reset(email)`, `confirm_reset(uid, token, new_password)` |
| `academies/services.py` | `AcademyService.create_academy(user, **data)` → assigns creator as OWNER |
| | `AcademyMemberService.add_member()`, `change_role()`, `remove_member()` — guards against removing last OWNER |
| `athletes/services.py` | `AthleteProfileService.award_stripe(athlete, awarded_by)` — max 4, uses F() |
| | `promote_belt(athlete, new_belt, awarded_by)` — validates progression, resets stripes to 0 |
| | `assign_coach(athlete, coach)` — guards circular references |
| `attendance/services.py` | `QRCodeService.generate(training_class, expiry_minutes)` — clamps 1–1440 min |
| | `CheckInService.check_in_via_qr(athlete, token)` — F() for mat_hours |
| | `CheckInService.check_in_manual(athlete, training_class)` — scopes both to same academy |
| | `DropInService.register(...)`, `expire_stale()` |
| `matches/services.py` | `MatchService.add_event(...)` — `select_for_update()` + F() for concurrent scoring |
| | `finish_match(match_pk, winner_id)`, `create_match(academy, a, b, duration)` |
| `tatami/services.py` | `MatchmakingService.pair_for_tournament(athletes, ...)` — sorts (belt_order, stripes, weight) |
| | `pair_for_survival(...)`, `advance_survival(...)`, `filter_by_weight_class(...)` |
| | `TimerService.start(session)`, `pause(session)`, `finish(session)` — row-level locking |

### Selectors reference

| Module | Key selectors |
|---|---|
| `academies/selectors.py` | `get_academies_for_user(user_id)`, `get_public_academies(search, city, country)` |
| | `get_members_for_academy(academy_id, role, active_only)`, `get_academy_stats(academy_id)` |
| `athletes/selectors.py` | `get_athletes_for_academy(academy_id, belt, search)` — annotates `total_check_ins` |
| | `get_athlete_by_user(user_id)`, `get_top_athletes_by_mat_hours(academy_id, limit)` |
| | `get_athletes_ready_for_promotion(academy_id)` — 4 stripes |
| `attendance/selectors.py` | `get_classes_for_academy(academy_id, upcoming_only)` — annotates `attendance_count` (no N+1) |
| | `get_check_ins_for_class(training_class_id)`, `get_athlete_attendance_history(athlete)` |
| | `get_active_drop_ins_for_academy(academy_id)` |
| `tatami/selectors.py` | `get_presets_for_academy(academy_id)`, `get_sessions_for_academy(academy_id)` |
| | `get_matchups_for_academy(academy_id, match_format)` |

---

## Domain Apps & Models

### `core`
- **`Belt`**: WHITE, BLUE, PURPLE, BROWN, BLACK with `order` for progression checks
- **`AcademyMembership`**: User → Academy with roles (STUDENT, PROFESSOR, OWNER) and `is_active`

### `academies`
- **`Academy`**: Tenant root — name, city, country, email, phone, website, `is_active`

### `athletes`
- **`AthleteProfile`** (1-to-1 with User): `belt`, `stripes` (0–4), `weight` (kg), `mat_hours` (atomic), `coach` (self-FK), `role`
- `get_lineage()` recursively traverses coach chain; capped at 100 levels to prevent DoS

### `techniques`
- **`TechniqueCategory`**: name, description, auto-slug
- **`Technique`**: name, slug, categories (M2M), difficulty (1–5), `min_belt`, image_url
- **`TechniqueVideo`**: FK to Technique, source, duration_seconds, tags
- **`TechniqueVariation`**: FK to Technique, videos (M2M)
- **`TechniqueFlow`**: from_technique → to_technique with `transition_type` (chain/counter/escape/setup)

### `attendance`
- **`TrainingClass`**: title, `class_type` (GI/NOGI/OPEN_MAT/KIDS/COMPETITION), professor (FK User), scheduled_at, duration_minutes, max_capacity
- **`QRCode`**: OneToOne → TrainingClass, token (auto UUID), expires_at; property `is_valid`
- **`CheckIn`**: athlete + training_class (unique_together), method (QR/MANUAL)
- **`DropInVisitor`**: first/last name, email, phone, `access_token` (UUID), `status` (PENDING/ACTIVE/EXPIRED)

### `matches`
- **`Match`**: athlete_a/b, date, duration_seconds, score_a/b, winner, is_finished
- **`MatchEvent`**: match, athlete, timestamp, points_awarded, event_type (POINTS/ADVANTAGE/PENALTY/SUBMISSION)

### `tatami`
- **`WeightClass`**: name, min/max_weight, gender (M/F/O); unique (name, gender)
- **`TimerPreset`**: format (IBJJF/ADCC/POSITIONAL/CUSTOM), round/rest/overtime durations, rounds; unique (academy, name)
- **`TimerSession`**: status (IDLE/RUNNING/PAUSED/FINISHED), current_round, elapsed_seconds
- **`Matchup`**: athlete_a/b, weight_class, `match_format` (TOURNAMENT/SURVIVAL), status (PENDING/IN_PROGRESS/COMPLETED/CANCELLED), winner

### `membership`
- **`MembershipPlan`**: plan_type (MONTHLY/ANNUAL/CLASS_PASS/DROP_IN), price, duration_days, class_limit
- **`Subscription`**: athlete, plan, start/end date, status (ACTIVE/EXPIRED/CANCELLED/PAUSED), classes_remaining; indexed (athlete, status)
- **`PromotionRequirement`**: per-belt thresholds (mat_hours, months_at_belt, stripes); academy nullable for global defaults; unique (academy, belt)
- **`DojoTabTransaction`**: DEBIT/CREDIT transactions per athlete
- **`DojoTabBalance`**: running balance; unique (athlete, academy)
- **`Seminar`**: capacity, price, status (OPEN/FULL/CANCELLED/COMPLETED); property `spots_remaining`
- **`SeminarRegistration`**: athlete, seminar, status (CONFIRMED/WAITLISTED/CANCELLED), payment_status; unique (seminar, athlete)

### `community`
- **`Achievement`**: platform-wide badges, `trigger_type` (CHECKIN_COUNT/MAT_HOURS/STREAK_DAYS/MANUAL), trigger_value
- **`AthleteAchievement`**: unique (athlete, achievement)
- **`OpenMatSession`**: event_date, start/end time, max_capacity, is_cancelled; property `going_count`
- **`OpenMatRSVP`**: status (GOING/NOT_GOING/MAYBE); unique (session, athlete)

### `learning`
- **`ClassTechniqueJournal`**: TrainingClass → Technique with professor_notes; unique (training_class, technique)
- **`VideoLibraryItem`**: url, source (YOUTUBE/VIMEO/OTHER), visibility (PUBLIC/PROFESSORS/PRIVATE), optional FK to Technique
- **`SparringNote`**: athlete, optional training_class, opponent_name, submission_log, performance_rating (1–5)

### `competitions` / `stats`
Stub apps — routers registered, viewsets exist, models minimal.

---

## Key Cross-app Relationships

- `CheckInService` atomically increments `AthleteProfile.mat_hours` (F() expression) on every check-in
- `PromotionService` reads `mat_hours`, `stripes`, `PromotionRequirement` → `PromotionReadiness`
- `MatchmakingService` sorts `(belt_order, stripes, weight)` before pairing
- `ClassTechniqueJournal`: `attendance.TrainingClass` → `techniques.Technique`
- `SparringNote` and `VideoLibraryItem` optionally reference `attendance.TrainingClass`
- `MatchService.add_event()` uses `select_for_update()` + F() for concurrent-safe score accumulation

---

## Coding Conventions

- **F() expressions** for all counter/balance increments — never read-modify-write
- **`select_for_update()` inside `transaction.atomic`** for concurrency-sensitive paths (match scoring, seminar spot reservation)
- **`get_queryset()` returns `.none()`** when the `academy` param is absent
- **`raise_exception=True`** on every `serializer.is_valid()` call
- New models: inherit `TenantMixin` + `TimestampMixin` when tenant-scoped and timestamped
- Academy identity comes from query params / URL kwargs, **never** from the request body
- Services are `@staticmethod`; never instantiate a service class to call a method
- Selectors return querysets (lazy); never call `.all()` or iterate inside a selector

---

## Migrations

```bash
python manage.py makemigrations
python manage.py check          # must pass before committing
python manage.py migrate
```

Always run `manage.py check` before committing any model change.

---

## Testing

```bash
pytest                          # all tests
pytest apps/attendance/         # single app
pytest -k "test_checkin"        # by name
pytest --cov=. --cov-report=html
```

**Shared fixtures** (`conftest.py`):
- Belt fixtures: `belt_white`, `belt_blue`, `belt_purple`, `belt_brown`, `belt_black`
- Factory fixtures: `academy`, `athlete`, `professor_athlete`, `make_user`, `make_athlete`
- API client fixtures: `api_client` (anon), `auth_client` (athlete), `professor_client`, `admin_client`

**Per-app test structure**: `tests/test_api.py`, `test_services.py`, `test_models.py`, `test_security.py`

**Cross-app tests** (`tests/`): concurrent access, filtering, integration flows, state machines, input validation

---

## Throttle Rates

| Scope | Rate |
|---|---|
| Anonymous | 200/hour |
| Authenticated user | 2000/hour |
| Login / token obtain | 10/minute |
| Token refresh | 20/minute |
| Registration | 10/minute |
| Password reset | 5/minute |

---

## Security Checklist (for new endpoints)

- [ ] Academy scoped from query param / URL kwarg, never body
- [ ] `get_queryset()` returns `.none()` when academy absent
- [ ] Correct permission class applied (Member/Professor/Owner)
- [ ] No N+1: use `select_related`/`prefetch_related` or annotate in selector
- [ ] Counters use F() expressions
- [ ] Concurrency-sensitive paths use `select_for_update()` inside `transaction.atomic`
- [ ] Depth-limited recursion (e.g., lineage traversal capped at 100)
