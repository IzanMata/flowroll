# Contributing to FlowRoll

Thank you for contributing. This document covers conventions, workflow, and review expectations.

---

## Table of Contents

1. [Development setup](#development-setup)
2. [Project conventions](#project-conventions)
3. [Branch naming](#branch-naming)
4. [Commit messages](#commit-messages)
5. [Pull request process](#pull-request-process)
6. [Testing requirements](#testing-requirements)
7. [Code style](#code-style)

---

## Development Setup

```bash
git clone <repo-url> flowroll
cd flowroll
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your local values
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Run the test suite before opening any PR:

```bash
pytest --tb=short
```

---

## Project Conventions

### Architecture rules

1. **No business logic in views.** ViewSets validate input with a serializer, call a service or selector, and return the result. Nothing more.

2. **services.py for writes.** Every function that creates, updates, or deletes data lives in `<app>/services.py`. Multi-table writes must be wrapped in `@transaction.atomic`.

3. **selectors.py for reads.** Every complex queryset lives in `<app>/selectors.py`. No writes, no side effects — only filtering, annotation, and `select_related`.

4. **Permissions in `core/permissions.py`.** New permission classes go here, not in individual app files. Use the existing four classes (`IsAcademyMember`, `IsAcademyProfessor`, `IsAcademyOwner`, `IsSuperAdmin`) before creating new ones.

5. **Tenant scoping.** Any model that belongs to an academy must inherit `TenantMixin`. ViewSets must scope their queryset to the academy in `get_queryset()` and verify the requesting user's membership before returning data.

6. **Atomic counters.** Never read a numeric field in Python and write it back. Use Django `F()` expressions:
   ```python
   # Wrong
   obj.count += 1
   obj.save()

   # Correct
   MyModel.objects.filter(pk=obj.pk).update(count=F("count") + 1)
   ```

7. **No `select_related` or `prefetch_related` for non-relational fields.** Calling `prefetch_related("char_field")` is a no-op and silently wastes a query. Only prefetch actual relations.

### Model conventions

- Every tenant-scoped model inherits `TenantMixin` + optionally `TimestampMixin` (from `core/mixins.py`).
- Every new model needs a `__str__` method.
- Add `Meta.indexes` for any field combination used in `filter()`, `order_by()`, or annotation filters.
- Add `Meta.ordering` for models with natural display order.

### Serializer conventions

- Use `SerializerMethodField` only when the value cannot be expressed as an annotation in the queryset. Annotate in `selectors.py` and read the annotation with a plain `IntegerField(read_only=True)`.
- Mark computed/auto fields as `read_only_fields` in `Meta`.
- Use `source="relation.field"` for flattened read-only fields (e.g., `username = CharField(source="user.username", read_only=True)`).
- Split list and detail serializers for models with heavy nested relations.

### URL conventions

- App URL files register all ViewSets with `DefaultRouter` and include `router.urls`.
- Custom actions use `@action(detail=True/False, methods=[...])`.
- All app URL prefixes are declared in `config/urls.py`.

---

## Branch Naming

Use the format: `<type>/<short-description>`

| Type | When to use |
|---|---|
| `feat/` | New feature or endpoint |
| `fix/` | Bug fix |
| `perf/` | Performance improvement |
| `refactor/` | Code restructuring without behaviour change |
| `docs/` | Documentation only |
| `test/` | Test additions or fixes |
| `chore/` | Dependency updates, build scripts, CI changes |
| `security/` | Security fixes |

**Examples**

```
feat/open-mat-rsvp-endpoints
fix/duplicate-checkin-race-condition
perf/annotate-going-count-selector
docs/api-reference-tatami
test/seminar-overbooking-guard
security/jwt-blacklist-refresh
```

Rules:
- Use lowercase and hyphens, no underscores or spaces.
- Keep the description under 40 characters.
- Branch off `main` for all work.

---

## Commit Messages

Use the Conventional Commits format:

```
<type>(<scope>): <short imperative summary>

[optional body]

[optional footer(s)]
```

### Type

| Type | Use for |
|---|---|
| `feat` | New feature |
| `fix` | Bug fix |
| `perf` | Performance improvement |
| `refactor` | No behaviour change |
| `docs` | Documentation changes |
| `test` | New or updated tests |
| `chore` | Build, CI, dependency changes |
| `security` | Security-related changes |

### Scope

Use the app or module name: `attendance`, `tatami`, `membership`, `core`, `settings`, `ci`, etc.

### Rules

- **Imperative mood** in the summary: "add", "fix", "remove" — not "added", "fixing", "removed".
- **50 chars max** for the summary line.
- **Blank line** between summary and body.
- Reference issues with `Fixes #<n>` or `Refs #<n>` in the footer.
- Breaking changes: add `BREAKING CHANGE:` in the footer and `!` after the type: `feat(core)!: rename IsAcademyAdmin to IsAcademyOwner`.

### Examples

```
feat(attendance): add QR expiry clamping to generate_qr action

Prevents professors from creating near-permanent QR codes by clamping
expiry_minutes to the range [1, 1440] (maximum 24 hours).

Fixes #42
```

```
fix(community): use F() expression in mat_hours increment

Replaces stale Python-side addition with a DB-side F() update to avoid
lost-update race conditions when two check-ins fire concurrently.
```

```
perf(community): annotate going_count in selector to eliminate N+1

get_upcoming_open_mats() now annotates going_count at the DB level
instead of issuing one COUNT per session row in serialization.
```

```
test(membership): add seminar overbooking guard integration test
```

---

## Pull Request Process

### Before opening a PR

- [ ] All existing tests pass: `pytest`
- [ ] New code has tests (see Testing Requirements below)
- [ ] Code is formatted: `black . && isort .`
- [ ] No lint errors: `flake8 .`
- [ ] Migration created if model fields changed: `python manage.py makemigrations`
- [ ] No secrets or `.env` values committed

### PR title

Match the commit format: `<type>(<scope>): <summary>` (50 chars max).

### PR description template

```markdown
## What

Brief description of what this PR does.

## Why

Why this change is needed. Link the issue if applicable.

## How

Key implementation decisions. Mention any tricky parts.

## Testing

How the change was tested. List test file(s) added or modified.

## Checklist

- [ ] Tests added / updated
- [ ] Migrations created (if applicable)
- [ ] `black`, `isort`, `flake8` pass
- [ ] Documentation updated (if applicable)
```

### Review expectations

- Reviewers aim to respond within **2 business days**.
- At least **1 approval** is required before merging.
- Address all comments before merging; use "Resolve conversation" only after the concern is resolved, not just acknowledged.
- Squash merge to keep `main` history clean (one commit per feature/fix).

### Merge strategy

Use **squash merge**. The final commit message on `main` should match the Conventional Commits format above.

---

## Testing Requirements

### What must have tests

| Change | Required tests |
|---|---|
| New endpoint (action or ViewSet) | Auth guard (401 without token), permission boundary (403 wrong role), happy path (201/200), error path (400/404) |
| New service function | Happy path, each error/exception branch |
| New security constraint | Positive case (allowed) + negative case (denied) — both must be explicit |
| Bug fix | A regression test that fails before the fix and passes after |

### Where to put tests

```
<app>/
  tests/
    __init__.py
    test_api.py        # ViewSet / endpoint tests
    test_services.py   # Service layer tests
    test_selectors.py  # Selector / query tests (if complex)
```

### Fixtures

Use the global fixtures from `conftest.py` and `factories.py` before defining local ones. If a fixture is needed by more than one test class in the same file, define it at module scope. If it would be useful across multiple apps, add it to the root `conftest.py`.

### Test class naming

```python
class TestTrainingClassMembershipGuard:   # what is being protected
    def test_non_member_cannot_see_classes(self, ...):  # explicit scenario
    def test_member_can_see_classes(self, ...):
```

### No mocking the database

Do not mock Django ORM calls or replace the database with in-memory stubs. All tests run against a real PostgreSQL test database. This ensures that database-level constraints, indexes, and `select_for_update()` behaviour are actually exercised.

---

## Code Style

### Formatting

```bash
black .          # auto-format all Python files
isort .          # sort imports
flake8 .         # lint (E501 line-length 88 matches black)
```

All three must pass with zero errors before a PR is opened. The CI pipeline enforces this.

### Import order (enforced by isort)

1. Standard library
2. Third-party packages
3. Django packages
4. DRF packages
5. Local project imports

Group separations are enforced by `isort --profile black`.

### Type hints

Use type hints on all new service and selector function signatures:

```python
def get_classes_for_academy(academy_id: int, upcoming_only: bool = False) -> QuerySet:
```

Type hints on ViewSet methods are optional but welcome for complex `get_queryset` overrides.

### Docstrings

Every class and public function must have a docstring explaining:

- What it does (one sentence is fine for simple functions)
- Any non-obvious parameters
- Side effects (e.g., "H-5 fix: uses F() to avoid lost-update race condition")
- Exceptions raised

Use plain English, not reStructuredText or NumPy style unless the function is particularly complex.

### Comments

Comments should explain **why**, not **what**. If the code is clear, no comment is needed. If there is a security fix, a race condition guard, or a surprising design decision, add a short comment referencing the issue or fix label (e.g., `# H-5 fix: ...`).
