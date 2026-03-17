---
name: database
triggers: ["migration", "migrate", "makemigrations", "schema", "database", "db", "seed", "fixture", "index", "model change"]
description: "Invoke when creating migrations, applying them, modifying models, or debugging DB issues."
---

# Database

## Stack

PostgreSQL 16 (Docker) / MariaDB-compatible locally. Driver: `psycopg[binary]`.
Config via `.env` → `POSTGRES_*` vars → `config/settings/base.py`.

## Migration workflow

```bash
source venv/bin/activate

# After any model change
python manage.py makemigrations <app>      # always specify the app
python manage.py check                     # must pass with 0 issues before committing
python manage.py migrate                   # apply to local DB

# In containers
podman-compose exec web python manage.py migrate
```

## Rules

- Always run `python manage.py check` before committing a model change — catches related-name clashes, missing migrations, etc.
- Always specify the app name in `makemigrations` to avoid accidentally generating migrations for unrelated apps
- When adding indexes via `Meta.indexes`, name them explicitly (`name="..."`) for readability
- If a migration stub exists with `operations = []`, delete it and regenerate — empty stubs break `makemigrations` state reconstruction
- Use `select_for_update()` + `transaction.atomic` when concurrent writes could race (see `SeminarService`, `DojoTabService`)
- Use `F()` expressions for all counter/balance increments — never read-modify-write

## Common patterns

```python
# Tenant-scoped model (standard pattern)
class MyModel(TenantMixin, TimestampMixin):
    ...

# Atomic counter increment
MyModel.objects.filter(pk=obj.pk).update(counter=F("counter") + 1)

# Balance update (race-safe)
DojoTabBalance.objects.get_or_create(athlete=athlete, academy=academy, defaults={"balance": 0})
DojoTabBalance.objects.filter(athlete=athlete, academy=academy).update(balance=F("balance") + delta)
```

## Connection settings

`CONN_MAX_AGE=60` and `CONN_HEALTH_CHECKS=True` (production) — persistent connections with health checks.

## Troubleshooting

- `KeyError: ('app', 'modelname')` in makemigrations → empty/stub migration exists; delete it and regenerate
- `AlreadyRegistered` in admin → model registered in two `admin.py` files; remove the duplicate
- `cannot import name X from Y.models` → model class missing from `models.py`; infer from `services.py` + `serializers.py`
