# CLAUDE.md

FlowRoll is a **multi-tenant BJJ Academy Management SaaS** — Django 5.2 + DRF 3.16, JWT auth (SimpleJWT), PostgreSQL, Redis, Celery. API schema at `/api/docs/` (drf-spectacular).

> Skills: `/test` → testing | `/deploy` → deployment | `/db` → database | `/api-review` → API review

---

## Multi-tenancy

`TenantMixin` (`core/mixins.py`) adds `academy = FK(Academy)` to every tenant-scoped model. `TimestampMixin` adds `created_at`/`updated_at`. All views scope querysets to `?academy=<id>`.

## Permissions (`core/permissions.py`)

Resolve academy from `view.kwargs["academy_pk"]` or `request.query_params["academy"]`, check `AcademyMembership`:

| Class | Roles |
|---|---|
| `IsAcademyMember` | STUDENT, PROFESSOR, OWNER |
| `IsAcademyProfessor` | PROFESSOR, OWNER |
| `IsAcademyOwner` | OWNER |
| `IsSuperAdmin` | Django superuser |

Default DRF permission: `IsAuthenticated`. Add tighter permissions at view/action level.

## Services / Selectors pattern

- `services.py` — all writes, `@staticmethod` + `@transaction.atomic` when touching multiple tables
- `selectors.py` — read-only querysets, filtering/annotation/`select_related` only
- ViewSets are thin: validate with serializer → call service/selector → return response

## Domain apps

| App | Key models |
|---|---|
| `core` | `Belt`, `AcademyMembership`, mixins, permissions |
| `academies` | `Academy` (tenant root) |
| `athletes` | `AthleteProfile` (belt, stripes, weight, mat_hours, coach) |
| `techniques` | `Technique`, `TechniqueCategory`, `TechniqueFlow`, `TechniqueVariation`, `TechniqueVideo` |
| `attendance` | `TrainingClass`, `QRCode`, `CheckIn` (increments mat_hours), `DropInVisitor` |
| `tatami` | `WeightClass`, `TimerPreset`/`TimerSession`, `Matchup`; `MatchmakingService` |
| `membership` | `MembershipPlan`, `Subscription`, `PromotionRequirement`, `DojoTabTransaction`/`DojoTabBalance`, `Seminar`/`SeminarRegistration` |
| `community` | `Achievement`, `AthleteAchievement`, `OpenMatSession`/`OpenMatRSVP`, streak logic |
| `learning` | `ClassTechniqueJournal`, `VideoLibraryItem`, `SparringNote` |
| `matches`/`competitions`/`stats` | Stubs only |

## Key cross-app relationships

- `CheckInService` atomically increments `AthleteProfile.mat_hours` on every check-in
- `PromotionService` reads `mat_hours`, `stripes`, `PromotionRequirement` → `PromotionReadiness`
- `MatchmakingService` sorts by `(belt_order, stripes, weight)` before pairing
- `ClassTechniqueJournal`: `attendance.TrainingClass` → `techniques.Technique`
- `SparringNote` and `VideoLibraryItem` optionally reference `attendance.TrainingClass`

## Coding conventions

- F() expressions for all counter/balance increments — never read-modify-write
- `select_for_update()` inside `transaction.atomic` for concurrency-sensitive operations (e.g. seminar spots)
- `get_queryset()` must return `.none()` when `academy` param is absent
- `raise_exception=True` on all `serializer.is_valid()` calls
- New models: inherit `TenantMixin` + `TimestampMixin` when tenant-scoped and timestamped
- Migrations: run `python manage.py check` before committing any model change
